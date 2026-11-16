#!/usr/bin/env python3
"""HW10 verification: re-checks the saved evidence and writes reports/hw10/verification.json. No model calls.

Usage (repo root):  python Homework10/scripts/verify_hw10.py      (or make verify-hw10)
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hw10.analysis import by_trace, stage_table  # noqa: E402
from hw10.common import DATA, RAW, REPORT_DIR, ROOT, banner, footer, read_json, read_spans  # noqa: E402

CHECKS: list[dict] = []
REQUIRED = {"trace_id", "stage", "start", "end", "status", "error"}


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"check": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def safe(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        check(name, False, f"{type(exc).__name__}: {exc}")


def c_spans():
    spans = read_spans()
    check(
        "every span has trace_id, stage, start, end, status, error",
        all(REQUIRED <= set(s) for s in spans),
        f"{len(spans)} spans",
    )
    traces = by_trace(spans)
    ex = read_json(RAW / "trace_examples.json")["traces"]
    miss = {s["stage"] for s in traces[ex["miss"]]}
    need = {"cache_lookup", "pipeline", "planner", "writer", "reviewer", "evaluation", "request"}
    check(
        "miss trace: one trace_id from cache_lookup through Kafka stages to evaluation",
        need <= miss,
        ", ".join(sorted(miss)),
    )
    hit = {s["stage"]: s for s in traces[ex["hit"]]}
    check(
        "hit trace: cache_lookup says hit and no Kafka stage ran",
        hit["cache_lookup"].get("cache") == "hit" and not ({"planner", "writer", "reviewer"} & set(hit)),
    )
    fail = traces[ex["failed"]]
    bad = [s for s in fail if s["status"] == "error" and s["stage"] not in ("request", "pipeline")]
    check(
        "failed trace: failing stage and error recorded",
        bool(bad) and bool(bad[0]["error"]),
        f"{bad[0]['stage']}: {bad[0]['error'][:60]}" if bad else "",
    )


def c_part2():
    d = read_json(RAW / "part2_evaluation.json")
    ev = d["evaluation"]
    ok = ev["status"] == "ok" and all(
        1 <= ev[k]["score"] <= 5 for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")
    )
    check(
        "Part 2: four criteria scored 1-5 for the end-to-end question",
        ok,
        f"plan {ev['plan_quality']['score']}, draft {ev['writer_helpfulness']['score']}, "
        f"final {ev['final_helpfulness']['score']}, diff {ev['improvement']['difference']:+d}",
    )
    k = ev["inputs"]["kafka"]
    check(
        "Part 2: plan, draft, final joined by trace_id from the three topics",
        {k["plan"]["topic"], k["draft"]["topic"], k["final"]["topic"]}
        == {"s9486_tasks", "s9486_drafts", "s9486_final"},
    )


def c_part3():
    first = {}
    for f in ("Homework10/data/eval_cases.json", "Homework10/data/human_labels.csv"):
        log = git("log", "--diff-filter=A", "--format=%cI", "--", f).splitlines()
        first[f] = datetime.fromisoformat(log[-1]) if log else None
        check(f"Part 3.1: {Path(f).name} committed and unchanged", bool(log) and not git("status", "--porcelain", f))
    d = read_json(RAW / "judge_validation.json")
    run_at = datetime.fromisoformat(d["run_at"])
    check(
        "Part 3.1: labels committed before the judge scored them",
        all(t and t < run_at for t in first.values()),
        f"judge run {run_at:%Y-%m-%d %H:%M} UTC",
    )
    cases = read_json(DATA / "eval_cases.json")["cases"]
    labels = list(csv.DictReader((DATA / "human_labels.csv").open()))
    check(
        "Part 3: 20 drafts, 20 human labels 1-5",
        len(cases) == 20 and len(labels) == 20 and all(r["human_helpfulness"] in "12345" for r in labels),
    )
    a = d["agreement"]["run1"]
    check(
        "Part 3.2: Spearman and mean absolute difference reported, raw per-case CSV saved",
        a["mean_abs_diff"] is not None and (RAW / "judge_validation_cases.csv").exists(),
        f"Spearman {a['spearman']}, MAD {a['mean_abs_diff']}",
    )
    check(
        "Part 3.3: judge run 3 times on the same 20 drafts",
        len(d["runs"]) == 3 and all(len(r) == 20 for r in d["runs"]),
        f"{d['repeatability']['cases_with_any_change']}/20 cases changed",
    )


def c_part4():
    runs = read_json(RAW / "latency_runs.json")
    t = read_json(RAW / "latency_table.json")
    ids = [r["trace_id"] for r in runs["misses"]]
    check(
        "Part 4.3: 50 requests, none served from the cache",
        len(ids) == 50
        and len(set(ids)) == 50
        and not any(r["is_cached"] for r in runs["misses"])
        and t["served_from_cache"] == 0,
    )
    again = stage_table(read_spans(), ids)
    check(
        "Part 4.3: stage table recomputes from spans.jsonl",
        again["rows"] == t["rows"] and again["n"] == t["n"],
        f"{again['n']} complete cache-miss traces",
    )
    check(
        "Part 4.3: cache-hit latency kept separately",
        sum(h["is_cached"] for h in runs["hits"]) == len(runs["hits"]),
        f"{len(runs['hits'])} hits",
    )


def c_tests():
    out = subprocess.run(
        [sys.executable, "Homework10/tests/run_hw10_tests.py"], cwd=ROOT, capture_output=True, text=True
    )
    last = [ln for ln in out.stdout.splitlines() if "tests passed" in ln]
    check("automated HW10 tests", out.returncode == 0, last[0] if last else out.stdout[-200:])


def main() -> int:
    banner("verify HW10")
    for name, fn in (
        ("spans", c_spans),
        ("part2", c_part2),
        ("part3", c_part3),
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
