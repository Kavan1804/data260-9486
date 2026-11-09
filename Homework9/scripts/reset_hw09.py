#!/usr/bin/env python3
"""Empty the HW9 semantic caches: only keys under s9486:semcache:, s9486:sweep:, s9486:stale:, s9486:test:
and their s9486:idx:* indexes. Never FLUSHALL/FLUSHDB. The Part 1 view counter keys are left alone.

Usage (repo root):  python Homework9/scripts/reset_hw09.py      (or make cache-reset)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redis.exceptions import ResponseError  # noqa: E402

from hw9.common import PREFIX, banner, delete_prefix, footer, key, redis_client  # noqa: E402

NAMESPACES = ("semcache", "sweep", "stale", "test")


def main() -> int:
    banner("reset HW9 cache keys (prefix-scoped)")
    r = redis_client()
    for ns in NAMESPACES:
        try:
            r.ft(key("idx", ns)).dropindex(delete_documents=False)
            dropped = "index dropped"
        except ResponseError:
            dropped = "no index"
        n = delete_prefix(r, key(ns) + ":*")
        print(f"  {key(ns)}:*  deleted {n} keys, {dropped}")
    left = sorted(k.decode() for k in r.scan_iter(match="*"))
    print(
        f"keys left in Redis: {len(left)}  (all start with {PREFIX}: {all(k.startswith(PREFIX + ':') for k in left)})"
    )
    for k in left[:10]:
        print(f"  {k}")
    return 0


if __name__ == "__main__":
    code = main()
    footer("cache reset")
    sys.exit(code)
