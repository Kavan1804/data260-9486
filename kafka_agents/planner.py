#!/usr/bin/env python3
"""Planner: reads a question from s9486_inbox, writes a short plan to s9486_tasks.

Run:  python kafka_agents/planner.py      (or make planner)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from kafka_agents.base import Agent, main, require  # noqa: E402

SYSTEM = (
    "You are the Planner in a rental-housing helper for students. Break the user's question into 2 to 4 short "
    'steps the Writer should cover. Reply only with JSON like {"steps": ["...", "..."]}.'
)


class Planner(Agent):
    name = "planner"
    in_topic = config.TOPIC_INBOX
    out_topic = config.TOPIC_TASKS

    def handle(self, msg: dict) -> dict:
        require(msg, "correlation_id", "question")
        if self.args.mode == "fast":
            steps, seconds = [f"Answer: {msg['question']}"], 0.0
        else:
            from kafka_agents.llm import ask

            reply, seconds = ask(SYSTEM, msg["question"], as_json=True)
            steps = reply.get("steps") if isinstance(reply, dict) else None
            if not isinstance(steps, list) or not steps or not all(isinstance(s, str) and s.strip() for s in steps):
                raise ValueError(f"planner reply has no usable steps: {reply}")
            steps = [s.strip() for s in steps[:4]]
        return {
            "correlation_id": msg["correlation_id"],
            "question": msg["question"],
            "plan": steps,
            "planner": {
                "mode": self.args.mode,
                "model": None if self.args.mode == "fast" else config.OLLAMA_MODEL,
                "seconds": seconds,
            },
            "trace": msg.get("trace", []),
        }


if __name__ == "__main__":
    main(Planner)
