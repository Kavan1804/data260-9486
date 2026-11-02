#!/usr/bin/env python3
"""HW8 Part 3B: kill the Writer in the middle of a message, restart it, see what happened to that message.

Each run uses a fresh consumer group and two tasks on the same partition:
  A  finishes normally in 0.5 s (so the group has a committed offset)
  B  takes 6 s of "work" (--work-seconds 6, fast mode); the Writer is killed with SIGKILL 2 s into it
Then a new Writer process starts in the same group.

  before fix  --commit auto    aiokafka commits the position every 1 s, so B's offset is committed while B is
                               still being worked on. After the restart B is skipped: it is lost.
  after fix   --commit manual  the offset is committed only after the draft was sent. B was not committed,
                               so Kafka gives it to the restarted Writer and it is completed.

Usage (repo root, `make kafka-up` first):  python Homework8/scripts/failure_consumer_death.py
Writes reports/hw08/raw/consumer_death.json
"""

from __future__ import annotations

import sys
import time
import uuid
from datetime import datetime

from hw8_common import (
    RAW,
    Proc,
    banner,
    footer,
    group_offsets,
    read_since,
    send_raw,
    skip_test_messages,
    task_message,
    topic_end,
    utc_now,
    write_json,
)

import config
from kafka_service.common import to_bytes

KEY = b"death-test"  # both tasks on one partition, so the offsets are easy to follow


def show_offsets(group: str, when: str) -> list[str]:
    rows = group_offsets(group)
    print(f"  committed offsets {when}:")
    for r in rows or ["(group has no committed offsets)"]:
        print(f"    {r}")
    return rows


def run_case(label: str, commit: str) -> dict:
    print(f"\n=== {label}: writer.py --commit {commit}", flush=True)
    group = f"{config.PREFIX}_writers_death_{commit}_{datetime.now():%H%M%S}"
    args = ["kafka_agents/writer.py", "--mode", "fast", "--group", group, "--commit", commit, "--work-seconds", "6"]
    start = topic_end(config.TOPIC_DRAFTS)

    first = Proc("writer", [*args, "--instance", "writer", "--from", "latest"])
    if not first.wait_for("ready:", 60):
        raise SystemExit("writer did not start")
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    send_raw(
        config.TOPIC_TASKS, [(KEY, to_bytes(task_message(a, "Task A: what is a sublease?", test={"work_s": 0.5})))]
    )
    print(f"  sent task A correlation_id={a}")
    first.wait_for(f"sent to topic={config.TOPIC_DRAFTS}", 30)
    time.sleep(1.5)  # manual: commit line follows right away; auto: wait for the 1 s auto-commit
    meta = send_raw(config.TOPIC_TASKS, [(KEY, to_bytes(task_message(b, "Task B: can my landlord raise rent?")))])
    print(f"  sent task B correlation_id={b} (partition={meta[0]['partition']} offset={meta[0]['offset']})")
    first.wait_for(f"working on correlation_id={b}", 30)
    time.sleep(2)
    first.kill()
    print(f"  >>> killed writer with SIGKILL while it was working on task B (exit code {first.p.returncode})")
    before = show_offsets(group, "right after the kill")

    second = Proc("writer*", [*args, "--instance", "writer-restarted"])
    second.wait_for("ready:", 60)
    completed = second.wait_for("committed offset", 30) if commit == "manual" else second.wait_for(b, 15)
    time.sleep(1)
    second.stop()
    after = show_offsets(group, "after the restart")

    drafts = read_since(config.TOPIC_DRAFTS, start)
    count = {cid: sum(1 for d in drafts if d["value"].get("correlation_id") == cid) for cid in (a, b)}
    b_done_by = sorted({d["value"]["writer"]["instance"] for d in drafts if d["value"].get("correlation_id") == b})
    result = "redelivered and completed" if count[b] == 1 else "lost (never completed)" if count[b] == 0 else "twice"
    print(f"  -> drafts: task A {count[a]}, task B {count[b]} -> task B {result} {b_done_by or ''}")
    return {
        "run": label,
        "commit": commit,
        "group": group,
        "task_a": a,
        "task_b": b,
        "offsets_after_kill": before,
        "offsets_after_restart": after,
        "drafts_task_a": count[a],
        "drafts_task_b": count[b],
        "task_b_completed_by": b_done_by,
        "restart_completed_b": bool(completed) and count[b] == 1,
        "result_task_b": result,
        "log_first_writer": [ln for ln in first.lines if ln[:4].isdigit()],
        "log_restarted_writer": [ln for ln in second.lines if ln[:4].isdigit()],
    }


def main() -> int:
    banner("Part 3B consumer death (SIGKILL the Writer mid-message, then restart)")
    rows = [run_case("before fix", "auto"), run_case("after fix", "manual")]
    skip_test_messages()
    print("\n--- summary")
    for r in rows:
        print(f"  {r['run']:10} commit={r['commit']:6} task B after restart: {r['result_task_b']}")
    write_json(RAW / "consumer_death.json", {"run_at": utc_now(), "work_seconds": 6, "runs": rows})
    ok = rows[0]["drafts_task_b"] == 0 and rows[1]["drafts_task_b"] == 1
    print(f"auto-commit lost task B and manual commit completed it after the restart: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    footer("Part 3B consumer death")
    sys.exit(code)
