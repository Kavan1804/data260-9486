"""Run the three retrieval-only pipelines against reports/hw03/questions.yaml.

TODO_RUN_MANUALLY - do not run this until:
  1. rag/corpus/ contains your real, >=200 KB domain corpus (see
     rag/corpus_prep.py and reports/hw03/SOURCES.md).
  2. reports/hw03/questions.yaml is committed as-is, so the expected answers
     cannot be rewritten after seeing retrieval output.

This script downloads the sentence-transformers/all-MiniLM-L6-v2 embedding
model from Hugging Face on first use (via rag/pipelines.py) and requires
llama-index and its dependencies to be installed (see requirements.txt).

Usage:
    python -m rag.run_experiments
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import yaml

from config import CORPUS_DIR, TOP_K
from rag.pipelines import build_index, build_nodes, get_embed_model, load_corpus, retrieve_and_score

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"
QUESTIONS_FILE = REPORT_DIR / "questions.yaml"

TECHNIQUES = ["token", "semantic", "sentence_window"]


def load_questions():
    data = yaml.safe_load(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return data["questions"]


def run_technique(technique, documents, questions, embed_model):
    nodes = build_nodes(documents, technique, embed_model=embed_model)
    index = build_index(nodes, embed_model=embed_model)

    chunk_lens = [len(node.get_content()) for node in nodes]
    num_chunks = len(nodes)
    avg_chunk_len = statistics.mean(chunk_lens) if chunk_lens else 0.0

    records = []
    for q in questions:
        rows, latency_ms = retrieve_and_score(
            index, technique, q["question"], k=TOP_K, embed_model=embed_model
        )
        records.append(
            {
                "technique": technique,
                "query_id": q["id"],
                "query": q["question"],
                "expected_answer": q["expected_answer"],
                "expected_source_file": q["expected_source_file"],
                "num_chunks": num_chunks,
                "avg_chunk_len": avg_chunk_len,
                "latency_ms": latency_ms,
                "rows": rows,
            }
        )
    return records


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    documents = load_corpus(CORPUS_DIR)
    if not documents:
        raise SystemExit(
            f"No .txt files found in {CORPUS_DIR}. Run rag/corpus_prep.py "
            "(after adding real sources) before running experiments."
        )

    questions = load_questions()
    embed_model = get_embed_model()

    run_log_lines = [f"HW3 retrieval experiment run - {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    for technique in TECHNIQUES:
        print(f"\n=== Technique: {technique} ===")
        records = run_technique(technique, documents, questions, embed_model)
        out_path = RAW_DIR / f"{technique}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        run_log_lines.append(
            f"{technique}: wrote {len(records)} query records to {out_path.relative_to(ROOT)}"
        )
        print(f"Wrote {out_path}")

    with (REPORT_DIR / "RUN_LOG.txt").open("a", encoding="utf-8") as f:
        f.write("\n".join(run_log_lines) + "\n")


if __name__ == "__main__":
    main()
