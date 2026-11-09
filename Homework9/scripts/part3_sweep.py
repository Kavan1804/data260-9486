#!/usr/bin/env python3
"""HW9 Part 3.2-3.4: threshold sweep over the 40 labeled cases in Homework9/data/cache_cases.yaml.

1. Empty the sweep cache (s9486:sweep:*), then put the 10 seed queries in it. Each seed is a real cache
   miss, so the HW8 pipeline answers it and the answer is stored with its embedding and data-version marker.
2. For each threshold 0.75 / 0.80 / 0.85 / 0.90 / 0.95, look up every case on its own against those 10 seeds
   (embedding + Redis KNN + version check, measured every time). Cases never write to the cache, so a case
   cannot hit another case and the order does not matter.
3. A hit costs the measured lookup time. A miss would run the HW8 pipeline: the first time a case misses, the
   real pipeline runs for it and its measured time is kept; at the other thresholds the same case reuses that
   measured pipeline time (the pipeline does not depend on the threshold). This keeps the run to about 30
   pipeline calls instead of about 110 on the 8 GB Mac. The script prints when a time is reused.
4. Cost model (Part 3.4, fixed here before the sweep was run):
       MISS_COST       = $0.01 per cache miss (one HW8 pipeline run = 3 model calls)
       FALSE_HIT_COST  = $2.50 per false hit  (a student gets another listing's facts; ~5 min of support time)
   total cost = misses * MISS_COST + false_hits * FALSE_HIT_COST
5. Print one false hit in full, with the correct answer from a fresh pipeline run of the incoming query.

Usage (repo root; Redis, Kafka, MySQL and Ollama running):  python Homework9/scripts/part3_sweep.py
Writes reports/hw09/raw/sweep_seeds.json, sweep_cases.csv, sweep_summary.json, false_hit.json
"""

from __future__ import annotations

import csv
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from hw9.common import DATA, RAW, banner, footer, log, ms_since, redis_client, utc_now, write_json  # noqa: E402
from hw9.ingress import SemanticQA  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402
from hw9.pipeline import KafkaPipeline, running_agents  # noqa: E402
from hw9.semantic_cache import RedisSemanticCache  # noqa: E402

THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
MISS_COST = 0.01
FALSE_HIT_COST = 2.50
CASES_FILE = DATA / "cache_cases.yaml"


def load_cases() -> tuple[list[dict], list[dict], str]:
    raw = CASES_FILE.read_bytes()
    spec = yaml.safe_load(raw)
    seeds, cases = spec["seeds"], spec["cases"]
    counts = {c: sum(x["category"] == c for x in cases) for c in ("exact", "paraphrase", "similar", "unrelated")}
    if len(seeds) != 10 or len(cases) != 40 or set(counts.values()) != {10}:
        raise SystemExit(f"cache_cases.yaml must have 10 seeds and 4 x 10 cases, got {len(seeds)} / {counts}")
    return seeds, cases, hashlib.sha256(raw).hexdigest()


