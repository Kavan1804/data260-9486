"""Small helpers shared by the HW9 modules and scripts (same pattern as hw8_common.py)."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HW9_DIR = ROOT / "Homework9"
for p in (ROOT, ROOT / "scripts", HW9_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from hw5_common import STUDENT  # noqa: E402 - same name in every terminal screenshot
from hw5_common import banner as _hw5_banner  # noqa: E402

import config  # noqa: E402

PREFIX = config.PREFIX  # s9486 - every Redis key in HW9 starts with this
DATA = HW9_DIR / "data"
REPORT_DIR = config.ROOT / "reports" / "hw09"
RAW = REPORT_DIR / "raw"
REDIS_URL = "redis://localhost:6379/0"


def banner(title: str) -> None:
    _hw5_banner(f"HW9 | {title}")


def footer(title: str) -> None:
    """Last line of every HW9 script, so the name is visible even when the banner has scrolled off."""
    print(f"===== {STUDENT} | SID4 {config.SID4} | {PREFIX} | HW9 | {title} - done =====", flush=True)


def stamp() -> str:
    """Local wall-clock time with milliseconds, used at the start of every log line."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def log(who: str, msg: str) -> None:
    print(f"{stamp()} [{who}] {msg}", flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def key(*parts: object) -> str:
    """Build a Redis key: key("views", "listing", 42) -> "s9486:views:listing:42"."""
    return ":".join([PREFIX, *(str(p) for p in parts)])


def redis_client():
    import redis

    client = redis.Redis.from_url(REDIS_URL, decode_responses=False)
    client.ping()
    return client


def delete_prefix(client, pattern: str) -> int:
    """Delete only keys matching s9486:<pattern> (SCAN, never FLUSHALL/FLUSHDB)."""
    if not pattern.startswith(PREFIX + ":"):
        raise ValueError(f"refusing to delete keys outside {PREFIX}: ({pattern})")
    n = 0
    batch = []
    for k in client.scan_iter(match=pattern, count=500):
        batch.append(k)
        if len(batch) >= 500:
            n += client.delete(*batch)
            batch = []
    if batch:
        n += client.delete(*batch)
    return n


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fill_metrics_section(marker: str, content: str) -> None:
    """Replace the text between <!-- {marker}:start --> and <!-- {marker}:end --> in reports/hw09/METRICS.md."""
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")
