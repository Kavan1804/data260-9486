#!/usr/bin/env python3
"""Fill the tables in reports/hw09/METRICS.md from reports/hw09/raw/*.json (no hand-typed numbers).

Usage (repo root):  python Homework9/scripts/build_metrics.py      (or make metrics-hw09)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import RAW, banner, fill_metrics_section, footer, read_json  # noqa: E402

VARIANT_NAMES = {
    "baseline": "Baseline",
    "evaluator_repair": "Evaluator Repair",
    "lesson_memory": "Lesson Memory",
    "validated_improvement": "Validated Improvement",
}


def flat(text: str, n: int = 400) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 4] + " ..."


def key_sentence(text: str, pattern: str) -> str:
    """First sentence of an answer that matches the pattern (the Writer's answers start with a plan recap)."""
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])|\n+", text):
        if re.search(pattern, sent):
            return flat(sent, 170)
    return flat(text, 170)


UNITS_FACT = r"(available[_ ]units|units?)\D{0,40}\b[0-9]\b|\b[0-9]\b\D{0,20}units?"
LANDLORD_FACT = r"[A-Z][a-z]+ [A-Z][a-z]+ \("
LANDLORD_NAME = r"landlord.{0,40}\b(is|name is|:)\s+[A-Z][a-z]+ [A-Z][a-z]+|[A-Z][a-z]+ [A-Z][a-z]+ \("


def part1() -> str:
    d = read_json(RAW / "part1_counter.json")
    return "\n".join(
        [
            "| Listing | Redis key | Accesses | Synced at | Redis after | MySQL view_count after |",
            "|---|---|---|---|---|---|",
            f"| {d['listing_code']} (id {d['listing_id']}) | `{d['redis_key']}` | {len(d['accesses'])} | "
            f"{', '.join(map(str, d['synced_at']))} | {d['final_redis']} | {d['final_db']} |",
        ]
    )


