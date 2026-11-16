#!/usr/bin/env python3
"""HW10 Part 4.3: stage latency over 50 confirmed cache misses (+ 10 cache hits as a separate metric).

Questions: 20 listing questions (city / address / home type, listings picked with random.Random(VERIFY_SEED)) and
30 general renting questions, none of them asked before in HW10. Before anything runs, every question is embedded
and checked against the s9486:hw10 cache: the run stops if any is >= 0.85 similar to a cached query. The 50 are
asked with store_on_miss=False, so they cannot hit each other either. Each request is checked again after it
runs (is_cached must be False). Every miss goes through the full HW8 pipeline and the Part 2 evaluator.
Then 10 cache hits (5 exact, 5 paraphrases of the trace-demo question) for the separate hit-latency metric.

Usage (repo root; run make trace-demo first so the cache has the demo entry):
    python Homework10/scripts/latency_experiment.py      (or make latency-run, ~70 min)
Writes reports/hw10/raw/latency_runs.json and latency_table.json
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

import config  # noqa: E402
from hw10.analysis import stage_table  # noqa: E402
from hw10.common import RAW, banner, footer, read_spans, utc_now, write_json  # noqa: E402
from hw10.runtime import make_qa, running_agents  # noqa: E402

GENERAL = [
    "How do I compare two apartments that have different lease lengths?",
    "What should a student do if the landlord does not return calls about a leak?",
    "Is it a good idea to pay rent with a credit card?",
    "How can I build a rental history if this is my first apartment?",
    "What does 'month-to-month' mean in a rental agreement?",
    "How should I document the condition of an apartment on move-in day?",
    "What can I do if my roommate stops paying their share of the rent?",
    "Are pets usually allowed in student apartments, and what fees come with them?",
    "How do I find out if a neighborhood near campus is safe at night?",
    "What questions should I ask during an apartment viewing?",
    "How early should I start looking for an apartment before the fall semester?",
    "What is a guarantor and when do students need one?",
    "How do I split a security deposit fairly between roommates?",
    "What should I do if I find mold in my bathroom?",
    "Can my landlord raise the rent in the middle of my lease?",
    "How do I break a lease early if I am studying abroad next term?",
    "What happens if I move out without giving notice?",
    "How do parking permits usually work for apartment complexes?",
    "What should be in a written roommate agreement?",
    "How do I report a broken smoke detector?",
    "Is renters insurance worth it for a small studio?",
    "How do I avoid paying an application fee for apartments I will not get?",
    "What are the pros and cons of living in a furnished apartment?",
    "How do I ask for a lease renewal with the same rent?",
    "What is a reasonable commute time from an apartment to campus?",
    "How do I handle a package that was stolen from my apartment lobby?",
    "What should I know about subletting rules in California?",
    "How can I lower my electricity bill in a small apartment?",
    "What does a landlord need to fix within a reasonable time?",
    "How do I get a copy of my lease if I lost mine?",
]
LISTING_TEMPLATES = [
    "What city is listing {c} in?",
    "What is the street address of listing {c}?",
    "What kind of home is listing {c}, and how many bedrooms does it have?",
]
HIT_QUERIES = [
    "Who is the landlord for listing LST-00117, and how many units are open there?",
    "Which landlord manages listing LST-00117, and how many units are available?",
] * 5


def questions() -> list[str]:
    from sqlalchemy import text

    from backend.app.database import engine

    with engine.connect() as conn:
        codes = [c for (c,) in conn.execute(text("SELECT listing_code FROM listings WHERE listing_code < 'LST-05000'"))]
    used = {"LST-00117"}
    rng = random.Random(config.VERIFY_SEED + 10)
    picked = rng.sample(sorted(set(codes) - used), 20)
    listing_qs = [LISTING_TEMPLATES[i % 3].format(c=c) for i, c in enumerate(picked)]
    qs = listing_qs + GENERAL
    rng.shuffle(qs)
    return qs


def finished_runs(qs: list[str]) -> dict[str, dict]:
    """--resume: requests from an earlier session that completed (request span ok, path miss), rebuilt from
    spans.jsonl. A request that was cut off has no request span and is simply run again."""
    from hw10.analysis import by_trace

    done = {}
    for tid, trace in by_trace(read_spans()).items():
        st = {s["stage"]: s for s in trace}
        req, look = st.get("request"), st.get("cache_lookup", {})
        if not req or req.get("path") != "miss" or req["status"] != "ok" or req.get("query") not in qs:
            continue
        scores = (st.get("evaluation") or {}).get("scores") or {}
        done[req["query"]] = {
            "trace_id": tid,
            "is_cached": look.get("cache") == "hit",
            "similarity": look.get("similarity"),
            "status": req["status"],
            "error": req.get("error"),
            "latency_ms": req["duration_ms"],
            "scores": scores,
            "session": "earlier (resumed)",
        }
    return done


def main() -> int:
    resume = "--resume" in sys.argv
    banner("Part 4.3 stage latency: 50 confirmed cache misses + 10 cache hits" + (" (resumed)" if resume else ""))
    qa, cache = make_qa()
    qs = questions()
    assert len(qs) == 50 and len(set(qs)) == 50
    done = finished_runs(qs) if resume else {}
    if resume:
        print(
            f"resume: {len(done)} of the 50 requests already completed in the earlier session (from spans.jsonl); "
            f"running the other {50 - len(done)}"
        )
    if cache.size() == 0:
        # Redis has no persistence; after a Docker restart the trace-demo entry is gone. Put it back (one extra
        # miss, not one of the 50) so the 10 cache-hit requests below have something to hit.
        print("cache is empty (Redis restarted) - re-seeding the trace-demo entry, not counted in the 50")
        with running_agents():
            seed = qa.ask(HIT_QUERIES[0], store_on_miss=True)
        print(f"  seeded: trace_id={seed['trace_id']} status={seed['status']}")
    print(f"cache {cache.entry_prefix}* has {cache.size()} entries (from make trace-demo)")
    worst = max((qa_lookup(cache, q) for q in qs), key=lambda x: x[1])
    print(f"pre-check: highest similarity of the 50 questions to anything cached = {worst[1]:.4f} ({worst[0][:60]})")
    if worst[1] >= cache.threshold:
        print("a question would be a cache hit - stopping")
        return 1

    runs, hits = [], []
    t_start = time.time()
    with running_agents():
        for i, q in enumerate(qs, 1):
            if q in done:
                runs.append({"n": i, "query": q, **done[q]})
                continue
            out = qa.ask(q, store_on_miss=False)
            ev = out.get("evaluation") or {}
            scores = {
                k: (ev.get(k) or {}).get("score") for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")
            }
            runs.append(
                {
                    "n": i,
                    "query": q,
                    "trace_id": out["trace_id"],
                    "is_cached": out["is_cached"],
                    "similarity": out["similarity"],
                    "status": out["status"],
                    "error": out.get("error"),
                    "latency_ms": out["latency_ms"],
                    "scores": scores,
                    "session": "this run",
                }
            )
            print(
                f"  {i:>2}/50 miss={not out['is_cached']} sim={out['similarity']:.3f} {out['status']:5} "
                f"{out['latency_ms'] / 1000:6.1f}s  scores={scores}  {q[:55]}",
                flush=True,
            )
        for q in HIT_QUERIES:
            out = qa.ask(q, store_on_miss=False)
            hits.append(
                {
                    "query": q,
                    "trace_id": out["trace_id"],
                    "is_cached": out["is_cached"],
                    "similarity": out["similarity"],
                    "latency_ms": out["latency_ms"],
                }
            )
            print(f"  hit  is_cached={out['is_cached']} sim={out['similarity']:.4f} {out['latency_ms']:7.1f} ms  {q}")

    served = sum(r["is_cached"] for r in runs)
    print(
        f"\nverified: {served} of 50 requests were served from the cache (must be 0); "
        f"{sum(r['status'] == 'ok' for r in runs)} finished ok; run took {(time.time() - t_start) / 60:.1f} min"
    )
    table = stage_table(read_spans(), [r["trace_id"] for r in runs])
    print(
        f"\n=== Stage latency over {table['n']} cache-miss requests (end-to-end p50 {table['e2e_p50_ms']:,.0f} ms, "
        f"p95 {table['e2e_p95_ms']:,.0f} ms) ==="
    )
    print(f"{'Stage':20} {'p50 (ms)':>10} {'p95 (ms)':>10} {'% of e2e':>9}")
    for row in table["rows"]:
        print(f"{row['stage']:20} {row['p50_ms']:>10,.1f} {row['p95_ms']:>10,.1f} {row['pct_of_e2e']:>8.1f}%")
    print(f"{'(other: Kafka client setup, offsets)':20} {'':>21} {table['other_pct']:>8.1f}%")
    hit_ms = sorted(h["latency_ms"] for h in hits)
    print(
        f"cache hits (separate metric): {sum(h['is_cached'] for h in hits)}/{len(hits)} hits, "
        f"p50 {hit_ms[len(hit_ms) // 2]:.1f} ms"
    )
    write_json(RAW / "latency_runs.json", {"run_at": utc_now(), "resumed": resume, "misses": runs, "hits": hits})
    write_json(RAW / "latency_table.json", {"run_at": utc_now(), **table, "served_from_cache": served})
    return 0 if served == 0 else 1


def qa_lookup(cache, q: str) -> tuple[str, float]:
    from hw9.embeddings import embed

    entry, sim = cache.nearest(embed(q))
    return q, sim


if __name__ == "__main__":
    code = main()
    footer("latency experiment")
    sys.exit(code)
