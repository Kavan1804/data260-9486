"""Small helpers shared by the HW5 scripts."""

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402

REPORT_DIR = ROOT / "reports" / "hw05"
RAW = REPORT_DIR / "raw"
STUDENT = "Kavan Siddesh"


def banner(title: str) -> None:
    """Header printed by every script so terminal screenshots show the name."""
    line = "=" * 78
    print(line)
    print(f"{STUDENT} | SID4 {config.SID4} | {config.PREFIX} | {title}")
    print(f"run at {datetime.now().isoformat(timespec='seconds')} | VERIFY_SEED {config.VERIFY_SEED}")
    print(line, flush=True)


def fill_metrics_section(marker: str, content: str) -> None:
    """Replace the text between <!-- {marker}:start --> and <!-- {marker}:end --> in METRICS.md."""
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")
