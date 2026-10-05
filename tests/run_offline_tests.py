#!/usr/bin/env python3
"""Part 4 (+ Part 5 III) offline test runner - plain asserts, no pytest.

Runs without MySQL, Ollama, TheMealDB, or an API key: the domain tools get an
in-memory repository fixture (dependency injection), the agent gets MockModel,
and every network socket is disabled for the whole run, so a test that tried
to reach a real service would fail instead of passing silently.

Usage (repo root):
    python tests/run_offline_tests.py
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in offline tests")


socket.socket.connect = _no_network  # type: ignore[method-assign]
socket.create_connection = _no_network  # type: ignore[assignment]

from hw5_common import banner  # noqa: E402

from domain_tools.agent import MockModel, run_agent  # noqa: E402
from domain_tools.contracts import REJECTED, SAFETY_ALLOWED, SAFETY_BLOCKED, VALID  # noqa: E402
from domain_tools.envelope import ENVELOPE_KEYS, is_envelope  # noqa: E402
from domain_tools.execute import execute_tool  # noqa: E402
from domain_tools.faults import FaultInjector, FaultyRepository, ScriptedInjector  # noqa: E402
from domain_tools.repository import InMemoryListingRepository  # noqa: E402
from domain_tools.retry import RetryPolicy  # noqa: E402
from domain_tools.safety import SAFETY_ERROR_PREFIX  # noqa: E402

FAST = RetryPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0, timeout_s=1.0)


def fixture_repo() -> InMemoryListingRepository:
    """Temporary fixture data shaped like s9486_rel (fresh copy per test)."""
    landlords = [
        {"id": 1, "full_name": "Ada Fixture", "company": "Test Rentals", "email": "ada@example.com"},
        {"id": 3, "full_name": "Tariq Fixture", "company": "Bay Test Homes", "email": "tariq@example.com"},
        {"id": 7, "full_name": "Nobody Owns", "company": "Empty Co", "email": "empty@example.com"},
    ]
    listings = [
        {"id": 1, "listing_code": "LST-00001", "title": "Studio near SJSU", "address": "1 San Carlos St, San Jose, CA", "available_units": 2, "landlord_id": 1},
        {"id": 2, "listing_code": "LST-00002", "title": "2BR Apartment with parking", "address": "2 Park Ave, Campbell, CA", "available_units": 1, "landlord_id": 3},
        {"id": 3, "listing_code": "LST-00003", "title": "Loft with balcony", "address": "3 Market St, Campbell, CA", "available_units": 4, "landlord_id": 3},
        {"id": 42, "listing_code": "LST-00042", "title": "1BR Condo pet friendly", "address": "42 Alameda, San Jose, CA", "available_units": 0, "landlord_id": 3},
    ]
    return InMemoryListingRepository(listings, landlords)


def call(name: str, inputs, repo=None, policy=FAST, attempts_log=None) -> dict:
    raw = execute_tool(name, inputs, repo=repo or fixture_repo(), policy=policy, attempts_log=attempts_log)
    assert isinstance(raw, str), "execute_tool must return a JSON string"
    result = json.loads(raw)
    assert is_envelope(result), f"not an {{ok, data, error}} envelope: {result}"
    return result


class SpyRepo:
    """Counts repository calls (to prove a blocked call never reaches storage)."""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def search(self, *a):
        self.calls += 1
        return self.inner.search(*a)

    def get_by_code(self, *a):
        self.calls += 1
        return self.inner.get_by_code(*a)

    def landlord_stats(self, *a):
        self.calls += 1
        return self.inner.landlord_stats(*a)


# ---------------------------------------------------------------- Part 4 tests

def test_search_listings_valid():
    r = call("search_listings", VALID["search_listings"])
    assert r["ok"] and r["error"] is None
    assert r["data"]["count"] == 2
    assert [l["listing_code"] for l in r["data"]["listings"]] == ["LST-00002", "LST-00003"]


def test_search_listings_rejected_input():
    inputs, expected, _ = REJECTED["search_listings"]
    r = call("search_listings", inputs)
    assert r["ok"] is False and r["data"] is None
    assert expected in r["error"], r["error"]


def test_get_listing_valid():
    r = call("get_listing", VALID["get_listing"])
    assert r["ok"] and r["data"]["listing_code"] == "LST-00042"
    assert r["data"]["landlord_name"] == "Tariq Fixture"


def test_get_listing_rejected_input():
    inputs, expected, _ = REJECTED["get_listing"]
    r = call("get_listing", inputs)
    assert r["ok"] is False and expected in r["error"], r["error"]


def test_landlord_portfolio_stats_valid():
    r = call("landlord_portfolio_stats", VALID["landlord_portfolio_stats"])
    d = r["data"]
    assert r["ok"] and d["listing_count"] == 3 and d["total_available_units"] == 5
    assert d["avg_units_per_listing"] == 1.67 and d["min_units"] == 0 and d["max_units"] == 4


def test_landlord_portfolio_stats_rejected_input():
    inputs, expected, _ = REJECTED["landlord_portfolio_stats"]
    r = call("landlord_portfolio_stats", inputs)
    assert r["ok"] is False and expected in r["error"], r["error"]


def test_not_found_is_clean_error():
    r1 = call("get_listing", {"listing_code": "LST-99999"})
    r2 = call("landlord_portfolio_stats", {"landlord_id": 999})
    assert not r1["ok"] and "No listing found" in r1["error"]
    assert not r2["ok"] and "No landlord found" in r2["error"]


def test_execute_tool_bad_name_and_inputs_do_not_crash():
    for name, inputs, expected in [
        ("drop_tables", {}, "Unknown tool"),
        (None, {}, "Unknown tool"),
        ("get_listing", "{not json", "must be a JSON object"),
        ("get_listing", ["LST-00001"], "must be a JSON object"),
        ("search_listings", {"query": "San Jose", "rent": 5}, "unexpected field"),
        ("landlord_portfolio_stats", {"landlord_id": True}, "must be an integer"),
    ]:
        r = call(name, inputs)
        assert r["ok"] is False and expected in r["error"], (name, inputs, r)
        assert tuple(r) == ENVELOPE_KEYS


def test_retry_first_attempt_success():
    log: list = []
    repo = FaultyRepository(fixture_repo(), ScriptedInjector([False]))
    r = call("get_listing", {"listing_code": "LST-00001"}, repo=repo, attempts_log=log)
    assert r["ok"] and len(log) == 1 and log[0]["outcome"] == "success"


def test_retry_fail_then_success():
    log: list = []
    repo = FaultyRepository(fixture_repo(), ScriptedInjector([True, False]))
    r = call("get_listing", {"listing_code": "LST-00001"}, repo=repo, attempts_log=log)
    assert r["ok"], r
    assert [a["outcome"] for a in log] == ["transient_failure", "success"]


def test_retry_exhausted_returns_clean_error():
    log: list = []
    repo = FaultyRepository(fixture_repo(), ScriptedInjector([True, True, True, True]))
    r = call("landlord_portfolio_stats", {"landlord_id": 3}, repo=repo, attempts_log=log)
    assert r["ok"] is False and "failed after 3 attempts" in r["error"], r
    assert len(log) == 3


def test_backoff_delays_are_bounded_exponential():
    p = RetryPolicy(max_attempts=5, base_delay_s=0.05, max_delay_s=0.4, timeout_s=1.0)
    assert [p.delay_before(n) for n in range(1, 6)] == [0.0, 0.05, 0.1, 0.2, 0.4]


def test_fault_injection_is_reproducible():
    def decisions(seed):
        inj = FaultInjector(0.5, seed)
        out = []
        for _ in range(30):
            try:
                inj.check()
                out.append(False)
            except Exception:
                out.append(True)
        return out

    assert decisions(269486) == decisions(269486)
    assert decisions(269486) != decisions(1)


# ---------------------------------------------------------------- Part 5 tests

def test_safety_rule_blocks_violating_call():
    spy = SpyRepo(fixture_repo())
    name, inputs = SAFETY_BLOCKED
    r = call(name, inputs, repo=spy)
    assert r == {"ok": False, "data": None, "error": r["error"]}
    assert r["error"].startswith(SAFETY_ERROR_PREFIX) and "familial status" in r["error"]
    assert spy.calls == 0, "a blocked call must never reach storage"
    name, inputs = SAFETY_ALLOWED
    assert call(name, inputs, repo=spy)["ok"], "the allowed search must still work"


def test_run_agent_mock_model_stops_at_max_steps():
    repo = fixture_repo()

    def executor(name, inputs):
        return execute_tool(name, inputs, repo=repo, policy=FAST)

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "agent_runs.jsonl"
        summary = run_agent("keep searching forever", model=MockModel(), max_steps=3,
                            executor=executor, log_path=log_path)
        events = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert summary["stop_reason"] == "max_steps", summary
    assert summary["steps"] == 3 and summary["tool_calls"] == 3
    assert [e["event"] for e in events].count("step") == 3
    assert [e["event"] for e in events].count("tool_call") == 3
    assert events[-1]["event"] == "stop" and events[-1]["stop_reason"] == "max_steps"


def test_agent_rejects_fabricated_tool_result():
    replies = [
        {"content": '{"ok": true, "data": {"listing_count": 999}, "error": null}', "tool_calls": []},
        {"content": "", "tool_calls": [{"name": "landlord_portfolio_stats", "arguments": {"landlord_id": 3}}]},
        {"content": "Landlord 3 manages 3 listings.", "tool_calls": []},
    ]
    repo = fixture_repo()
    summary = run_agent("how many listings for landlord 3?", model=MockModel(replies), max_steps=5,
                        executor=lambda n, i: execute_tool(n, i, repo=repo, policy=FAST), log_path=None)
    assert summary["stop_reason"] == "completed" and summary["steps"] == 3 and summary["tool_calls"] == 1, summary
    assert summary["final_answer"] == "Landlord 3 manages 3 listings."


TESTS = [
    test_search_listings_valid,
    test_search_listings_rejected_input,
    test_get_listing_valid,
    test_get_listing_rejected_input,
    test_landlord_portfolio_stats_valid,
    test_landlord_portfolio_stats_rejected_input,
    test_not_found_is_clean_error,
    test_execute_tool_bad_name_and_inputs_do_not_crash,
    test_retry_first_attempt_success,
    test_retry_fail_then_success,
    test_retry_exhausted_returns_clean_error,
    test_backoff_delays_are_bounded_exponential,
    test_fault_injection_is_reproducible,
    test_safety_rule_blocks_violating_call,
    test_run_agent_mock_model_stops_at_max_steps,
    test_agent_rejects_fabricated_tool_result,
]


def main() -> int:
    banner("Part 4 + 5 offline tests (no DB, no LLM, no network)")
    passed = 0
    for i, test in enumerate(TESTS, 1):
        try:
            test()
            passed += 1
            print(f"PASS  {i:2d}. {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {i:2d}. {test.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=2, file=sys.stdout)
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
