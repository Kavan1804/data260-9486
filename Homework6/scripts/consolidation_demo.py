#!/usr/bin/env python3
"""HW6 Part 4.5: consolidate the 55-line test MEMORY.md and check the result.

Copies Homework6/fixtures/MEMORY_original_55.md to
reports/hw06/raw/MEMORY_consolidated.md, runs the real /compact command on that
copy (backend.app.file_memory.handle_command), prints the before/after counts,
the merged duplicates, the resolved contradictions and the flagged resolutions,
and writes reports/hw06/raw/consolidation_report.json. The fixture itself is
not changed, so the original and consolidated versions can both be committed.

No model, database or network needed.

Usage (repo root):
    python Homework6/scripts/consolidation_demo.py
"""

from __future__ import annotations

import shutil
import sys

from hw6_common import FIXTURES, RAW, banner, write_json

from backend.app import file_memory

ORIGINAL = FIXTURES / "MEMORY_original_55.md"
CONSOLIDATED = RAW / "MEMORY_consolidated.md"


def main() -> int:
    banner("Part 4 consolidation of the 55-line MEMORY.md fixture")
    original = ORIGINAL.read_text(encoding="utf-8")
    due, reasons = file_memory.needs_consolidation(original)
    print(f"original: {ORIGINAL.relative_to(file_memory.config.ROOT)} - {len(original.splitlines())} lines, "
          f"{file_memory.count_memory_lines(original)} non-empty non-comment lines")
    print(f"consolidation due: {due} ({'; '.join(reasons)})\n")

    CONSOLIDATED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ORIGINAL, CONSOLIDATED)
    result = file_memory.handle_command("/compact", path=CONSOLIDATED)
    report = result["report"]
    print(result["reply"], "\n")

    print(f"Duplicates merged ({len(report['duplicates_merged'])} lines):")
    for d in report["duplicates_merged"]:
        print(f"  [{d['key']}] {d['value']}")
    print(f"\nContradictions resolved ({len(report['contradictions_resolved'])}):")
    for c in report["contradictions_resolved"]:
        print(f"  [{c['key']}] kept {c['kept']!r} ({c['kept_seen']}, {c['kept_source']}) "
              f"over {c['dropped']!r} ({c['dropped_seen']}, {c['dropped_source']})")
    print(f"\nFlagged as possibly resolved incorrectly ({len(report['needs_review'])}):")
    for r in report["needs_review"]:
        print(f"  [{r['key']}] kept {r['kept']!r} over {r['dropped']!r}: {r['why']}")

    consolidated = CONSOLIDATED.read_text(encoding="utf-8")
    checks = file_memory.verify_consolidation(original, consolidated, report)
    print("\nChecks:")
    for c in checks:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['check']}: {c['details']}")
    print(f"\n----- {CONSOLIDATED.name} -----\n{consolidated}")

    write_json(RAW / "consolidation_report.json", {"original": str(ORIGINAL), "consolidated": str(CONSOLIDATED),
                                                   "compact_reply": result["reply"], "report": report,
                                                   "checks": checks})
    print(f"Wrote {CONSOLIDATED} and {RAW / 'consolidation_report.json'}")
    return 0 if all(c["passed"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
