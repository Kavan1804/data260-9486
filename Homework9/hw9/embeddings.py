"""Query embeddings for the semantic cache.

all-minilm in Ollama is the SentenceTransformers model all-MiniLM-L6-v2 (384 dimensions), served by the same
local Ollama server that runs llama3.2:3b, so no torch/sentence-transformers install is needed on the 8 GB Mac.
Vectors are L2-normalised, so the dot product equals cosine similarity.
"""

from __future__ import annotations

import httpx
import numpy as np

import config

EMBED_MODEL = "all-minilm"
EMBED_DIM = 384
# Keep the small embedding model loaded next to llama3.2:3b. Without this, on the 8 GB Mac Ollama unloaded it
# between calls and the first lookup after a pipeline run took ~34 s (seen in the first Part 2 run).
KEEP_ALIVE = "60m"


def embed(text: str) -> np.ndarray:
    resp = httpx.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": [text], "keep_alive": KEEP_ALIVE},
        timeout=120,
    )
    resp.raise_for_status()
    vec = np.asarray(resp.json()["embeddings"][0], dtype=np.float32)
    if vec.shape != (EMBED_DIM,):
        raise ValueError(f"expected {EMBED_DIM} dims from {EMBED_MODEL}, got {vec.shape}")
    return vec / np.linalg.norm(vec)


def warm_up() -> float:
    """Load the embedding model once before anything is timed. Returns the seconds it took (printed, not timed)."""
    import time

    start = time.perf_counter()
    embed("warm up")
    return round(time.perf_counter() - start, 2)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
