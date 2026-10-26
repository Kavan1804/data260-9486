#!/usr/bin/env python3
"""HW7 Part 2: run the three fixed tasks (A, B, C) many times with the same model settings, plus the
nonexistent-ID error-recovery case, and measure tool-call reliability.

Settings for every attempt: llama3.2:3b, temperature 0.7, num_ctx 8192, max_steps 8, max_failed_repairs 2,
require_tool=True. Only the sampling seed changes per attempt (VERIFY_SEED + attempt number), so the
attempts are not 21 copies of the same temperature-0 run.

Writes reports/hw07/raw/reliability_attempts.csv/.json, raw/error_recovery.json, raw/agent_runs_hw7.jsonl
and the Part 2 table in METRICS.md.

Usage (repo root, Ollama + MySQL running):
    python Homework7/scripts/run_agent_reliability.py [--per-task 7]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from hw7_common import RAW, banner, fill_metrics_section, write_csv, write_json

import config
from domain_tools.agent import OllamaModel, run_agent
from domain_tools.execute import default_repository
from domain_tools.fixed_tasks import load_tasks, verify, verify_error_recovery

TEMPERATURE = 0.7
MAX_STEPS = 8
MAX_FAILED_REPAIRS = 2
LOG = RAW / "agent_runs_hw7.jsonl"


def model_for(seed: int) -> OllamaModel:
    return OllamaModel(model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX, temperature=TEMPERATURE, seed=seed)


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}% ({a}/{b})" if b else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-task", type=int, default=7)
    args = ap.parse_args()
    tasks = load_tasks()
    repo = default_repository()
    banner(
        f"Part 2 agent reliability: {args.per_task} x tasks A/B/C with {config.OLLAMA_MODEL} "
        f"(temperature {TEMPERATURE}, max_steps {MAX_STEPS})"
    )
    if LOG.exists():
        LOG.unlink()

    rows = []
    attempt = 0
    for i in range(args.per_task):
        for task_id in ("A", "B", "C"):
            attempt += 1
            seed = config.VERIFY_SEED + attempt
            task = tasks["tasks"][task_id]
            print(f"\n=== attempt {attempt}: task {task_id} ({task['name']}), seed {seed}")
            print(f"USER: {task['prompt']}")
            s = run_agent(
                task["prompt"],
                model=model_for(seed),
                max_steps=MAX_STEPS,
                log_path=LOG,
                scenario=f"{task_id}-{i + 1}",
                require_tool=True,
                max_failed_repairs=MAX_FAILED_REPAIRS,
                on_event=print,
            )
            v = verify(task_id, s, repo)
            print(f"ANSWER: {(s['final_answer'] or '').strip()[:400]}")
            print(
                f"-> total tool calls {s['tool_calls']}, stop_reason {s['stop_reason']}, verifier "
                f"{'PASS' if v['passed'] else 'FAIL'}, failures {v['failure_kinds'] or 'none'}, "
                f"{s['duration_s']} s",
                flush=True,
            )
            rows.append(
                {
                    "attempt": attempt,
                    "task": task_id,
                    "seed": seed,
                    "temperature": TEMPERATURE,
                    "model": s["model"],
                    "run_id": s["run_id"],
                    "tool_calls": s["tool_calls"],
                    "steps": s["steps"],
                    "stop_reason": s["stop_reason"],
                    "verifier_passed": v["passed"],
                    "answer_correct": v["answer_correct"],
                    "failure_kinds": ";".join(v["failure_kinds"]),
                    "raw_failures": ";".join(f["kind"] for f in s["failures"]),
                    "call_slots": s["call_slots"],
                    "first_try_valid": s["first_try_valid"],
                    "repaired": s["repaired"],
                    "failed_repairs": s["failed_repairs"],
                    "prompt_tokens": s["prompt_tokens"],
                    "completion_tokens": s["completion_tokens"],
                    "duration_s": s["duration_s"],
                    "tools_used": " > ".join(t["tool"] for t in s["tool_log"]),
                    "unsupported_claims": ";".join(v["unsupported_claims"]),
                    "final_answer": s["final_answer"],
                    "checks": v["checks"],
                }
            )

    # Error recovery: nonexistent listing id.
    er = tasks["error_recovery"]
    print(f"\n=== error recovery: {er['name']}\nUSER: {er['prompt']}")
    s = run_agent(
        er["prompt"],
        model=model_for(config.VERIFY_SEED),
        max_steps=MAX_STEPS,
        log_path=LOG,
        scenario="error-recovery",
        require_tool=True,
        on_event=print,
    )
    ev = verify_error_recovery(s)
    print(f"ANSWER: {s['final_answer']}")
    print(
        f"-> total tool calls {s['tool_calls']}, stop_reason {s['stop_reason']}, handled without crashing: "
        f"{ev['passed']}"
    )
    write_json(RAW / "error_recovery.json", {"summary": s, "check": ev})

    write_csv(RAW / "reliability_attempts.csv", [{k: v for k, v in r.items() if k != "checks"} for r in rows])
    write_json(RAW / "reliability_attempts.json", rows)

    slots = sum(r["call_slots"] for r in rows)
    first = sum(r["first_try_valid"] for r in rows)
    fixed = sum(r["repaired"] for r in rows)
    cats = Counter(k for r in rows for k in filter(None, r["failure_kinds"].split(";")))
    raw_kinds = Counter(k for r in rows for k in filter(None, r["raw_failures"].split(";")))
    per_task = {t: [r for r in rows if r["task"] == t] for t in ("A", "B", "C")}
    lines = [
        f"{len(rows)} attempts ({args.per_task} per task), model {config.OLLAMA_MODEL}, temperature {TEMPERATURE}, "
        f"max_steps {MAX_STEPS}, max failed repairs {MAX_FAILED_REPAIRS}, seed = VERIFY_SEED + attempt.",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Tool-call attempts (slots) | {slots} |",
        f"| Well-formed before repair (first try) | {pct(first, slots)} |",
        f"| Well-formed after repair path | {pct(first + fixed, slots)} |",
        f"| Repairs that worked / failed | {fixed} / {sum(r['failed_repairs'] for r in rows)} |",
        f"| Task success (verifier) | {pct(sum(r['verifier_passed'] for r in rows), len(rows))} |",
        f"| Total tool calls executed | {sum(r['tool_calls'] for r in rows)} "
        f"(mean {sum(r['tool_calls'] for r in rows) / len(rows):.2f} per attempt) |",
        "",
        "| Task | Attempts | Verifier pass | Mean tool calls | Stop reasons |",
        "|---|---|---|---|---|",
    ]
    for t, rs in per_task.items():
        stops = Counter(r["stop_reason"] for r in rs)
        lines.append(
            f"| {t} | {len(rs)} | {sum(r['verifier_passed'] for r in rs)} | "
            f"{sum(r['tool_calls'] for r in rs) / len(rs):.2f} | {dict(stops)} |"
        )
    lines += ["", "| Failure type | Attempts with this failure |", "|---|---|"]
    for cat in ("malformed_arguments", "unknown_tool", "text_instead_of_tool", "lost_chain"):
        lines.append(f"| {cat.replace('_', ' ')} | {cats.get(cat, 0)} |")
    lines += [
        "",
        f"Raw rejected-call kinds (every rejection, not per attempt): {dict(raw_kinds) or 'none'}.",
        f"Error recovery (LST-99999): handled without crashing = {ev['passed']}, tool error = "
        f"{ev['tool_error']!r}, stop_reason = {ev['stop_reason']}.",
    ]
    print("\n" + "\n".join(lines))
    fill_metrics_section("part2-table", "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
