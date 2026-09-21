"""Retrieval-only LlamaIndex pipelines: Token / Semantic / Sentence-window.

Importing this module does not download anything. The embedding model and
the LlamaIndex node parsers are only touched inside the functions below, so
this file can be imported (e.g. by compute_metrics.py) without triggering a
Hugging Face download or requiring the corpus to exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from config import (
    EMBEDDING_MODEL_NAME,
    SEMANTIC_BREAKPOINT_PERCENTILE,
    SEMANTIC_BUFFER_SIZE,
    SENTENCE_WINDOW_SIZE,
    TOKEN_CHUNK_OVERLAP,
    TOKEN_CHUNK_SIZE,
    TOP_K,
)

Technique = Literal["token", "semantic", "sentence_window"]


def get_embed_model():
    """Construct the shared HuggingFace sentence embedding model.

    Requires sentence-transformers and llama-index-embeddings-huggingface to
    be installed, and downloads sentence-transformers/all-MiniLM-L6-v2 from
    Hugging Face on first use.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    return HuggingFaceEmbedding(model_name=EMBEDDING_MODEL_NAME)


def load_corpus(corpus_dir: str | Path):
    """Load every .txt file in corpus_dir as one LlamaIndex Document per file."""
    from llama_index.core import Document

    corpus_dir = Path(corpus_dir)
    documents = []
    for path in sorted(corpus_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        documents.append(Document(text=text, metadata={"source_file": path.name}))
    return documents


def build_nodes(documents, technique: Technique, embed_model=None):
    """Chunk documents into nodes using the requested technique."""
    embed_model = embed_model or get_embed_model()

    if technique == "token":
        from llama_index.core.node_parser import TokenTextSplitter

        splitter = TokenTextSplitter(
            chunk_size=TOKEN_CHUNK_SIZE,
            chunk_overlap=TOKEN_CHUNK_OVERLAP,
        )
        return splitter.get_nodes_from_documents(documents)

    if technique == "semantic":
        from llama_index.core.node_parser import SemanticSplitterNodeParser

        splitter = SemanticSplitterNodeParser(
            buffer_size=SEMANTIC_BUFFER_SIZE,
            breakpoint_percentile_threshold=SEMANTIC_BREAKPOINT_PERCENTILE,
            embed_model=embed_model,
        )
        return splitter.get_nodes_from_documents(documents)

    if technique == "sentence_window":
        from llama_index.core.node_parser import SentenceWindowNodeParser

        splitter = SentenceWindowNodeParser.from_defaults(
            window_size=SENTENCE_WINDOW_SIZE,
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
        return splitter.get_nodes_from_documents(documents)

    raise ValueError(f"Unknown technique: {technique}")


def build_index(nodes, embed_model=None):
    """Build an in-memory VectorStoreIndex (SimpleVectorStore) over nodes."""
    from llama_index.core import VectorStoreIndex

    embed_model = embed_model or get_embed_model()
    return VectorStoreIndex(nodes, embed_model=embed_model)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


@dataclass
class RetrievedRow:
    rank: int
    store_score: float | None
    cosine_sim: float
    chunk_len: int
    preview: str
    source_file: str | None


def retrieve_and_score(index, technique: str, query: str, k: int = TOP_K, embed_model=None):
    """Retrieval-only helper required by HW3 Part 2.

    Prints the query embedding's dimension and first 8 values, retrieves the
    top-k nodes, explicitly re-embeds their text to compute cosine similarity
    against the query embedding (rather than trusting the store score alone),
    and prints a rank/store_score/cosine_sim/chunk_len/preview table plus the
    query-vector and stacked doc-vector shapes.

    Returns (rows, latency_ms) where rows is a list of dicts matching that
    table, ready to be written to reports/hw03/raw/.
    """
    embed_model = embed_model or get_embed_model()

    query_vec = np.array(embed_model.get_query_embedding(query))
    print(f"[{technique}] query embedding dim: {query_vec.shape[0]}")
    print(f"[{technique}] query embedding first 8 values: {query_vec[:8].tolist()}")

    retriever = index.as_retriever(similarity_top_k=k)

    start = time.perf_counter()
    results = retriever.retrieve(query)
    latency_ms = (time.perf_counter() - start) * 1000

    doc_texts = [node.get_content() for node in results]
    if doc_texts:
        doc_vecs = np.array(embed_model.get_text_embedding_batch(doc_texts))
    else:
        doc_vecs = np.zeros((0, query_vec.shape[0]))

    print(f"[{technique}] query vector shape: {query_vec.shape}")
    print(f"[{technique}] doc vectors shape: {doc_vecs.shape}")

    rows = []
    print(f"[{technique}] rank | store_score | cosine_sim | chunk_len | preview")
    for rank, (node_with_score, doc_vec) in enumerate(zip(results, doc_vecs), start=1):
        text = node_with_score.get_content()
        cos = cosine_similarity(query_vec, doc_vec)
        preview = text[:160].replace("\n", " ")
        row = {
            "rank": rank,
            "store_score": float(node_with_score.score) if node_with_score.score is not None else None,
            "cosine_sim": cos,
            "chunk_len": len(text),
            "preview": preview,
            "source_file": node_with_score.node.metadata.get("source_file"),
        }
        rows.append(row)
        print(f"[{technique}] {rank} | {row['store_score']} | {cos:.4f} | {row['chunk_len']} | {preview}")

    return rows, latency_ms
