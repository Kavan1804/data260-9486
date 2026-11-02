#!/usr/bin/env python3
"""HW8 Part 3A: duplicate delivery. The exact same message bytes (same correlation_id) are sent twice.

1. Part 1 worker (the real side effect is a new listing in its dict):
     before fix: worker restarted with WORKER_IDEMPOTENCY=off -> two different listing_ids, 2 listings stored
     after fix:  WORKER_IDEMPOTENCY=on -> the saved response is sent again, same listing_id, 1 listing stored
2. Writer (side effect = a draft on s9486_drafts):
     before fix: writer.py --no-idempotency -> two drafts;  after fix: writer.py -> one draft, duplicate skipped

Usage (repo root, `make kafka-up` first):  python Homework8/scripts/failure_duplicate.py
Writes reports/hw08/raw/duplicate_replay.json
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime

from hw8_common import (
    RAW,
    ROOT,
    Proc,
    banner,
    docker_logs,
    footer,
    read_since,
    send_raw,
    skip_test_messages,
    task_message,
    topic_end,
    utc_now,
    write_json,
)

import config
from kafka_service import messages
from kafka_service.common import stamp, to_bytes
from kafka_service.rpc import KafkaRPC

LISTING = {
    "title": "Duplicate test 1BR",
    "address": "1 Replay Ave, San Jose, CA",
    "listing_code": "LST-94863",
    "available_units": 1,
    "landlord_id": 6,
}


def restart_worker(idempotency: str) -> None:
    since = utc_now()
    env = {**os.environ, "WORKER_IDEMPOTENCY": idempotency}
    subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", "--no-deps", "worker"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=True,
    )
    for _ in range(60):
        if docker_logs("s9486_worker", since, "Consumer is ready and listening"):
            break
        time.sleep(1)
    ready = docker_logs("s9486_worker", since, "idempotency=")
    print(f"  worker container recreated (empty dict): {ready[-1] if ready else '(no start line found)'}", flush=True)
    time.sleep(3)  # give the worker a moment to join its consumer group


async def get_listing(listing_id: str) -> dict:
    rpc = KafkaRPC(name="check", quiet=True)
    await rpc.start()
    try:
        return (await rpc.request(messages.GET, {"listing_id": listing_id})).response
    finally:
        await rpc.stop()


def worker_case(label: str, idempotency: str) -> dict:
    print(f"\n=== Worker, {label}: WORKER_IDEMPOTENCY={idempotency}", flush=True)
    restart_worker(idempotency)
    request = messages.build_request(messages.CREATE, LISTING)
    cid = request["correlation_id"]
    raw = to_bytes(request)
    start = topic_end(config.TOPIC_RESPONSES)
    since, since_ms = utc_now(), stamp()
    metas = send_raw(config.TOPIC_REQUESTS, [(cid.encode(), raw)])
    time.sleep(2)
    metas += send_raw(config.TOPIC_REQUESTS, [(cid.encode(), raw)])  # replay: same bytes, same correlation_id
    for m in metas:
        print(f"  sent CREATE_LISTING correlation_id={cid} to partition={m['partition']} offset={m['offset']}")
    time.sleep(3)

    responses = [
        r["value"] for r in read_since(config.TOPIC_RESPONSES, start) if r["value"].get("correlation_id") == cid
    ]
    ids = [r.get("listing_id") for r in responses]
    found = {i: asyncio.run(get_listing(i)).get("success") for i in sorted(set(filter(None, ids)))}
    lines = [ln for ln in docker_logs("s9486_worker", since) if ln[:23] >= since_ms and cid in ln]
    for ln in lines:
        print(f"  worker | {ln[:220]}")
    for r in responses:
        print(f"  response: success={r.get('success')} listing_id={r.get('listing_id')}")
    print(
        f"  -> {len(responses)} responses, {len(set(ids))} different listing_id(s), "
        f"{sum(found.values())} listing(s) exist for this one request"
    )
    return {
        "consumer": "Part 1 worker",
        "run": label,
        "idempotency": idempotency,
        "correlation_id": cid,
        "sent": metas,
        "responses": responses,
        "distinct_listing_ids": len(set(ids)),
        "listings_created": sum(found.values()),
        "worker_log": lines,
    }


def writer_case(label: str, idempotent: bool) -> dict:
    print(f"\n=== Writer, {label}: idempotency {'on' if idempotent else 'off'}", flush=True)
    group = f"{config.PREFIX}_writers_dup_{'after' if idempotent else 'before'}_{datetime.now():%H%M%S}"
    args = ["kafka_agents/writer.py", "--mode", "fast", "--group", group, "--instance", "writer", "--from", "latest"]
    w = Proc("writer", args + ([] if idempotent else ["--no-idempotency"]))
    try:
        if not w.wait_for("ready:", 60):
            raise SystemExit("writer did not start")
        cid = str(uuid.uuid4())
        raw = to_bytes(task_message(cid, "Is a security deposit refundable?"))
        start = topic_end(config.TOPIC_DRAFTS)
        send_raw(config.TOPIC_TASKS, [(cid.encode(), raw), (cid.encode(), raw)])  # same message twice
        print(f"  sent the same task twice, correlation_id={cid}")
        end = time.time() + 30
        while w.count("committed offset") < 2 and time.time() < end:  # both deliveries handled
            time.sleep(0.2)
    finally:
        w.stop()
    drafts = [r for r in read_since(config.TOPIC_DRAFTS, start) if r["value"].get("correlation_id") == cid]
    print(f"  -> drafts on {config.TOPIC_DRAFTS} for this correlation_id: {len(drafts)}")
    return {
        "consumer": "Writer agent",
        "run": label,
        "idempotency": "on" if idempotent else "off",
        "correlation_id": cid,
        "drafts_written": len(drafts),
        "writer_log": [ln for ln in w.lines if cid in ln or "committed" in ln],
    }


def main() -> int:
    banner("Part 3A duplicate delivery (replay the same correlation_id)")
    rows = [worker_case("before fix", "off"), worker_case("after fix", "on")]
    rows += [writer_case("before fix", False), writer_case("after fix", True)]
    skip_test_messages()

    print("\n--- summary")
    for r in rows:
        effect = (
            f"{r['listings_created']} listing(s) created"
            if "listings_created" in r
            else f"{r['drafts_written']} draft(s)"
        )
        print(f"  {r['consumer']:14} {r['run']:10} idempotency={r['idempotency']:3}  replay -> {effect}")
    write_json(RAW / "duplicate_replay.json", {"run_at": utc_now(), "runs": rows})
    ok = rows[0]["listings_created"] == 2 and rows[1]["listings_created"] == 1
    ok = ok and rows[2]["drafts_written"] == 2 and rows[3]["drafts_written"] == 1
    print(f"before fix made a second side effect and after fix did not: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    footer("Part 3A duplicate delivery")
    sys.exit(code)
