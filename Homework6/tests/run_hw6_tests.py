#!/usr/bin/env python3
"""HW6 test runner - plain asserts, no pytest (same style as tests/run_offline_tests.py).

Default (offline): no MongoDB, Ollama, MySQL or network. Chat memory runs on
InMemoryMemoryStore + FakeModel + HashEmbedder, and every socket is disabled so a
test that tried to reach a real service fails instead of passing silently.

--live: also runs the MongoDB tests through FastAPI's TestClient against the
throwaway database s9486_doc_test (dropped at the end). Needs MongoDB at
MONGODB_URI; the model is still FakeModel, so Ollama is not needed.

Both modes point CHAT_USAGE_LOG and MEMORY_MD at temp files, so the real
reports/hw06/raw/chat_usage.jsonl and MEMORY.md are never touched.

Usage (repo root):
    python Homework6/tests/run_hw6_tests.py
    python Homework6/tests/run_hw6_tests.py --live
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIVE = "--live" in sys.argv
_TMP = Path(tempfile.mkdtemp(prefix="hw6_tests_"))
os.environ["CHAT_USAGE_LOG"] = str(_TMP / "chat_usage.jsonl")
os.environ["MEMORY_MD"] = str(_TMP / "MEMORY.md")

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts", ROOT / "Homework6" / "scripts"):
    sys.path.insert(0, str(p))


def _no_network(*_args, **_kwargs):
    raise RuntimeError("network access is disabled in offline tests")


if not LIVE:
    socket.socket.connect = _no_network  # type: ignore[method-assign]
    socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import config  # noqa: E402
from backend.app import file_memory, memory_logic  # noqa: E402
from backend.app.doc_schema import PROPERTY_TYPES, STATUSES, ListingDocCreate, ListingDocUpdate  # noqa: E402
from backend.app.mongo import EPISODES, LISTINGS, MESSAGES, SUMMARIES, VALIDATORS  # noqa: E402
from backend.app.routers.listing_docs import to_object_id  # noqa: E402
from hw5_common import banner  # noqa: E402

FIXTURE_55 = ROOT / "Homework6" / "fixtures" / "MEMORY_original_55.md"
VALID_DOC = {"title": "Sunny studio near SJSU", "description": "Walk to campus", "status": "available",
             "property_type": "studio", "available_from": "2026-12-01T09:00:00Z"}


class FakeModel:
    """Stand-in for domain_tools.agent.OllamaModel: same chat() signature, canned replies."""

    name = "FakeModel"

    def __init__(self):
        self.calls: list[str] = []

    def chat(self, messages: list[dict], tools: list[dict], fmt: str | None = None) -> dict:
        system, last = messages[0]["content"], messages[-1]["content"]
        self.calls.append(system[:20])
        usage = {"tool_calls": [], "prompt_tokens": 40, "completion_tokens": 8}
        if system.startswith("Extract"):
            facts = [] if last.rstrip().endswith("?") else [{"fact": last[:80], "importance": 0.8}]
            return {"content": json.dumps({"facts": facts}), **usage}
        if system.startswith("Update the running summary"):
            return {"content": "- user is looking for a rental", **usage}
        if system.startswith("Condense"):
            return {"content": "- lifetime: user rents in the Bay Area", **usage}
        if system.startswith("From the conversation"):
            return {"content": json.dumps({"facts": [{"key": "user.city", "fact": "Wants to live in Santa Clara",
                                                      "source": "user"}]}), **usage}
        return {"content": f"fake reply to: {last[:40]}", "tool_calls": [],
                "prompt_tokens": len(json.dumps(messages)) // 4, "completion_tokens": 7}


def expect_invalid(model, data: dict) -> str:
    try:
        model(**data)
    except ValidationError as exc:
        return str(exc)
    raise AssertionError(f"expected a validation error for {data}")


def run_chat(store, model, messages: list[str], user="u1", session="s1", **kw) -> list[dict]:
    return [memory_logic.chat_turn(store, model, memory_logic.HashEmbedder(), user, m, session_id=session,
                                   log_path=None, **kw) for m in messages]


# ---------- configuration ----------

def test_config_values():
    assert (config.SID4, config.PORT_BASE, config.PREFIX, config.SEED, config.VERIFY_SEED, config.DOMAIN_ID) == \
        (9486, 8486, "s9486", 9486, 269486, 6)
    assert config.PORT_BASE == 8000 + config.SID4 % 900 and config.DOMAIN_ID == config.SID4 % 8
    assert config.MONGODB_DB == "s9486_doc" and config.MONGODB_URI.startswith("mongodb://")
    assert config.OLLAMA_MODEL and not config.OLLAMA_MODEL.startswith("<")


def test_placeholder_env_values_are_ignored():
    os.environ["HW6_TEST_VALUE"] = "<I_MUST_PROVIDE_MODEL_NAME>"
    assert config._env_value("HW6_TEST_VALUE") is None
    os.environ["HW6_TEST_VALUE"] = " real-value "
    assert config._env_value("HW6_TEST_VALUE") == "real-value"
    del os.environ["HW6_TEST_VALUE"]


# ---------- Part 1 schemas + MongoDB validators ----------

def test_mongo_validators_match_pydantic_rules():
    listing = VALIDATORS[LISTINGS]
    assert set(listing["required"]) >= {"title", "status", "property_type", "available_from", "created_at", "updated_at"}
    assert listing["properties"]["title"]["maxLength"] == 100
    assert listing["properties"]["status"]["enum"] == list(STATUSES)
    assert listing["properties"]["property_type"]["enum"] == list(PROPERTY_TYPES)
    assert set(VALIDATORS[MESSAGES]["required"]) == {"user_id", "session_id", "role", "content", "created_at"}
    assert set(VALIDATORS[SUMMARIES]["required"]) == {"user_id", "session_id", "scope", "text", "created_at"}
    assert set(VALIDATORS[EPISODES]["required"]) == {"user_id", "session_id", "fact", "importance", "embedding",
                                                    "created_at"}
    assert VALIDATORS[EPISODES]["properties"]["importance"]["maximum"] == 1


def test_listing_schema_valid_and_default_status():
    doc = ListingDocCreate(**{k: v for k, v in VALID_DOC.items() if k != "status"})
    assert doc.status == "available" and doc.available_from.year == 2026


def test_listing_schema_missing_required_field():
    msg = expect_invalid(ListingDocCreate, {k: v for k, v in VALID_DOC.items() if k != "title"})
    assert "title" in msg and "Field required" in msg


def test_listing_schema_invalid_enum():
    msg = expect_invalid(ListingDocCreate, {**VALID_DOC, "property_type": "castle"})
    assert "property_type" in msg


def test_listing_schema_invalid_date():
    msg = expect_invalid(ListingDocCreate, {**VALID_DOC, "available_from": "2026-13-45"})
    assert "available_from" in msg


def test_listing_schema_title_longer_than_100():
    msg = expect_invalid(ListingDocCreate, {**VALID_DOC, "title": "x" * 101})
    assert "at most 100 characters" in msg


def test_listing_schema_wrong_type():
    msg = expect_invalid(ListingDocCreate, {**VALID_DOC, "title": 12345})
    assert "title" in msg


def test_listing_update_rules():
    assert ListingDocUpdate(status="rented").model_dump(exclude_unset=True) == {"status": "rented"}
    assert ListingDocUpdate().model_dump(exclude_unset=True) == {}
    assert ListingDocUpdate(description=None).model_dump(exclude_unset=True) == {"description": None}
    expect_invalid(ListingDocUpdate, {"title": None})
    expect_invalid(ListingDocUpdate, {"unknown": 1})


def test_malformed_object_id_is_400():
    try:
        to_object_id("not-an-object-id")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected HTTPException 400")
    assert str(to_object_id("0123456789abcdef01234567")) == "0123456789abcdef01234567"


# ---------- Part 2 memory logic ----------

def test_hash_embedder_and_cosine():
    emb = memory_logic.HashEmbedder()
    a, b, c = emb.embed(["I have a dog named Biscuit", "my dog Biscuit", "budget is 2600 dollars"])
    assert len(a) == memory_logic.EMBED_DIM and all(isinstance(x, float) for x in a)
    assert abs(memory_logic.cosine(a, a) - 1.0) < 1e-9
    assert memory_logic.cosine(a, b) > memory_logic.cosine(a, c)
    assert memory_logic.cosine([], a) == 0.0


def test_select_window_and_compress_policy():
    msgs = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i} " + "x" * 300} for i in range(20)]
    assert len(memory_logic.select_window(msgs, 4)) == 4
    assert memory_logic.select_window(msgs, 4)[-1]["content"].startswith("m19")
    comp = memory_logic.select_window(msgs, 12, "compress")
    keep = config.COMPRESS_KEEP_RECENT
    assert len(comp) == 12
    assert all(len(m["content"]) <= config.COMPRESS_MAX_CHARS + 4 for m in comp[:-keep])
    assert all(len(m["content"]) > 300 for m in comp[-keep:])
    assert len(msgs[0]["content"]) > 300  # the stored messages are not modified


def test_parse_facts_limits_and_clamps():
    raw = json.dumps({"facts": [{"fact": "Has a dog", "importance": 1.7}, {"fact": "has a dog", "importance": 0.2},
                                {"fact": "Budget $2,600", "importance": -1}, {"fact": "Likes parks"},
                                {"fact": "Fourth fact", "importance": 0.4}]})
    facts = memory_logic.parse_facts(raw)
    assert [f["fact"] for f in facts] == ["Has a dog", "Budget $2,600", "Likes parks"]
    assert facts[0]["importance"] == 1.0 and facts[1]["importance"] == 0.0 and facts[2]["importance"] == 0.5
    assert memory_logic.parse_facts("not json") == []


def test_build_prompt_contains_all_parts():
    window = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    msgs, parts = memory_logic.build_prompt("- session bullet", "- lifetime bullet", window, "now?",
                                            [{"fact": "Has a dog", "importance": 0.9}])
    system = msgs[0]["content"]
    assert msgs[0]["role"] == "system" and system.startswith(memory_logic.SYSTEM_PRIMER)
    assert "lifetime bullet" in system and "session bullet" in system and "- Has a dog" in system
    assert msgs[1:3] == window and msgs[-1] == {"role": "user", "content": "now?"}
    assert set(parts) == {"system_primer", "long_term_summary", "short_term_window", "episodic_facts", "current_message"}


def test_chat_turn_memory_flow():
    store, model = memory_logic.InMemoryMemoryStore(), FakeModel()
    texts = [f"Fact number {i}: I like feature {i}" for i in range(1, 11)]
    out = run_chat(store, model, texts, short_term_n=4)
    assert len(store.messages) == 20 and [m["role"] for m in store.messages[:2]] == ["user", "assistant"]
    assert out[0]["memory_used"]["short_term"]["count"] == 0
    assert out[-1]["memory_used"]["short_term"]["count"] == 4 and out[-1]["turn"] == 10
    assert [o["memory_written"]["session_summary_created"] for o in out].count(True) == 2  # turns 5 and 10
    assert out[4]["memory_written"]["session_summary_created"] and not out[4]["memory_written"]["lifetime_summary_created"]
    assert out[9]["memory_written"]["lifetime_summary_created"]  # 2nd session summary -> lifetime
    lifetime = store.latest_summary("u1", "user")
    assert lifetime["session_id"] is None and lifetime["scope"] == "user"
    assert out[5]["memory_used"]["session_summary"] == "- user is looking for a rental"
    assert len(store.episode_docs) == 10
    assert all(0 <= e["importance"] <= 1 and isinstance(e["embedding"][0], float) for e in store.episode_docs)


def test_episodic_retrieval_ranks_relevant_fact():
    store, model = memory_logic.InMemoryMemoryStore(), FakeModel()
    run_chat(store, model, ["I have a dog named Biscuit", "My budget is 2600 dollars", "I work in North San Jose"])
    out = run_chat(store, model, ["Is my dog Biscuit allowed?"])[0]
    facts = out["memory_used"]["episodic_facts"]
    assert facts and facts[0]["fact"] == "I have a dog named Biscuit"
    assert len(facts) <= config.EPISODIC_TOP_K and facts == sorted(facts, key=lambda f: f["score"], reverse=True)


def test_usage_row_has_part3_fields():
    store = memory_logic.InMemoryMemoryStore()
    log = _TMP / "usage_test.jsonl"
    memory_logic.chat_turn(store, FakeModel(), memory_logic.HashEmbedder(), "u2", "hello there", session_id="s",
                           short_term_n=4, policy="compress", phase="conversation", run_id="r1", log_path=log)
    row = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    for k in ("prompt_tokens", "completion_tokens", "system_primer_tokens_est", "long_term_summary_tokens_est",
              "short_term_window_tokens_est", "episodic_facts_tokens_est", "latency_ms", "short_term_n", "user_id",
              "session_id", "turn", "timestamp", "policy", "token_source"):
        assert k in row, k
    assert row["short_term_n"] == 4 and row["policy"] == "compress" and row["token_source"] == "ollama"
    assert memory_logic.approx_tokens("abcd" * 10) == 10


def test_aggregate_and_memory_reads_in_memory_store():
    store = memory_logic.InMemoryMemoryStore()
    run_chat(store, FakeModel(), ["one", "two", "three"], user="u3")
    days = store.daily_counts("u3")
    assert sum(d["messages"] for d in days) == 6 and days[0]["user_messages"] == 3
    assert len(store.user_messages("u3", 16)) == 6


# ---------- Part 4 file memory ----------

def test_file_memory_load_and_system_prompt():
    agent, mem = _TMP / "AGENT.md", _TMP / "MEMORY_load.md"
    agent.write_text("1. Use FastAPI.\n", encoding="utf-8")
    mem.write_text("## Facts\n- [user.city] San Jose (source: user)\n", encoding="utf-8")
    prompt = file_memory.build_system_prompt("BASE", file_memory.load_agent_md(agent), file_memory.load_memory_md(mem))
    assert prompt.startswith("BASE") and "Use FastAPI" in prompt and "San Jose" in prompt
    assert prompt.index("AGENT.md") < prompt.index("MEMORY.md")
    assert file_memory.load_memory_md(_TMP / "missing.md") == ""
    assert "## Project description" in file_memory.load_agent_md()  # the real root AGENT.md


def test_count_lines_and_needs_consolidation():
    now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    text = "# T\n<!-- comment -->\n<!--\nmulti\n-->\n\n- a\n- b\n"
    assert file_memory.count_memory_lines(text) == 3
    fresh = f"<!-- last_consolidated: {(now - timedelta(hours=2)).isoformat()} -->\n- a\n"
    stale = f"<!-- last_consolidated: {(now - timedelta(hours=25)).isoformat()} -->\n- a\n"
    assert file_memory.needs_consolidation(fresh, now) == (False, [])
    due, reasons = file_memory.needs_consolidation(stale, now)
    assert due and "25.0 h" in reasons[0]
    long_text = fresh + "".join(f"- fact {i}\n" for i in range(41))
    assert file_memory.needs_consolidation(long_text, now)[0]
    assert file_memory.needs_consolidation("- a\n", now)[1] == ["no recorded consolidation time"]
    assert file_memory.read_last_consolidated("<!-- last_consolidated: never -->") is None


def test_consolidation_of_55_line_fixture():
    original = FIXTURE_55.read_text(encoding="utf-8")
    assert len(original.splitlines()) == 55
    new_text, report = file_memory.consolidate(original, datetime(2026, 10, 18, tzinfo=timezone.utc))
    checks = file_memory.verify_consolidation(original, new_text, report)
    assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]
    assert len(new_text.splitlines()) < 40
    kept = {c["key"]: c["kept"] for c in report["contradictions_resolved"]}
    assert kept["user.budget"] == "Monthly budget is $2,800" and kept["user.city"] == "Wants listings in Santa Clara"
    flagged = {r["key"] for r in report["needs_review"]}
    assert flagged == {"user.bedrooms", "user.pets"}
    assert "merged: 3" in new_text  # project.domain appeared three times
    again, report2 = file_memory.consolidate(new_text)  # consolidating twice changes nothing material
    assert report2["after_facts"] == report["after_facts"] and not report2["contradictions_resolved"]


def test_memory_commands():
    path = _TMP / "MEMORY_cmd.md"
    path.write_text(FIXTURE_55.read_text(encoding="utf-8"), encoding="utf-8")
    help_out = file_memory.handle_command("/help")
    assert all(c in help_out["reply"] for c in ("/memory", "/compact", "/dream", "/help"))
    mem = file_memory.handle_command("/memory", path=path)
    assert mem["consolidation_due"] and mem["lines"] == 52
    comp = file_memory.handle_command("/compact", path=path)
    assert "before 55 lines" in comp["reply"] and comp["report"]["after_total_lines"] < 40
    dream = file_memory.handle_command("/dream", FakeModel(), [{"role": "user", "content": "I moved to Santa Clara"}],
                                       path=path)
    assert len(dream["added"]) == 1 and "Wants to live in Santa Clara" in path.read_text(encoding="utf-8")
    assert "## Resolved contradictions" in path.read_text(encoding="utf-8")  # other sections survive /dream
    again = file_memory.handle_command("/dream", FakeModel(), [{"role": "user", "content": "Santa Clara"}], path=path)
    assert again["added"] == []  # no duplicate append
    assert file_memory.is_command("/compact") and not file_memory.is_command("hello /compact")
    assert "Unknown" in file_memory.handle_command("/nope")["reply"]


def test_agent_md_instructions_and_function_rules():
    import agent_md_check

    summary = agent_md_check.agent_md_summary(config.AGENT_MD.read_text(encoding="utf-8"))
    assert summary["passed"] and len(summary["required_categories_covered"]) >= 3
    src = (ROOT / "backend" / "app" / "file_memory.py").read_text(encoding="utf-8")
    assert all(c["passed"] for c in agent_md_check.check_function(src, "count_memory_lines"))
    bad = 'import openai\ndef f(x):\n    print("http://localhost:8486")\n    return x\n'
    failed = {c["rule"] for c in agent_md_check.check_function(bad, "f") if not c["passed"]}
    assert failed == {"R6_type_hints", "R7_docstring", "R9_no_hardcoded_config", "R10_no_print",
                      "R13_no_banned_imports"}
    assert not agent_md_check.safe_to_run("import os\ndef f(): pass\n")[0]
    assert agent_md_check.safe_to_run("from datetime import date\ndef f(): pass\n")[0]


# ---------- Part 3 scoring + cost, verification ----------

def test_score_probe_rubric():
    import score_probes

    probe = {"criteria": [["2900"]], "stale": ["2600"]}
    assert score_probes.score_answer("Your budget is $2,900 per month.", probe)[0] == 5
    assert score_probes.score_answer("Your budget is $2,600.", probe)[0] == 2
    assert score_probes.score_answer("I don't know.", probe)[0] == 1
    three = {"criteria": [["a"], ["b"], ["c"]]}
    assert [score_probes.score_answer(t, three)[0] for t in ("a b c", "a b", "a", "z")] == [5, 4, 3, 1]


def test_cost_formula():
    import memory_cost

    # 1,000 input + 100 output tokens per turn: (1000*$1 + 100*$5)/1M = $0.0015/turn -> x30 x10,000 = $450
    assert round(memory_cost.cost_for(1000, 100), 2) == 450.0
    s = [{"setting": "a", "cost_with_upkeep": 10, "probe_mean": 4.0}, {"setting": "b", "cost_with_upkeep": 5,
                                                                        "probe_mean": 3.8},
         {"setting": "c", "cost_with_upkeep": 3, "probe_mean": 2.0}]
    best, worst, _ = memory_cost.pick_best_worst(s)
    assert best["setting"] == "b" and worst["setting"] == "a"


def test_verification_payload_shape():
    import verify_hw06

    payload = verify_hw06.build_payload([{"check": "x", "passed": True, "details": ""}])
    for k in ("homework", "sid4", "commit_hash", "seed", "verify_seed", "configuration", "checks", "summary",
              "generated_at"):
        assert k in payload, k
    assert payload["homework"] == "HW6" and payload["sid4"] == 9486 and payload["verify_seed"] == 269486
    assert payload["summary"] == {"passed": 1, "total": 1, "all_passed": True}


TESTS = [
    test_config_values,
    test_placeholder_env_values_are_ignored,
    test_mongo_validators_match_pydantic_rules,
    test_listing_schema_valid_and_default_status,
    test_listing_schema_missing_required_field,
    test_listing_schema_invalid_enum,
    test_listing_schema_invalid_date,
    test_listing_schema_title_longer_than_100,
    test_listing_schema_wrong_type,
    test_listing_update_rules,
    test_malformed_object_id_is_400,
    test_hash_embedder_and_cosine,
    test_select_window_and_compress_policy,
    test_parse_facts_limits_and_clamps,
    test_build_prompt_contains_all_parts,
    test_chat_turn_memory_flow,
    test_episodic_retrieval_ranks_relevant_fact,
    test_usage_row_has_part3_fields,
    test_aggregate_and_memory_reads_in_memory_store,
    test_file_memory_load_and_system_prompt,
    test_count_lines_and_needs_consolidation,
    test_consolidation_of_55_line_fixture,
    test_memory_commands,
    test_agent_md_instructions_and_function_rules,
    test_score_probe_rubric,
    test_cost_formula,
    test_verification_payload_shape,
]


# ---------- --live: MongoDB through FastAPI TestClient ----------

TEST_DB = f"{config.MONGODB_DB}_test"
_client = None


def live_client():
    """App with only the HW6 routers (no MySQL), the test database, FakeModel and HashEmbedder."""
    global _client
    if _client is None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from backend.app.mongo import get_db, mongo_db
        from backend.app.routers import listing_docs, memory

        app = FastAPI()
        app.include_router(listing_docs.router)
        app.include_router(memory.router)
        app.dependency_overrides[mongo_db] = lambda: get_db(TEST_DB)
        app.dependency_overrides[memory.get_chat_model] = FakeModel
        app.dependency_overrides[memory.get_embedder] = memory_logic.HashEmbedder
        _client = TestClient(app)
    return _client


def test_live_mongo_connection_and_validators():
    from backend.app.mongo import get_db

    db = get_db(TEST_DB)
    assert db.command("ping")["ok"] == 1
    infos = {c["name"]: c for c in db.list_collections()}
    for name in VALIDATORS:
        assert "$jsonSchema" in infos[name]["options"]["validator"], name


def test_live_crud_cycle():
    c = live_client()
    created = c.post("/api/listings", json=VALID_DOC)
    assert created.status_code == 201, created.text
    doc = created.json()
    assert doc["status"] == "available" and doc["created_at"] == doc["updated_at"]
    assert any(d["id"] == doc["id"] for d in c.get("/api/listings").json())
    assert c.get(f"/api/listings/{doc['id']}").json()["title"] == VALID_DOC["title"]
    upd = c.put(f"/api/listings/{doc['id']}", json={"status": "rented", "description": None})
    assert upd.status_code == 200 and upd.json()["status"] == "rented" and upd.json()["description"] is None
    assert upd.json()["updated_at"] >= doc["updated_at"]
    assert c.delete(f"/api/listings/{doc['id']}").status_code == 200
    assert c.get(f"/api/listings/{doc['id']}").status_code == 404


def test_live_validation_errors():
    c = live_client()
    cases = {
        "missing required field": ({k: v for k, v in VALID_DOC.items() if k != "available_from"}, 422),
        "invalid enum": ({**VALID_DOC, "status": "sold"}, 422),
        "invalid date": ({**VALID_DOC, "available_from": "next tuesday"}, 422),
        "title > 100": ({**VALID_DOC, "title": "t" * 101}, 422),
        "wrong type": ({**VALID_DOC, "title": 42}, 422),
    }
    for name, (body, code) in cases.items():
        r = c.post("/api/listings", json=body)
        assert r.status_code == code and r.json()["detail"], (name, r.status_code, r.text)
    assert c.get("/api/listings/123").status_code == 400
    assert c.put("/api/listings/123", json={"status": "rented"}).status_code == 400
    assert c.delete("/api/listings/123").status_code == 400
    missing = "0123456789abcdef01234567"
    assert c.get(f"/api/listings/{missing}").status_code == 404
    assert c.put(f"/api/listings/{missing}", json={"status": "rented"}).status_code == 404
    assert c.delete(f"/api/listings/{missing}").status_code == 404
    doc = c.post("/api/listings", json=VALID_DOC).json()
    assert c.put(f"/api/listings/{doc['id']}", json={}).status_code == 400
    c.delete(f"/api/listings/{doc['id']}")


def test_live_db_validator_rejects_bad_document():
    from pymongo.errors import WriteError

    from backend.app.mongo import get_db

    try:
        get_db(TEST_DB)[LISTINGS].insert_one({"title": "x" * 150, "status": "sold"})
    except WriteError as exc:
        assert exc.code == 121
    else:
        raise AssertionError("MongoDB accepted a document that breaks the $jsonSchema")


def test_live_chat_memory_endpoints():
    c = live_client()
    for i, m in enumerate(["I have a dog named Biscuit", "My budget is 2600", "I work downtown",
                           "I need parking", "I like quiet streets", "Is my dog Biscuit allowed?"], 1):
        r = c.post("/api/chat", json={"user_id": "live-user", "session_id": "live-s1", "message": m})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["turn"] == i and body["reply"].startswith("fake reply")
    assert body["memory_used"]["episodic_facts"][0]["fact"] == "I have a dog named Biscuit"
    assert body["memory_used"]["session_summary"]  # written at user message 5
    mem = c.get("/api/memory/live-user").json()
    assert len(mem["messages"]) == 12 and mem["latest_session_summary"]["scope"] == "session"
    assert mem["episodes"] and mem["episodes"][0]["embedding_dim"] == memory_logic.EMBED_DIM
    agg = c.get("/api/aggregate/live-user").json()
    assert sum(d["messages"] for d in agg["daily_message_counts"]) == 12 and agg["recent_summaries"]
    assert c.post("/api/chat", json={"user_id": "live-user", "message": "/help"}).json()["command"] == "/help"
    assert c.post("/api/chat", json={"user_id": "", "message": "hi"}).status_code == 422


LIVE_TESTS = [
    test_live_mongo_connection_and_validators,
    test_live_crud_cycle,
    test_live_validation_errors,
    test_live_db_validator_rejects_bad_document,
    test_live_chat_memory_endpoints,
]


def reset_test_db() -> None:
    from backend.app import mongo

    mongo.get_client().drop_database(TEST_DB)
    mongo._ready.discard(TEST_DB)  # so the next get_db(TEST_DB) recreates the validated collections


def main() -> int:
    banner(f"HW6 tests ({'offline + live MongoDB ' + TEST_DB if LIVE else 'offline: no DB, no LLM, no network'})")
    tests = TESTS + (LIVE_TESTS if LIVE else [])
    if LIVE:
        try:
            reset_test_db()
        except Exception as exc:  # noqa: BLE001
            print(f"MongoDB not reachable at {config.MONGODB_URI} ({type(exc).__name__}); start it first "
                  "(see Homework6/README_HW6.md).")
            return 1
    passed = 0
    for i, test in enumerate(tests, 1):
        try:
            test()
            passed += 1
            print(f"PASS  {i:2d}. {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {i:2d}. {test.__name__}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=2, file=sys.stdout)
    if LIVE:
        reset_test_db()
        print(f"(dropped test database {TEST_DB})")
    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
