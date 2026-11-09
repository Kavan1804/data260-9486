#!/usr/bin/env python3
"""HW9 verification: re-checks the saved evidence against the live system and writes reports/hw09/verification.json.

No model calls. Needs Redis and MySQL. Usage (repo root):  python Homework9/scripts/verify_hw09.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw9.common import DATA, PREFIX, RAW, REPORT_DIR, ROOT, banner, footer, read_json, redis_client  # noqa: E402

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def safe(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - a missing file or service is a failed check, not a crash
        check(name, False, f"{type(exc).__name__}: {exc}")


def c_redis():
    r = redis_client()
    info = r.info("server")
    idx = [i.decode() for i in r.execute_command("FT._LIST")]
    check("Redis is up with the query engine", True, f"redis {info['redis_version']}, FT indexes {idx or 'none now'}")
    keys = [k.decode() for k in r.scan_iter(match="*")]
    bad = [k for k in keys if not k.startswith(PREFIX + ":")] + [i for i in idx if not i.startswith(PREFIX + ":")]
    check("every Redis key and index starts with s9486:", not bad, f"{len(keys)} keys, bad={bad[:3]}")


def c_part1():
    from hw9.listing_store import ListingDatabaseWithCache

    d = read_json(RAW / "part1_counter.json")
    db = ListingDatabaseWithCache()
    live_redis = int(db.redis_client.get(d["redis_key"]) or 0)
    live_db = db.db_view_count(d["listing_id"])
    check(
        "Part 1: 25 accesses, synced at 10 and 20",
        [a["total"] for a in d["accesses"]] == list(range(1, 26)) and d["synced_at"] == [10, 20],
        f"synced_at={d['synced_at']}",
    )
    check(
        "Part 1: live Redis/MySQL match the saved run",
        (live_redis, live_db) == (d["final_redis"], d["final_db"]) == (25, 20),
        f"Redis {live_redis}, MySQL view_count {live_db}",
    )


def c_part2():
    d = read_json(RAW / "part2_results.json")
    rows, s = d["rows"], d["summary"]
    cats = {r["category"] for r in rows}
    check(
        "Part 2: >=10 queries with new, exact and paraphrase",
        len(rows) >= 10 and cats == {"new", "exact", "paraphrase"},
        f"{len(rows)} queries",
    )
    misses = sum(not r["is_cached"] for r in rows)
    check(
        "Part 2: pipeline ran only on misses (never on a hit)",
        s["pipeline_calls"] == misses and not any(r["is_cached"] and r["pipeline_called"] for r in rows),
        f"{s['pipeline_calls']} calls, {misses} misses",
    )
    check(
        "Part 2: every response has is_cached, similarity and latency",
        all({"is_cached", "similarity", "latency_ms"} <= set(r) for r in rows),
        f"hit rate {s['hit_rate_pct']}%, cached {s['avg_cached_ms']} ms vs {s['avg_non_cached_ms']} ms",
    )


def c_sweep():
    d = read_json(RAW / "sweep_summary.json")
    yaml_path = "Homework9/data/cache_cases.yaml"
    commit = git("log", "--diff-filter=A", "--format=%H %cI", "--", yaml_path).splitlines()
    committed = git("show", f"{commit[-1].split()[0]}:{yaml_path}") + "\n" if commit else ""
    same = hashlib.sha256(committed.encode()).hexdigest() == d["cases_sha256"]
    first_commit_time = datetime.fromisoformat(commit[-1].split()[1]) if commit else None
    sweep_time = datetime.fromisoformat(d["run_at"])
    check(
        "Part 3: cache_cases.yaml committed before the sweep and not changed",
        bool(commit) and same and first_commit_time < sweep_time,
        f"commit {commit[-1][:7] if commit else '-'} at {first_commit_time}, sweep {sweep_time:%Y-%m-%d %H:%M:%S}",
    )
    check(
        "Part 3: 5 thresholds with hit rate, false-hit rate, latency, cost",
        [s["threshold"] for s in d["summary"]] == [0.75, 0.8, 0.85, 0.9, 0.95]
        and all({"hit_rate", "false_hit_rate", "mean_latency_ms", "total_cost"} <= set(s) for s in d["summary"]),
        f"cheapest {d['lowest_cost_threshold']}",
    )
    check("Part 3: one false hit shown in full", (RAW / "false_hit.json").exists())


def c_stale():
    d = read_json(RAW / "stale_demo.json")
    st = d["steps"]
    from hw9.listing_store import ListingDatabaseWithCache

    live = ListingDatabaseWithCache().get_listing(d["listing_code"])["available_units"]
    check(
        "Part 3.5: stale hit, then version change detected and refreshed",
        [x["is_cached"] for x in st] == [False, True, True, False, True]
        and st[3]["data_version"] != st[0]["data_version"],
        f"{d['listing_code']} versions {st[0]['data_version']} -> {st[3]['data_version']}",
    )
    check("Part 3.5: listing row restored after the demo", live == d["original_units"], f"available_units={live}")


def c_part4():
    for name in ("training_data.json", "validation_data.json", "test_data.json"):
        rows = read_json(DATA / name)
        check(
            f"Part 4: {name} has questions only", all(set(r) == {"id", "question"} for r in rows), f"{len(rows)} rows"
        )
    lessons = read_json(DATA / "lessons.json")
    need = {"lesson_id", "failure_pattern", "correction", "created_at", "use_count"}
    check(
        "Part 4: lessons.json has the required fields", all(need <= set(x) for x in lessons), f"{len(lessons)} lessons"
    )
    check(
        "Part 4: lessons only from training questions",
        all(all(s.startswith("tr") for s in x["source"]) for x in lessons),
    )
    check(
        "Part 4: every lesson went through validation",
        all(x["status"] in ("kept", "rejected") and "validation" in x for x in lessons),
    )
    rev = read_json(RAW / "revision_demo.json")
    check(
        "Part 4: revision demo REVISE then 2nd attempt, max 2",
        rev["attempts"] == 2 and rev["history"][0]["evaluation"]["result"] == "REVISE",
        f"final {rev['final_result']}",
    )
    v = read_json(RAW / "variants_summary.json")
    test_sha = hashlib.sha256((DATA / "test_data.json").read_bytes()).hexdigest()
    check(
        "Part 4: four variants on the same, unchanged test_data.json",
        len(v["summary"]) == 4 and all(s["test_sha256"] == test_sha for s in v["summary"]),
        ", ".join(f"{s['variant']} {s['correct']}/12" for s in v["summary"]),
    )
    attempts = [
        r["attempts"]
        for n in ("baseline", "evaluator_repair", "lesson_memory", "validated_improvement")
        for r in read_json(RAW / f"variants_{n}.json")["rows"]
    ]
    check("Part 4: no question used more than 2 attempts", max(attempts) <= 2)


def c_tests():
    out = subprocess.run([sys.executable, "Homework9/tests/run_hw9_tests.py"], cwd=ROOT, capture_output=True, text=True)
    last = [ln for ln in out.stdout.splitlines() if "tests passed" in ln]
    check("automated HW9 tests", out.returncode == 0, last[0] if last else out.stdout[-200:])


def main() -> int:
    banner("verify HW9")
    for name, fn in (
        ("redis", c_redis),
        ("part1", c_part1),
        ("part2", c_part2),
        ("sweep", c_sweep),
        ("stale", c_stale),
        ("part4", c_part4),
        ("tests", c_tests),
    ):
        safe(name, fn)
    passed = sum(c["ok"] for c in CHECKS)
    head = git("rev-parse", "--short=12", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    print(f"\n{passed}/{len(CHECKS)} checks passed   commit {head}{' (uncommitted changes)' if dirty else ''}")
    (REPORT_DIR / "verification.json").write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "commit": head,
                "dirty_tree": dirty,
                "passed": passed,
                "total": len(CHECKS),
                "checks": CHECKS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    code = main()
    footer("verify")
    sys.exit(code)
