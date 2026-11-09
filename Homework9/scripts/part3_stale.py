#!/usr/bin/env python3
"""HW9 Part 3.5: a stale cached answer, then the data-version invalidation that fixes it.

The question depends on one s9486_rel row (listings.available_units of one listing):
  1. ask once -> miss -> HW8 pipeline answers from the current row -> stored with version LST-xxxxx@<fingerprint>
  2. ask again -> hit (the version still matches)
  3. UPDATE listings SET available_units = 0 (the unit got leased)
  4. ask with the version check OFF -> stale hit: the cache still says the old number
  5. ask with the version check ON  -> stored version != current fingerprint -> entry deleted -> miss ->
     pipeline answers from the new row -> stored with the new version
  6. ask again -> hit on the refreshed entry
  7. put the row back (available_units = original) so the other parts see the original data

Usage (repo root; Redis, Kafka, MySQL and Ollama running):  python Homework9/scripts/part3_stale.py
Writes reports/hw09/raw/stale_demo.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import RAW, banner, footer, log, redis_client, utc_now, write_json  # noqa: E402
from hw9.ingress import SemanticQA  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402
from hw9.pipeline import KafkaPipeline, running_agents  # noqa: E402
from hw9.semantic_cache import RedisSemanticCache  # noqa: E402


def show(step: str, out: dict) -> dict:
    print(
        f"    -> is_cached={out['is_cached']} similarity={out['similarity']:.4f} latency_ms={out['latency_ms']:.1f} "
        f"data_version={out['data_version']}"
    )
    print(f"    answer: {out['answer'][:260].replace(chr(10), ' ')}")
    return {
        "step": step,
        **{k: out.get(k) for k in ("is_cached", "similarity", "latency_ms", "data_version", "answer")},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="LST-00888")
    ap.add_argument("--keep-change", action="store_true", help="do not put the row back at the end")
    args = ap.parse_args()
    query = f"How many units are available at listing {args.code}?"

    banner(f"Part 3.5 stale answer + data-version invalidation ({args.code})")
    r = redis_client()
    store = ListingDatabaseWithCache(r)
    cache = RedisSemanticCache(r, "stale", 0.85)
    print(f"cleared {cache.clear()} old entries under {cache.entry_prefix}*")
    before = store.get_listing(args.code)
    original_units = before["available_units"]
    print(f"{args.code} in s9486_rel: available_units={original_units}  fingerprint={store.fingerprint(args.code)}")
    pipeline = KafkaPipeline()
    no_check = SemanticQA(cache, store, pipeline, check_version=False)
    checked = SemanticQA(cache, store, pipeline, check_version=True)
    steps = []
    try:
        with running_agents():
            print(f"\n[1] first ask (cache empty): {query}")
            steps.append(show("first ask", checked.ask(query)))

            print("\n[2] ask again before any change")
            steps.append(show("repeat before update", checked.ask(query)))

            print(f"\n[3] UPDATE listings SET available_units = 0 WHERE listing_code = '{args.code}'")
            store.set_available_units(args.code, 0)
            now = store.get_listing(args.code)
            log("stale", f"{args.code} available_units is now {now['available_units']} in MySQL")
            print(f"    new fingerprint={store.fingerprint(args.code)} (cache entry still has the old one)")

            print("\n[4] ask with the version check OFF (plain semantic cache)")
            stale = show("stale hit (check off)", no_check.ask(query))
            steps.append(stale)
            print(
                f"    STALE: MySQL says {now['available_units']} units, the cached answer was written when it was "
                f"{original_units}"
            )

            print("\n[5] ask with the data-version check ON")
            calls = pipeline.calls
            steps.append(show("version check on", checked.ask(query)))
            print(f"    pipeline called again: {pipeline.calls > calls}")

            print("\n[6] ask again after the refresh")
            steps.append(show("repeat after refresh", checked.ask(query)))
    finally:
        if not args.keep_change:
            store.set_available_units(args.code, original_units)
            log("stale", f"restored {args.code} available_units={original_units} (end of demo)")
        print(f"cleared {cache.clear()} demo entries under {cache.entry_prefix}*")

    write_json(
        RAW / "stale_demo.json",
        {
            "run_at": utc_now(),
            "listing_code": args.code,
            "query": query,
            "original_units": original_units,
            "steps": steps,
        },
    )
    ok = (
        len(steps) == 5
        and not steps[0]["is_cached"]
        and steps[1]["is_cached"]
        and steps[2]["is_cached"]
        and not steps[3]["is_cached"]
        and steps[4]["is_cached"]
        and steps[3]["data_version"] != steps[0]["data_version"]
    )
    print(f"\nstale hit shown, then detected and refreshed: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    code = main()
    footer("Part 3.5 stale answers")
    sys.exit(code)
