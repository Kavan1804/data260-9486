#!/usr/bin/env python3
"""HW10 automated checks (no model calls, no Kafka). Usage (repo root):  python Homework10/tests/run_hw10_tests.py"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw10 import analysis, evaluator  # noqa: E402
from hw10.common import DATA, PREFIX, ROOT, STUDENT  # noqa: E402
from hw10.judge import JUDGE_SETTINGS, to_1_5  # noqa: E402
from kafka_agents import tracing  # noqa: E402


def span(tid, stage, start, dur, **kw):
    return {
        "trace_id": tid,
        "stage": stage,
        "start_ms": start,
        "end_ms": start + dur,
        "duration_ms": dur,
        "start": "2026-11-15T00:00:00+00:00",
        "end": "2026-11-15T00:00:01+00:00",
        "status": "ok",
        **kw,
    }


def fake_trace(tid="t1"):
    return [
        span(tid, "cache_lookup", 0, 50, cache="miss"),
        span(tid, "pipeline", 100, 3000, final_received_ms=3100),
        span(tid, "planner", 110, 900, queue_wait_ms=10),
        span(tid, "writer", 1020, 1500, queue_wait_ms=20),
        span(tid, "reviewer", 2550, 500, queue_wait_ms=30),
        span(tid, "evaluation", 3200, 1000),
        span(tid, "request", 0, 4200, path="miss"),
    ]


# ---------------------------------------------------------------- tracing
def test_span_has_required_fields_and_goes_to_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spans.jsonl"
        os.environ["TRACE_SPANS_FILE"] = str(path)
        try:
            tracing.write_span("abc", "writer", 1.0, 2.5, "error", "boom", queue_wait_ms=5)
        finally:
            del os.environ["TRACE_SPANS_FILE"]
        s = json.loads(path.read_text())
    assert {"trace_id", "stage", "start", "end", "status", "error"} <= set(s)
    assert s["duration_ms"] == 1500.0 and s["status"] == "error" and s["error"] == "boom"


def test_no_span_file_when_tracing_is_off():
    os.environ.pop("TRACE_SPANS_FILE", None)
    with tempfile.TemporaryDirectory() as d:
        tracing.write_span("abc", "planner", 1.0, 2.0)
        assert list(Path(d).iterdir()) == []


def test_agent_loop_uses_correlation_id_as_trace_id():
    src = (ROOT / "kafka_agents" / "base.py").read_text()
    assert "write_span(cid, self.name" in src  # the agent span's trace_id is the message's correlation_id
    ingress = (ROOT / "Homework10" / "hw10" / "traced_ingress.py").read_text()
    assert "correlation_id=trace_id" in ingress and ingress.count("uuid.uuid4()") == 1


# ---------------------------------------------------------------- analysis
def test_queue_wait_sums_three_hops_and_final_delivery():
    # 10 + 20 + 30 on the topics + (3100 final received - 3050 reviewer end) = 110
    assert analysis.queue_wait_ms(fake_trace()) == 110.0


def test_percentiles():
    assert analysis.pct([1, 2, 3, 4], 0.5) == 2.5
    assert abs(analysis.pct(list(range(1, 101)), 0.95) - 95.05) <= 0.06  # numpy gives 95.05; pct rounds to 0.1
    assert analysis.pct([], 0.5) is None


def test_stage_table_and_share_of_end_to_end():
    t = analysis.stage_table(fake_trace(), ["t1"])
    rows = {r["stage"]: r for r in t["rows"]}
    assert t["n"] == 1 and rows["Writer"]["p50_ms"] == 1500
    assert rows["Writer"]["pct_of_e2e"] == round(100 * 1500 / 4200, 1)


def test_hits_and_errors_are_counted_separately():
    spans = fake_trace() + [
        span("t2", "request", 5000, 300, path="hit"),
        {**span("t3", "request", 6000, 9000, path="miss"), "status": "error"},
    ]
    s = analysis.request_summary(spans)
    assert (s["requests"], s["hits"], s["misses"], s["errors"]) == (3, 1, 2, 1)
    assert s["hit_p50_ms"] == 300 and s["miss_p50_ms"] == 4200  # the failed miss is not in the latency


# ---------------------------------------------------------------- evaluator / judge
def test_missing_message_gives_error_not_crash():
    res = evaluator.evaluate("t9", {"plan": None, "draft": None, "final": None})
    assert res["status"] == "error" and "missing plan, draft, final" in res["error"]


def test_slow_judge_is_bounded():
    import hw10.evaluator as ev

    def msg(**kw):
        return {"message": {"correlation_id": "t", "question": "q", **kw}, "kafka": {}}

    real = ev.score
    ev.score = lambda *a, **k: time.sleep(5)
    try:
        t = time.time()
        res = ev.evaluate(
            "t",
            {"plan": msg(plan=["a"]), "draft": msg(draft="d"), "final": msg(answer="d")},
            judge=object(),
            deadline_s=0.5,
        )
    finally:
        ev.score = real
    assert res["status"] == "error" and "did not finish" in res["error"] and time.time() - t < 3


def test_improvement_interpretation_does_not_force_a_positive_result():
    same = evaluator.interpret(4, 4, True, {})
    assert "cannot be better than the draft" in same
    assert "noise" in evaluator.interpret(4, 5, True, {})
    assert "worse" in evaluator.interpret(4, 3, False, {})


def test_score_scale_is_1_to_5():
    assert [to_1_5(x) for x in (0.0, 0.25, 0.5, 0.75, 1.0)] == [1, 2, 3, 4, 5]
    assert JUDGE_SETTINGS["temperature"] == 0.0 and JUDGE_SETTINGS["timeout_s"] <= 120


def test_agreement_statistics():
    sys.path.insert(0, str(ROOT / "Homework10" / "scripts"))
    from judge_validation import agreement

    a = agreement([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert a["spearman"] == 1.0 and a["mean_abs_diff"] == 0
    b = agreement([1, 2, 3, 4, 5], [2, 2, 4, 4, 4])
    assert b["mean_abs_diff"] == 0.6


# ---------------------------------------------------------------- data
def test_eval_cases_are_20_writer_drafts():
    cases = json.loads((DATA / "eval_cases.json").read_text())["cases"]
    assert len(cases) == 20 and len({c["case_id"] for c in cases}) == 20
    assert all(c["draft"] and c["writer"]["mode"] == "llm" and c["trace_id"] for c in cases)
    assert not any("judge" in c or "label" in c for c in cases)


def test_human_labels_if_present_are_1_to_5():
    path = DATA / "human_labels.csv"
    if not path.exists():
        return
    rows = list(csv.DictReader(path.open()))
    assert all(r["human_helpfulness"] in {"1", "2", "3", "4", "5"} for r in rows)


def test_dashboard_pages_render():
    from streamlit.testing.v1 import AppTest

    for page in ("Summary", "Evaluation", "Trace lookup"):
        at = AppTest.from_file(str(ROOT / "Homework10" / "dashboard" / "app.py"), default_timeout=60)
        at.run()
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, (page, [e.value for e in at.exception])


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
    print(f"\n{len(tests) - failed}/{len(tests)} HW10 tests passed")
    print(f"===== {STUDENT} | SID4 9486 | {PREFIX} | HW10 | tests - done =====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
