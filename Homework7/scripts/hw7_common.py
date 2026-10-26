"""Small helpers shared by the HW7 scripts (same pattern as hw5_common.py / hw6_common.py)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from hw5_common import STUDENT  # noqa: E402,F401 - same name in every terminal screenshot
from hw5_common import banner as _hw5_banner  # noqa: E402

import config  # noqa: E402

HW7_DIR = ROOT / "Homework7"
FIXTURES = HW7_DIR / "fixtures"
REPORT_DIR = config.HW7_REPORT_DIR  # reports/hw07
RAW = REPORT_DIR / "raw"
BASE_URL = f"http://localhost:{config.PORT_BASE}"


def banner(title: str) -> None:
    _hw5_banner(f"HW7 | {title}")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def fill_metrics_section(marker: str, content: str) -> None:
    """Replace the text between <!-- {marker}:start --> and <!-- {marker}:end --> in reports/hw07/METRICS.md."""
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")
