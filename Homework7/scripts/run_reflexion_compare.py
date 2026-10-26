#!/usr/bin/env python3
"""HW7 Part 3: original loop (Part 2) vs. Reflexion loop on the same three fixed tasks.

For each task and each run i, both loops get the same model settings and the same seed
(VERIFY_SEED + 500 + run number), so the only difference is the Reflexion path.

Writes reports/hw07/raw/reflexion_comparison.csv/.json, raw/reflections.jsonl,
raw/agent_runs_reflexion.jsonl and the Part 3 table in METRICS.md.

Usage (repo root, Ollama + MySQL running):
    python Homework7/scripts/run_reflexion_compare.py [--runs-per-task 5]
"""

from __future__ import annotations

import argparse
import sys
import time

from hw7_common import RAW, banner, fill_metrics_section, write_csv, write_json

import config
from domain_tools.agent import OllamaModel, run_agent
from domain_tools.execute import default_repository
from domain_tools.fixed_tasks import load_tasks, verify
from domain_tools.reflexion import MAX_RETRIES, TOKEN_BUDGET, TOOL_BUDGET, ReflectionStore, run_with_reflexion

TEMPERATURE = 0.7
LOG = RAW / "agent_runs_reflexion.jsonl"


def model_for(seed: int) -> OllamaModel:
    return OllamaModel(model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX, temperature=TEMPERATURE, seed=seed)


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-per-task", type=int, default=5)
    args = ap.parse_args()
    tasks = load_tasks()
    repo = default_repository()
    banner(
        f"Part 3 original loop vs Reflexion ({args.runs_per_task} runs per task, {config.OLLAMA_MODEL}, "
        f"temperature {TEMPERATURE}, max {MAX_RETRIES} retries, budget {TOOL_BUDGET} tools / {TOKEN_BUDGET} tokens)"
    )
    for p in (LOG, RAW / "reflections.jsonl"):
        if p.exists():
            p.unlink()
    store = ReflectionStore(RAW / "reflections.jsonl")
    rows = []
    for i in range(args.runs_per_task):
        for task_id in ("A", "B", "C"):
            seed = config.VERIFY_SEED + 500 + i * 3 + ord(task_id) - 64
            prompt = tasks["tasks"][task_id]["prompt"]
            print(f"\n=== task {task_id} run {i + 1} (seed {seed})")

            print("[original loop]")
            t0 = time.perf_counter()
            s = run_agent(
                prompt,
                model=model_for(seed),
                max_steps=8,
                log_path=LOG,
                scenario=f"{task_id}-original",
                require_tool=True,
                on_event=print,
            )
            v = verify(task_id, s, repo)
            orig = {
                "loop": "original",
                "task": task_id,
                "run": i + 1,
                "seed": seed,
                "passed": v["passed"],
                "answer_correct": v["answer_correct"],
                "stop_reason": "success" if v["passed"] else s["stop_reason"],
                "retries": 0,
                "tool_calls": s["tool_calls"],
                "tokens": s["prompt_tokens"] + s["completion_tokens"],
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
                "unsupported_claims": len(v["unsupported_claims"]),
                "unsupported_list": ";".join(v["unsupported_claims"]),
                "false_rejection_candidate": (not v["passed"]) and v["answer_correct"],
                "final_answer": s["final_answer"],
            }
            print(
                f"-> original: verifier {'PASS' if v['passed'] else 'FAIL'}, {s['tool_calls']} tool calls, "
                f"{orig['tokens']} tokens, {orig['latency_ms']} ms"
            )

            print("[reflexion loop]")
            r = run_with_reflexion(
                task_id,
                model_for(seed),
                repo,
                user_id="s9486_reader",
                run_id=f"{task_id}-{i + 1}",
                store=store,
                log_path=LOG,
                on_event=print,
            )
            refl = {
                "loop": "reflexion",
                "task": task_id,
                "run": i + 1,
                "seed": seed,
                "passed": r["passed"],
                "answer_correct": r["answer_correct"],
                "stop_reason": r["stop_reason"],
                "retries": r["retries"],
                "tool_calls": r["tool_calls"],
                "tokens": r["tokens"],
                "latency_ms": r["latency_ms"],
                "unsupported_claims": len(r["unsupported_claims"]),
                "unsupported_list": ";".join(r["unsupported_claims"]),
                "false_rejection_candidate": (not r["passed"]) and r["answer_correct"],
                "final_answer": r["final_answer"],
                "reflections": r["reflections"],
                "attempt_verdicts": [a["verdict"] for a in r["attempt_details"]],
            }
            print(
                f"-> reflexion: stop={r['stop_reason']}, retries {r['retries']}, {r['tool_calls']} tool calls, "
                f"{r['tokens']} tokens, {r['latency_ms']} ms"
            )
            rows += [orig, refl]

    write_csv(
        RAW / "reflexion_comparison.csv",
        [{k: v for k, v in r.items() if k not in ("reflections", "attempt_verdicts")} for r in rows],
    )
    write_json(RAW / "reflexion_comparison.json", rows)

    def arm(name: str) -> dict:
        rs = [r for r in rows if r["loop"] == name]
        return {
            "success": f"{sum(r['passed'] for r in rs)}/{len(rs)} ({100 * mean([r['passed'] for r in rs]):.0f}%)",
            "unsupported": f"{sum(r['unsupported_claims'] for r in rs)} claims in "
            f"{sum(r['unsupported_claims'] > 0 for r in rs)} runs",
            "retry": f"{sum(r['retries'] > 0 for r in rs)}/{len(rs)} runs ({sum(r['retries'] for r in rs)} retries)",
            "tools": f"{mean([r['tool_calls'] for r in rs]):.2f}",
            "tokens": f"{mean([r['tokens'] for r in rs]):.0f}",
            "latency": f"{mean([r['latency_ms'] for r in rs]):.0f}",
            "false_rej": f"{sum(r['false_rejection_candidate'] for r in rs)}",
            "stops": ", ".join(
                f"{k}: {sum(r['stop_reason'] == k for r in rs)}" for k in sorted({r["stop_reason"] for r in rs})
            ),
        }

    o, f = arm("original"), arm("reflexion")
    lines = [
        f"{args.runs_per_task} runs per task x 3 tasks per loop, same seeds for both loops. Means are per run; "
        "Reflexion numbers include all attempts of a run.",
        "",
        "| Metric | Original loop | Reflexion loop |",
        "|---|---|---|",
        f"| Task success | {o['success']} | {f['success']} |",
        f"| Unsupported claims | {o['unsupported']} | {f['unsupported']} |",
        f"| Retry rate | {o['retry']} | {f['retry']} |",
        f"| Tool calls (mean per run) | {o['tools']} | {f['tools']} |",
        f"| Tokens (mean per run) | {o['tokens']} | {f['tokens']} |",
        f"| Latency (ms, mean per run) | {o['latency']} | {f['latency']} |",
        f"| Verifier false rejections (strict FAIL, answer correct) | {o['false_rej']} | {f['false_rej']} |",
        f"| Stop reasons | {o['stops']} | {f['stops']} |",
    ]
    print("\n" + "\n".join(lines))
    fill_metrics_section("part3-table", "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
