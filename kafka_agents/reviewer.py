#!/usr/bin/env python3
"""Reviewer: reads a draft from s9486_drafts, writes the final JSON (status + answer) to s9486_final.

Run:  python kafka_agents/reviewer.py      (or make reviewer)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from kafka_agents.base import Agent, main, require  # noqa: E402

SYSTEM = (
    "You are the Reviewer. Check whether the draft answers the question and covers the plan, without made-up "
    'facts. Reply only with JSON like {"approved": true, "notes": "one or two sentences"}.'
)


class Reviewer(Agent):
    name = "reviewer"
    in_topic = config.TOPIC_DRAFTS
    out_topic = config.TOPIC_FINAL

    def handle(self, msg: dict) -> dict:
        require(msg, "correlation_id", "question", "draft")
        if self.args.mode == "fast":
            approved, notes, seconds = True, "fast mode: approved without a model check", 0.0
        else:
            from kafka_agents.llm import ask

            plan = "\n".join(f"- {s}" for s in msg.get("plan", []))
            reply, seconds = ask(
                SYSTEM, f"Question: {msg['question']}\n\nPlan:\n{plan}\n\nDraft:\n{msg['draft']}", as_json=True
            )
            if not isinstance(reply, dict) or not isinstance(reply.get("approved"), bool):
                raise ValueError(f"reviewer reply has no true/false 'approved': {reply}")
            approved, notes = reply["approved"], str(reply.get("notes", "")).strip()
        return {
            "correlation_id": msg["correlation_id"],
            "status": "approved" if approved else "needs_revision",
            "answer": msg["draft"],
            "review": {
                "approved": approved,
                "notes": notes,
                "mode": self.args.mode,
                "model": None if self.args.mode == "fast" else config.OLLAMA_MODEL,
                "seconds": seconds,
            },
            "question": msg["question"],
            "plan": msg.get("plan", []),
            "writer": msg.get("writer"),
            "trace": msg.get("trace", []),
        }


if __name__ == "__main__":
    main(Reviewer)
