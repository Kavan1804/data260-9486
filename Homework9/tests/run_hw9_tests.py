#!/usr/bin/env python3
"""HW9 automated checks (no model calls, no MySQL writes). Needs the s9486_redis container for the Redis tests.

The model, the HW8 pipeline, the embedder and the database engine are replaced by small fakes, so these run in
a few seconds and give the same result every time. Redis tests use the s9486:test: namespace and clean it up.

Usage (repo root):  python Homework9/tests/run_hw9_tests.py      (or make test-hw9)
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from hw9 import agents, common  # noqa: E402
from hw9.common import DATA, PREFIX, delete_prefix, key, redis_client  # noqa: E402
from hw9.ingress import SemanticQA  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402
from hw9.semantic_cache import RedisSemanticCache  # noqa: E402

common.log = lambda *a, **k: None  # keep the test output to one line per test
for mod in ("hw9.ingress", "hw9.agents", "hw9.listing_store"):
    sys.modules[mod].log = common.log

R = redis_client()
TEST_LISTING_ID = 999_999  # no such listing row; the fake engine records the UPDATE instead


# ---------------------------------------------------------------- fakes
class FakeConn:
    def __init__(self, log):
        self.log = log

    def execute(self, stmt, params=None):
        self.log.append((str(stmt), dict(params or {})))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeEngine:
    def __init__(self):
        self.updates = []

    def begin(self):
        return FakeConn(self.updates)


class FakeStore:
    """get_listing/fingerprint like ListingDatabaseWithCache, with a version we can change."""

    def __init__(self):
        self.units = {"LST-00001": 1}

    def get_listing(self, code):
        if code not in self.units:
            return None
        return {
            "listing_code": code,
            "title": "Test Studio",
            "address": "1 Test St, San Jose, CA",
            "available_units": self.units[code],
            "landlord_name": "Ann Lee",
            "landlord_company": "Test Co",
            "id": 1,
            "landlord_id": 7,
        }

    def get_landlord(self, landlord_id):
        return {"landlord_id": landlord_id, "full_name": "Ann Lee", "company": "Test Co"}

    def fingerprint(self, code):
        return f"v{self.units.get(code)}"


def fake_embed(text: str) -> np.ndarray:
    """Same text -> same vector; texts sharing a 'topic' word are close, others far apart."""
    topics = ["units", "landlord", "deposit", "lease", "heater"]
    v = np.zeros(384, dtype=np.float32)
    for i, t in enumerate(topics):
        if t in text.lower():
            v[i] = 1.0
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    v[10 + h % 300] = 0.15  # small text-specific part: exact repeats score 1.0, paraphrases a bit lower
    if not v[:5].any():
        v[320 + h % 60] = 1.0
    return v / np.linalg.norm(v)


class CountingPipeline:
    def __init__(self):
        self.calls = 0

    def __call__(self, question):
        self.calls += 1
        return {"answer": f"answer #{self.calls}", "status": "approved", "correlation_id": f"c{self.calls}"}


def fresh_cache(threshold=0.85):
    c = RedisSemanticCache(R, "test", threshold)
    c.clear()
    return c


# ---------------------------------------------------------------- tests
def test_counter_increments_and_syncs_at_10_and_20():
    eng = FakeEngine()
    db = ListingDatabaseWithCache(redis=R, engine=eng)
    db.on_log = lambda msg: None
    R.delete(key("views", "listing", TEST_LISTING_ID))
    totals = [db.increment_listing_views(TEST_LISTING_ID) for _ in range(25)]
    assert totals == list(range(1, 26)), totals
    synced = [p["count"] for _, p in eng.updates]
    assert synced == [10, 20], synced
    assert all("UPDATE listings SET view_count" in s for s, _ in eng.updates)
    assert int(R.get(key("views", "listing", TEST_LISTING_ID))) == 25
    R.delete(key("views", "listing", TEST_LISTING_ID))


def test_counter_uses_redis_incr_on_prefixed_key():
    db = ListingDatabaseWithCache(redis=R, engine=FakeEngine())
    k = key("views", "listing", TEST_LISTING_ID)
    R.delete(k)
    db.increment_listing_views(TEST_LISTING_ID)
    assert k == f"{PREFIX}:views:listing:{TEST_LISTING_ID}" and int(R.get(k)) == 1
    R.delete(k)


def test_cache_miss_then_exact_hit_flags_and_similarity():
    pipe = CountingPipeline()
    qa = SemanticQA(fresh_cache(), FakeStore(), pipe, embedder=fake_embed)
    first = qa.ask("How many units are at LST-00001?")
    second = qa.ask("How many units are at LST-00001?")
    assert first["is_cached"] is False and second["is_cached"] is True
    assert second["similarity"] >= 0.9999 and isinstance(first["similarity"], float)
    assert second["answer"] == first["answer"] and "latency_ms" in second


def test_agent_pipeline_not_rerun_on_valid_hit():
    pipe = CountingPipeline()
    qa = SemanticQA(fresh_cache(), FakeStore(), pipe, embedder=fake_embed)
    qa.ask("What should I know about the security deposit?")
    for _ in range(3):
        assert qa.ask("What should I know about the security deposit?")["is_cached"]
    assert pipe.calls == 1, pipe.calls


def test_new_question_misses():
    pipe = CountingPipeline()
    qa = SemanticQA(fresh_cache(), FakeStore(), pipe, embedder=fake_embed)
    qa.ask("How do I ask about the heater?")
    out = qa.ask("Who is the landlord?")
    assert out["is_cached"] is False and out["similarity"] < 0.85 and pipe.calls == 2


def test_data_version_marker_stored_and_invalidation_refreshes():
    store, pipe = FakeStore(), CountingPipeline()
    cache = fresh_cache()
    qa = SemanticQA(cache, store, pipe, embedder=fake_embed)
    q = "How many units are at LST-00001?"
    first = qa.ask(q)
    assert cache.get(first["cache_key"])["data_version"] == "LST-00001@v1"
    store.units["LST-00001"] = 0  # the row changes
    stale = SemanticQA(cache, store, pipe, check_version=False, embedder=fake_embed).ask(q)
    assert stale["is_cached"] and stale["answer"] == "answer #1"  # stale hit without the check
    fresh = qa.ask(q)
    assert fresh["is_cached"] is False and fresh["answer"] == "answer #2" and fresh["data_version"] == "LST-00001@v0"
    assert cache.get(first["cache_key"]) == {}  # old entry deleted
    assert qa.ask(q)["is_cached"] is True and pipe.calls == 2


def test_every_redis_key_starts_with_prefix():
    qa = SemanticQA(fresh_cache(), FakeStore(), CountingPipeline(), embedder=fake_embed)
    qa.ask("units at LST-00001?")
    ListingDatabaseWithCache(redis=R, engine=FakeEngine()).increment_listing_views(TEST_LISTING_ID)
    keys = [k.decode() for k in R.scan_iter(match="*")]
    assert keys and all(k.startswith(PREFIX + ":") for k in keys), [k for k in keys if not k.startswith(PREFIX)]
    indexes = [i.decode() for i in R.execute_command("FT._LIST")]
    assert all(i.startswith(PREFIX + ":") for i in indexes), indexes
    R.delete(key("views", "listing", TEST_LISTING_ID))


def test_prefix_cleanup_refuses_other_keys():
    try:
        delete_prefix(R, "*")
    except ValueError:
        return
    raise AssertionError("delete_prefix('*') should refuse")


def test_hw9_source_has_no_unprefixed_redis_keys():
    """demo.py had 'user:..' keys and flushdb(); the HW9 copy must prefix keys and never flush."""
    demo = (common.HW9_DIR / "demo.py").read_text()
    assert "flushdb()" not in demo and 'f"user:' not in demo and 'f"users:city:' not in demo
    for p in (common.HW9_DIR / "hw9").glob("*.py"):
        src = p.read_text()
        assert ".flushall(" not in src and ".flushdb(" not in src and '"FLUSH' not in src.upper(), p.name


def test_max_two_attempts_enforced():
    class AlwaysWrong:
        def answer(self, question, lessons=None, feedback=None):
            return {"answer": "I am not sure.", "seconds": 0.0, "lessons_used": []}

    res = agents.run_question("tr01", "Who is the landlord?", AlwaysWrong(), agents.EvaluatorAgent(), max_attempts=5)
    assert res["attempts"] == 2 and res["final_result"] == "REVISE"


def test_revision_uses_feedback_and_passes():
    ref = json.loads((DATA / "reference_data.json").read_text())
    name = ref["listings"][ref["questions"]["tr01"]["listing_code"]]["landlord_name"]

    class LearnsFromFeedback:
        def answer(self, question, lessons=None, feedback=None):
            text = f"The landlord is {name}." if feedback and name in feedback["feedback"] else "No idea."
            return {"answer": text, "seconds": 0.0, "lessons_used": []}

    res = agents.run_question("tr01", "Who is the landlord?", LearnsFromFeedback(), agents.EvaluatorAgent())
    assert res["attempts"] == 2 and res["final_result"] == "PASS"
    assert res["history"][0]["evaluation"]["result"] == "REVISE" and res["history"][0]["evaluation"]["feedback"]


def test_evaluator_not_recorded_and_missing_listing():
    ev = agents.EvaluatorAgent()
    rent = next(k for k, v in ev.ref["questions"].items() if v["asks"] == ["rent"])
    assert ev.evaluate(rent, "The rent is about $2,400 per month.")["result"] == "REVISE"
    assert "unsupported_claim" in ev.evaluate(rent, "The rent is about $2,400 per month.")["tags"]
    assert ev.evaluate(rent, "The listing data does not include the monthly rent.")["result"] == "PASS"
    miss = next(k for k, v in ev.ref["questions"].items() if v["asks"] == ["missing"])
    assert ev.evaluate(miss, "No listing with that code exists in the database.")["result"] == "PASS"
    assert ev.evaluate(miss, "It is in San Jose.")["tags"] == ["invented_listing"]


def test_lessons_saved_and_reloaded_with_use_count():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.json"
        store = agents.LessonStore(path)
        lesson = store.create("missing_fact:landlord", {"landlord"}, ["tr01", "tr05"])
        assert set(agents.LessonStore(path).lessons[0]) >= {
            "lesson_id",
            "failure_pattern",
            "correction",
            "created_at",
            "use_count",
        }
        again = agents.LessonStore(path)
        rel = again.relevant("Which person manages listing LST-00001?", ("candidate",))
        assert [x["lesson_id"] for x in rel] == [lesson["lesson_id"]]
        assert again.relevant("What is the rent at LST-00001?", ("candidate",)) == []
        again.mark_used(rel)
        assert agents.LessonStore(path).lessons[0]["use_count"] == 1


def test_lessons_are_put_in_the_answer_prompt():
    seen = {}

    def fake_chat(messages, tools):
        seen["system"] = messages[0]["content"]
        return {"content": "ok", "tool_calls": []}

    a = agents.AnsweringAgent(FakeStore(), chat=fake_chat)
    a.answer("Who is the landlord of LST-00001?", [{"lesson_id": "lesson_001", "correction": "Give the full name."}])
    assert "Give the full name." in seen["system"]


def test_answering_agent_runs_the_landlord_tool():
    calls = []

    def fake_chat(messages, tools):
        calls.append(messages[-1])
        if len(calls) == 1:
            return {"content": "", "tool_calls": [{"name": "get_landlord", "arguments": {"landlord_id": 7}}]}
        return {"content": "The landlord is Ann Lee.", "tool_calls": []}

    out = agents.AnsweringAgent(FakeStore(), chat=fake_chat).answer("Who is the landlord of LST-00001?")
    assert out["answer"] == "The landlord is Ann Lee." and out["tools_called"][0]["result"]["full_name"] == "Ann Lee"
    assert calls[1]["role"] == "tool" and "Ann Lee" in calls[1]["content"]
    assert '"landlord_id": 7' in calls[0]["content"] and "Ann Lee" not in calls[0]["content"]  # record has only the id


def test_validation_gate_rejects_regression_and_keeps_improvement():
    p, f = {"result": "PASS", "tags": []}, {"result": "REVISE", "tags": ["missing_fact:units"]}
    bad = {"result": "REVISE", "tags": ["unsupported_claim"]}
    assert agents.gate_decision({"a": p, "b": f}, {"a": p, "b": p})["decision"] == "kept"
    assert agents.gate_decision({"a": p, "b": f}, {"a": p, "b": f})["decision"] == "kept"  # unchanged is ok
    regress = agents.gate_decision({"a": p, "b": f}, {"a": f, "b": p})
    assert regress["decision"] == "rejected" and regress["previously_correct_now_wrong"] == ["a"]
    assert agents.gate_decision({"a": f, "b": f}, {"a": p, "b": bad})["decision"] == "rejected"


def test_test_data_not_used_to_create_lessons():
    src = (common.HW9_DIR / "scripts" / "part4_train.py").read_text()
    code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("test_data" in ln for ln in code_lines if '"""' not in ln and "never opened" not in ln)
    lessons_file = DATA / "lessons.json"
    if lessons_file.exists():
        for lesson in json.loads(lessons_file.read_text()):
            assert all(s.startswith("tr") for s in lesson["source"]), lesson
    variants = (common.HW9_DIR / "scripts" / "part4_variants.py").read_text()
    assert "LessonStore(read_only=True)" in variants and ".create(" not in variants


