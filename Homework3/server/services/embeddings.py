from typing import List
import numpy as np
from .openai_client import get_client, embedding_model

def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    client = get_client()
    model = embedding_model()
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]

def cosine_sim(a: List[float], b: List[float]) -> float:
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)

def top_k_by_embedding(query: str, candidates: List[dict], k: int = 5) -> List[dict]:
    if not candidates:
        return []
    vecs = embed_texts([query])
    if not vecs:
        return []
    q = vecs[0]
    scored = []
    for c in candidates:
        emb = c.get("embedding")
        if not emb:
            continue
        score = cosine_sim(q, emb)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]
