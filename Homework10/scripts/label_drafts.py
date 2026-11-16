#!/usr/bin/env python3
"""HW10 Part 3.1: hand-label the 20 Writer drafts (you type the labels; nothing here uses a model).

Shows each case's question (with the database facts the Writer got) and the draft, then asks for a helpfulness
label 1-5 (1 = very poor, 5 = excellent - the same scale the judge uses). Writes Homework10/data/human_labels.csv
after every answer, so you can stop with Ctrl+C and run it again to continue where you left off.

  1 very poor   wrong, off-topic, or makes up facts
  2 poor        partly answers, but with important errors or gaps
  3 acceptable  answers, but vague, padded or misses a detail
  4 good        correct and useful, minor issues
  5 excellent   correct, complete, specific and concise

Usage (repo root):  python Homework10/scripts/label_drafts.py      (or make label-drafts)
"""

from __future__ import annotations

import csv
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw10.common import DATA, STUDENT, read_json  # noqa: E402

LABELS = DATA / "human_labels.csv"
SCALE = "1 very poor | 2 poor | 3 acceptable | 4 good | 5 excellent"


def load() -> dict[str, int]:
    if not LABELS.exists():
        return {}
    with LABELS.open(encoding="utf-8") as f:
        return {r["case_id"]: int(r["human_helpfulness"]) for r in csv.DictReader(f)}


def save(cases: list[dict], labels: dict[str, int]) -> None:
    with LABELS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "trace_id", "human_helpfulness", "labeler"])
        for c in cases:
            if c["case_id"] in labels:
                w.writerow([c["case_id"], c["trace_id"], labels[c["case_id"]], STUDENT])


def main() -> int:
    cases = read_json(DATA / "eval_cases.json")["cases"]
    labels = load()
    print(f"Labeling {len(cases)} Writer drafts ({len(labels)} already done). Scale: {SCALE}\n")
    for c in cases:
        if c["case_id"] in labels:
            continue
        print("=" * 100)
        print(f"{c['case_id']}  QUESTION: {c['question']}")
        facts = c["question_with_facts"][len(c["question"]) :].strip()
        if facts:
            print(textwrap.indent(facts, "    "))
        print("-" * 100)
        print(textwrap.fill(" ".join(c["draft"].split()), 100) if len(c["draft"]) < 400 else c["draft"])
        print("-" * 100)
        while True:
            ans = input(f"{c['case_id']} helpfulness ({SCALE}): ").strip()
            if ans in {"1", "2", "3", "4", "5"}:
                labels[c["case_id"]] = int(ans)
                save(cases, labels)
                break
            print("  please type a number from 1 to 5")
    print(f"\nall {len(labels)} labels saved to {LABELS.relative_to(LABELS.parents[2])}")
    print(f"===== {STUDENT} | HW10 | human labels - done =====")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped - the labels so far are saved; run again to continue")
        sys.exit(0)
