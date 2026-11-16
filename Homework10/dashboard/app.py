"""HW10 Part 1: Streamlit operations dashboard for my HW8/HW9 system (Kavan Siddesh, s9486).

Run (repo root):  make dashboard      ->  http://localhost:8501
Data sources (all written by the logged runs, nothing typed in by hand):
  reports/hw10/raw/spans.jsonl              one JSON span per stage per request (trace_id = HW8 correlation_id)
  reports/hw10/raw/part2_evaluation.json    the end-to-end evaluated question (Part 2)
  reports/hw10/raw/latency_runs.json        the 50-miss experiment (+ judge scores per request)
  reports/hw10/raw/judge_validation.json    judge vs human labels, 3 runs (Part 3)
  reports/hw10/raw/trace_examples.json      the hit / miss / failed trace ids (Part 4.2)
  Redis s9486:hw10:*                        live count of cached answers
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "Homework9", ROOT / "Homework10"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from hw10.analysis import by_trace, journey, request_summary, stage_table  # noqa: E402

RAW = ROOT / "reports" / "hw10" / "raw"
METRICS = ROOT / "reports" / "hw10" / "METRICS.md"
LOCAL_TZ = "America/Los_Angeles"

st.set_page_config(page_title="s9486 operations", layout="wide")


# ---------------------------------------------------------------- data (cached)
@st.cache_data(ttl=30)
def load_spans() -> list[dict]:
    path = RAW / "spans.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


@st.cache_data(ttl=30)
def load_json(name: str):
    path = RAW / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@st.cache_resource
def redis_conn():
    """One Redis connection for the whole app session (expensive to open on every rerun)."""
    try:
        import redis

        r = redis.Redis.from_url("redis://localhost:6379/0")
        r.ping()
        return r
    except Exception:  # noqa: BLE001 - the dashboard still works from the files if Redis is down
        return None


def notes(heading: str) -> str:
    if not METRICS.exists():
        return ""
    text = METRICS.read_text(encoding="utf-8")
    if f"### {heading}" not in text:
        return ""
    a = text.index(f"### {heading}")
    b = text.find("\n### ", a + 4)
    return text[a : b if b > 0 else None].split("\n", 1)[1].strip()


def local(iso: str) -> str:
    return pd.Timestamp(iso).tz_convert(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ---------------------------------------------------------------- layout
st.sidebar.markdown("### Kavan Siddesh\nSID4 9486 · PREFIX `s9486`  \nDATA 260 · HW10")
page = st.sidebar.radio("Page", ["Summary", "Evaluation", "Trace lookup"])
st.sidebar.caption("Rental housing listings · HW8 Kafka pipeline + HW9 Redis semantic cache")
spans = load_spans()


def summary_page():
    st.title("Summary")
    window = st.selectbox("Time window", ["All logged HW10 requests", "Last 24 hours", "Last 2 hours"])
    since = None
    if window != "All logged HW10 requests":
        hours = 24 if window == "Last 24 hours" else 2
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000
    s = request_summary(spans, since)
    if not s["requests"]:
        st.warning("No requests in this window.")
        return
    st.caption(
        f"Source: `reports/hw10/raw/spans.jsonl`, `request` spans (one per request). Window: {window} - "
        f"requests from {local(s['first'])} to {local(s['last'])} ({LOCAL_TZ})."
    )
    c = st.columns(4)
    c[0].metric("Requests", s["requests"])
    c[1].metric("Cache hit rate", f"{s['hit_rate']:.1%}", help="hits / all requests (request span path)")
    c[2].metric("Error rate", f"{s['error_rate']:.1%}", help="request spans with status error / all requests")
    c[3].metric("Errors", s["errors"])
    c = st.columns(4)
    c[0].metric("Cache hits", s["hits"])
    c[1].metric("Cache misses", s["misses"])
    c[2].metric("Hit latency p50 / p95", f"{s['hit_p50_ms']:,.0f} / {s['hit_p95_ms']:,.0f} ms" if s["hits"] else "-")
    c[3].metric(
        "Miss end-to-end p50 / p95",
        f"{s['miss_p50_ms'] / 1000:,.1f} / {s['miss_p95_ms'] / 1000:,.1f} s" if s["miss_p50_ms"] else "-",
        help="successful misses: cache lookup + Kafka pipeline + cache store + evaluation",
    )
    st.caption(
        "Cache hits and misses are counted from the `cache_lookup` result of each trace; hit latency is kept "
        "separate from miss latency because a hit never runs the pipeline."
    )

    reqs = [x for x in spans if x["stage"] == "request" and (since is None or x["start_ms"] >= since)]
    df = pd.DataFrame(
        {
            "time": [local(x["start"]) for x in reqs],
            "path": [x.get("path") for x in reqs],
            "status": [x["status"] for x in reqs],
            "latency_s": [x["duration_ms"] / 1000 for x in reqs],
        }
    )
    left, right = st.columns(2)
    left.markdown("**Requests by path**")
    left.bar_chart(df.groupby(["path", "status"]).size().unstack(fill_value=0))
    right.markdown("**End-to-end latency per request (s)**")
    right.scatter_chart(df, x="time", y="latency_s", color="path")

    table = stage_table(spans, [x["trace_id"] for x in reqs])
    if table["n"]:
        st.markdown(f"**Stage latency over {table['n']} successful cache misses in this window**")
        st.dataframe(pd.DataFrame(table["rows"]), hide_index=True)
    r = redis_conn()
    if r is not None:
        st.caption(
            f"Live: {sum(1 for _ in r.scan_iter('s9486:hw10:entry:*'))} answers cached under `s9486:hw10:` "
            "(Redis, via st.cache_resource)."
        )


def evaluation_page():
    st.title("Evaluation")
    st.subheader("Part 2 - GEval scores by pipeline stage (judge: llama3.2:3b, 1-5)")
    rows = []
    for x in spans:
        if x["stage"] == "evaluation" and x["status"] == "ok" and x.get("scores"):
            rows.append({"trace_id": x["trace_id"], **x["scores"]})
    p2 = load_json("part2_evaluation.json")
    if p2 and (p2.get("evaluation") or {}).get("status") == "ok":
        ev = p2["evaluation"]
        imp = ev["improvement"]
        st.markdown(f"**End-to-end test question:** {p2['query']}  \n`trace_id` `{p2['trace_id']}`")
        c = st.columns(4)
        c[0].metric("Plan Quality", ev["plan_quality"]["score"])
        c[1].metric("Writer Helpfulness", ev["writer_helpfulness"]["score"])
        c[2].metric("Final Answer Helpfulness", ev["final_helpfulness"]["score"])
        c[3].metric("Final - Draft", f"{imp['difference']:+d}")
        st.markdown(
            f"- **Plan reason:** {ev['plan_quality']['reason']}\n"
            f"- **Writer reason:** {ev['writer_helpfulness']['reason']}\n"
            f"- **Final reason:** {ev['final_helpfulness']['reason']}\n"
            f"- **Final vs draft:** {imp['interpretation']}"
        )
        with st.expander("Plan, draft and final answer (joined by trace_id from s9486_tasks / drafts / final)"):
            st.write(ev["inputs"]["plan"])
            st.markdown(f"**Draft:** {ev['inputs']['draft']}")
            st.markdown(f"**Final:** {ev['inputs']['final_answer']}")
    if rows:
        df = pd.DataFrame(rows)
        st.markdown(f"**All evaluated requests ({len(df)}), mean score per stage**")
        means = df[["plan_quality", "writer_helpfulness", "final_helpfulness"]].mean().round(2)
        c = st.columns(3)
        c[0].metric("Planner (plan quality)", means["plan_quality"])
        c[1].metric("Writer (draft helpfulness)", means["writer_helpfulness"])
        c[2].metric("Reviewer output (final helpfulness)", means["final_helpfulness"])
        df["final_minus_draft"] = df["final_helpfulness"] - df["writer_helpfulness"]
        st.dataframe(df, hide_index=True, height=220)

    st.subheader("Part 3 - Is the judge reliable?")
    jv = load_json("judge_validation.json")
    if not jv:
        st.info("Judge validation has not run yet (needs the committed human labels).")
    else:
        a, rep = jv["agreement"]["run1"], jv["repeatability"]
        c = st.columns(4)
        c[0].metric("Spearman (judge run 1 vs human)", a["spearman"])
        c[1].metric("Mean |judge - human|", a["mean_abs_diff"])
        c[2].metric("Cases that changed across 3 runs", f"{rep['cases_with_any_change']}/{rep['cases']}")
        c[3].metric("Mean / max |change|", f"{rep['mean_abs_change']} / {rep['max_abs_change']}")
        st.dataframe(pd.DataFrame(jv["agreement"]).T, height=180)
        human = jv["human"]
        per = [
            {"case": i, "human": human[i], **{f"run{k + 1}": r[i]["score"] for k, r in enumerate(jv["runs"])}}
            for i in human
        ]
        st.dataframe(pd.DataFrame(per), hide_index=True, height=250)
    text = notes("Coordination")
    if text:
        st.subheader("What the scores say about Planner, Writer and Reviewer")
        st.markdown(text)


def trace_page():
    st.title("Trace lookup")
    ex = (load_json("trace_examples.json") or {}).get("traces", {})
    choice = st.radio("Example traces", ["(type your own)", *[f"{k}: {v}" for k, v in ex.items()]], horizontal=True)
    default = choice.split(": ", 1)[1] if ": " in choice else ""
    tid = st.text_input("trace_id", value=default).strip()
    if not tid:
        return
    trace = by_trace(spans).get(tid)
    if not trace:
        st.error("No spans with this trace_id in reports/hw10/raw/spans.jsonl")
        return
    j = journey(trace)
    lookup = next((x for x in j if x["stage"] == "cache_lookup"), {})
    req = next((x for x in j if x["stage"] == "request"), {})
    path = lookup.get("cache", "?").upper()
    if req.get("status") == "error":
        st.error(f"Cache {path} path - request FAILED: {req.get('error')}")
    elif path == "HIT":
        st.success(f"Cache HIT path - served from Redis (similarity {lookup.get('similarity')}), pipeline not run")
    else:
        st.info(
            f"Cache MISS path - cache lookup -> Kafka planner -> writer -> reviewer -> evaluation "
            f"(best similarity {lookup.get('similarity')})"
        )
    st.caption(f"Query: {lookup.get('query', '')}  ·  times in {LOCAL_TZ}  ·  source: spans.jsonl")
    rows = []
    for x in j:
        detail = {
            k: x[k]
            for k in ("cache", "similarity", "queue_wait_ms", "attempts", "dead_letter", "scores", "path")
            if x.get(k) is not None
        }
        rows.append(
            {
                "stage": x["stage"],
                "start": local(x["start"]),
                "end": local(x["end"]),
                "duration_ms": x["duration_ms"],
                "status": x["status"],
                "error": x.get("error") or "",
                "details": json.dumps(detail),
            }
        )
    df = pd.DataFrame(rows)

    def color(row):
        return ["background-color: #fde2e2" if row["status"] == "error" else ""] * len(row)

    st.dataframe(df.style.apply(color, axis=1), hide_index=True)
    st.markdown("**Stage durations (ms)**")
    st.bar_chart(df[df["stage"] != "request"].set_index("stage")["duration_ms"], horizontal=True)


{"Summary": summary_page, "Evaluation": evaluation_page, "Trace lookup": trace_page}[page]()