def main() -> int:
    banner("Part 3 threshold sweep (40 labeled cases x 5 thresholds)")
    seeds, cases, sha = load_cases()
    print(f"cases file: {CASES_FILE.relative_to(CASES_FILE.parents[2])}  sha256={sha[:16]}...  (labels not edited)")
    print(f"cost model: miss ${MISS_COST:.2f}, false hit ${FALSE_HIT_COST:.2f}")
    r = redis_client()
    cache = RedisSemanticCache(r, "sweep", threshold=0.85)
    print(f"cleared {cache.clear()} old entries under {cache.entry_prefix}*")
    store = ListingDatabaseWithCache(r)
    pipeline = KafkaPipeline()
    qa = SemanticQA(cache, store, pipeline, check_version=True, store_on_miss=False)
    seed_by_query: dict[str, str] = {}
    pipeline_ms: dict[str, float] = {}  # case id -> measured pipeline time (first miss)
    pipeline_answer: dict[str, str] = {}

    with running_agents():
        # ---- 1. seed the cache with the 10 seed queries (real pipeline answers)
        print("\n=== seeding the sweep cache with 10 queries (real HW8 pipeline) ===", flush=True)
        seed_rows = []
        seeder = SemanticQA(cache, store, pipeline, check_version=True, store_on_miss=True)
        for s in seeds:
            out = seeder.ask(s["query"], threshold=1.01)  # 1.01: never a hit, always runs the pipeline
            seed_by_query[s["query"]] = s["id"]
            seed_rows.append({"id": s["id"], **{k: out[k] for k in ("query", "answer", "latency_ms", "data_version")}})
            print(f"  seeded {s['id']} in {out['latency_ms'] / 1000:.1f}s  version={out['data_version']}", flush=True)
        write_json(RAW / "sweep_seeds.json", {"run_at": utc_now(), "seeds": seed_rows})
        print(f"cache now has {cache.size()} entries")

        # ---- 2. the sweep
        rows = []
        for t in THRESHOLDS:
            print(f"\n=== threshold {t:.2f} ===", flush=True)
            for c in cases:
                start = time.perf_counter()
                look = qa.lookup(c["query"])
                entry, sim = look["entry"], look["similarity"]
                matched = seed_by_query.get(entry["query"]) if entry else None
                hit = entry is not None and sim >= t
                version_ok = True
                if hit and entry["data_version"] != "none":
                    version_ok = qa.data_version(entry["depends_on"].split(",")) == entry["data_version"]
                    hit = version_ok
                lookup_ms = ms_since(start)
                reused = False
                if hit:
                    latency = lookup_ms
                else:
                    if c["id"] not in pipeline_ms:
                        log("sweep", f"{c['id']} miss at {t:.2f} -> running the HW8 pipeline once for this case")
                        out = qa.ask(c["query"], threshold=1.01)
                        pipeline_ms[c["id"]] = out["timings"]["pipeline_ms"]
                        pipeline_answer[c["id"]] = out["answer"]
                    else:
                        reused = True
                    latency = lookup_ms + pipeline_ms[c["id"]]
                correct_hit = hit and c["label"] == "should_hit" and matched == c.get("matches")
                false_hit = hit and not correct_hit
                rows.append(
                    {
                        "threshold": t,
                        "id": c["id"],
                        "category": c["category"],
                        "label": c["label"],
                        "query": c["query"],
                        "similarity": sim,
                        "nearest_seed": matched,
                        "hit": hit,
                        "false_hit": false_hit,
                        "lookup_ms": lookup_ms,
                        "pipeline_ms": None if hit else pipeline_ms[c["id"]],
                        "pipeline_time_reused": reused,
                        "latency_ms": round(latency, 1),
                    }
                )
                tag = "FALSE HIT" if false_hit else ("hit" if hit else "miss")
                note = " (pipeline time reused)" if reused else ""
                print(
                    f"  {c['id']} {c['label']:11} sim={sim:.4f} nearest={matched} -> {tag:9} {latency:9.1f} ms{note}",
                    flush=True,
                )

        # ---- 3. summary table
        summary = []
        for t in THRESHOLDS:
            rs = [x for x in rows if x["threshold"] == t]
            hits = sum(x["hit"] for x in rs)
            fh = sum(x["false_hit"] for x in rs)
            misses = len(rs) - hits
            summary.append(
                {
                    "threshold": t,
                    "hits": hits,
                    "hit_rate": round(hits / len(rs), 3),
                    "false_hits": fh,
                    "false_hit_rate": round(fh / hits, 3) if hits else 0.0,
                    "misses": misses,
                    "missed_should_hit": sum(not x["hit"] and x["label"] == "should_hit" for x in rs),
                    "mean_latency_ms": round(sum(x["latency_ms"] for x in rs) / len(rs), 1),
                    "total_cost": round(misses * MISS_COST + fh * FALSE_HIT_COST, 2),
                }
            )
        print("\n=== Threshold sweep (40 cases each) ===")
        print("threshold  hit rate        false-hit rate   mean latency (ms)  total cost")
        for s in summary:
            print(
                f"  {s['threshold']:.2f}    {s['hits']:>2}/40 = {s['hit_rate']:.1%}   "
                f"{s['false_hits']:>2}/{s['hits']:<2} = {s['false_hit_rate']:.1%}   {s['mean_latency_ms']:>14.1f}"
                f"     ${s['total_cost']:.2f}  (misses {s['misses']} x ${MISS_COST} + false hits {s['false_hits']}"
                f" x ${FALSE_HIT_COST})"
            )
        best = min(summary, key=lambda s: (s["total_cost"], -s["threshold"]))
        print(f"lowest total cost: threshold {best['threshold']:.2f} (${best['total_cost']:.2f})")

        # ---- 4. one false hit in full (prefer the cheapest threshold, else 0.85, else any)
        false_rows = [x for x in rows if x["false_hit"]]
        example = None
        for t in (best["threshold"], 0.85, *THRESHOLDS):
            pick = sorted([x for x in false_rows if x["threshold"] == t], key=lambda x: -x["similarity"])
            if pick:
                example = pick[0]
                break
        if example:
            seed_q = next(s["query"] for s in seeds if s["id"] == example["nearest_seed"])
            seed_answer = next(s["answer"] for s in seed_rows if s["id"] == example["nearest_seed"])
            if example["id"] not in pipeline_answer:
                log("sweep", f"running the HW8 pipeline for {example['id']} to get its correct answer")
                pipeline_answer[example["id"]] = qa.ask(example["query"], threshold=1.01)["answer"]
            fh = {
                "threshold": example["threshold"],
                "case_id": example["id"],
                "category": example["category"],
                "incoming_query": example["query"],
                "cached_query": seed_q,
                "cached_seed": example["nearest_seed"],
                "similarity": example["similarity"],
                "cached_answer_returned": seed_answer,
                "correct_answer_pipeline": pipeline_answer[example["id"]],
            }
            write_json(RAW / "false_hit.json", fh)
            print(f"\n=== one false hit in full (threshold {fh['threshold']:.2f}) ===")
            print(f"incoming query : {fh['incoming_query']}   [{fh['case_id']}, labeled should_miss/other seed]")
            print(f"cached query   : {fh['cached_query']}   [{fh['cached_seed']}]")
            print(f"similarity     : {fh['similarity']:.4f}")
            print(f"cached answer returned:\n  {fh['cached_answer_returned'][:600]}")
            print("correct answer (fresh HW8 pipeline run for the incoming query):")
            print(f"  {fh['correct_answer_pipeline'][:600]}")

    write_json(
        RAW / "sweep_summary.json",
        {
            "run_at": utc_now(),
            "cases_sha256": sha,
            "miss_cost": MISS_COST,
            "false_hit_cost": FALSE_HIT_COST,
            "summary": summary,
            "lowest_cost_threshold": best["threshold"],
            "pipeline_runs_for_cases": len(pipeline_ms),
        },
    )
    with (RAW / "sweep_cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(
        f"\npipeline runs: {len(seeds)} seeds + {len(pipeline_ms)} cases; raw rows in reports/hw09/raw/sweep_cases.csv"
    )
    return 0


if __name__ == "__main__":
    code = main()
    footer("Part 3 threshold sweep")
    sys.exit(code)
