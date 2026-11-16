"""Turn spans.jsonl into per-trace journeys and the Part 4.3 stage-latency table (used by scripts and dashboard)."""

from __future__ import annotations

from collections import defaultdict

STAGE_ORDER = ["cache_lookup", "pipeline", "planner", "writer", "reviewer", "cache_store", "evaluation", "request"]


def by_trace(spans: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for s in spans:
        if s.get("trace_id"):
            out[s["trace_id"]].append(s)
    return out


def journey(spans: list[dict]) -> list[dict]:
    """Spans of one trace in stage order (time order, request last)."""
    return sorted(spans, key=lambda s: (s["stage"] == "request", s["start_ms"]))


def queue_wait_ms(trace: list[dict]) -> float | None:
    """inbox->planner + tasks->writer + drafts->reviewer (from the Kafka record timestamps) + final->ingress."""
    st = {s["stage"]: s for s in trace}
    if not all(k in st for k in ("planner", "writer", "reviewer", "pipeline")):
        return None
    waits = [st[k].get("queue_wait_ms") for k in ("planner", "writer", "reviewer")]
    if any(w is None for w in waits):
        return None
    final_hop = st["pipeline"].get("final_received_ms", st["pipeline"]["end_ms"]) - st["reviewer"]["end_ms"]
    return round(sum(waits) + max(final_hop, 0.0), 1)


def pct(values: list[float], q: float) -> float | None:
    """Percentile with linear interpolation (same as numpy's default)."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (k - lo), 1)


def stage_table(spans: list[dict], trace_ids: list[str]) -> dict:
    """p50/p95 per stage over the given (cache-miss) traces, and each stage's share of end-to-end latency."""
    traces = by_trace(spans)
    rows = {k: [] for k in ("Cache lookup", "Planner", "Writer", "Reviewer", "Queue wait (total)", "Evaluation")}
    e2e = []
    used = []
    for tid in trace_ids:
        st = {s["stage"]: s for s in traces.get(tid, [])}
        req = st.get("request")
        if not req or req.get("path") != "miss" or req["status"] != "ok":
            continue
        qw = queue_wait_ms(traces[tid])
        parts = {
            "Cache lookup": st.get("cache_lookup", {}).get("duration_ms"),
            "Planner": st.get("planner", {}).get("duration_ms"),
            "Writer": st.get("writer", {}).get("duration_ms"),
            "Reviewer": st.get("reviewer", {}).get("duration_ms"),
            "Queue wait (total)": qw,
            "Evaluation": st.get("evaluation", {}).get("duration_ms"),
        }
        if any(v is None for v in parts.values()):
            continue
        used.append(tid)
        e2e.append(req["duration_ms"])
        for k, v in parts.items():
            rows[k].append(v)
    total = sum(e2e)
    table = []
    for k, vals in rows.items():
        table.append(
            {
                "stage": k,
                "p50_ms": pct(vals, 0.5),
                "p95_ms": pct(vals, 0.95),
                "pct_of_e2e": round(100 * sum(vals) / total, 1) if total else None,
            }
        )
    covered = sum(r["pct_of_e2e"] or 0 for r in table)
    return {
        "n": len(used),
        "trace_ids": used,
        "rows": table,
        "e2e_p50_ms": pct(e2e, 0.5),
        "e2e_p95_ms": pct(e2e, 0.95),
        "other_pct": round(100 - covered, 1),
    }


def request_summary(spans: list[dict], since_ms: float | None = None) -> dict:
    reqs = [s for s in spans if s["stage"] == "request" and (since_ms is None or s["start_ms"] >= since_ms)]
    hits = [s for s in reqs if s.get("path") == "hit"]
    misses = [s for s in reqs if s.get("path") == "miss"]
    errors = [s for s in reqs if s["status"] != "ok"]
    ok_miss = [s["duration_ms"] for s in misses if s["status"] == "ok"]
    return {
        "requests": len(reqs),
        "hits": len(hits),
        "misses": len(misses),
        "hit_rate": round(len(hits) / len(reqs), 3) if reqs else None,
        "errors": len(errors),
        "error_rate": round(len(errors) / len(reqs), 3) if reqs else None,
        "hit_p50_ms": pct([s["duration_ms"] for s in hits], 0.5),
        "hit_p95_ms": pct([s["duration_ms"] for s in hits], 0.95),
        "miss_p50_ms": pct(ok_miss, 0.5),
        "miss_p95_ms": pct(ok_miss, 0.95),
        "first": min((s["start"] for s in reqs), default=None),
        "last": max((s["end"] for s in reqs), default=None),
    }
