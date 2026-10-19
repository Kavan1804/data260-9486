"""Small helpers shared by the HW6 scripts (same pattern as scripts/hw5_common.py)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import config  # noqa: E402
from hw5_common import STUDENT  # noqa: E402,F401 - same name in every terminal screenshot
from hw5_common import banner as _hw5_banner  # noqa: E402

HW6_DIR = ROOT / "Homework6"
FIXTURES = HW6_DIR / "fixtures"
PROBES_YAML = HW6_DIR / "memory_probes.yaml"
REPORT_DIR = config.HW6_REPORT_DIR          # reports/hw06 (the folder the HW6 PDF asks for)
RAW = REPORT_DIR / "raw"
BASE_URL = f"http://localhost:{config.PORT_BASE}"

# Part 3 settings: label -> (SHORT_TERM_N, policy)
SETTINGS = {
    "n4": (4, "none"),
    "n12": (12, "none"),
    "n30": (30, "none"),
    "compress": (12, "compress"),
}
SETTING_NAMES = {
    "n4": "SHORT_TERM_N=4",
    "n12": "SHORT_TERM_N=12",
    "n30": "SHORT_TERM_N=30",
    "compress": f"Compression policy (N=12, last {config.COMPRESS_KEEP_RECENT} verbatim, "
                f"older clipped to {config.COMPRESS_MAX_CHARS} chars)",
}


def banner(title: str) -> None:
    _hw5_banner(f"HW6 | {title}")


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


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fill_metrics_section(marker: str, content: str) -> None:
    """Replace the text between <!-- {marker}:start --> and <!-- {marker}:end --> in reports/hw06/METRICS.md."""
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")
