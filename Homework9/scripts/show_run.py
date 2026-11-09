#!/usr/bin/env python3
"""Print the last logged run of a make target from reports/hw09/RUN_LOG.txt (for screenshots).

The model runs take minutes (the sweep ~30 min) and rerunning them would overwrite the raw files the report is
built from, so the screenshots show the logged output itself: the original lines and timestamps, with only the
noisy Kafka client lines left out. The banner says it is a replay and when the run happened.

Usage (repo root):  python Homework9/scripts/show_run.py sweep      (or make show-run T=sweep)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import REPORT_DIR, banner, footer  # noqa: E402

# target -> line to start from (None = whole section)
START = {
    "cache-demo": "=== Results ===",
    "sweep": "=== Threshold sweep",
    "part4-train": "=== Phase A",
    "variants": "=== Results on test_data.json",
}


def section(target: str) -> list[str]:
    lines = (REPORT_DIR / "RUN_LOG.txt").read_text(encoding="utf-8").splitlines()
    head = f" {target} (Kavan Siddesh) ====="
    starts = [i for i, ln in enumerate(lines) if ln.startswith("===== ") and ln.endswith(head)]
    if not starts:
        raise SystemExit(f"no logged run of `make {target}` in RUN_LOG.txt")
    i = starts[-1]
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("===== 20")), len(lines))
    return lines[i:j]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    target = sys.argv[1]
    lines = section(target)
    banner(f"replay of the logged `make {target}` run (from RUN_LOG.txt, not a new run)")
    print(lines[0])  # the original "===== <time> <target> (Kavan Siddesh) =====" line
    body = lines[1:]
    start = START.get(target)
    if start:
        k = next((n for n, ln in enumerate(body) if ln.startswith(start)), 0)
        if k:
            print(f"  ... ({k} lines of the run above this point not shown)")
        body = body[k:]
    for ln in body:
        if "[send_question]" in ln:
            continue
        print(ln)
    return 0


if __name__ == "__main__":
    code = main()
    footer(f"replay {sys.argv[1] if len(sys.argv) > 1 else ''}".strip())
    sys.exit(code)
