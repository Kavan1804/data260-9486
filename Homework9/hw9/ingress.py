"""Semantic-cache ingress in front of the HW8 Q&A pipeline (Parts 2 and 3).

ask(query):
  1. embed the query (all-minilm)                         -> embed_ms
  2. KNN search in the Redis vector index (cosine)        -> search_ms
  3. similarity >= threshold:
       check the stored data-version marker (if on)       -> version_ms
       still current -> HIT: return the stored answer, is_cached=True, pipeline not called
       changed       -> delete the entry, go on as a MISS (reason "stale")
  4. MISS: look up the listing facts the question mentions in s9486_rel, run the HW8 pipeline with them,
     store query + embedding + final answer + data-version marker, return is_cached=False.

The data-version marker is "<listing_code>@<fingerprint>" for every LST-xxxxx code in the query, where the
fingerprint is a hash of that listing row (see ListingDatabaseWithCache.fingerprint). General questions that do
not mention a listing get "none" and never go stale this way.
"""

from __future__ import annotations

import re
import time

from hw9.common import log, ms_since
from hw9.embeddings import embed

CODE = re.compile(r"\bLST-\d{5}\b")


def listing_codes(query: str) -> list[str]:
    return sorted(set(CODE.findall(query.upper())))


def facts_block(store, codes: list[str]) -> str:
    """Facts from MySQL that the HW8 Writer gets with the question (it has no database access of its own)."""
    lines = []
    for code in codes:
        f = store.get_listing(code)
        if f is None:
            lines.append(f"- {code}: no listing with this code exists in the database.")
        else:
            lines.append(
                f'- {code}: title "{f["title"]}", address {f["address"]}, available_units={f["available_units"]}, '
                f"landlord {f['landlord_name']} ({f['landlord_company']})"
            )
    return "Facts from the s9486_rel listings database (use these exact values, do not guess others):\n" + "\n".join(
        lines
    )


class SemanticQA:
    def __init__(self, cache, store, pipeline, check_version: bool = True, store_on_miss: bool = True, embedder=None):
        self.cache = cache
        self.store = store
        self.pipeline = pipeline
        self.check_version = check_version
        self.store_on_miss = store_on_miss
        self.embed = embedder or embed

    def data_version(self, codes: list[str]) -> str:
        if not codes:
            return "none"
        return ";".join(f"{c}@{self.store.fingerprint(c)}" for c in codes)

    def lookup(self, query: str) -> dict:
        """Steps 1-3 only (no pipeline call). Used by ask() and by the Part 3 sweep."""
        t = time.perf_counter()
        vec = self.embed(query)
        embed_ms = ms_since(t)
        t = time.perf_counter()
        entry, sim = self.cache.nearest(vec)
        search_ms = ms_since(t)
        return {"vec": vec, "entry": entry, "similarity": sim, "embed_ms": embed_ms, "search_ms": search_ms}

    def ask(self, query: str, threshold: float | None = None) -> dict:
        threshold = self.cache.threshold if threshold is None else threshold
        start = time.perf_counter()
        log("ingress", f"received query={query!r}")
        look = self.lookup(query)
        entry, sim = look["entry"], look["similarity"]
        timings = {"embed_ms": look["embed_ms"], "search_ms": look["search_ms"]}
        matched = entry["query"] if entry else None
        reason = "empty cache" if entry is None else f"best similarity {sim:.4f} < {threshold}"

        if entry is not None and sim >= threshold:
            stale = False
            if self.check_version and entry["data_version"] != "none":
                t = time.perf_counter()
                current = self.data_version(entry["depends_on"].split(","))
                timings["version_ms"] = ms_since(t)
                stale = current != entry["data_version"]
                if stale:
                    self.cache.delete(entry["key"])
                    log(
                        "ingress",
                        f"STALE entry for {matched!r}: stored version {entry['data_version']} != current {current}"
                        " -> entry deleted, treating as a miss",
                    )
                    reason = "stale (data-version changed)"
            if not stale:
                total = ms_since(start)
                log("ingress", f"CACHE HIT similarity={sim:.4f} matched={matched!r} latency={total:.1f} ms")
                return {
                    "query": query,
                    "answer": entry["answer"],
                    "is_cached": True,
                    "similarity": sim,
                    "matched_query": matched,
                    "latency_ms": total,
                    "timings": timings,
                    "data_version": entry["data_version"],
                    "cache_key": entry["key"],
                    "status": entry.get("status", ""),
                }

        log("ingress", f"CACHE MISS ({reason}) -> running the HW8 agent pipeline")
        codes = listing_codes(query)
        question = query if not codes else f"{query}\n\n{facts_block(self.store, codes)}"
        version = self.data_version(codes)
        t = time.perf_counter()
        final = self.pipeline(question)
        timings["pipeline_ms"] = ms_since(t)
        answer = final.get("answer", "")
        cache_key = None
        if self.store_on_miss and answer:
            t = time.perf_counter()
            cache_key = self.cache.store(query, look["vec"], answer, version, codes, final.get("status", ""))
            timings["store_ms"] = ms_since(t)
        total = ms_since(start)
        log("ingress", f"CACHE MISS done: pipeline {timings['pipeline_ms'] / 1000:.1f}s, total latency={total:.1f} ms")
        return {
            "query": query,
            "answer": answer,
            "is_cached": False,
            "similarity": sim,
            "matched_query": matched,
            "latency_ms": total,
            "timings": timings,
            "data_version": version,
            "cache_key": cache_key,
            "status": final.get("status", ""),
            "miss_reason": reason,
            "correlation_id": final.get("correlation_id"),
        }
