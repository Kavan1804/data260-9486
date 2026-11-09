#!/usr/bin/env python3
"""HW9 Part 1: Redis-backed view counter for one listing (25 accesses, MySQL sync every 10).

Starts from 0 for this one listing (its Redis key and its view_count row), so every run prints the same counts.

Usage (repo root, Redis + MySQL running):  python Homework9/scripts/part1_counter.py [--code LST-00042] [--n 25]
Writes reports/hw09/raw/part1_counter.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import RAW, banner, footer, key, stamp, utc_now, write_json  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="LST-00042")
    ap.add_argument("--n", type=int, default=25)
    args = ap.parse_args()

    banner(f"Part 1 view counter ({args.code}, {args.n} accesses)")
    db = ListingDatabaseWithCache()
    listing = db.get_listing(args.code)
    if listing is None:
        print(f"{args.code} not found")
        return 1
    lid = listing["id"]
    rkey = key("views", "listing", lid)
    print(f"listing {args.code} (id={lid}): {listing['title']}")
    print(f"Redis key: {rkey}    MySQL column: s9486_rel.listings.view_count")
    db.reset_views(lid)
    print(f"reset: Redis key deleted, view_count set to 0 (DB now {db.db_view_count(lid)})")

    print("\n=== Testing Counter ===\n")
    rows = []
    pending: list[str] = []
    db.on_log = pending.append  # print the method's sync message right under its access line
    for i in range(1, args.n + 1):
        total = db.increment_listing_views(lid)
        synced = total % 10 == 0
        print(f"Access #{i}: Total = {total}", flush=True)
        for msg in pending:
            print(f"{msg}   [{stamp()}]", flush=True)
        pending.clear()
        rows.append({"access": i, "total": total, "synced": synced, "db_view_count": db.db_view_count(lid)})

    redis_value = int(db.redis_client.get(rkey))
    db_value = db.db_view_count(lid)
    last_sync = max((r["total"] for r in rows if r["synced"]), default=0)
    print("\n--- after the run")
    print(f"Redis  GET {rkey} = {redis_value}")
    print(f"MySQL  SELECT view_count FROM listings WHERE id={lid} -> {db_value}")
    print(f"synced at totals: {[r['total'] for r in rows if r['synced']]}")
    print(f"MySQL matches Redis at the last sync ({last_sync}): {db_value == last_sync}")
    print(f"views since the last sync (only in Redis until #{last_sync + 10}): {redis_value - db_value}")
    write_json(
        RAW / "part1_counter.json",
        {
            "run_at": utc_now(),
            "listing_code": args.code,
            "listing_id": lid,
            "redis_key": rkey,
            "accesses": rows,
            "final_redis": redis_value,
            "final_db": db_value,
            "synced_at": [r["total"] for r in rows if r["synced"]],
        },
    )
    return 0 if db_value == last_sync and redis_value == args.n else 1


if __name__ == "__main__":
    code = main()
    footer("Part 1 counter")
    sys.exit(code)
