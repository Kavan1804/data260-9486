#!/usr/bin/env python3
"""HW8 Part 3C: a poison message on s9486_tasks, before and after bounded retries + s9486_dead_letter.

Every run sends, on one partition and in this order:  a good warm-up task, the poison message(s), 2 good tasks.

  before fix  --poison-handling none  the Writer crashes on the poison message without committing it. Restarting
              it reads the same message again and crashes again, so the 2 good tasks behind it never run.
  after fix   default                 each bad message is tried 3 times (WRITER_MAX_RETRIES), then written to
              s9486_dead_letter with the error and committed, and the 2 good tasks are processed.

Poison messages: bytes that are not JSON, and a JSON task with no "plan" field.
Usage (repo root, `make kafka-up` first):  python Homework8/scripts/failure_poison.py
Writes reports/hw08/raw/poison_message.json
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

KEY = b"poison-test"


def run_case(label: str, handling: str) -> dict:
    print(f"\n=== {label}: writer.py --poison-handling {handling}", flush=True)
    group = f"{config.PREFIX}_writers_poison_{'after' if handling != 'none' else 'before'}_{datetime.now():%H%M%S}"
    args = ["kafka_agents/writer.py", "--mode", "fast", "--group", group, "--poison-handling", handling]
    drafts_start, dlq_start = topic_end(config.TOPIC_DRAFTS), topic_end(config.TOPIC_DEAD_LETTER)

    w = Proc("writer", [*args, "--instance", "writer", "--from", "latest"])
    if not w.wait_for("ready:", 60):
        raise SystemExit("writer did not start")
    warm = str(uuid.uuid4())
    send_raw(config.TOPIC_TASKS, [(KEY, to_bytes(task_message(warm, "Warm-up: what is renter's insurance?")))])
    w.wait_for("committed offset", 30)

    good = [str(uuid.uuid4()), str(uuid.uuid4())]
    batch = [("poison: not JSON", b'{"correlation_id": "not closed...')]
    if handling != "none":
        batch.append(("poison: no plan", to_bytes({"correlation_id": str(uuid.uuid4()), "question": "no plan"})))
    batch += [(f"good {i}", to_bytes(task_message(c, f"Good task {i}"))) for i, c in enumerate(good, 1)]
    metas = send_raw(config.TOPIC_TASKS, [(KEY, value) for _, value in batch])
    for (what, _), m in zip(batch, metas):
        print(f"  sent {what:17} partition={m['partition']} offset={m['offset']}")

    restarts = []
    if handling == "none":
        w.p.wait(timeout=60)
        w._t.join(timeout=5)
        print(f"  >>> writer exited with code {w.p.returncode}")
        r = Proc("writer*", [*args, "--instance", "writer-restarted"])
        r.p.wait(timeout=90)
        r._t.join(timeout=5)
        print(f"  >>> restarted writer exited with code {r.p.returncode} (same message again)")
        restarts.append(r)
    else:
        end = time.time() + 60
        while time.time() < end and not all(w.count(c) >= 2 for c in good):
            time.sleep(0.2)
        time.sleep(1)
        w.stop()

    offsets = group_offsets(group)
    print("  committed offsets at the end:")
    for row in offsets:
        print(f"    {row}")
    drafts = [d for d in read_since(config.TOPIC_DRAFTS, drafts_start) if isinstance(d["value"], dict)]
    good_done = sum(1 for c in good if any(d["value"].get("correlation_id") == c for d in drafts))
    dead = read_since(config.TOPIC_DEAD_LETTER, dlq_start)
    for d in dead:
        v = d["value"]
        print(
            f"  {config.TOPIC_DEAD_LETTER} offset={d['offset']}: error={v['error']!r} attempts={v['attempts']} "
            f"source={v['source']}"
        )
    attempts = [ln for ln in w.lines if "attempt " in ln or "FAILED" in ln]
    print(f"  -> good tasks processed after the poison: {good_done}/2, messages in dead-letter: {len(dead)}")
    return {
        "run": label,
        "poison_handling": handling,
        "max_retries": config.WRITER_MAX_RETRIES if handling != "none" else None,
        "group": group,
        "sent": metas,
        "writer_exit_codes": [w.p.returncode] + [r.p.returncode for r in restarts],
        "good_tasks_processed": good_done,
        "dead_letter": [d["value"] for d in dead],
        "retry_log": attempts,
        "offsets_end": offsets,
        "log": [ln for p in [w, *restarts] for ln in p.lines if ln[:4].isdigit() or "Error" in ln],
    }


def main() -> int:
    banner("Part 3C poison message (bounded retries + dead-letter topic)")
    rows = [run_case("before fix", "none"), run_case("after fix", "retry-dlq")]
    skip_test_messages()
    print("\n--- summary")
    for r in rows:
        print(
            f"  {r['run']:10} good tasks after the poison: {r['good_tasks_processed']}/2, "
            f"dead-letter messages: {len(r['dead_letter'])}, writer exit codes: {r['writer_exit_codes']}"
        )
    write_json(RAW / "poison_message.json", {"run_at": utc_now(), "runs": rows})
    ok = (
        rows[0]["good_tasks_processed"] == 0
        and rows[1]["good_tasks_processed"] == 2
        and len(rows[1]["dead_letter"]) == 2
    )
    print(f"poison blocked the queue before the fix and went to {config.TOPIC_DEAD_LETTER} after it: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    footer("Part 3C poison message")
    sys.exit(code)
