#!/usr/bin/env python3
"""HW8 test runner - plain asserts, no pytest (same style as the HW5-HW7 runners).

Offline only: no Kafka, no Ollama, no MySQL. Every socket is disabled, so a test that tried to reach a real
service would fail. The Kafka behavior itself is checked live by verify_hw08.py and the Part 3 scripts.

Covers: the request/response schema, the worker's CREATE/GET/error paths and its idempotency switch, the agents'
fast-mode steps, the shared agent loop (retries, dead-letter, duplicate skip, crash mode) with fake Kafka
objects, and the VERIFY_SEED ordering messages.

Usage (repo root):  python Homework8/tests/run_hw8_tests.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts", ROOT / "Homework8" / "scripts"):
    sys.path.insert(0, str(p))
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://test:test@localhost:3306/s9486_rel")


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in offline tests")


socket.socket.connect = _no_network  # type: ignore[method-assign]
socket.create_connection = _no_network  # type: ignore[assignment]

from failure_ordering import make_messages  # noqa: E402
from hw5_common import banner  # noqa: E402

import config  # noqa: E402
from kafka_agents.base import parse_args, peek_correlation_id  # noqa: E402
from kafka_agents.planner import Planner  # noqa: E402
from kafka_agents.reviewer import Reviewer  # noqa: E402
from kafka_agents.writer import Writer  # noqa: E402
from kafka_service import messages  # noqa: E402
from kafka_service.common import to_bytes  # noqa: E402
from kafka_service.worker import ListingWorker  # noqa: E402

# The worker and agents log every step; keep the test output to PASS/FAIL lines.
for _mod in ("kafka_service.worker", "kafka_agents.base", "kafka_agents.writer"):
    sys.modules[_mod].log = lambda *_a, **_k: None

LISTING = {
    "title": "Test 1BR",
    "address": "1 Test St, San Jose, CA",
    "listing_code": "lst-12345",
    "available_units": 2,
    "landlord_id": 6,
}


def req(op: str, data, cid: str | None = None) -> bytes:
    return to_bytes(messages.build_request(op, data, cid))


# ---------- Part 1: schema and worker ----------


def test_config_topics():
    assert (config.SID4, config.PORT_BASE, config.PREFIX) == (9486, 8486, "s9486")
    assert (config.SEED, config.VERIFY_SEED, config.DOMAIN_ID) == (9486, 269486, 6)
    assert config.TOPIC_REQUESTS == "s9486_entity_requests" and config.TOPIC_RESPONSES == "s9486_entity_responses"
    topics = [config.TOPIC_INBOX, config.TOPIC_TASKS, config.TOPIC_DRAFTS, config.TOPIC_FINAL, config.TOPIC_DEAD_LETTER]
    assert topics == ["s9486_inbox", "s9486_tasks", "s9486_drafts", "s9486_final", "s9486_dead_letter"]


def test_request_schema():
    r = messages.build_request(messages.CREATE, LISTING)
    assert list(r) == ["correlation_id", "reply_to", "operation", "data"]
    assert r["reply_to"] == config.TOPIC_RESPONSES and r["operation"] == "CREATE_LISTING"
    uuid.UUID(r["correlation_id"])
    assert messages.build_request(messages.GET, {}, "fixed-id")["correlation_id"] == "fixed-id"


def test_create_then_get():
    w = ListingWorker()
    topic, created = w.process(req(messages.CREATE, LISTING, "c1"))
    assert topic == config.TOPIC_RESPONSES
    assert created["success"] is True and created["correlation_id"] == "c1" and created["message"] == "Listing created"
    uuid.UUID(created["listing_id"])
    _, got = w.process(req(messages.GET, {"listing_id": created["listing_id"]}, "c2"))
    assert got["success"] is True and got["correlation_id"] == "c2"
    assert got["listing"]["listing_code"] == "LST-12345"  # same normalisation as the REST API
    assert got["listing"]["listing_id"] == created["listing_id"]


def test_validation_errors():
    w = ListingWorker()
    bad = [
        {k: v for k, v in LISTING.items() if k != "address"},
        {**LISTING, "title": "  "},
        {**LISTING, "listing_code": "LST-1"},
        {**LISTING, "landlord_id": 0},
        {**LISTING, "available_units": 501},
        {**LISTING, "extra": 1},
        "not an object",
    ]
    for i, data in enumerate(bad):
        _, out = w.process(req(messages.CREATE, data, f"bad-{i}"))
        assert out["success"] is False and out["correlation_id"] == f"bad-{i}" and out["error"], out
    assert w.store == {}


def test_unknown_operation_and_id():
    w = ListingWorker()
    _, out = w.process(req("DELETE_LISTING", {}, "u1"))
    assert out == {"correlation_id": "u1", "success": False, "error": "Unknown operation"}
    _, out = w.process(req(messages.GET, {"listing_id": str(uuid.uuid4())}, "u2"))
    assert out == {"correlation_id": "u2", "success": False, "error": "Listing not found"}
    _, out = w.process(req(messages.GET, {}, "u3"))
    assert out["success"] is False and out["correlation_id"] == "u3"


def test_bad_envelopes():
    w = ListingWorker()
    topic, out = w.process(b"not json")
    assert topic == config.TOPIC_RESPONSES and out["success"] is False and out["correlation_id"] is None
    _, out = w.process(to_bytes({"correlation_id": "e1", "operation": messages.CREATE, "data": LISTING}))
    assert out["success"] is False and "reply_to" in out["error"] and out["correlation_id"] == "e1"
    _, out = w.process(to_bytes({**messages.build_request(messages.CREATE, LISTING, "e2"), "reply_to": "other"}))
    assert out["success"] is False and out["correlation_id"] == "e2"


def test_worker_idempotency_switch():
    raw = req(messages.CREATE, LISTING, "dup")
    off = ListingWorker(idempotent=False)
    a, b = off.process(raw)[1], off.process(raw)[1]
    assert a["listing_id"] != b["listing_id"] and len(off.store) == 2  # before fix: two listings
    on = ListingWorker(idempotent=True)
    a, b = on.process(raw)[1], on.process(raw)[1]
    assert a == b and len(on.store) == 1  # after fix: same response, one listing
    # Same correlation_id but a different operation is a different request (homework_demo.py does this).
    got = on.process(req(messages.GET, {"listing_id": a["listing_id"]}, "dup"))[1]
    assert got["success"] is True and "listing" in got


# ---------- Part 2: agent steps in fast mode ----------


def agent(cls, *argv):
    return cls(parse_args(cls.name, ["--mode", "fast", *argv]))


def test_agent_steps_fast_mode():
    trace = [{"agent": "send_question"}]
    plan = agent(Planner).handle({"correlation_id": "p1", "question": "Q?", "trace": trace})
    assert plan["correlation_id"] == "p1" and plan["plan"] and plan["trace"] == trace
    draft = agent(Writer).handle(plan)
    assert draft["correlation_id"] == "p1" and draft["draft"] and draft["plan"] == plan["plan"]
    final = agent(Reviewer).handle(draft)
    assert final["correlation_id"] == "p1" and final["status"] == "approved" and final["answer"] == draft["draft"]
    assert set(final) >= {"correlation_id", "status", "answer", "review"}
    json.dumps(final)


def test_agent_steps_reject_bad_input():
    for cls, msg in [
        (Planner, {"correlation_id": "x"}),
        (Writer, {"correlation_id": "x", "question": "q"}),
        (Writer, {"correlation_id": "x", "question": "q", "plan": "not a list"}),
        (Reviewer, {"correlation_id": "x", "question": "q"}),
    ]:
        try:
            agent(cls).handle(msg)
        except ValueError:
            continue
        raise AssertionError(f"{cls.name} accepted {msg}")


def test_peek_correlation_id():
    assert peek_correlation_id(b'{"correlation_id": "abc"}') == "abc"
    assert peek_correlation_id(b"{broken") is None and peek_correlation_id(None) is None


# ---------- Part 3: the shared loop with fake Kafka objects ----------


class FakeProducer:
    def __init__(self):
        self.sent = []

    async def send_and_wait(self, topic, value, key=None):
        self.sent.append((topic, json.loads(value)))
        return SimpleNamespace(topic=topic, partition=0, offset=len(self.sent) - 1)


class FakeConsumer:
    def __init__(self):
        self.commits = []

    async def commit(self, offsets):
        self.commits.append({tp.partition: off for tp, off in offsets.items()})


def record(value: bytes, offset: int = 0):
    return SimpleNamespace(topic=config.TOPIC_TASKS, partition=1, offset=offset, key=b"k", value=value)


def run_records(w, values):
    prod, cons = FakeProducer(), FakeConsumer()

    async def go():
        for i, v in enumerate(values):
            await w.one_record(record(v, i), cons, prod)

    asyncio.run(go())
    return prod, cons


def task(cid):
    return to_bytes({"correlation_id": cid, "question": "q", "plan": ["a"]})


def test_loop_commits_after_send_and_skips_duplicates():
    w = agent(Writer)
    prod, cons = run_records(w, [task("t1"), task("t1")])
    assert [t for t, _ in prod.sent] == [config.TOPIC_DRAFTS]  # the replay made no second draft
    assert cons.commits == [{1: 1}, {1: 2}]  # both offsets committed, each after it was handled
    w2 = agent(Writer, "--no-idempotency")
    prod, _ = run_records(w2, [task("t1"), task("t1")])
    assert len(prod.sent) == 2


def test_loop_retries_then_dead_letter():
    w = agent(Writer, "--max-retries", "2")
    import kafka_agents.base as base

    real_sleep = base.asyncio.sleep
    base.asyncio.sleep = lambda *_: real_sleep(0)  # no back-off wait in tests
    try:
        prod, cons = run_records(w, [b"{oops", task("good")])
    finally:
        base.asyncio.sleep = real_sleep
    assert [t for t, _ in prod.sent] == [config.TOPIC_DEAD_LETTER, config.TOPIC_DRAFTS]
    dead = prod.sent[0][1]
    assert dead["attempts"] == 2 and dead["source"]["offset"] == 0 and "JSONDecodeError" in dead["error"]
    assert cons.commits == [{1: 1}, {1: 2}]  # poison committed after the DLQ write, so it does not block


def test_loop_crash_mode_does_not_commit():
    w = agent(Writer, "--poison-handling", "none")
    prod, cons = FakeProducer(), FakeConsumer()
    try:
        asyncio.run(w.one_record(record(b"{oops"), cons, prod))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("expected the writer to exit")
    assert prod.sent == [] and cons.commits == []


def test_auto_commit_mode_has_no_manual_commit():
    w = agent(Writer, "--commit", "auto")
    _, cons = run_records(w, [task("a1")])
    assert cons.commits == []


def test_commit_failure_after_rebalance_does_not_crash():
    from aiokafka.errors import CommitFailedError

    class RebalancedConsumer(FakeConsumer):
        async def commit(self, offsets):
            raise CommitFailedError("group rebalanced")

    w = agent(Writer)
    prod = FakeProducer()
    asyncio.run(w.one_record(record(task("r1")), RebalancedConsumer(), prod))  # must not raise
    assert len(prod.sent) == 1 and "r1" in w.done  # a redelivery of r1 would now be skipped
    prod2, cons2 = run_records(w, [task("r1")])
    assert prod2.sent == [] and cons2.commits == [{1: 1}]


# ---------- Part 3D: VERIFY_SEED messages ----------


def test_ordering_messages_from_verify_seed():
    a, b = make_messages(config.VERIFY_SEED), make_messages(config.VERIFY_SEED)
    assert a == b and len(a) == 20  # same seed, same 20 messages
    by_listing = {}
    for m in a:
        by_listing.setdefault(m["test"]["entity"], []).append(m["test"]["seq"])
    assert len(by_listing) == 4 and all(seqs == [1, 2, 3, 4, 5] for seqs in by_listing.values())
    assert len({m["correlation_id"] for m in a}) == 20


TESTS = [
    test_config_topics,
    test_request_schema,
    test_create_then_get,
    test_validation_errors,
    test_unknown_operation_and_id,
    test_bad_envelopes,
    test_worker_idempotency_switch,
    test_agent_steps_fast_mode,
    test_agent_steps_reject_bad_input,
    test_peek_correlation_id,
    test_loop_commits_after_send_and_skips_duplicates,
    test_loop_retries_then_dead_letter,
    test_loop_crash_mode_does_not_commit,
    test_auto_commit_mode_has_no_manual_commit,
    test_commit_failure_after_rebalance_does_not_crash,
    test_ordering_messages_from_verify_seed,
]


def main() -> int:
    banner("HW8 tests (offline: no Kafka, no LLM, no network)")
    passed = 0
    for i, test in enumerate(TESTS, 1):
        try:
            test()
            passed += 1
            print(f"PASS  {i:2d}. {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {i:2d}. {test.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3, file=sys.stdout)
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
