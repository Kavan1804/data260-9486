#!/usr/bin/env python3
"""HW9 Part 4.2-4.3: learn lessons on training_data.json, keep only the ones validation_data.json accepts.

Phase A (training, in order): each question runs with evaluator repair (max 2 attempts) and loads any lessons
         created so far that match its topic. The Evaluator's failure tags on the *first* attempt are counted;
         when a tag reaches REPEAT first-attempt failures a lesson is created and saved to lessons.json with
         status "candidate". Later training questions on that topic load it.
         REPEAT was 2 at first. In the two logged runs with REPEAT=2 the model failed only one training question
         (tr03), so no lesson was ever made. The PDF's demonstration asks for "a lesson created after one failed
         answer", so REPEAT is 1 now, and the validation gate (Phase B) decides whether the lesson is kept.
Phase B (validation gate, one lesson at a time, in creation order):
         before = validation set with the lessons kept so far; after = the same plus the candidate.
         Single attempt (no repair) so the result shows what the lesson does to the first answer.
         Keep only if: failures after <= failures before, no question that passed before fails after, and no
         new made-up value or invented listing on the not-recorded / missing-listing questions.
         Otherwise status "rejected" (it stays in the file so the Lesson Memory variant can show its effect).
Phase C: one later validation question that loads a kept lesson, showing use_count going up.

test_data.json is never opened here. Usage (repo root; MySQL + Ollama):  python Homework9/scripts/part4_train.py
Writes Homework9/data/lessons.json and reports/hw09/raw/part4_training.json, part4_validation.json
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.agents import (  # noqa: E402
    LESSON_TEXT,
    LESSONS_FILE,
    AnsweringAgent,
    EvaluatorAgent,
    LessonStore,
    gate_decision,
    question_topics,
    run_question,
)
from hw9.common import DATA, RAW, banner, footer, log, read_json, utc_now, write_json  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402

REPEAT = 1  # first-attempt failures with the same tag before a lesson is made (was 2, see the docstring)


def run_validation(label, questions, answerer, evaluator, lessons, statuses) -> dict:
    rows = {}
    for q in questions:
        res = run_question(q["id"], q["question"], answerer, evaluator, 1, lessons, statuses, quiet=True)
        h = res["history"][0]
        rows[q["id"]] = {
            "result": res["final_result"],
            "tags": h["evaluation"]["tags"],
            "lessons": res["lessons_loaded"],
            "answer": res["final_answer"],
        }
    failed = sorted(k for k, v in rows.items() if v["result"] != "PASS")
    print(f"    {label:28} pass {len(rows) - len(failed)}/{len(rows)}   failing: {failed or '-'}", flush=True)
    return {"rows": rows, "failed": failed}


def main() -> int:
    banner("Part 4.2-4.3 training lessons + validation gate")
    train = read_json(DATA / "training_data.json")
    valid = read_json(DATA / "validation_data.json")
    LESSONS_FILE.write_text("[]\n", encoding="utf-8")  # start with no lessons
    lessons = LessonStore()
    answerer = AnsweringAgent(ListingDatabaseWithCache())
    evaluator = EvaluatorAgent()

    # ---------------- Phase A
    print(f"\n=== Phase A: training ({len(train)} questions, repair on) ===")
    print(f"a lesson is created after {REPEAT} failed first answer(s) with the same evaluator tag")
    seen: dict[str, list[str]] = defaultdict(list)
    topics_of: dict[str, set[str]] = defaultdict(set)
    training = []
    for q in train:
        res = run_question(q["id"], q["question"], answerer, evaluator, 2, lessons, ("candidate", "kept"), quiet=True)
        first = res["history"][0]["evaluation"]
        why = first["explanation"] if first["tags"] else ""
        print(
            f"  {q['id']} lessons={res['lessons_loaded'] or '-'}  attempt1={first['result']:6} "
            f"final={res['final_result']:6} attempts={res['attempts']}  {why}",
            flush=True,
        )
        training.append(res)
        for tag in first["tags"]:
            seen[tag].append(q["id"])
            topics_of[tag] |= question_topics(q["question"])
            if len(seen[tag]) == REPEAT and tag in LESSON_TEXT:
                lesson = lessons.create(tag, topics_of[tag], list(seen[tag]))
                log(
                    "lessons",
                    f"LESSON CREATED {lesson['lesson_id']} after failure pattern '{tag}' in {seen[tag]}: "
                    f"{lesson['correction']}",
                )
    write_json(RAW / "part4_training.json", {"run_at": utc_now(), "failure_tags": seen, "results": training})
    print(f"failure tags on first attempts: { {k: v for k, v in seen.items()} or 'none' }")
    print(f"lessons created: {[x['lesson_id'] for x in lessons.lessons] or 'none'}")

    # ---------------- Phase B
    print(f"\n=== Phase B: validation gate ({len(valid)} validation questions, single attempt) ===")
    gate = []
    current = run_validation("before any lesson", valid, answerer, evaluator, lessons, ("kept",))
    for lesson in list(lessons.lessons):
        lid = lesson["lesson_id"]
        lesson["status"] = "trial"
        after = run_validation(f"with {lid} added", valid, answerer, evaluator, lessons, ("kept", "trial"))
        decision = gate_decision(current["rows"], after["rows"])
        keep = decision["decision"] == "kept"
        lesson["status"] = decision["decision"]
        lesson["validation"] = decision
        lessons.save()
        print(
            f"  {lid} ({lesson['tag']}): failing {len(current['failed'])} -> {len(after['failed'])}, "
            f"broke {decision['previously_correct_now_wrong'] or 'none'}, "
            f"new unsupported {decision['new_unsupported_answers'] or 'none'} => {lesson['status'].upper()}",
            flush=True,
        )
        gate.append({"lesson_id": lid, "before": current, "after": after, "decision": lesson["status"]})
        if keep:
            current = after
    write_json(RAW / "part4_validation.json", {"run_at": utc_now(), "gate": gate})

    # ---------------- Phase C
    kept = [x for x in lessons.lessons if x["status"] == "kept"]
    reuse = None
    if kept:
        print("\n=== Phase C: a later related question loads a stored lesson ===")
        for q in valid:
            rel = lessons.relevant(q["question"], ("kept",))
            if rel:
                before = {x["lesson_id"]: x["use_count"] for x in rel}
                res = run_question(q["id"], q["question"], answerer, evaluator, 2, lessons, ("kept",), quiet=True)
                after = {x["lesson_id"]: x["use_count"] for x in rel}
                print(f"  question {q['id']}: {q['question']}")
                for x in rel:
                    print(f'  loaded {x["lesson_id"]}: "{x["correction"]}"')
                    print(f"    use_count {before[x['lesson_id']]} -> {after[x['lesson_id']]}")
                print(f"  answer: {res['final_answer']}")
                print(f"  evaluator: {res['final_result']} in {res['attempts']} attempt(s)")
                reuse = {
                    "question": q,
                    "lessons": rel,
                    "use_count_before": before,
                    "use_count_after": after,
                    "result": res,
                }
                break
    write_json(RAW / "part4_reuse.json", {"run_at": utc_now(), "reuse": reuse})

    print("\n=== lessons.json ===")
    for x in lessons.lessons:
        print(
            f"  {x['lesson_id']} [{x['status']}] use_count={x['use_count']} applies_to={x['applies_to']} "
            f"from {x['source']}: {x['failure_pattern']}"
        )
    if not lessons.lessons:
        print("  (no failure pattern in training, so no lesson was created)")
    return 0


if __name__ == "__main__":
    code = main()
    footer("Part 4 training + validation")
    sys.exit(code)
