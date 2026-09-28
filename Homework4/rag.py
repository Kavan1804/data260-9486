#!/usr/bin/env python3
"""HW4 Part 4 - grounded RAG over the rental-housing corpus.

Pipeline: load corpus -> clean HTML -> chunk (500 chars, 50 overlap) ->
MiniLM embeddings -> FAISS (cosine via inner product on normalized vectors)
-> top-k retrieval (printed before any LLM call) -> one of three configs:

  A. no_rag       question only
  B. basic_rag    top-3 raw chunks pasted into the prompt
  C. context_rag  irrelevant/duplicate chunks removed, survivors grouped by
                  source and labelled [n], grounding rules, citations, refusal

Usage (from Homework4/, Ollama running):
    python rag.py                         # full run -> reports/hw04/raw/
    python rag.py --retrieve-only         # retrieval printouts only, no LLM
    python rag.py --ask "question" --mode context --k 3
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import faiss
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CORPUS_DIR,
    EMBEDDING_MODEL_NAME,
    K_SWEEP,
    LLM_MODEL,
    OLLAMA_URL,
    REFUSAL_TEXT,
    RELEVANCE_THRESHOLD,
    ROOT,
    SEED,
    TOP_K,
)

RAW = ROOT / "reports" / "hw04" / "raw"
QUESTIONS_FILE = ROOT / "rag_questions.json"
CONFIGS = ["no_rag", "basic_rag", "context_rag"]

GROUNDED_SYSTEM_PROMPT = f"""You answer questions about rental housing law using ONLY the numbered sources in the context.
Rules:
1. Use only facts stated in the sources. Do not use outside knowledge.
2. Cite the source number in square brackets after each fact, for example [1] or [2].
3. If the sources do not contain enough evidence to answer, reply with exactly:
{REFUSAL_TEXT}
4. If the question is ambiguous, say which reading you answered and answer only that reading from the sources.
5. Keep the answer to at most three sentences."""


# ---------------------------------------------------------------- corpus

class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "head", "noscript"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "tr", "section"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def clean_text(raw: str) -> str:
    if "<html" in raw.lower():
        parser = _TextExtractor()
        parser.feed(raw)
        raw = "".join(parser.parts)
    raw = raw.replace("\xa0", " ")
    # Menus and code-picker lists become 1-3 word lines; real sentences are longer.
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if len(ln.split()) >= 4)


def load_corpus() -> list[dict]:
    docs = []
    for path in sorted(CORPUS_DIR.iterdir()):
        if path.suffix.lower() not in {".txt", ".html", ".htm"} or path.stat().st_size == 0:
            continue
        text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
        if text:
            docs.append({"source": path.name, "text": text})
    if len(docs) < 5:
        print(f"WARNING: only {len(docs)} non-empty documents in {CORPUS_DIR}; the assignment needs at least 5.")
    return docs


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Character windows of `size` with `overlap`, snapped to whitespace."""
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut != -1 else end
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        next_start = end - overlap
        space = text.find(" ", next_start, end)
        start = space + 1 if space != -1 else next_start
    return chunks


def build_chunks(docs: list[dict]) -> list[dict]:
    chunks = []
    for doc in docs:
        stem = Path(doc["source"]).stem
        for i, text in enumerate(chunk_text(doc["text"])):
            chunks.append({"chunk_id": f"{stem}#{i:03d}", "source": doc["source"], "position": i, "text": text})
    return chunks


# ---------------------------------------------------------------- index

class VectorStore:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        vectors = self._embed([c["text"] for c in chunks])
        self.index = faiss.IndexFlatIP(vectors.shape[1])
        self.index.add(vectors)

    def _embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype("float32")

    def search(self, query: str, k: int) -> list[dict]:
        scores, ids = self.index.search(self._embed([query]), k)
        return [
            {**self.chunks[i], "rank": r + 1, "score": round(float(s), 4)}
            for r, (s, i) in enumerate(zip(scores[0], ids[0]))
            if i != -1
        ]


