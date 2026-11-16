#!/usr/bin/env python3
"""Fill the tables in reports/hw10/METRICS.md from reports/hw10/raw/ (no hand-typed numbers).

Usage (repo root):  python Homework10/scripts/build_metrics.py      (or make metrics-hw10)
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw10.analysis import by_trace, journey, request_summary  # noqa: E402
from hw10.common import RAW, REPORT_DIR, banner, footer, read_json, read_spans  # noqa: E402


def fill(marker: str, content: str) -> None:
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")


def part2() -> str:
    d = read_json(RAW / "part2_evaluation.json")
    ev = d["evaluation"]
    imp = ev["improvement"]
    rows = [
        "| Criterion | Score (1-5) | Saved with it |",
        "|---|---|---|",
        f"| Plan Quality | {ev['plan_quality']['score']} | reason: {ev['plan_quality']['reason']} |",
        f"| Writer Helpfulness | {ev['writer_helpfulness']['score']} | "
        f"trace_id `{ev['writer_helpfulness']['trace_id']}` |",
        f"| Final Answer Helpfulness | {ev['final_helpfulness']['score']} | "
        f"final answer: {' '.join(ev['final_helpfulness']['final_answer'].split())[:300]} |",
        f"| Final-vs-Draft Improvement | draft {imp['draft_score']}, final {imp['final_score']}, "
        f"difference {imp['difference']:+d} | {imp['interpretation']} |",
    ]
    head = (
        f"Question: {d['query']}  \ntrace_id: `{d['trace_id']}` - judge `{ev['judge']['model']}` (temperature "
        f"{ev['judge']['temperature']}, num_ctx {ev['judge']['num_ctx']}), evaluation took {ev['seconds']} s, "
        f"{ev['judge_calls']} judge calls. Final answer identical to the draft: {imp['final_equals_draft']}."
    )
    return head + "\n\n" + "\n".join(rows)


def stage_scores() -> str:
    runs = read_json(RAW / "latency_runs.json")["misses"]
    ok = [r for r in runs if r["scores"] and all(v is not None for v in r["scores"].values())]
    keys = [
        ("plan_quality", "Planner - Plan Quality"),
        ("writer_helpfulness", "Writer - Writer Helpfulness"),
        ("final_helpfulness", "Reviewer output - Final Answer Helpfulness"),
    ]
    lines = ["| Stage / criterion | Mean | Median | Min | Max | Scores 1/2/3/4/5 |", "|---|---|---|---|---|---|"]
    for k, label in keys:
        v = [r["scores"][k] for r in ok]
        dist = "/".join(str(v.count(i)) for i in range(1, 6))
        lines.append(
            f"| {label} | {statistics.mean(v):.2f} | {statistics.median(v):g} | {min(v)} | {max(v)} | {dist} |"
        )
    diff = [r["scores"]["final_helpfulness"] - r["scores"]["writer_helpfulness"] for r in ok]
    lines.append("")
    lines.append(
        f"Evaluated requests: {len(ok)} of {len(runs)}. Final - draft: {sum(d > 0 for d in diff)} better, "
        f"{sum(d == 0 for d in diff)} same, {sum(d < 0 for d in diff)} worse (mean {statistics.mean(diff):+.2f})."
    )
    return "\n".join(lines)


def judge() -> str:
    d = read_json(RAW / "judge_validation.json")
    lines = [
        "| Judge scores vs human labels | Spearman | p-value | Mean abs. difference | Exact matches |",
        "|---|---|---|---|---|",
    ]
    for k, a in d["agreement"].items():
        lines.append(f"| {k} | {a['spearman']} | {a['p_value']} | {a['mean_abs_diff']} | {a['exact_agreement']}/20 |")
    r = d["repeatability"]
    lines += [
        "",
        "| Repeatability (3 runs) | Value |",
        "|---|---|",
        f"| Cases whose score changed | {r['cases_with_any_change']}/{r['cases']} |",
        f"| Run pairs with a change | {r['pairwise_changed']}/{r['pairwise_comparisons']} |",
        f"| Mean absolute change | {r['mean_abs_change']} |",
        f"| Max absolute change | {r['max_abs_change']} |",
        "",
        "| Case | Human | Run 1 | Run 2 | Run 3 |",
        "|---|---|---|---|---|",
    ]
    for cid, h in d["human"].items():
        lines.append(f"| {cid} | {h} | " + " | ".join(str(run[cid]["score"]) for run in d["runs"]) + " |")
    return "\n".join(lines)


def latency() -> str:
    t = read_json(RAW / "latency_table.json")
    runs = read_json(RAW / "latency_runs.json")
    hits = runs["hits"]
    hit_ms = sorted(h["latency_ms"] for h in hits)
    lines = ["| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |", "|---|---|---|---|"]
    for r in t["rows"]:
        lines.append(f"| {r['stage']} | {r['p50_ms']:,.1f} | {r['p95_ms']:,.1f} | {r['pct_of_e2e']:.1f}% |")
    lines.append(f"| (other: Kafka client setup, offset reads, cache store) | | | {t['other_pct']:.1f}% |")
    sessions = {}
    for r in runs["misses"]:
        sessions[r.get("session", "this run")] = sessions.get(r.get("session", "this run"), 0) + 1
    lines += [
        "",
        f"Requests: {t['n']} confirmed cache misses (served from cache: {t['served_from_cache']}); end-to-end p50 "
        f"{t['e2e_p50_ms'] / 1000:.1f} s, p95 {t['e2e_p95_ms'] / 1000:.1f} s. Sessions: "
        + ", ".join(f"{k}: {v}" for k, v in sessions.items())
        + ".",
        f"Cache hits (separate metric): {sum(h['is_cached'] for h in hits)}/{len(hits)} served from cache, p50 "
        f"{hit_ms[len(hit_ms) // 2]:.0f} ms, max {hit_ms[-1]:.0f} ms.",
    ]
    return "\n".join(lines)


def traces() -> str:
    ex = read_json(RAW / "trace_examples.json")["traces"]
    spans = by_trace(read_spans())
    lines = ["| Example | trace_id | Stages (duration ms, status) |", "|---|---|---|"]
    for k, tid in ex.items():
        parts = ", ".join(f"{s['stage']} {s['duration_ms']:,.0f} {s['status']}" for s in journey(spans[tid]))
        lines.append(f"| {k} | `{tid}` | {parts} |")
    fail = journey(spans[ex["failed"]])
    bad = next(s for s in fail if s["status"] == "error" and s["stage"] not in ("request", "pipeline"))
    lines.append("")
    lines.append(
        f"Failed trace: failing stage **{bad['stage']}** ({bad['attempts']} attempts, sent to the dead-letter "
        f"topic), error: `{bad['error']}`."
    )
    return "\n".join(lines)


def summary() -> str:
    s = request_summary(read_spans())
    return (
        f"All logged HW10 requests ({s['first'][:19]} to {s['last'][:19]} UTC, source raw/spans.jsonl): "
        f"{s['requests']} requests, {s['hits']} hits / {s['misses']} misses (hit rate {s['hit_rate']:.1%}), "
        f"{s['errors']} errors (error rate {s['error_rate']:.1%}); successful miss end-to-end p50 "
        f"{s['miss_p50_ms'] / 1000:.1f} s, p95 {s['miss_p95_ms'] / 1000:.1f} s; hit p50 {s['hit_p50_ms']:.0f} ms."
    )


def main() -> int:
    banner("fill METRICS.md from raw/")
    for marker, fn, needs in (
        ("summary", summary, "spans.jsonl"),
        ("part2", part2, "part2_evaluation.json"),
        ("stage-scores", stage_scores, "latency_runs.json"),
        ("judge", judge, "judge_validation.json"),
        ("traces", traces, "trace_examples.json"),
        ("latency", latency, "latency_table.json"),
    ):
        if (RAW / needs).exists():
            fill(marker, fn())
            print(f"  filled {marker}")
        else:
            print(f"  skipped {marker} (no raw/{needs} yet)")
    return 0


if __name__ == "__main__":
    code = main()
    footer("metrics")
    sys.exit(code)
