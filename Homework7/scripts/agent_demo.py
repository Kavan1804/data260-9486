#!/usr/bin/env python3
"""HW7 Part 2 screenshots: run fixed tasks A, B, C and the nonexistent-ID case once each.

Same loop and settings as the reliability run (llama3.2:3b, max_steps 8, require_tool, repair path), with
temperature 0 so a re-run shows the same thing. Prints every tool call with its inputs, the answer, the total
tool calls and the verifier result. Writes nothing; the measured results come from run_agent_reliability.py.

Usage (repo root, Ollama + MySQL running):
    python Homework7/scripts/agent_demo.py            # A, B, C
    python Homework7/scripts/agent_demo.py --error    # nonexistent listing id
"""

from __future__ import annotations

import argparse
import sys

from hw7_common import banner

import config
from domain_tools.agent import OllamaModel, run_agent
from domain_tools.execute import default_repository
from domain_tools.fixed_tasks import load_tasks, verify, verify_error_recovery


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--error", action="store_true", help="run the nonexistent-ID case instead of A/B/C")
    args = ap.parse_args()
    tasks = load_tasks()
    model = OllamaModel(model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX)
    if args.error:
        banner("Part 2 error recovery: nonexistent listing id")
        er = tasks["error_recovery"]
        print(f"USER: {er['prompt']}")
        s = run_agent(er["prompt"], model=model, max_steps=8, log_path=None, require_tool=True, on_event=print)
        v = verify_error_recovery(s)
        print(f"ANSWER: {s['final_answer']}")
        print(
            f"-> total tool calls: {s['tool_calls']}, stop_reason: {s['stop_reason']}, handled without crashing: "
            f"{v['passed']}"
        )
        return 0
    banner("Part 2 agent loop on fixed tasks A, B, C (no follow-up prompting)")
    repo = default_repository()
    for task_id in ("A", "B", "C"):
        task = tasks["tasks"][task_id]
        print(f"\n=== task {task_id}: {task['name']}\nUSER: {task['prompt']}")
        s = run_agent(task["prompt"], model=model, max_steps=8, log_path=None, require_tool=True, on_event=print)
        v = verify(task_id, s, repo)
        print("ANSWER: " + " ".join((s["final_answer"] or "").split())[:400])
        print(
            f"-> total tool calls: {s['tool_calls']}, stop_reason: {s['stop_reason']}, verifier "
            f"{'PASS' if v['passed'] else 'FAIL'} {v['failure_kinds'] or ''}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
