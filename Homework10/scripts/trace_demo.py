#!/usr/bin/env python3
"""HW10 Part 2 + Part 4.2: one end-to-end evaluated question and the three required traces.

  1. cache MISS  - a new question goes cache -> s9486_inbox -> planner -> writer -> reviewer -> s9486_final, is
                   stored in the cache, then the evaluator joins plan/draft/final by trace_id and runs GEval.
                   This is the Part 2 end-to-end evaluation (raw/part2_evaluation.json).
  2. cache HIT   - the same question again: served from Redis, no pipeline, no evaluation.
  3. FAILED      - a new question sent with test.fail_stage = "planner": the Planner fails 3 times, sends it to
                   s9486_dead_letter, no final arrives within 90 s, and the trace shows where and why.
The cache namespace s9486:hw10:* is emptied first (only its own keys).

Usage (repo root; Redis, Kafka, MySQL, Ollama running):  python Homework10/scripts/trace_demo.py
Writes reports/hw10/raw/trace_examples.json and part2_evaluation.json; spans go to raw/spans.jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw10.analysis import by_trace, journey  # noqa: E402
from hw10.common import RAW, banner, footer, read_spans, utc_now, write_json  # noqa: E402
from hw10.runtime import make_qa, running_agents  # noqa: E402

DEMO_QUESTION = "Who is the landlord for listing LST-00117, and how many units are open there?"
FAIL_QUESTION = "What are the quiet hours rules I should ask about before renting an apartment?"


def show(trace_id: str) -> None:
    for s in journey(by_trace(read_spans())[trace_id]):
        extra = {k: s[k] for k in ("cache", "similarity", "queue_wait_ms", "attempts", "path") if s.get(k) is not None}
        err = f"  ERROR: {s['error'][:110]}" if s.get("error") else ""
        print(
            f"    {s['stage']:12} {s['start'][11:23]} -> {s['end'][11:23]} {s['duration_ms']:>10,.1f} ms  "
            f"{s['status']:5} {extra}{err}"
        )


def main() -> int:
    banner("Part 2 + 4.2 evaluated run and the three traces (miss, hit, failed)")
    qa, cache = make_qa()
    print(f"cleared {cache.clear()} old entries under {cache.entry_prefix}*")
    examples = {}
    with running_agents():
        print(f"\n[1] cache MISS: {DEMO_QUESTION}")
        miss = qa.ask(DEMO_QUESTION)
        examples["miss"] = miss["trace_id"]
        print(f"  trace_id={miss['trace_id']} status={miss['status']} latency={miss['latency_ms']:,.1f} ms")
        show(miss["trace_id"])
        ev = miss.get("evaluation") or {}
        if ev.get("status") == "ok":
            imp = ev["improvement"]
            print(
                f"  GEval (judge {ev['judge']['model']}, 1-5): plan quality {ev['plan_quality']['score']}, "
                f"writer helpfulness {ev['writer_helpfulness']['score']}, final helpfulness "
                f"{ev['final_helpfulness']['score']}, final - draft = {imp['difference']:+d}"
            )
            print(f"  plan reason: {ev['plan_quality']['reason'][:200]}")
            print(f"  improvement: {imp['interpretation']}")
        else:
            print(f"  evaluation: {ev.get('status')} {ev.get('error')}")
        write_json(RAW / "part2_evaluation.json", {"run_at": utc_now(), **miss})

        print("\n[2] cache HIT: same question again")
        hit = qa.ask(DEMO_QUESTION)
        examples["hit"] = hit["trace_id"]
        print(
            f"  trace_id={hit['trace_id']} is_cached={hit['is_cached']} similarity={hit['similarity']:.4f} "
            f"latency={hit['latency_ms']:,.1f} ms"
        )
        show(hit["trace_id"])

        print(f"\n[3] FAILED trace (planner fails on purpose): {FAIL_QUESTION}")
        fail = qa.ask(FAIL_QUESTION, store_on_miss=False, fail_stage="planner", final_timeout_s=90)
        examples["failed"] = fail["trace_id"]
        print(f"  trace_id={fail['trace_id']} status={fail['status']} failed stage={fail.get('failed_stage')}")
        print(f"  error: {fail.get('error')}")
        show(fail["trace_id"])

    write_json(
        RAW / "trace_examples.json",
        {
            "run_at": utc_now(),
            "traces": examples,
            "questions": {"miss": DEMO_QUESTION, "hit": DEMO_QUESTION, "failed": FAIL_QUESTION},
        },
    )
    print("\ntrace ids for the dashboard (Trace lookup page):")
    for k, v in examples.items():
        print(f"  {k:7} {v}")
    ok = miss["status"] == "ok" and hit["is_cached"] and fail["status"] == "error"
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    footer("trace demo")
    sys.exit(code)
