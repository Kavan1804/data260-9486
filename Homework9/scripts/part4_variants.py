#!/usr/bin/env python3
"""HW9 Part 4.4: run the same test_data.json separately on the four variants.

  baseline               Answering Agent only, 1 attempt, no lessons
  evaluator_repair       up to 2 attempts with Evaluator feedback, no lessons
  lesson_memory          repair + every lesson saved in lessons.json (no validation)
  validated_improvement  repair + only lessons with status "kept" (passed the validation gate)

lessons.json is opened read-only here: the test run never creates, edits or counts lessons (use counts during
the test are reported in the raw file only). The test file's sha256 is printed before every variant.

Usage (repo root; MySQL + Ollama):  python Homework9/scripts/part4_variants.py
Writes reports/hw09/raw/variants_<name>.json and variants_summary.json
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.agents import VARIANTS, AnsweringAgent, EvaluatorAgent, LessonStore, run_question  # noqa: E402
from hw9.common import DATA, RAW, banner, footer, read_json, utc_now, write_json  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402

TEST_FILE = DATA / "test_data.json"


def main() -> int:
    banner("Part 4.4 four variants on the unchanged test set")
    answerer = AnsweringAgent(ListingDatabaseWithCache())
    evaluator = EvaluatorAgent()
    summary = []
    for name, (max_attempts, statuses) in VARIANTS.items():
        sha = hashlib.sha256(TEST_FILE.read_bytes()).hexdigest()
        test = read_json(TEST_FILE)
        lessons = LessonStore(read_only=True)
        usable = [x["lesson_id"] for x in lessons.lessons if x["status"] in statuses]
        print(
            f"\n=== {name}: max attempts {max_attempts}, lessons {usable or 'none'}  "
            f"(test_data.json sha256 {sha[:16]}..., {len(test)} questions) ===",
            flush=True,
        )
        rows = []
        for q in test:
            res = run_question(q["id"], q["question"], answerer, evaluator, max_attempts, lessons, statuses, quiet=True)
            rows.append(res)
            print(
                f"  {q['id']} {res['final_result']:6} attempts={res['attempts']} {res['latency_s']:5.1f}s "
                f"lessons={res['lessons_loaded'] or '-'}  {res['final_answer'][:90].replace(chr(10), ' ')}",
                flush=True,
            )
        correct = sum(r["final_result"] == "PASS" for r in rows)
        s = {
            "variant": name,
            "correct": correct,
            "incorrect": len(rows) - correct,
            "avg_attempts": round(sum(r["attempts"] for r in rows) / len(rows), 2),
            "avg_latency_s": round(sum(r["latency_s"] for r in rows) / len(rows), 2),
            "lessons_available": usable,
            "test_sha256": sha,
        }
        summary.append(s)
        write_json(RAW / f"variants_{name}.json", {"run_at": utc_now(), "summary": s, "rows": rows})

    print("\n=== Results on test_data.json ===")
    print(f"{'variant':24} {'correct':>8} {'incorrect':>10} {'avg attempts':>13} {'avg latency':>12}")
    for s in summary:
        print(
            f"{s['variant']:24} {s['correct']:>5}/12 {s['incorrect']:>10} {s['avg_attempts']:>13.2f} "
            f"{s['avg_latency_s']:>10.2f} s"
        )
    same = len({s["test_sha256"] for s in summary}) == 1
    print(f"test_data.json identical for all four runs: {same}")
    write_json(RAW / "variants_summary.json", {"run_at": utc_now(), "summary": summary, "same_test_file": same})
    return 0 if same else 1


if __name__ == "__main__":
    code = main()
    footer("Part 4.4 variants")
    sys.exit(code)
