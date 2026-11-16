"""HW10 tracing: one structured JSON span per stage, appended to the file in TRACE_SPANS_FILE.

trace_id is the HW8 correlation_id (no second request id). When TRACE_SPANS_FILE is not set, write_span does
nothing, so the HW8/HW9 runs behave exactly as before.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

_lock = threading.Lock()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds")


def write_span(
    trace_id: str | None,
    stage: str,
    start: float,
    end: float,
    status: str = "ok",
    error: str | None = None,
    **attrs,
) -> dict | None:
    """start/end are time.time() seconds. Returns the span (also when it is not written)."""
    span = {
        "trace_id": trace_id,
        "stage": stage,
        "start": iso(start),
        "end": iso(end),
        "start_ms": round(start * 1000, 1),
        "end_ms": round(end * 1000, 1),
        "duration_ms": round((end - start) * 1000, 1),
        "status": status,
        "error": error,
        **attrs,
    }
    path = os.getenv("TRACE_SPANS_FILE")
    if path:
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(span, default=str) + "\n")
    return span


def now() -> float:
    return time.time()
