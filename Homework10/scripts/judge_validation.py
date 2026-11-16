#!/usr/bin/env python3
"""HW10 Part 3.2-3.3: compare the GEval judge with my human labels, and test repeatability.

Refuses to run unless Homework10/data/eval_cases.json and human_labels.csv are committed and unchanged since
that commit (Part 3.1: labels frozen before any judge score exists). Then the judge (Writer Helpfulness, same
metric and settings as Part 2) scores the same 20 drafts three times.

  agreement:     Spearman rank correlation and mean absolute difference, judge run 1 vs human labels
                 (also shown for runs 2 and 3 and for the per-case median of the three runs)
  repeatability: how many cases changed score across the 3 runs, mean and max absolute change between runs

Usage (repo root; Ollama running):  python Homework10/scripts/judge_validation.py      (or make judge-validation)
Writes reports/hw10/raw/judge_validation.json and judge_validation_cases.csv (raw per-case data)
"""

from __future__ import annotations

import csv
import statistics
import subprocess
import sys
import time
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

from scipy.stats import spearmanr  # noqa: E402

from hw10.common import DATA, RAW, ROOT, banner, footer, read_json, utc_now, write_json  # noqa: E402
from hw10.judge import JUDGE_SETTINGS, OllamaJudge, score  # noqa: E402

RUNS = 3
FILES = ["Homework10/data/eval_cases.json", "Homework10/data/human_labels.csv"]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def frozen_commit() -> dict:
    info = {}
    for f in FILES:
        first = git("log", "--diff-filter=A", "--format=%h %cI", "--", f).splitlines()
        changed = bool(git("status", "--porcelain", "--", f))
        if not first or changed:
            raise SystemExit(f"{f} must be committed (and unchanged) before the judge runs - see Part 3.1")
        info[f] = first[-1]
    return info


def agreement(human: list[int], judge: list[int]) -> dict:
    rho, p = spearmanr(human, judge)
    return {
        "spearman": None if rho != rho else round(float(rho), 3),  # NaN when one side is constant
        "p_value": None if p != p else round(float(p), 4),
        "mean_abs_diff": round(statistics.mean(abs(h - j) for h, j in zip(human, judge)), 3),
        "exact_agreement": sum(h == j for h, j in zip(human, judge)),
    }


def main() -> int:
    banner("Part 3 judge validation (20 drafts x 3 runs vs human labels)")
    commits = frozen_commit()
    for f, c in commits.items():
        print(f"frozen: {f} first committed {c}")
    cases = read_json(DATA / "eval_cases.json")["cases"]
    with (DATA / "human_labels.csv").open(encoding="utf-8") as f:
        human = {r["case_id"]: int(r["human_helpfulness"]) for r in csv.DictReader(f)}
    if set(human) != {c["case_id"] for c in cases}:
        raise SystemExit("human_labels.csv must have one label for every case")
    print(f"judge settings: {JUDGE_SETTINGS}")

    runs: list[dict[str, dict]] = []
    for run in range(1, RUNS + 1):
        judge = OllamaJudge()
        t = time.time()
        res = {}
        for c in cases:
            try:
                res[c["case_id"]] = score("Writer Helpfulness", judge, c["question_with_facts"], c["draft"])
            except Exception as exc:  # noqa: BLE001 - one failed call is recorded, not fatal
                res[c["case_id"]] = {"score": None, "raw": None, "reason": f"ERROR {type(exc).__name__}: {exc}"}
        runs.append(res)
        got = [res[c["case_id"]]["score"] for c in cases]
        print(f"run {run}: {got}  ({time.time() - t:.0f}s, {judge.calls} judge calls)", flush=True)

    ids = [c["case_id"] for c in cases]
    ok_ids = [i for i in ids if all(r[i]["score"] is not None for r in runs)]
    h = [human[i] for i in ok_ids]
    per_run = {f"run{k + 1}": agreement(h, [runs[k][i]["score"] for i in ok_ids]) for k in range(RUNS)}
    median = [int(statistics.median(r[i]["score"] for r in runs)) for i in ok_ids]
    per_run["median_of_3"] = agreement(h, median)

    changes = [abs(runs[a][i]["score"] - runs[b][i]["score"]) for i in ok_ids for a, b in combinations(range(RUNS), 2)]
    changed_cases = [i for i in ok_ids if len({r[i]["score"] for r in runs}) > 1]
    repeat = {
        "cases_with_any_change": len(changed_cases),
        "cases": len(ok_ids),
        "changed_case_ids": changed_cases,
        "pairwise_comparisons": len(changes),
        "pairwise_changed": sum(c > 0 for c in changes),
        "mean_abs_change": round(statistics.mean(changes), 3) if changes else 0.0,
        "max_abs_change": max(changes) if changes else 0,
    }

    print("\n=== Agreement with human labels (1-5) ===")
    print(f"{'judge scores':14} {'Spearman':>9} {'p':>8} {'MAD':>6} {'exact':>6}")
    for k, a in per_run.items():
        exact = f"{a['exact_agreement']:>3}/{len(h)}"
        print(f"{k:14} {a['spearman']!s:>9} {a['p_value']!s:>8} {a['mean_abs_diff']:>6} {exact}")
    print("\n=== Repeatability (3 runs, same inputs and settings) ===")
    print(
        f"cases whose score changed: {repeat['cases_with_any_change']}/{repeat['cases']}  "
        f"pairwise changes: {repeat['pairwise_changed']}/{repeat['pairwise_comparisons']}  "
        f"mean |change| {repeat['mean_abs_change']}  max |change| {repeat['max_abs_change']}"
    )
    print("\ncase  human  run1 run2 run3")
    for i in ids:
        print(f"{i:5} {human[i]:>5}  " + "  ".join(f"{r[i]['score']!s:>3}" for r in runs))

    with (RAW / "judge_validation_cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["case_id", "trace_id", "question", "human", "judge_run1", "judge_run2", "judge_run3", "reason_run1"]
        )
        for c in cases:
            i = c["case_id"]
            w.writerow(
                [i, c["trace_id"], c["question"], human[i], *(r[i]["score"] for r in runs), runs[0][i]["reason"]]
            )
    write_json(
        RAW / "judge_validation.json",
        {
            "run_at": utc_now(),
            "frozen_commits": commits,
            "judge": JUDGE_SETTINGS,
            "agreement": per_run,
            "repeatability": repeat,
            "runs": runs,
            "human": human,
        },
    )
    return 0


if __name__ == "__main__":
    code = main()
    footer("judge validation")
    sys.exit(code)
