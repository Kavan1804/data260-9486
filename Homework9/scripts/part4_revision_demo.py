#!/usr/bin/env python3
"""HW9 Part 4.1: one complete revision sequence with a controlled bad first answer.

The first answer is written on purpose to be incomplete (it leaves out the number of units and the landlord),
so the Evaluator -> feedback -> revision path runs every time. The second attempt is the real Answering Agent
(llama3.2:3b) with the Evaluator's feedback. The loop stops after 2 attempts either way.

Usage (repo root; MySQL and Ollama running):  python Homework9/scripts/part4_revision_demo.py
Writes reports/hw09/raw/revision_demo.json
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.agents import AnsweringAgent, EvaluatorAgent, run_question  # noqa: E402
from hw9.common import DATA, RAW, banner, footer, read_json, utc_now, write_json  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402

QID = "tr03"  # "For <code>, how many units are available and who is the landlord?"


def wrap(s: str) -> str:
    return textwrap.fill(s, 110, initial_indent="    ", subsequent_indent="    ")


def main() -> int:
    banner("Part 4.1 revision sequence (controlled incomplete first answer)")
    question = next(q["question"] for q in read_json(DATA / "training_data.json") if q["id"] == QID)
    code = question.split()[1].rstrip(",")
    controlled = f"Listing {code} has units open right now."  # intentionally incomplete: no number, no landlord
    res = run_question(
        QID,
        question,
        AnsweringAgent(ListingDatabaseWithCache()),
        EvaluatorAgent(),
        max_attempts=2,
        forced_first_answer=controlled,
    )
    print(f"\nQuestion ({QID}): {question}")
    for h in res["history"]:
        ev = h["evaluation"]
        who = "controlled, written on purpose" if h.get("controlled") else f"Answering Agent, {h['seconds']}s"
        label = "Initial answer" if h["attempt"] == 1 else "Revised answer"
        print(f"\n[attempt {h['attempt']}] {label} ({who}):")
        print(wrap(h["answer"]))
        print(f"  Evaluator: {ev['result']} - {ev['explanation']}")
        if ev["feedback"]:
            print(f"  Feedback : {ev['feedback']}")
    print(f"\nFinal evaluation: {res['final_result']}   attempts: {res['attempts']} (max 2)")
    print("Final response:")
    print(wrap(res["final_answer"]))
    write_json(RAW / "revision_demo.json", {"run_at": utc_now(), **res})
    return 0 if res["attempts"] == 2 else 1


if __name__ == "__main__":
    code = main()
    footer("Part 4.1 revision")
    sys.exit(code)
