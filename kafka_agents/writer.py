#!/usr/bin/env python3
"""Writer: reads a plan from s9486_tasks (2 partitions), writes a draft answer to s9486_drafts.

Run:  python kafka_agents/writer.py      (or make writer; make writer2 starts a second instance in the same group)
--mode fast skips the model and returns a fixed template; the Part 3 failure tests use it so 20+ messages finish
quickly and the timing is the same on every run. A task may carry test.work_s to say how long "work" takes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from kafka_agents.base import Agent, main, require  # noqa: E402
from kafka_service.common import log  # noqa: E402

SYSTEM = (
    "You are the Writer in a rental-housing helper for students. Write a clear answer to the question that "
    "follows the plan step by step. Keep it under 180 words and do not invent prices or addresses."
)


class Writer(Agent):
    name = "writer"
    in_topic = config.TOPIC_TASKS
    out_topic = config.TOPIC_DRAFTS

    def handle(self, msg: dict) -> dict:
        require(msg, "correlation_id", "question", "plan")
        if not isinstance(msg["plan"], list):
            raise ValueError("plan must be a list of steps")
        work_s = float((msg.get("test") or {}).get("work_s", self.args.work_seconds))
        if self.args.mode == "fast":
            if work_s:
                log(self.label, f"working on correlation_id={msg['correlation_id']} for {work_s:.2f}s")
                time.sleep(work_s)
            draft, seconds = "Draft (fast mode): " + " | ".join(msg["plan"]), work_s
        else:
            from kafka_agents.llm import ask

            plan = "\n".join(f"{i}. {s}" for i, s in enumerate(msg["plan"], 1))
            log(self.label, f"working on correlation_id={msg['correlation_id']} with {config.OLLAMA_MODEL}")
            draft, seconds = ask(SYSTEM, f"Question: {msg['question']}\n\nPlan:\n{plan}")
            if not draft:
                raise ValueError("model returned an empty draft")
        out = {
            "correlation_id": msg["correlation_id"],
            "question": msg["question"],
            "plan": msg["plan"],
            "draft": draft,
            "writer": {
                "instance": self.label,
                "mode": self.args.mode,
                "model": None if self.args.mode == "fast" else config.OLLAMA_MODEL,
                "seconds": seconds,
            },
            "trace": msg.get("trace", []),
        }
        if msg.get("test"):
            out["test"] = msg["test"]
        return out


if __name__ == "__main__":
    main(Writer)
