"""Small helpers shared by the HW10 modules, scripts and dashboard (same pattern as hw9/common.py)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HW10_DIR = ROOT / "Homework10"
for p in (ROOT, ROOT / "scripts", ROOT / "Homework9", HW10_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # deepeval must not send usage data anywhere

from hw5_common import STUDENT  # noqa: E402
from hw5_common import banner as _hw5_banner  # noqa: E402

import config  # noqa: E402

PREFIX = config.PREFIX
DATA = HW10_DIR / "data"
REPORT_DIR = ROOT / "reports" / "hw10"
RAW = REPORT_DIR / "raw"
SPANS = RAW / "spans.jsonl"  # every stage of every traced request, one JSON object per line


def banner(title: str) -> None:
    _hw5_banner(f"HW10 | {title}")


def footer(title: str) -> None:
    print(f"===== {STUDENT} | SID4 {config.SID4} | {PREFIX} | HW10 | {title} - done =====", flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enable_tracing() -> Path:
    """Spans from this process and from the agents it starts (they inherit the env) go to raw/spans.jsonl."""
    RAW.mkdir(parents=True, exist_ok=True)
    os.environ["TRACE_SPANS_FILE"] = str(SPANS)
    return SPANS


def read_spans(path: Path = SPANS) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a half-written line from a killed process is skipped, not fatal
    return out


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