def test_four_variants_run_independently():
    assert list(agents.VARIANTS) == ["baseline", "evaluator_repair", "lesson_memory", "validated_improvement"]
    assert agents.VARIANTS["baseline"] == (1, ())
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "lessons.json"
        s = agents.LessonStore(path)
        s.create("missing_fact:landlord", {"landlord"}, ["tr01", "tr05"])
        s.lessons[0]["status"] = "rejected"
        s.save()
        before = path.read_bytes()
        calls = {}
        for name, (attempts, statuses) in agents.VARIANTS.items():
            ro = agents.LessonStore(path, read_only=True)

            class Fake:
                def answer(self, question, lessons=None, feedback=None):
                    calls.setdefault(name, []).append([x["lesson_id"] for x in lessons or []])
                    return {"answer": "No idea.", "seconds": 0.0, "lessons_used": []}

            res = agents.run_question(
                "tr01", "Who is the landlord?", Fake(), agents.EvaluatorAgent(), attempts, ro, statuses
            )
            assert res["attempts"] == attempts
        assert path.read_bytes() == before  # read-only stores never write
        assert calls["lesson_memory"][0] == ["lesson_001"] and calls["validated_improvement"][0] == []


def test_input_datasets_have_no_answers():
    for name in ("training_data.json", "validation_data.json", "test_data.json"):
        rows = json.loads((DATA / name).read_text())
        assert rows and all(set(r) == {"id", "question"} for r in rows), name
    ref = json.loads((DATA / "reference_data.json").read_text())
    ids = {
        r["id"]
        for n in ("training_data.json", "validation_data.json", "test_data.json")
        for r in json.loads((DATA / n).read_text())
    }
    assert ids == set(ref["questions"])


def test_cache_cases_has_40_labeled_cases():
    spec = yaml.safe_load((DATA / "cache_cases.yaml").read_text())
    cases = spec["cases"]
    assert len(spec["seeds"]) == 10 and len(cases) == 40
    for cat, label in (
        ("exact", "should_hit"),
        ("paraphrase", "should_hit"),
        ("similar", "should_miss"),
        ("unrelated", "should_miss"),
    ):
        group = [c for c in cases if c["category"] == cat]
        assert len(group) == 10 and all(c["label"] == label for c in group), cat
    seeds = {s["id"]: s["query"] for s in spec["seeds"]}
    assert all(c["query"] == seeds[c["matches"]] for c in cases if c["category"] == "exact")


def main() -> int:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc(limit=3, file=sys.stdout)
    RedisSemanticCache(R, "test").clear()
    R.ft(key("idx", "test")).dropindex()
    print(f"\n{len(tests) - failed}/{len(tests)} HW9 tests passed")
    print(f"===== {common.STUDENT} | SID4 9486 | {PREFIX} | HW9 | tests - done =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
