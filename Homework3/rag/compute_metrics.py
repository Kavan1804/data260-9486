"""Recompute HW3 Part 2 summary metrics from reports/hw03/raw/*.jsonl.

This script only reads the JSONL files already written by
rag/run_experiments.py - it never calls the embedding model or a retriever
itself, so it is safe to re-run any number of times to regenerate the
summary table and the confident-miss check.

Usage:
    python -m rag.compute_metrics
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"

TECHNIQUES = ["token", "semantic", "sentence_window"]
LABELS = {"token": "Token", "semantic": "Semantic", "sentence_window": "Sentence window"}

# A "confidently scored" retrieval: top-1 cosine at or above this threshold.
CONFIDENT_COSINE_THRESHOLD = 0.5


def load_records(technique):
    path = RAW_DIR / f"{technique}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(records):
    if not records:
        return None
    top1 = [max((row["cosine_sim"] for row in rec["rows"]), default=0.0) for rec in records]
    mean_at_k = [
        statistics.mean(row["cosine_sim"] for row in rec["rows"]) if rec["rows"] else 0.0
        for rec in records
    ]
    hits = [
        1 if rec["expected_source_file"] in {row.get("source_file") for row in rec["rows"]} else 0
        for rec in records
    ]
    latencies = [rec["latency_ms"] for rec in records]
    return {
        "num_chunks": records[0]["num_chunks"],
        "avg_chunk_len": records[0]["avg_chunk_len"],
        "top1_cosine": statistics.mean(top1),
        "mean_at_k_cosine": statistics.mean(mean_at_k),
        "recall_at_k": statistics.mean(hits),
        "mean_latency_ms": statistics.mean(latencies),
    }


def find_confident_misses(records, cosine_threshold=CONFIDENT_COSINE_THRESHOLD):
    """A confidently scored top-1 retrieval whose chunk text does not contain
    the expected answer - required by the HW3 Part 2 write-up section that
    asks you to explain why the embedding likely considered it similar."""
    misses = []
    for rec in records:
        if not rec["rows"]:
            continue
        top = rec["rows"][0]
        if (
            top["cosine_sim"] >= cosine_threshold
            and rec["expected_answer"].lower() not in top["preview"].lower()
        ):
            misses.append(
                {
                    "technique": rec["technique"],
                    "query_id": rec["query_id"],
                    "query": rec["query"],
                    "cosine_sim": top["cosine_sim"],
                    "preview": top["preview"],
                    "expected_answer": rec["expected_answer"],
                }
            )
    return misses


def render_table(summaries):
    header = (
        "| Technique | Chunks | Avg chunk length | Top-1 cosine | "
        "Mean@k cosine | Recall@k | Mean retrieval latency (ms) |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for technique in TECHNIQUES:
        s = summaries.get(technique)
        label = LABELS[technique]
        if s is None:
            lines.append(f"| {label} | TODO_RUN_MANUALLY | | | | | |")
            continue
        lines.append(
            f"| {label} | {s['num_chunks']} | {s['avg_chunk_len']:.1f} | "
            f"{s['top1_cosine']:.4f} | {s['mean_at_k_cosine']:.4f} | "
            f"{s['recall_at_k']:.2f} | {s['mean_latency_ms']:.2f} |"
        )
    return "\n".join(lines)


def main():
    summaries = {}
    all_records = []
    for technique in TECHNIQUES:
        records = load_records(technique)
        all_records.extend(records)
        summaries[technique] = summarize(records)

    table = render_table(summaries)
    print(table)

    misses = find_confident_misses(all_records)
    print(f"\nConfidently scored misses found: {len(misses)}")
    for miss in misses:
        print(json.dumps(miss, indent=2))

    out = {"table_markdown": table, "confident_misses": misses}
    out_path = RAW_DIR / "summary_metrics.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print("Paste the table above into reports/hw03/METRICS.md.")


if __name__ == "__main__":
    main()