def format_retrieval(qid: str, question: str, hits: list[dict], k: int) -> str:
    lines = [f"=== {qid} (top_k={k}) {question}"]
    for h in hits:
        preview = h["text"].replace("\n", " ")
        lines.append(f"  #{h['rank']} score={h['score']:.4f} source={h['source']} chunk_id={h['chunk_id']}")
        lines.append(f"     {preview}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- context engineering

def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def engineer_context(hits: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (kept, dropped). Dropped items carry a reason."""
    kept, dropped = [], []
    for h in hits:
        if h["score"] < RELEVANCE_THRESHOLD:
            dropped.append({**h, "reason": f"irrelevant (score < {RELEVANCE_THRESHOLD})"})
            continue
        # overlapping windows and repeated legal headings produce near-copies
        dup_of = next(
            (k for k in kept if len(_words(h["text"]) & _words(k["text"])) / max(1, len(_words(h["text"]) | _words(k["text"]))) >= 0.8),
            None,
        )
        if dup_of:
            dropped.append({**h, "reason": f"duplicate of {dup_of['chunk_id']}"})
            continue
        kept.append(h)

    # group by source (best-scoring source first), then document order inside a source
    best = {}
    for h in kept:
        best[h["source"]] = max(best.get(h["source"], -1), h["score"])
    kept.sort(key=lambda h: (-best[h["source"]], h["position"]))
    return kept, dropped


def context_block(kept: list[dict]) -> str:
    return "\n\n".join(
        f"[{n}] (source: {h['source']}, chunk_id: {h['chunk_id']}, score: {h['score']:.2f})\n{h['text']}"
        for n, h in enumerate(kept, start=1)
    )


# ---------------------------------------------------------------- LLM

def call_llm(messages: list[dict]) -> dict:
    start = time.perf_counter()
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "seed": SEED, "num_ctx": 4096, "num_predict": 300},
        },
        timeout=600,
    )
    r.raise_for_status()
    data = r.json()
    text = re.sub(r"<think>.*?</think>", "", data["message"]["content"], flags=re.S).strip()
    return {
        "answer_raw": text,
        "latency_s": round(time.perf_counter() - start, 2),
        "prompt_tokens": data.get("prompt_eval_count"),
        "output_tokens": data.get("eval_count"),
    }


def normalize_refusal(text: str) -> str:
    return REFUSAL_TEXT if REFUSAL_TEXT.lower() in text.lower() else text


def run_config(config: str, question: str, hits: list[dict]) -> dict:
    record = {"config": config, "retrieved": [_hit_meta(h) for h in hits]}
    if config == "no_rag":
        messages = [{"role": "user", "content": f"Answer concisely.\n\nQuestion: {question}"}]
        record["retrieved"] = []
    elif config == "basic_rag":
        context = "\n\n".join(h["text"] for h in hits)
        messages = [{"role": "user", "content": f"Use the context to answer the question.\n\nContext:\n{context}\n\nQuestion: {question}"}]
        record["context_chunk_ids"] = [h["chunk_id"] for h in hits]
    else:
        kept, dropped = engineer_context(hits)
        record["context_chunk_ids"] = [h["chunk_id"] for h in kept]
        record["dropped"] = [{"chunk_id": d["chunk_id"], "score": d["score"], "reason": d["reason"]} for d in dropped]
        if not kept:
            # nothing relevant survived, so refuse without asking the model
            record.update(answer_raw=REFUSAL_TEXT, answer=REFUSAL_TEXT, refusal_source="retrieval gate",
                          latency_s=0.0, prompt_tokens=0, output_tokens=0, prompt_chars=0)
            return record
        user = f"Context:\n{context_block(kept)}\n\nQuestion: {question}"
        messages = [{"role": "system", "content": GROUNDED_SYSTEM_PROMPT}, {"role": "user", "content": user}]

    record["prompt_chars"] = sum(len(m["content"]) for m in messages)
    record.update(call_llm(messages))
    record["answer"] = normalize_refusal(record["answer_raw"]) if config == "context_rag" else record["answer_raw"]
    if config == "context_rag" and record["answer"] == REFUSAL_TEXT:
        record["refusal_source"] = "model"
    return record


def _hit_meta(h: dict) -> dict:
    return {"rank": h["rank"], "chunk_id": h["chunk_id"], "source": h["source"], "score": h["score"]}


# ---------------------------------------------------------------- evaluation

def _has_all(text: str, keywords: list[str]) -> bool:
    low = text.lower().replace("-", " ")
    return all(k.lower().replace("-", " ") in low for k in keywords)


def evaluate(q: dict, rec: dict, chunk_text_by_id: dict) -> dict:
    answer = rec["answer"]
    refused = answer.strip() == REFUSAL_TEXT
    context_ids = rec.get("context_chunk_ids", [])
    context_text = " ".join(chunk_text_by_id[c] for c in context_ids)

    if rec["config"] == "no_rag":
        retrieval = "n/a"
    elif q["should_refuse"]:
        retrieval = "n/a (no relevant chunk exists)"
    else:
        retrieval = _has_all(context_text, q["evidence_keywords"])

    if q["should_refuse"]:
        correct = refused
    else:
        correct = (not refused) and _has_all(answer, q["answer_keywords"])

    if rec["config"] == "no_rag":
        grounded = "n/a"
    elif refused:
        grounded = True  # a refusal makes no unsupported claim
    else:
        cited = [int(n) for n in re.findall(r"\[(\d+)\]", answer)]
        if rec["config"] == "context_rag" and cited:
            support = " ".join(chunk_text_by_id[context_ids[n - 1]] for n in cited if 0 < n <= len(context_ids))
        else:
            support = context_text
        grounded = bool(q["answer_keywords"]) and _has_all(support, q["answer_keywords"]) and _has_all(answer, q["answer_keywords"])

    refusal_ok = refused if q["should_refuse"] else not refused
    if rec["config"] == "context_rag":
        format_ok = answer == REFUSAL_TEXT if refused else bool(re.search(r"\[\d+\]", answer))
    else:
        format_ok = "n/a"
    return {
        "qid": q["id"],
        "config": rec["config"],
        "correct_retrieval": retrieval,
        "correct_answer": correct,
        "grounded": grounded,
        "refused": refused,
        "refused_when_needed": refusal_ok,
        "format_ok": format_ok,
    }


def _rate(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if isinstance(r[key], bool)]
    return f"{sum(vals)}/{len(vals)}" if vals else "n/a"


def evaluation_markdown(evals: list[dict]) -> str:
    def cell(v):
        return "yes" if v is True else "no" if v is False else v

    lines = [
        "| Q | Config | Correct retrieval | Correct answer | Grounded | Refused when needed |",
        "|---|---|---|---|---|---|",
    ]
    for e in evals:
        lines.append(
            f"| {e['qid']} | {e['config']} | {cell(e['correct_retrieval'])} | {cell(e['correct_answer'])} | "
            f"{cell(e['grounded'])} | {cell(e['refused_when_needed'])} |"
        )
    lines += [
        "",
        "| Config | Accuracy (correct answers) | Faithfulness (grounded) | Format compliance | Robustness (refusal behaviour) |",
        "|---|---|---|---|---|",
    ]
    for config in CONFIGS:
        rows = [e for e in evals if e["config"] == config]
        lines.append(
            f"| {config} | {_rate(rows, 'correct_answer')} | {_rate(rows, 'grounded')} | "
            f"{_rate(rows, 'format_ok')} | {_rate(rows, 'refused_when_needed')} |"
        )
    lines += [
        "",
        "_Automatic keyword-based checks (see rag.py `evaluate`). Q4 is ambiguous by design and should be reviewed by hand._",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- runs

def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def full_run(store: VectorStore, questions: list[dict], sweep_ids: list[str]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    run_at = datetime.now().isoformat(timespec="seconds")
    text_by_id = {c["chunk_id"]: c["text"] for c in store.chunks}
    printouts = [f"Retrieved chunks - run at {run_at} - embedding={EMBEDDING_MODEL_NAME}, chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}\n"]
    by_config = {c: [] for c in CONFIGS}
    evals = []

    for q in questions:
        hits = store.search(q["question"], TOP_K)
        block = format_retrieval(q["id"], q["question"], hits, TOP_K)
        print(block, flush=True)  # retrieval shown before any generation
        printouts.append(block)
        for config in CONFIGS:
            rec = {"qid": q["id"], "question": q["question"], "top_k": TOP_K, **run_config(config, q["question"], hits)}
            by_config[config].append(rec)
            evals.append(evaluate(q, rec, text_by_id))
            print(f"  [{config}] ({rec['latency_s']}s) {rec['answer']}\n", flush=True)

    sweep, sweep_lines = [], ["| Q | k | Retrieved (source, score) | Kept after filtering | Dropped | Evidence in context | Correct answer | Answer |", "|---|---|---|---|---|---|---|---|"]
    for qid in sweep_ids:
        q = next(x for x in questions if x["id"] == qid)
        for k in K_SWEEP:
            hits = store.search(q["question"], k)
            block = format_retrieval(q["id"], q["question"], hits, k)
            print(block, flush=True)
            printouts.append(block)
            rec = {"qid": qid, "question": q["question"], "top_k": k, **run_config("context_rag", q["question"], hits)}
            ev = evaluate(q, rec, text_by_id)
            rec["evaluation"] = ev
            sweep.append(rec)
            retrieved = "; ".join(f"{h['chunk_id']} ({h['score']:.2f})" for h in rec["retrieved"])
            dropped = "; ".join(f"{d['chunk_id']}: {d['reason']}" for d in rec.get("dropped", [])) or "-"
            answer = rec["answer"].replace("|", "/").replace("\n", " ")
            sweep_lines.append(
                f"| {qid} | {k} | {retrieved} | {len(rec['context_chunk_ids'])} | {dropped} | "
                f"{ev['correct_retrieval']} | {ev['correct_answer']} | {answer} |"
            )
            print(f"  [context_rag k={k}] {rec['answer']}\n", flush=True)

    for config in CONFIGS:
        write_jsonl(RAW / f"{config}.jsonl", by_config[config])
    write_jsonl(RAW / "k_sweep.jsonl", sweep)
    (RAW / "retrieved_chunks.txt").write_text("\n".join(printouts), encoding="utf-8")
    (RAW / "k_sweep.md").write_text("\n".join(sweep_lines) + "\n", encoding="utf-8")

    comparison = ["| Q | Type | No RAG | Basic RAG | Context RAG |", "|---|---|---|---|---|"]
    for q in questions:
        answers = [next(r for r in by_config[c] if r["qid"] == q["id"])["answer"].replace("|", "/").replace("\n", " ") for c in CONFIGS]
        comparison.append(f"| {q['id']} | {q['type']} | " + " | ".join(answers) + " |")
    (RAW / "six_question_results.md").write_text(f"Run at {run_at}, model={LLM_MODEL}, top_k={TOP_K}\n\n" + "\n".join(comparison) + "\n", encoding="utf-8")

    refusals = [
        {"qid": r["qid"], "config": r["config"], "answer": r["answer"], "exact_refusal": r["answer"] == REFUSAL_TEXT,
         "refusal_source": r.get("refusal_source")}
        for c in CONFIGS for r in by_config[c] if r["qid"] in {q["id"] for q in questions if q["should_refuse"]}
    ]
    (RAW / "refusals.json").write_text(json.dumps(refusals, indent=2), encoding="utf-8")

    table = evaluation_markdown(evals)
    (RAW / "evaluation_table.md").write_text(f"Run at {run_at}, model={LLM_MODEL}\n\n{table}\n", encoding="utf-8")
    with open(RAW / "evaluation.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(evals[0].keys()))
        writer.writeheader()
        writer.writerows(evals)
    (RAW / "rag_run_meta.json").write_text(json.dumps({
        "run_at": run_at, "llm_model": LLM_MODEL, "embedding_model": EMBEDDING_MODEL_NAME,
        "chunk_size_chars": CHUNK_SIZE, "chunk_overlap_chars": CHUNK_OVERLAP, "top_k": TOP_K, "k_sweep": K_SWEEP,
        "relevance_threshold": RELEVANCE_THRESHOLD, "n_chunks": len(store.chunks),
        "sources": sorted({c["source"] for c in store.chunks}), "seed": SEED,
    }, indent=2), encoding="utf-8")
    print(table)
    print(f"\nSaved RAG outputs to {RAW}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieve-only", action="store_true")
    parser.add_argument("--ask")
    parser.add_argument("--mode", choices=["none", "basic", "context"], default="context")
    parser.add_argument("--k", type=int, default=TOP_K)
    args = parser.parse_args()

    docs = load_corpus()
    chunks = build_chunks(docs)
    print(f"Loaded {len(docs)} documents -> {len(chunks)} chunks (chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP} chars)")
    for d in docs:
        print(f"  {d['source']}: {sum(c['source'] == d['source'] for c in chunks)} chunks")
    store = VectorStore(chunks)

    spec = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    questions = spec["questions"]

    if args.ask:
        hits = store.search(args.ask, args.k)
        print(format_retrieval("ASK", args.ask, hits, args.k))
        config = {"none": "no_rag", "basic": "basic_rag", "context": "context_rag"}[args.mode]
        rec = run_config(config, args.ask, hits)
        print(json.dumps({k: v for k, v in rec.items() if k != "retrieved"}, indent=2))
    elif args.retrieve_only:
        for q in questions:
            for k in ([TOP_K] if q["id"] not in spec["k_sweep_questions"] else K_SWEEP):
                print(format_retrieval(q["id"], q["question"], store.search(q["question"], k), k))
    else:
        full_run(store, questions, spec["k_sweep_questions"])


if __name__ == "__main__":
    sys.exit(main())
