#!/usr/bin/env python3
"""HW8 Part 2: one complete message journey s9486_inbox -> s9486_tasks -> s9486_drafts -> s9486_final.

Starts planner.py, writer.py and reviewer.py as three separate processes (the same commands as the four-terminal
run), sends one question with send_question.py as a fourth process, then prints every log line that carries the
question's correlation_id in time order. Uses the real model (llama3.2:3b) and the normal consumer groups.
Stop any agents you started in other terminals first, so this run's agents get the messages.

Usage (repo root, `make kafka-up` and Ollama running):  python Homework8/scripts/pipeline_demo.py ["question"]
Writes reports/hw08/raw/pipeline_journey.json (and the final message to raw/final_message.json)
"""

from __future__ import annotations

import json
import re
import sys

from hw8_common import RAW, Proc, banner, footer, utc_now, write_json

import config

AGENT_LOGS = RAW / "agent_logs"
CID = re.compile(r"correlation_id=([0-9a-f-]{36})")


def journey_lines(procs: list[Proc], cid: str) -> list[str]:
    """Lines with this correlation_id, plus each agent's offset-commit line right after its send."""
    picked = []
    for proc in procs:
        lines = [ln for ln in proc.lines if ln[:4].isdigit()]
        for i, line in enumerate(lines):
            if cid in line:
                picked.append(line)
                if " sent to " in line and i + 1 < len(lines) and "committed offset" in lines[i + 1]:
                    picked.append(lines[i + 1])
    return sorted(set(picked))  # every line starts with its timestamp


def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else None
    banner(f"Part 2 three-agent pipeline (model {config.OLLAMA_MODEL})")
    AGENT_LOGS.mkdir(parents=True, exist_ok=True)
    agents = [Proc(n, [f"kafka_agents/{n}.py"], AGENT_LOGS / f"{n}.log") for n in ("planner", "writer", "reviewer")]
    try:
        for a in agents:
            if not a.wait_for("ready:", timeout=60):
                print(f"{a.name} did not join its group in time")
                return 1
        args = ["kafka_agents/send_question.py", "--timeout", "400"] + ([question] if question else [])
        sender = Proc("send", args)
        sender.p.wait(timeout=420)
        sender._t.join(timeout=5)
    finally:
        for a in agents:
            a.stop()

    sent = next((ln for ln in sender.lines if "sent question" in ln), "")
    match = CID.search(sent)
    if not match or sender.p.returncode != 0:
        print("no final message came back")
        return 1
    cid = match.group(1)
    final = json.loads((RAW / "final_message.json").read_text(encoding="utf-8"))

    lines = journey_lines([sender, *agents], cid)
    print(f"\n--- message journey for correlation_id={cid} (all processes, time order)")
    for line in lines:
        print("  " + (line if len(line) <= 230 else line[:230] + " ..."))

    stages = [t.get("agent") for t in final.get("trace", [])]
    same_id = final.get("correlation_id") == cid
    print(f"\n--- final message on {config.TOPIC_FINAL}: status={final.get('status')} same correlation_id={same_id}")
    print(f"    stages in trace: {' -> '.join(stages)}")
    write_json(
        RAW / "pipeline_journey.json",
        {
            "run_at": utc_now(),
            "model": config.OLLAMA_MODEL,
            "correlation_id": cid,
            "journey": lines,
            "final": final,
            "correlation_id_preserved": same_id,
        },
    )
    return 0 if same_id and final.get("status") and final.get("answer") else 1


if __name__ == "__main__":
    code = main()
    footer("Part 2 pipeline")
    sys.exit(code)
