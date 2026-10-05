#!/usr/bin/env python3
"""Part 3: 150 fault-injected tool calls (50 each at 0%, 20%, 50%).

Each storage attempt draws from random.Random(VERIFY_SEED); the attempt fails
when draw < rate. Every rate starts from the same seed, so the run is
reproducible: re-running gives the same draws, failures, and retry counts
(latencies vary slightly because they are real MySQL timings).

Outputs (reports/hw05/raw/):
  retry_calls.csv / retry_calls.json - one record per call (all 150)
  retry_summary.json                 - success rate, mean and p99 latency per rate
and the Part 3 table in METRICS.md.

Usage (repo root):  python scripts/run_retry_experiment.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import time
from dataclasses import asdict
from datetime import datetime

from hw5_common import RAW, banner, fill_metrics_section

import config
from domain_tools.execute import DEFAULT_POLICY, default_repository, execute_tool
from domain_tools.faults import FaultInjector, FaultyRepository

CITIES = ["San Jose", "Campbell", "Sunnyvale", "Santa Clara", "Milpitas", "Mountain View"]


def call_plan(n: int) -> tuple[str, dict]:
    """Deterministic mix of the three domain tools (same plan for every rate)."""
    kind = (n - 1) % 3
    if kind == 0:
        return "search_listings", {"query": CITIES[n % len(CITIES)], "limit": 5}
    if kind == 1:
        return "get_listing", {"listing_code": f"LST-{(n * 97) % 5000 + 1:05d}"}
    return "landlord_portfolio_stats", {"landlord_id": n % config.N_LANDLORDS + 1}


def p99(values: list[float]) -> float:
    """Nearest-rank p99: with 50 samples this is the slowest call."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.99 * len(ordered)) - 1)]


def summarize_data(result: dict):
    d = result["data"]
    if "listings" in d:
        return f"{d['count']} listings"
    if "listing_count" in d:
        return f"landlord {d['landlord_id']}: {d['listing_count']} listings"
    return d.get("listing_code")


def main() -> int:
    banner("Part 3 - fault injection: 3 rates x 50 calls")
    policy = DEFAULT_POLICY
    print(f"policy: max_attempts={policy.max_attempts}, backoff {policy.base_delay_s * 1000:.0f} ms x2 "
          f"(cap {policy.max_delay_s * 1000:.0f} ms), timeout {policy.timeout_s:.1f} s/attempt; seed={config.VERIFY_SEED}")
    repo = default_repository()
    execute_tool("get_listing", {"listing_code": "LST-00001"}, repo=repo)  # warm the connection pool (not recorded)

    records, summary = [], []
    for rate in config.FAILURE_RATES:
        injector = FaultInjector(rate, config.VERIFY_SEED)
        faulty = FaultyRepository(repo, injector)
        rows = []
        for n in range(1, config.CALLS_PER_RATE + 1):
            tool, inputs = call_plan(n)
            attempts: list = []
            before = len(injector.draws)
            start = time.perf_counter()
            result = json.loads(execute_tool(tool, inputs, repo=faulty, policy=policy, attempts_log=attempts))
            latency = (time.perf_counter() - start) * 1000
            draws = injector.draws[before:]
            rows.append({
                "failure_rate": rate,
                "call_no": n,
                "tool": tool,
                "inputs": json.dumps(inputs),
                "attempts": len(attempts),
                "retries": len(attempts) - 1,
                "draws": ";".join(f"{d['draw']:.6f}" for d in draws),
                "injected_failures": ";".join("F" if d["injected_failure"] else "-" for d in draws),
                "attempt_outcomes": ";".join(a["outcome"] for a in attempts),
                "success": result["ok"],
                "latency_ms": round(latency, 3),
                "error": result["error"] or "",
                "result": summarize_data(result) if result["ok"] else "",
            })
        lat = [r["latency_ms"] for r in rows]
        decisions = "".join(r["injected_failures"] + "|" for r in rows)
        s = {
            "failure_rate": rate,
            "calls": len(rows),
            "successes": sum(r["success"] for r in rows),
            "success_rate": sum(r["success"] for r in rows) / len(rows),
            "total_attempts": sum(r["attempts"] for r in rows),
            "injected_failures": sum(r["injected_failures"].count("F") for r in rows),
            "calls_with_retry": sum(r["retries"] > 0 for r in rows),
            "mean_latency_ms": round(statistics.mean(lat), 2),
            "p99_latency_ms": round(p99(lat), 2),
            "decision_sha1": hashlib.sha1(decisions.encode()).hexdigest()[:12],
        }
        summary.append(s)
        records.extend(rows)
        print(f"rate {rate:4.0%}: success {s['successes']}/{s['calls']} ({s['success_rate']:.0%}), "
              f"attempts {s['total_attempts']}, injected failures {s['injected_failures']}, "
              f"calls retried {s['calls_with_retry']}, mean {s['mean_latency_ms']:.2f} ms, "
              f"p99 {s['p99_latency_ms']:.2f} ms, decisions sha1 {s['decision_sha1']}")

    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / "retry_calls.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    meta = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "seed": config.VERIFY_SEED,
        "policy": asdict(policy),
        "storage": "MySQL s9486_rel via MySQLListingRepository",
        "p99_method": "nearest rank, ceil(0.99 * n)",
        "latency": "wall clock of execute_tool, including backoff waits",
    }
    (RAW / "retry_calls.json").write_text(json.dumps({"meta": meta, "calls": records}, indent=2) + "\n", encoding="utf-8")
    (RAW / "retry_summary.json").write_text(json.dumps({"meta": meta, "rates": summary}, indent=2) + "\n", encoding="utf-8")

    table = ["| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) | Attempts | Injected failures | Calls retried |",
             "|---|---|---|---|---|---|---|"]
    for s in summary:
        table.append(f"| {s['failure_rate']:.0%} | {s['success_rate']:.0%} ({s['successes']}/{s['calls']}) | "
                     f"{s['mean_latency_ms']:.2f} | {s['p99_latency_ms']:.2f} | {s['total_attempts']} | "
                     f"{s['injected_failures']} | {s['calls_with_retry']} |")
    fill_metrics_section("retry-table", "\n".join(table) + f"\n\nSource: raw/retry_summary.json, run {meta['run_at']}.")
    print("\nsaved reports/hw05/raw/retry_calls.csv, retry_calls.json, retry_summary.json; updated METRICS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
