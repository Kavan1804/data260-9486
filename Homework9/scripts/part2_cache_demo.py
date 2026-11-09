#!/usr/bin/env python3
"""HW9 Part 2: semantic response cache in front of the HW8 agent pipeline (12 queries, threshold 0.85).

The queries mix new questions, exact duplicates and paraphrases. The cache namespace s9486:semcache is
emptied first (only its own keys), so the first question of each topic is always a miss and runs the real
HW8 pipeline (planner -> writer -> reviewer with llama3.2:3b over Kafka).

Usage (repo root; Redis, Kafka, MySQL and Ollama running):  python Homework9/scripts/part2_cache_demo.py
Writes reports/hw09/raw/part2_results.json and part2_results.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import RAW, banner, footer, redis_client, utc_now, write_json  # noqa: E402
from hw9.ingress import SemanticQA  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402
from hw9.pipeline import KafkaPipeline, running_agents  # noqa: E402
from hw9.semantic_cache import RedisSemanticCache  # noqa: E402

THRESHOLD = 0.85
QUERIES = [
    ("new", "How many units are available at listing LST-00117?"),
    ("exact", "How many units are available at listing LST-00117?"),
    ("new", "What should I check before signing a lease for an apartment in San Jose?"),
    ("paraphrase", "Before I sign an apartment lease in San Jose, what things should I check?"),
    ("new", "Who is the landlord for listing LST-00230?"),
    ("paraphrase", "Which landlord manages listing LST-00230?"),
    ("new", "How can I get my full security deposit back when I move out?"),
    ("exact", "What should I check before signing a lease for an apartment in San Jose?"),
    ("new", "What is a fair way to split rent and utilities with roommates?"),
    ("paraphrase", "When I move out, how do I make sure my security deposit is returned?"),
    ("paraphrase", "How many open units does listing LST-00117 have right now?"),
    ("exact", "What is a fair way to split rent and utilities with roommates?"),
]


def avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def main() -> int:
    banner(f"Part 2 semantic cache ({len(QUERIES)} queries, threshold {THRESHOLD})")
    r = redis_client()
    cache = RedisSemanticCache(r, "semcache", THRESHOLD)
    print(f"cleared {cache.clear()} old entries under {cache.entry_prefix}*  (index {cache.index_name})")
    pipeline = KafkaPipeline()
    qa = SemanticQA(cache, ListingDatabaseWithCache(r), pipeline)

    rows = []
    with running_agents():
        for i, (category, query) in enumerate(QUERIES, 1):
            print(f"\n--- Q{i} [{category}] {query}", flush=True)
            calls_before = pipeline.calls
            out = qa.ask(query)
            out["n"], out["category"] = i, category
            out["pipeline_called"] = pipeline.calls > calls_before
            rows.append(out)
            print(
                f"    is_cached={out['is_cached']}  similarity={out['similarity']:.4f}  "
                f"latency_ms={out['latency_ms']:.1f}  pipeline_called={out['pipeline_called']}"
            )
            print(f"    answer: {out['answer'][:150].replace(chr(10), ' ')}...")

    hits = [o for o in rows if o["is_cached"]]
    misses = [o for o in rows if not o["is_cached"]]
    print("\n=== Results ===")
    print(f"{'#':>2} {'category':10} {'is_cached':9} {'similarity':>10} {'latency_ms':>11}  matched cached query")
    for o in rows:
        matched = o["matched_query"] if o["is_cached"] else "-"
        print(
            f"{o['n']:>2} {o['category']:10} {str(o['is_cached']):9} {o['similarity']:>10.4f} "
            f"{o['latency_ms']:>11.1f}  {matched}"
        )
    summary = {
        "queries": len(rows),
        "by_category": {
            c: {
                "queries": sum(o["category"] == c for o in rows),
                "hits": sum(o["category"] == c and o["is_cached"] for o in rows),
            }
            for c in ("new", "exact", "paraphrase")
        },
        "hits": len(hits),
        "hit_rate_pct": round(100 * len(hits) / len(rows), 1),
        "avg_cached_ms": avg([o["latency_ms"] for o in hits]),
        "avg_non_cached_ms": avg([o["latency_ms"] for o in misses]),
        "pipeline_calls": pipeline.calls,
        "threshold": THRESHOLD,
    }
    print(
        f"\ncache hit rate: {summary['hits']}/{summary['queries']} = {summary['hit_rate_pct']}%   "
        f"pipeline calls: {summary['pipeline_calls']}"
    )
    for c, v in summary["by_category"].items():
        print(f"  {c:10} {v['hits']}/{v['queries']} served from cache")
    print(f"avg latency cached:     {summary['avg_cached_ms']} ms  ({len(hits)} queries)")
    print(f"avg latency non-cached: {summary['avg_non_cached_ms']} ms  ({len(misses)} queries)")

    write_json(RAW / "part2_results.json", {"run_at": utc_now(), "summary": summary, "rows": rows})
    with (RAW / "part2_results.csv").open("w", newline="", encoding="utf-8") as f:
        cols = ["n", "category", "query", "is_cached", "similarity", "latency_ms", "matched_query", "status"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    code = main()
    footer("Part 2 semantic cache")
    sys.exit(code)
