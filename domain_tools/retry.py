"""Per-attempt timeout plus bounded exponential backoff for storage calls (Part 3)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")

# Shared worker pool: a call that overruns its timeout keeps running in the
# background (the MySQL driver read_timeout ends it), but the caller moves on.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-call")


class TransientError(Exception):
    """A failure worth retrying (injected fault, timeout, dropped connection)."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3          # 1 try + 2 retries
    base_delay_s: float = 0.05     # delay before retry n is base * 2**(n-1)
    max_delay_s: float = 0.4       # cap on any single backoff delay
    timeout_s: float = 2.0         # per attempt

    def delay_before(self, attempt: int) -> float:
        """Backoff delay before `attempt` (attempt 1 has none)."""
        return 0.0 if attempt <= 1 else min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 2))


class RetryExhausted(Exception):
    def __init__(self, attempts: list[dict]):
        self.attempts = attempts
        last = attempts[-1]["error"] if attempts else "no attempts"
        super().__init__(f"failed after {len(attempts)} attempt(s): {last}")


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (TransientError, TimeoutError, ConnectionError)):
        return True
    try:  # SQLAlchemy is optional here so offline tests do not need it
        from sqlalchemy.exc import DBAPIError, OperationalError

        return isinstance(exc, OperationalError) or (isinstance(exc, DBAPIError) and exc.connection_invalidated)
    except ImportError:
        return False


def call_with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy,
    *,
    sleep: Callable[[float], None] = time.sleep,
    attempts_log: list[dict] | None = None,
) -> T:
    """Run fn with a timeout per attempt, retrying transient failures with backoff.

    Each attempt is appended to attempts_log as
    {attempt, delay_before_s, outcome, latency_ms, error}. Non-transient errors
    (bugs, bad input) are raised immediately without retrying.
    """
    log = attempts_log if attempts_log is not None else []
    for attempt in range(1, policy.max_attempts + 1):
        delay = policy.delay_before(attempt)
        if delay:
            sleep(delay)
        start = time.perf_counter()
        entry = {"attempt": attempt, "delay_before_s": delay}
        future = _POOL.submit(fn)
        try:
            result = future.result(timeout=policy.timeout_s)
        except FutureTimeout:
            future.cancel()
            entry.update(outcome="timeout", error=f"timed out after {policy.timeout_s:.1f}s")
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_transient(exc):
                entry.update(outcome="error", error=f"{type(exc).__name__}: {exc}")
                entry["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
                log.append(entry)
                raise
            entry.update(outcome="transient_failure", error=f"{type(exc).__name__}: {exc}")
        else:
            entry.update(outcome="success", error=None)
            entry["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
            log.append(entry)
            return result
        entry["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
        log.append(entry)
    raise RetryExhausted(log)
