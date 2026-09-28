#!/usr/bin/env python3
"""Measure the naive vs fixed list endpoints: 3 page sizes x 2 versions x 30 requests.

Latency is measured client-side (full HTTP round trip) with perf_counter.
SQL statements per request come from the X-SQL-Count header set by the backend.
A few warm-up requests per configuration are sent first and not recorded.

Usage (from Homework4/, backend running on port 8486):
    HW4_EMAIL=you@example.com python scripts/measure_n1.py   # prompts for password
"""

import csv
import getpass
import json
import math
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import HARDWARE, PAGE_SIZES, PORT_BASE, REQUESTS_PER_SIZE, SEED, WARMUP_REQUESTS  # noqa: E402

BASE_URL = f"http://localhost:{PORT_BASE}"
RAW = ROOT / "reports" / "hw04" / "raw"
METRICS = ROOT / "reports" / "hw04" / "METRICS.md"
VERSIONS = ["naive", "fixed"]


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (with 30 samples, p99 is the slowest request)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def login(session: requests.Session) -> None:
    email = os.getenv("HW4_EMAIL") or input("Login email: ").strip()
    password = os.getenv("HW4_PASSWORD") or getpass.getpass("Password: ")
    r = session.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=10)
    if r.status_code != 200:
        sys.exit(f"Login failed ({r.status_code}): {r.text}")


def one_request(session: requests.Session, version: str, page_size: int) -> dict:
    url = f"{BASE_URL}/listings/{version}"
    start = time.perf_counter()
    r = session.get(url, params={"page": 1, "page_size": page_size}, timeout=30)
    latency_ms = (time.perf_counter() - start) * 1000
    body = r.json() if r.status_code == 200 else {}
    items = body.get("items", [])
    return {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "version": version,
        "page_size": page_size,
        "status": r.status_code,
        "latency_ms": round(latency_ms, 3),
        "server_handler_ms": float(r.headers.get("X-Handler-Time-ms", "nan")),
        "sql_statements": int(r.headers.get("X-SQL-Count", -1)),
        "items_returned": len(items),
        "inquiries_returned": sum(len(i["inquiries"]) for i in items),
    }


def summarize(rows: list[dict]) -> list[dict]:
    summary = []
    for size in PAGE_SIZES:
        for version in VERSIONS:
            sel = [r for r in rows if r["page_size"] == size and r["version"] == version]
            lat = [r["latency_ms"] for r in sel]
            sql = sorted({r["sql_statements"] for r in sel})
            summary.append(
                {
                    "page_size": size,
                    "version": version,
                    "requests": len(sel),
                    "sql_statements_per_request": sql[0] if len(sql) == 1 else sql,
                    "p50_ms": round(percentile(lat, 50), 2),
                    "p95_ms": round(percentile(lat, 95), 2),
                    "p99_ms": round(percentile(lat, 99), 2),
                    "mean_ms": round(sum(lat) / len(lat), 2),
                }
            )
    return summary


def markdown_tables(summary: list[dict], run_at: str) -> str:
    lines = [
        f"_Measured {run_at}; client-side latency over localhost; page=1; "
        f"{REQUESTS_PER_SIZE} recorded requests per row after {WARMUP_REQUESTS} warm-ups._",
        "",
        "| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['page_size']} | {s['version']} | {s['sql_statements_per_request']} | "
            f"{s['p50_ms']} | {s['p95_ms']} | {s['p99_ms']} |"
        )
    lines += ["", "| Page size | Speedup at p50 (naive / fixed) | Speedup at p95 | SQL stmts saved/req |", "|---|---|---|---|"]
    for size in PAGE_SIZES:
        n = next(s for s in summary if s["page_size"] == size and s["version"] == "naive")
        f = next(s for s in summary if s["page_size"] == size and s["version"] == "fixed")
        saved = (
            n["sql_statements_per_request"] - f["sql_statements_per_request"]
            if isinstance(n["sql_statements_per_request"], int) and isinstance(f["sql_statements_per_request"], int)
            else "varies"
        )
        lines.append(f"| {size} | {n['p50_ms'] / f['p50_ms']:.2f}x | {n['p95_ms'] / f['p95_ms']:.2f}x | {saved} |")
    return "\n".join(lines)


def update_metrics(table_md: str) -> None:
    start, end = "<!-- N1_RESULTS_START -->", "<!-- N1_RESULTS_END -->"
    text = METRICS.read_text(encoding="utf-8")
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        METRICS.write_text(f"{before}{start}\n{table_md}\n{end}{after}", encoding="utf-8")
        print(f"Updated {METRICS}")


def main() -> None:
    session = requests.Session()
    if requests.get(f"{BASE_URL}/health", timeout=5).status_code != 200:
        sys.exit(f"Backend not responding on {BASE_URL}")
    login(session)

    run_at = datetime.now().isoformat(timespec="seconds")
    print(f"[{run_at}] N+1 measurement start - SEED={SEED}, sizes={PAGE_SIZES}, {REQUESTS_PER_SIZE} req each")
    rows = []
    for size in PAGE_SIZES:
        for version in VERSIONS:
            for _ in range(WARMUP_REQUESTS):
                one_request(session, version, size)
            batch = [one_request(session, version, size) for _ in range(REQUESTS_PER_SIZE)]
            rows.extend(batch)
            bad = [r for r in batch if r["status"] != 200]
            p50 = percentile([r["latency_ms"] for r in batch], 50)
            print(
                f"  size={size:<4} {version:<6} sql/req={batch[0]['sql_statements']:<4} "
                f"items={batch[0]['items_returned']:<4} inquiries={batch[0]['inquiries_returned']:<4} "
                f"p50={p50:.2f}ms errors={len(bad)}"
            )

    expected = len(PAGE_SIZES) * len(VERSIONS) * REQUESTS_PER_SIZE
    assert len(rows) == expected, f"expected {expected} rows, got {len(rows)}"
    summary = summarize(rows)
    meta = {
        "run_at": run_at,
        "base_url": BASE_URL,
        "seed": SEED,
        "hardware": HARDWARE,
        "python": platform.python_version(),
        "page": 1,
        "warmup_requests_per_config": WARMUP_REQUESTS,
        "recorded_requests": len(rows),
        "percentile_method": "nearest-rank",
    }

    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / "n1_requests.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (RAW / "n1_requests.json").write_text(json.dumps({"meta": meta, "requests": rows}, indent=2), encoding="utf-8")
    (RAW / "n1_summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2), encoding="utf-8")

    table_md = markdown_tables(summary, run_at)
    print("\n" + table_md + "\n")
    update_metrics(table_md)
    print(f"Saved {len(rows)} requests to {RAW / 'n1_requests.csv'} (+ .json, n1_summary.json)")


if __name__ == "__main__":
    main()
