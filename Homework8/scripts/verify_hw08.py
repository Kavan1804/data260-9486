#!/usr/bin/env python3
"""HW8 smoke test. Writes reports/hw08/verification.json.

Checks behavior, not wording: the three containers are up, Kafka is reachable and every s9486_ topic exists
(s9486_tasks with 2 partitions), CREATE_LISTING -> GET_LISTING round-trips through Kafka with the same
correlation_id, unknown operation / unknown id / bad fields give clean errors, the FastAPI wrapper on 8486 works,
one question goes inbox -> tasks -> drafts -> final with the real model, a replayed CREATE makes no second
listing, a poison task ends up in s9486_dead_letter and the next task still runs, the ordering files exist and
the keyed run kept order, the offline tests and Ruff pass, and the report files exist.

It sends test messages and starts agent processes in their own consumer groups; at the end the normal Part 2
groups are moved past those messages. It never edits application code.
Usage (repo root, `make kafka-up` and Ollama running):  make verify-hw08
After the final commit and `git tag hw8`, re-run so commit_hash is the tagged commit.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime

import httpx
from hw8_common import (
    BASE_URL,
    RAW,
    REPORT_DIR,
    ROOT,
    Proc,
    banner,
    footer,
    kafka_cli,
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
from kafka_service.common import to_bytes
from kafka_service.rpc import KafkaRPC

OUT = REPORT_DIR / "verification.json"
TOPICS = {
    config.TOPIC_REQUESTS: 1,
    config.TOPIC_RESPONSES: 1,
    config.TOPIC_INBOX: 1,
    config.TOPIC_TASKS: 2,
    config.TOPIC_DRAFTS: 1,
    config.TOPIC_FINAL: 1,
    config.TOPIC_DEAD_LETTER: 1,
}
LISTING = {
    "title": "Verify studio",
    "address": "1 Washington Sq, San Jose, CA",
    "listing_code": "LST-26948",
    "available_units": 1,
    "landlord_id": 6,
}
FILES = [
    "docker-compose.yml",
    "Dockerfile",
    "scripts/kafka_create_topics.sh",
    "kafka_service/worker.py",
    "kafka_service/rpc.py",
    "kafka_service/messages.py",
    "backend/app/routers/kafka_listings.py",
    "kafka_agents/base.py",
    "kafka_agents/planner.py",
    "kafka_agents/writer.py",
    "kafka_agents/reviewer.py",
    "kafka_agents/send_question.py",
    "Homework8/homework_demo.py",
    "reports/hw08/RUN_LOG.txt",
    "reports/hw08/METRICS.md",
    "reports/hw08/AI_USE.md",
]
RAW_FILES = [
    "part1_demo_kafka.json",
    "part1_demo_api.json",
    "part1_error_cases.json",
    "pipeline_journey.json",
    "final_message.json",
    "duplicate_replay.json",
    "consumer_death.json",
    "poison_message.json",
    "ordering_messages.json",
    "ordering_unkeyed.csv",
    "ordering_keyed.csv",
    "ordering_summary.json",
]

checks: list[dict] = []


def check(name: str, passed: bool, detail="") -> bool:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}", flush=True)
    return bool(passed)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


async def rpc_checks() -> None:
    rpc = KafkaRPC(name="verify", quiet=True)
    await rpc.start()
    try:
        created = await rpc.request(messages.CREATE, LISTING)
        c = created.response
        check("create_listing_ok", c.get("success") is True and c.get("message") == "Listing created", c)
        listing_id = c.get("listing_id")
        try:
            uuid.UUID(str(listing_id))
            is_uuid = True
        except ValueError:
            is_uuid = False
        check("listing_id_present", is_uuid, f"listing_id={listing_id}")

        got = await rpc.request(messages.GET, {"listing_id": listing_id})
        g = got.response
        same = g.get("success") is True and g.get("listing", {}).get("listing_id") == listing_id
        same = same and all(g["listing"].get(k) == v for k, v in LISTING.items())
        check("get_listing_ok", same, g)
        check(
            "correlation_id_preserved",
            c.get("correlation_id") == created.request["correlation_id"]
            and g.get("correlation_id") == got.request["correlation_id"],
            f"create {created.request['correlation_id']} -> {c.get('correlation_id')}; "
            f"get {got.request['correlation_id']} -> {g.get('correlation_id')}",
        )

        bad = await rpc.request("DELETE_LISTING", {"listing_id": listing_id})
        r = bad.response
        check(
            "unknown_operation_error",
            r.get("success") is False and r.get("error") and r.get("correlation_id") == bad.request["correlation_id"],
            r,
        )
        missing = (await rpc.request(messages.GET, {"listing_id": str(uuid.uuid4())})).response
        check("unknown_listing_id_error", missing.get("success") is False and bool(missing.get("error")), missing)
        invalid = (await rpc.request(messages.CREATE, {**LISTING, "title": ""})).response
        check(
            "invalid_fields_rejected", invalid.get("success") is False and "title" in invalid.get("error", ""), invalid
        )

        # Part 3A on the running worker: the same bytes twice must not create a second listing.
        req = messages.build_request(messages.CREATE, {**LISTING, "listing_code": "LST-26949"})
        start = await asyncio.to_thread(topic_end, config.TOPIC_RESPONSES)
        await asyncio.to_thread(send_raw, config.TOPIC_REQUESTS, [(None, to_bytes(req))] * 2)
        await asyncio.sleep(3)
        replies = [
            x["value"]
            for x in await asyncio.to_thread(read_since, config.TOPIC_RESPONSES, start)
            if x["value"].get("correlation_id") == req["correlation_id"]
        ]
        ids = {x.get("listing_id") for x in replies}
        check(
            "duplicate_no_side_effect",
            len(replies) == 2 and len(ids) == 1,
            f"{len(replies)} responses for one correlation_id, {len(ids)} distinct listing_id",
        )
    finally:
        await rpc.stop()


def pipeline_check(stamp: str) -> None:
    agents = [
        Proc(n, [f"kafka_agents/{n}.py", "--group", f"{config.PREFIX}_{n}s_verify_{stamp}"], echo=False)
        for n in ("planner", "writer", "reviewer")
    ]
    try:
        ready = all(a.wait_for("ready:", 60) for a in agents)
        sender = Proc(
            "send",
            ["kafka_agents/send_question.py", "--timeout", "400", "--no-save", "What is a security deposit?"],
            echo=False,
        )
        sender.p.wait(timeout=420)
        sender._t.join(timeout=5)
    finally:
        for a in agents:
            a.stop()
    text = "\n".join(sender.lines)
    start = text.find("{")
    final = json.loads(text[start:]) if ready and sender.p.returncode == 0 and start >= 0 else {}
    sent = next((ln for ln in sender.lines if "sent question" in ln), "")
    stages = [t.get("agent") for t in final.get("trace", [])]
    check(
        "pipeline_reaches_final",
        bool(final.get("status")) and bool(final.get("answer")) and final.get("correlation_id", "-") in sent,
        f"status={final.get('status')} stages={stages} correlation_id={final.get('correlation_id')}",
    )


def poison_check(stamp: str) -> None:
    group = f"{config.PREFIX}_writers_verify_poison_{stamp}"
    w = Proc("writer", ["kafka_agents/writer.py", "--mode", "fast", "--group", group, "--from", "latest"], echo=False)
    try:
        w.wait_for("ready:", 60)
        dlq, drafts = topic_end(config.TOPIC_DEAD_LETTER), topic_end(config.TOPIC_DRAFTS)
        good = str(uuid.uuid4())
        metas = send_raw(
            config.TOPIC_TASKS, [(b"verify", b"{not json"), (b"verify", to_bytes(task_message(good, "q")))]
        )
        w.wait_for(f"sent to topic={config.TOPIC_DRAFTS}", 30)
        time.sleep(1)
    finally:
        w.stop()
    dead = [d["value"] for d in read_since(config.TOPIC_DEAD_LETTER, dlq)]
    hit = [d for d in dead if d.get("source", {}).get("offset") == metas[0]["offset"]]
    after = any(d["value"].get("correlation_id") == good for d in read_since(config.TOPIC_DRAFTS, drafts))
    check(
        "poison_reaches_dead_letter",
        bool(hit) and hit[0].get("attempts") == config.WRITER_MAX_RETRIES and after,
        f"dead-letter entries={len(hit)} attempts={hit[0].get('attempts') if hit else None}, next task done={after}",
    )


def main() -> int:
    banner("HW8 verification (smoke test)")
    stamp = datetime.now().strftime("%H%M%S")
    check(
        "config_values",
        (config.SID4, config.PORT_BASE, config.PREFIX, config.SEED, config.VERIFY_SEED, config.DOMAIN_ID)
        == (9486, 8486, "s9486", 9486, 269486, 6),
        f"PORT_BASE={config.PORT_BASE} PREFIX={config.PREFIX} DOMAIN_ID={config.DOMAIN_ID}",
    )
    names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    want = ["s9486_kafka", "s9486_worker", "s9486_api"]
    check("docker_containers_running", all(n in names for n in want), f"running: {[n for n in want if n in names]}")

    try:
        topic_end(config.TOPIC_REQUESTS)
        check("kafka_reachable", True, config.KAFKA_BOOTSTRAP)
    except Exception as exc:  # noqa: BLE001
        check("kafka_reachable", False, f"{type(exc).__name__}: {exc}")
        return finish()
    described = kafka_cli("kafka-topics.sh", "--describe")
    found = {}
    for line in described.splitlines():
        parts = line.split()
        if line.startswith("Topic:") and "PartitionCount:" in parts:
            found[parts[1]] = int(parts[parts.index("PartitionCount:") + 1])
    check("topics_created", all(found.get(t) == n for t, n in TOPICS.items()), {t: found.get(t) for t in TOPICS})

    asyncio.run(rpc_checks())

    try:
        cid = str(uuid.uuid4())
        r = httpx.post(f"{BASE_URL}/api/kafka/listings", json={"correlation_id": cid, "data": LISTING}, timeout=20)
        body = r.json()
        check(
            "fastapi_wrapper_8486",
            r.status_code == 201 and body.get("correlation_id") == cid,
            f"HTTP {r.status_code}, correlation_id echoed={body.get('correlation_id') == cid}",
        )
    except httpx.HTTPError as exc:
        check("fastapi_wrapper_8486", False, f"{type(exc).__name__}: {exc}")

    pipeline_check(stamp)
    poison_check(stamp)
    skip_test_messages()

    missing = [
        f
        for f in ["ordering_messages.json", "ordering_unkeyed.csv", "ordering_keyed.csv", "ordering_summary.json"]
        if not (RAW / f).exists()
    ]
    keyed = {}
    if not missing:
        keyed = json.loads((RAW / "ordering_summary.json").read_text())["runs"]["keyed"]
    check(
        "ordering_files_exist",
        not missing and keyed.get("listings_split_across_partitions") == 0 and keyed.get("listings_out_of_order") == 0,
        f"missing={missing}, keyed run: split={keyed.get('listings_split_across_partitions')} "
        f"out_of_order={keyed.get('listings_out_of_order')}",
    )

    t = subprocess.run([sys.executable, "Homework8/tests/run_hw8_tests.py"], cwd=ROOT, capture_output=True, text=True)
    check("offline_tests_pass", t.returncode == 0, (t.stdout.strip().splitlines() or ["no output"])[-1])
    lint = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
    check("ruff_clean", lint.returncode == 0, lint.stdout.strip().splitlines()[-1] if lint.stdout else "")
    gone = [f for f in FILES if not (ROOT / f).exists()] + [f"raw/{f}" for f in RAW_FILES if not (RAW / f).exists()]
    check(
        "evidence_files_exist", not gone, f"missing: {gone}" if gone else f"{len(FILES)} files + {len(RAW_FILES)} raw"
    )
    return finish()


def finish() -> int:
    passed = sum(c["passed"] for c in checks)
    data = {
        "homework": "HW8",
        "sid4": config.SID4,
        "port_base": config.PORT_BASE,
        "prefix": config.PREFIX,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "domain_id": config.DOMAIN_ID,
        "commit_hash": git("rev-parse", "HEAD"),
        "tag_hw8": git("rev-parse", "-q", "--verify", "refs/tags/hw8^{commit}") or None,
        "working_tree_clean": git("status", "--porcelain") == "",
        "run_at": utc_now(),
        "model": {
            "name": config.OLLAMA_MODEL,
            "server": config.OLLAMA_URL,
            "num_ctx": config.AGENT_NUM_CTX,
            "temperature": 0.2,
            "seed": config.SEED,
            "used_by": "planner, writer, reviewer (pipeline_reaches_final); other checks use fast mode or no model",
        },
        "kafka": {"bootstrap": config.KAFKA_BOOTSTRAP, "image": "apache/kafka:3.9.2 (KRaft)", "topics": TOPICS},
        "writer_max_retries": config.WRITER_MAX_RETRIES,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "all_passed": passed == len(checks),
    }
    write_json(OUT, data)
    print(f"\n{passed}/{len(checks)} checks passed -> {OUT.relative_to(ROOT)}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    code = main()
    footer("verification")
    sys.exit(code)
