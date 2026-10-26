#!/usr/bin/env python3
"""HW6 Part 2 demo: send the 12 messages in fixtures/chat_demo_12.json to POST /api/chat
(one session), print each reply with the memory it used, then save
GET /api/memory/{user_id} and GET /api/aggregate/{user_id}.

Needs the backend (make backend), MongoDB and Ollama running.

Usage (repo root):
    python Homework6/scripts/chat_demo.py [--user-id demo-user] [--session-id session-1]
Writes reports/hw06/raw/chat_demo_transcript.json, memory_<user>.json, aggregate_<user>.json.
"""

from __future__ import annotations

import argparse
import json
import sys

import requests
from hw6_common import BASE_URL, FIXTURES, RAW, banner, write_json


def main() -> int:
    fixture = json.loads((FIXTURES / "chat_demo_12.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", default=fixture["user_id"])
    ap.add_argument("--session-id", default=fixture["session_id"])
    ap.add_argument("--base-url", default=BASE_URL)
    args = ap.parse_args()

    banner(f"Part 2 chat demo: {len(fixture['messages'])} messages -> POST /api/chat")
    print(f"user_id={args.user_id} session_id={args.session_id}\n", flush=True)
    transcript = []
    for i, text in enumerate(fixture["messages"], 1):
        r = requests.post(
            f"{args.base_url}/api/chat",
            timeout=600,
            json={"user_id": args.user_id, "session_id": args.session_id, "message": text},
        )
        if r.status_code != 200:
            print(f"[{i}] HTTP {r.status_code}: {r.text}")
            return 1
        body = r.json()
        used, wrote, usage = body["memory_used"], body["memory_written"], body["usage"]
        print(f"--- turn {body['turn']} ---")
        print(f"USER:      {text}")
        print(f"ASSISTANT: {body['reply']}")
        print(
            f"  short-term window: {used['short_term']['count']} msgs | "
            f"session summary: {'yes' if used['session_summary'] else 'no'} | "
            f"lifetime summary: {'yes' if used['lifetime_summary'] else 'no'}"
        )
        for e in used["episodic_facts"]:
            print(f"  episodic fact (cosine {e['score']}): {e['fact']}")
        print(
            f"  facts stored: {[f['fact'] for f in wrote['facts_extracted']]} | "
            f"session summary created: {wrote['session_summary_created']} | "
            f"lifetime summary created: {wrote['lifetime_summary_created']}"
        )
        print(
            f"  tokens prompt/completion: {usage['prompt_tokens']}/{usage['completion_tokens']} | "
            f"latency {usage['latency_ms']} ms\n",
            flush=True,
        )
        transcript.append({"user": text, "response": body})

    write_json(RAW / "chat_demo_transcript.json", transcript)
    for name in ("memory", "aggregate"):
        r = requests.get(f"{args.base_url}/api/{name}/{args.user_id}", timeout=30)
        print(f"===== GET /api/{name}/{args.user_id} -> {r.status_code} =====")
        print(json.dumps(r.json(), indent=2))
        write_json(RAW / f"{name}_{args.user_id}.json", r.json())
    print(f"\nSaved transcript, memory and aggregate JSON under {RAW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
