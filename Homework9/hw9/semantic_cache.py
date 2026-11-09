"""Redis-backed semantic cache: one HASH per cached query plus a Redis Query Engine vector index.

Keys:   s9486:<namespace>:entry:<id>    HASH  query, answer, embedding (float32 bytes), data_version, depends_on, ...
Index:  s9486:idx:<namespace>           FT index over that key prefix, embedding = VECTOR FLAT, COSINE, 384 dims

Redis returns the cosine *distance* (1 - cosine similarity) for a KNN query, so similarity = 1 - distance.
"""

from __future__ import annotations

import time
import uuid

import numpy as np
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

from hw9.common import delete_prefix, key
from hw9.embeddings import EMBED_DIM

RETURN_FIELDS = ("query", "answer", "data_version", "depends_on", "status", "created_at", "dist")


class RedisSemanticCache:
    def __init__(self, client, namespace: str = "semcache", threshold: float = 0.85):
        self.r = client
        self.namespace = namespace
        self.threshold = threshold
        self.entry_prefix = key(namespace, "entry") + ":"
        self.index_name = key("idx", namespace)
        self.ensure_index()

    def ensure_index(self) -> None:
        try:
            self.r.ft(self.index_name).info()
        except ResponseError:
            self.r.ft(self.index_name).create_index(
                [
                    TextField("query"),
                    TagField("data_version"),
                    TagField("depends_on"),
                    VectorField(
                        "embedding", "FLAT", {"TYPE": "FLOAT32", "DIM": EMBED_DIM, "DISTANCE_METRIC": "COSINE"}
                    ),
                ],
                definition=IndexDefinition(prefix=[self.entry_prefix], index_type=IndexType.HASH),
            )

    def nearest(self, vec: np.ndarray) -> tuple[dict | None, float]:
        """Closest cached query and its cosine similarity (None, 0.0 when the cache is empty)."""
        q = (
            Query("*=>[KNN 1 @embedding $vec AS dist]")
            .sort_by("dist")
            .return_fields(*RETURN_FIELDS)
            .paging(0, 1)
            .dialect(2)
        )
        res = self.r.ft(self.index_name).search(q, query_params={"vec": vec.astype(np.float32).tobytes()})
        if not res.docs:
            return None, 0.0
        doc = res.docs[0]
        entry = {f: _text(getattr(doc, f, "")) for f in RETURN_FIELDS}
        entry["key"] = _text(doc.id)
        return entry, round(1.0 - float(entry["dist"]), 4)

    def store(
        self, query: str, vec: np.ndarray, answer: str, data_version: str, depends_on: list[str], status: str = ""
    ) -> str:
        k = self.entry_prefix + uuid.uuid4().hex[:12]
        self.r.hset(
            k,
            mapping={
                "query": query,
                "answer": answer,
                "embedding": vec.astype(np.float32).tobytes(),
                "data_version": data_version,
                "depends_on": ",".join(depends_on),
                "status": status,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        return k

    def get(self, entry_key: str) -> dict:
        raw = self.r.hgetall(entry_key)
        return {_text(k): _text(v) for k, v in raw.items() if _text(k) != "embedding"}

    def delete(self, entry_key: str) -> int:
        return self.r.delete(entry_key)

    def size(self) -> int:
        return int(self.r.ft(self.index_name).info()["num_docs"])

    def clear(self) -> int:
        """Drop this namespace's index and entries (only keys under s9486:<namespace>:)."""
        try:
            self.r.ft(self.index_name).dropindex(delete_documents=False)
        except ResponseError:
            pass
        n = delete_prefix(self.r, self.entry_prefix + "*")
        self.ensure_index()
        return n


def _text(v) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)
