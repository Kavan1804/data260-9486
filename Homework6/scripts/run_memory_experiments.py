#!/usr/bin/env python3
"""HW6 Part 3: run the same 30-message conversation + 5 probes for each memory setting.

Settings (hw6_common.SETTINGS): SHORT_TERM_N = 4, 12, 30, and the compression policy
(N=12, newest 4 messages verbatim, older ones clipped). Each setting uses a fresh
user_id and session_id, so no summary or episode leaks from one setting to another.
Requests go through the real POST /api/chat (short_term_n / policy are request fields).

Needs the backend, MongoDB and Ollama running. Takes a while on a laptop: every
turn is one reply call + one fact-extraction call (+ a summary call every 5 turns).

Usage (repo root):
    python Homework6/scripts/run_memory_experiments.py                    # all four settings
    python Homework6/scripts/run_memory_experiments.py --settings n4 n12 n30
    python Homework6/scripts/run_memory_experiments.py --settings compress
Writes (one file per setting, so settings can be run separately):
    reports/hw06/raw/turns_<setting>.csv     one row per /api/chat request (conversation + probes)
    reports/hw06/raw/probe_answers_<setting>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import requests
import yaml
from hw6_common import BASE_URL, FIXTURES, PROBES_YAML, RAW, SETTING_NAMES, SETTINGS, banner, write_csv, write_json

USAGE_FIELDS = [
    "run_id",
    "setting",
    "phase",
    "user_id",
    "session_id",
    "turn",
    "short_term_n",
    "policy",
    "model",
    "embedding_model",
    "prompt_tokens",
    "completion_tokens",
    "token_source",
    "prompt_tokens_est",
    "completion_tokens_est",
    "system_primer_tokens_est",
    "long_term_summary_tokens_est",
    "short_term_window_tokens_est",
    "episodic_facts_tokens_est",
    "current_message_tokens_est",
    "window_messages",
    "episodes_retrieved",
    "aux_calls",
    "aux_prompt_tokens",
    "aux_completion_tokens",
    "model_latency_ms",
    "latency_ms",
    "session_summary_created",
    "lifetime_summary_created",
    "timestamp",
]


def send(base_url: str, payload: dict) -> dict:
    r = requests.post(f"{base_url}/api/chat", json=payload, timeout=900)
    r.raise_for_status()
    return r.json()


def run_setting(label: str, run_id: str, conversation: list[str], probes: list[dict], base_url: str) -> None:
    n, policy = SETTINGS[label]
    user_id, session_id = f"exp-{run_id}-{label}", f"{label}-session"
    print(f"\n### {SETTING_NAMES[label]}  (user_id={user_id})", flush=True)
    rows, answers = [], []
    common = {"user_id": user_id, "session_id": session_id, "short_term_n": n, "policy": policy, "run_id": run_id}

    for i, text in enumerate(conversation, 1):
        body = send(base_url, {**common, "message": text, "phase": "conversation"})
        u = body["usage"]
        rows.append({"setting": label, **{k: u.get(k) for k in USAGE_FIELDS if k != "setting"}})
        print(
            f"  turn {i:2d}: prompt_tokens={u['prompt_tokens']} (est {u['prompt_tokens_est']}) "
            f"window={u['window_messages']} episodes={u['episodes_retrieved']} latency={u['latency_ms']} ms",
            flush=True,
        )

    for p in probes:
        body = send(base_url, {**common, "message": p["question"], "phase": "probe"})
        u = body["usage"]
        rows.append({"setting": label, **{k: u.get(k) for k in USAGE_FIELDS if k != "setting"}})
        answers.append(
            {
                "setting": label,
                "run_id": run_id,
                "probe_id": p["id"],
                "question": p["question"],
                "expected": p["expected"],
                "answer": body["reply"],
                "episodic_facts": [e["fact"] for e in body["memory_used"]["episodic_facts"]],
            }
        )
        print(f"  probe {p['id']}: {body['reply'][:160]!r}", flush=True)

    write_csv(RAW / f"turns_{label}.csv", rows)
    write_json(RAW / f"probe_answers_{label}.json", answers)
    print(f"  -> {RAW / f'turns_{label}.csv'} ({len(rows)} rows), {RAW / f'probe_answers_{label}.json'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", nargs="+", choices=list(SETTINGS), default=list(SETTINGS))
    ap.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    ap.add_argument("--base-url", default=BASE_URL)
    args = ap.parse_args()

    conversation = json.loads((FIXTURES / "conversation_30.json").read_text(encoding="utf-8"))["messages"]
    probes = yaml.safe_load(PROBES_YAML.read_text(encoding="utf-8"))["probes"]
    assert len(conversation) == 30 and len(probes) == 5, "fixture must have 30 messages and 5 probes"

    banner(f"Part 3 memory experiments run_id={args.run_id} settings={args.settings}")
    for label in args.settings:
        run_setting(label, args.run_id, conversation, probes, args.base_url)
    print("\nNext: python Homework6/scripts/score_probes.py && python Homework6/scripts/memory_cost.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