def part2() -> str:
    d = read_json(RAW / "part2_results.json")
    s = d["summary"]
    lines = [
        "| # | Category | Query | is_cached | Similarity | Latency (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for r in d["rows"]:
        lines.append(
            f"| {r['n']} | {r['category']} | {r['query']} | {r['is_cached']} | {r['similarity']:.4f} | "
            f"{r['latency_ms']:,.1f} |"
        )
    cat = s["by_category"]
    lines += [
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Queries (new / exact / paraphrase) | {s['queries']} ({cat['new']['queries']} / {cat['exact']['queries']} / "
        f"{cat['paraphrase']['queries']}) |",
        f"| Cache hit rate | {s['hits']}/{s['queries']} = {s['hit_rate_pct']}% |",
        f"| Served from cache: new / exact / paraphrase | {cat['new']['hits']}/{cat['new']['queries']} / "
        f"{cat['exact']['hits']}/{cat['exact']['queries']} / "
        f"{cat['paraphrase']['hits']}/{cat['paraphrase']['queries']} |",
        f"| Average latency, cached | {s['avg_cached_ms']:,.1f} ms |",
        f"| Average latency, not cached (HW8 pipeline) | {s['avg_non_cached_ms']:,.1f} ms |",
        f"| HW8 pipeline calls | {s['pipeline_calls']} |",
    ]
    return "\n".join(lines)


def part3() -> str:
    d = read_json(RAW / "sweep_summary.json")
    lines = [
        "| Threshold | Hit rate | False-hit rate | Mean latency (ms) | Total cost |",
        "|---|---|---|---|---|",
    ]
    for s in d["summary"]:
        lines.append(
            f"| {s['threshold']:.2f} | {s['hits']}/40 = {s['hit_rate']:.1%} | {s['false_hits']}/{s['hits']} = "
            f"{s['false_hit_rate']:.1%} | {s['mean_latency_ms']:,.1f} | ${s['total_cost']:.2f} |"
        )
    lines += [
        "",
        f"Total cost = misses x ${d['miss_cost']:.2f} + false hits x ${d['false_hit_cost']:.2f}. "
        "Misses and false hits per threshold:",
        "",
        "| Threshold | Misses | False hits | Should-hit cases missed |",
        "|---|---|---|---|",
    ]
    for s in d["summary"]:
        lines.append(f"| {s['threshold']:.2f} | {s['misses']} | {s['false_hits']} | {s['missed_should_hit']} |")
    return "\n".join(lines)


def false_hit() -> str:
    path = RAW / "false_hit.json"
    if not path.exists():
        return "_No false hit happened at any threshold._"
    f = read_json(path)
    return "\n".join(
        [
            f"- Threshold: {f['threshold']:.2f}",
            f"- Cached query ({f['cached_seed']}): {f['cached_query']}",
            f"- Incoming query ({f['case_id']}, labeled {f['category']}): {f['incoming_query']}",
            f"- Similarity: {f['similarity']:.4f}",
            f"- Cached answer returned (key sentence): {key_sentence(f['cached_answer_returned'], LANDLORD_NAME)}",
            f"- Correct answer, fresh pipeline run (key sentence): "
            f"{key_sentence(f['correct_answer_pipeline'], LANDLORD_NAME)}",
            "- Full answers: reports/hw09/raw/false_hit.json",
        ]
    )


def stale() -> str:
    d = read_json(RAW / "stale_demo.json")
    lines = ["| Step | is_cached | Latency (ms) | data_version | Key sentence of the answer |", "|---|---|---|---|---|"]
    for s in d["steps"]:
        lines.append(
            f"| {s['step']} | {s['is_cached']} | {s['latency_ms']:,.1f} | `@{s['data_version'].split('@')[-1][:8]}` | "
            f"{key_sentence(s['answer'], UNITS_FACT)} |"
        )
    return "\n".join(lines)


def part4() -> str:
    d = read_json(RAW / "variants_summary.json")
    lines = [
        "| Variant | Correct answers | Incorrect answers | Average attempts | Average latency |",
        "|---|---|---|---|---|",
    ]
    for s in d["summary"]:
        lines.append(
            f"| {VARIANT_NAMES[s['variant']]} | {s['correct']} | {s['incorrect']} | {s['avg_attempts']:.2f} | "
            f"{s['avg_latency_s']:.2f} s |"
        )
    lines.append("")
    lines.append(f"Same test_data.json for all four runs: {d['same_test_file']}")
    return "\n".join(lines)


def lessons() -> str:
    path = Path(__file__).resolve().parents[1] / "data" / "lessons.json"
    rows = read_json(path)
    if not rows:
        return "_No lesson was created (no failure pattern repeated in training)._"
    lines = [
        "| Lesson | Failure pattern | From | Validation (failing before -> after) | Decision | use_count |",
        "|---|---|---|---|---|---|",
    ]
    for x in rows:
        v = x.get("validation", {})
        lines.append(
            f"| {x['lesson_id']} | {x['failure_pattern']} | {', '.join(x['source'])} | "
            f"{len(v.get('failing_before', []))} -> {len(v.get('failing_after', []))} | "
            f"{x['status']} | {x['use_count']} |"
        )
    return "\n".join(lines)


def main() -> int:
    banner("fill METRICS.md from raw/")
    for marker, fn, needs in (
        ("part1-table", part1, "part1_counter.json"),
        ("part2-table", part2, "part2_results.json"),
        ("sweep-table", part3, "sweep_summary.json"),
        ("false-hit", false_hit, "sweep_summary.json"),
        ("stale-table", stale, "stale_demo.json"),
        ("lessons-table", lessons, "variants_summary.json"),
        ("variants-table", part4, "variants_summary.json"),
    ):
        if (RAW / needs).exists():
            fill_metrics_section(marker, fn())
            print(f"  filled {marker}")
        else:
            print(f"  skipped {marker} (no raw/{needs} yet)")
    return 0


if __name__ == "__main__":
    code = main()
    footer("metrics")
    sys.exit(code)
