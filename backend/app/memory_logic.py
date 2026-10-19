"""HW6 Part 2 + 3: short-term, long-term and episodic memory for POST /api/chat.

Storage goes through a small store object (MongoDB for real runs, in-memory for
offline tests) - the same dependency-injection idea as the HW5 listing
repository. The chat model is the HW5 adapter (domain_tools.agent.OllamaModel)
and tests pass a fake model with the same chat() signature.

Token accounting (Part 3):
  prompt_tokens / completion_tokens  - real counts reported by Ollama
                                       (prompt_eval_count / eval_count); None if missing
  *_tokens_est                       - per-component ESTIMATES, ceil(chars / 4);
                                       Ollama only reports a total, so the split is approximate
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import config

SYSTEM_PRIMER = (
    "You are the s9486 rental-housing assistant for the DATA 260 listings app. "
    "Help the user with apartments, rent, move-in dates and landlords. "
    "Use the memory sections below when they are relevant; if you do not know something, say so. "
    "Answer in 2-4 sentences."
)

EXTRACT_PROMPT = (
    "Extract at most 3 short, durable facts about the user from the message below "
    "(preferences, budget, dates, people, places, constraints). Ignore greetings and questions with no facts. "
    'Reply with JSON only: {"facts": [{"fact": "<= 15 words, third person", "importance": 0.0-1.0}]}. '
    'Use {"facts": []} when there is nothing worth remembering.'
)

SESSION_SUMMARY_PROMPT = (
    "Update the running summary of this conversation. Write at most 6 concise bullets starting with '- '. "
    "Keep names, numbers, dates and the user's stated preferences. No introduction."
)

LIFETIME_SUMMARY_PROMPT = (
    "Condense these session summaries into one lifetime profile of the user. Write at most 8 concise bullets "
    "starting with '- '. If two summaries disagree, keep the newer one. No introduction."
)

EMBED_DIM = 256


# ---------- helpers ----------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def approx_tokens(text: str | None) -> int:
    """Local token ESTIMATE (about 4 characters per token for English text)."""
    return math.ceil(len(text) / 4) if text else 0


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---------- embeddings ----------

_STOP = set("a an and are as at be but by for from has have i i'm im in is it its me my of on or so that the "
            "this to was we were what when where which who will with you your".split())


class HashEmbedder:
    """Deterministic local fallback used when OLLAMA_EMBED_MODEL is not set: a hashed
    bag-of-words vector (md5 bucket per word, L2-normalised). Matches shared words,
    not meaning - it is labelled hash-bow-256 in every episode it writes."""

    name = f"hash-bow-{EMBED_DIM}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * EMBED_DIM
            for word in re.findall(r"[a-z0-9$]+", text.lower()):
                if word in _STOP:
                    continue
                word = word[:-1] if len(word) > 3 and word.endswith("s") else word
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OllamaEmbedder:
    """Embeddings from the local Ollama server (/api/embed) with the configured embedding model."""

    def __init__(self, model: str, url: str = config.OLLAMA_URL, timeout_s: float = 60.0):
        self.name = model
        self.url = url.rstrip("/") + "/api/embed"
        self.timeout_s = timeout_s

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        resp = httpx.post(self.url, json={"model": self.name, "input": texts}, timeout=self.timeout_s)
        resp.raise_for_status()
        return [[float(x) for x in v] for v in resp.json()["embeddings"]]


def default_embedder():
    return OllamaEmbedder(config.OLLAMA_EMBED_MODEL) if config.OLLAMA_EMBED_MODEL else HashEmbedder()


def default_model():
    from domain_tools.agent import OllamaModel  # the HW5 adapter

    return OllamaModel(model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX)


def embed_safely(embedder, texts: list[str]) -> tuple[list[list[float]], str]:
    """Embed with the configured embedder; fall back to HashEmbedder if Ollama is unreachable."""
    try:
        return embedder.embed(texts), embedder.name
    except Exception:  # noqa: BLE001 - recorded through the returned model name
        fallback = HashEmbedder()
        return fallback.embed(texts), fallback.name


# ---------- storage ----------

class MemoryStore(Protocol):
    def add_message(self, user_id: str, session_id: str, role: str, content: str) -> Any: ...
    def recent_messages(self, user_id: str, session_id: str, n: int, exclude_id: Any = None) -> list[dict]: ...
    def count_user_messages(self, user_id: str, session_id: str) -> int: ...
    def latest_summary(self, user_id: str, scope: str, session_id: str | None = None) -> dict | None: ...
    def add_summary(self, user_id: str, session_id: str | None, scope: str, text: str) -> None: ...
    def session_summaries(self, user_id: str, limit: int) -> list[dict]: ...
    def count_session_summaries(self, user_id: str) -> int: ...
    def add_episode(self, doc: dict) -> None: ...
    def episodes(self, user_id: str, limit: int) -> list[dict]: ...
    def user_messages(self, user_id: str, limit: int) -> list[dict]: ...
    def daily_counts(self, user_id: str) -> list[dict]: ...
    def recent_summaries(self, user_id: str, limit: int) -> list[dict]: ...


class MongoMemoryStore:
    def __init__(self, db):
        from .mongo import EPISODES, MESSAGES, SUMMARIES

        self.messages = db[MESSAGES]
        self.summaries = db[SUMMARIES]
        self.episodes_col = db[EPISODES]

    def add_message(self, user_id, session_id, role, content):
        doc = {"user_id": user_id, "session_id": session_id, "role": role, "content": content, "created_at": now_utc()}
        return self.messages.insert_one(doc).inserted_id

    def recent_messages(self, user_id, session_id, n, exclude_id=None):
        query: dict = {"user_id": user_id, "session_id": session_id}
        if exclude_id is not None:
            query["_id"] = {"$ne": exclude_id}
        docs = list(self.messages.find(query).sort([("created_at", -1), ("_id", -1)]).limit(n))
        return docs[::-1]  # oldest first

    def count_user_messages(self, user_id, session_id):
        return self.messages.count_documents({"user_id": user_id, "session_id": session_id, "role": "user"})

    def latest_summary(self, user_id, scope, session_id=None):
        query = {"user_id": user_id, "scope": scope}
        if scope == "session" and session_id is not None:
            query["session_id"] = session_id
        return self.summaries.find_one(query, sort=[("created_at", -1), ("_id", -1)])

    def add_summary(self, user_id, session_id, scope, text):
        self.summaries.insert_one({"user_id": user_id, "session_id": session_id, "scope": scope, "text": text,
                                   "created_at": now_utc()})

    def session_summaries(self, user_id, limit):
        return list(self.summaries.find({"user_id": user_id, "scope": "session"})
                    .sort([("created_at", -1), ("_id", -1)]).limit(limit))

    def count_session_summaries(self, user_id):
        return self.summaries.count_documents({"user_id": user_id, "scope": "session"})

    def add_episode(self, doc):
        self.episodes_col.insert_one(doc)

    def episodes(self, user_id, limit):
        return list(self.episodes_col.find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(limit))

    def user_messages(self, user_id, limit):
        docs = list(self.messages.find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(limit))
        return docs[::-1]

    def daily_counts(self, user_id):
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "messages": {"$sum": 1},
                "user_messages": {"$sum": {"$cond": [{"$eq": ["$role", "user"]}, 1, 0]}},
                "assistant_messages": {"$sum": {"$cond": [{"$eq": ["$role", "assistant"]}, 1, 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]
        return [{"date": r["_id"], "messages": r["messages"], "user_messages": r["user_messages"],
                 "assistant_messages": r["assistant_messages"]} for r in self.messages.aggregate(pipeline)]

    def recent_summaries(self, user_id, limit):
        return list(self.summaries.find({"user_id": user_id}).sort([("created_at", -1), ("_id", -1)]).limit(limit))


class InMemoryMemoryStore:
    """Offline stand-in with the same methods (unit tests only)."""

    def __init__(self):
        self.messages: list[dict] = []
        self.summaries: list[dict] = []
        self.episode_docs: list[dict] = []
        self._next = 0

    def _id(self) -> int:
        self._next += 1
        return self._next

    def add_message(self, user_id, session_id, role, content):
        doc = {"_id": self._id(), "user_id": user_id, "session_id": session_id, "role": role, "content": content,
               "created_at": now_utc()}
        self.messages.append(doc)
        return doc["_id"]

    def recent_messages(self, user_id, session_id, n, exclude_id=None):
        docs = [m for m in self.messages
                if m["user_id"] == user_id and m["session_id"] == session_id and m["_id"] != exclude_id]
        return docs[-n:]

    def count_user_messages(self, user_id, session_id):
        return sum(1 for m in self.messages
                   if m["user_id"] == user_id and m["session_id"] == session_id and m["role"] == "user")

    def latest_summary(self, user_id, scope, session_id=None):
        docs = [s for s in self.summaries if s["user_id"] == user_id and s["scope"] == scope
                and (scope != "session" or session_id is None or s["session_id"] == session_id)]
        return docs[-1] if docs else None

    def add_summary(self, user_id, session_id, scope, text):
        self.summaries.append({"_id": self._id(), "user_id": user_id, "session_id": session_id, "scope": scope,
                               "text": text, "created_at": now_utc()})

    def session_summaries(self, user_id, limit):
        return [s for s in self.summaries if s["user_id"] == user_id and s["scope"] == "session"][::-1][:limit]

    def count_session_summaries(self, user_id):
        return len(self.session_summaries(user_id, 10**9))

    def add_episode(self, doc):
        self.episode_docs.append({"_id": self._id(), **doc})

    def episodes(self, user_id, limit):
        return [e for e in self.episode_docs if e["user_id"] == user_id][::-1][:limit]

    def user_messages(self, user_id, limit):
        return [m for m in self.messages if m["user_id"] == user_id][-limit:]

    def daily_counts(self, user_id):
        days: dict[str, Counter] = {}
        for m in self.messages:
            if m["user_id"] == user_id:
                c = days.setdefault(m["created_at"].strftime("%Y-%m-%d"), Counter())
                c["messages"] += 1
                c[f"{m['role']}_messages"] += 1
        return [{"date": d, "messages": c["messages"], "user_messages": c["user_messages"],
                 "assistant_messages": c["assistant_messages"]} for d, c in sorted(days.items())]

    def recent_summaries(self, user_id, limit):
        return [s for s in self.summaries if s["user_id"] == user_id][::-1][:limit]


# ---------- memory logic ----------

def select_window(messages: list[dict], n: int, policy: str = "none") -> list[dict]:
    """Short-term memory: the last n messages (oldest first).
    policy="compress" (Part 3): the newest COMPRESS_KEEP_RECENT messages stay verbatim and
    older ones in the window are clipped to COMPRESS_MAX_CHARS characters."""
    window = [{"role": m["role"], "content": m["content"]} for m in messages[-n:]] if n > 0 else []
    if policy == "compress":
        cut = len(window) - config.COMPRESS_KEEP_RECENT
        for m in window[:max(cut, 0)]:
            if len(m["content"]) > config.COMPRESS_MAX_CHARS:
                m["content"] = m["content"][:config.COMPRESS_MAX_CHARS].rstrip() + " ..."
    return window


def retrieve_episodes(store, embedder, user_id: str, query: str, k: int = config.EPISODIC_TOP_K) -> list[dict]:
    """Top-k stored facts by cosine similarity between the query embedding and each episode
    embedding. Only episodes written by the same embedding model are compared."""
    candidates = store.episodes(user_id, 500)
    if not candidates or k <= 0:
        return []
    [qvec], model_name = embed_safely(embedder, [query])
    scored = []
    for e in candidates:
        if e.get("embedding_model", model_name) != model_name:
            continue
        score = cosine(qvec, e.get("embedding") or [])
        if score > 0:
            scored.append({"fact": e["fact"], "importance": e["importance"], "score": round(score, 4),
                           "session_id": e.get("session_id")})
    scored.sort(key=lambda x: (x["score"], x["importance"]), reverse=True)
    return scored[:k]


def parse_facts(content: str, limit: int = config.MAX_FACTS_PER_MESSAGE) -> list[dict]:
    """Read {"facts": [{"fact", "importance"}]} from a model reply; bad JSON -> no facts."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = obj.get("facts", []) if isinstance(obj, dict) else obj if isinstance(obj, list) else []
    facts, seen = [], set()
    for item in items:
        if isinstance(item, str):
            item = {"fact": item, "importance": 0.5}
        if not isinstance(item, dict):
            continue
        fact = " ".join(str(item.get("fact", "")).split())[:200]
        try:
            importance = float(item.get("importance", 0.5))
        except (TypeError, ValueError):
            importance = 0.5
        if fact and fact.lower() not in seen:
            seen.add(fact.lower())
            facts.append({"fact": fact, "importance": round(min(max(importance, 0.0), 1.0), 2)})
    return facts[:limit]


def _call(model, messages: list[dict], usage: dict, fmt: str | None = None) -> str:
    """Model call for memory upkeep (extraction / summaries); its tokens go to the aux_* counters."""
    reply = model.chat(messages, [], fmt=fmt) if fmt else model.chat(messages, [])
    usage["aux_calls"] += 1
    usage["aux_prompt_tokens"] += reply.get("prompt_tokens") or 0
    usage["aux_completion_tokens"] += reply.get("completion_tokens") or 0
    return (reply.get("content") or "").strip()


def extract_and_store_facts(store, model, embedder, user_id: str, session_id: str, message: str, usage: dict) -> list[dict]:
    content = _call(model, [{"role": "system", "content": EXTRACT_PROMPT},
                            {"role": "user", "content": message}], usage, fmt="json")
    facts = parse_facts(content)
    if not facts:
        return []
    vectors, model_name = embed_safely(embedder, [f["fact"] for f in facts])
    for f, vec in zip(facts, vectors):
        store.add_episode({"user_id": user_id, "session_id": session_id, "fact": f["fact"],
                           "importance": f["importance"], "embedding": vec, "embedding_model": model_name,
                           "created_at": now_utc()})
    return facts


def should_summarize(user_message_count: int, every: int = config.SUMMARIZE_EVERY_USER_MSGS) -> bool:
    return every > 0 and user_message_count > 0 and user_message_count % every == 0


def maybe_summarize(store, model, user_id: str, session_id: str, user_message_count: int, usage: dict) -> dict:
    """Every SUMMARIZE_EVERY_USER_MSGS user messages write a session summary; after every
    LIFETIME_EVERY_SESSION_SUMMARIES session summaries condense them into the lifetime summary."""
    made = {"session_summary_created": False, "lifetime_summary_created": False}
    if not should_summarize(user_message_count):
        return made
    every = config.SUMMARIZE_EVERY_USER_MSGS
    recent = store.recent_messages(user_id, session_id, 2 * every)
    previous = store.latest_summary(user_id, "session", session_id)
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    prompt = (f"Previous summary:\n{previous['text']}\n\n" if previous else "") + f"Recent messages:\n{transcript}"
    text = _call(model, [{"role": "system", "content": SESSION_SUMMARY_PROMPT}, {"role": "user", "content": prompt}], usage)
    if text:
        store.add_summary(user_id, session_id, "session", text)
        made["session_summary_created"] = True

    if made["session_summary_created"] and store.count_session_summaries(user_id) % config.LIFETIME_EVERY_SESSION_SUMMARIES == 0:
        sessions = store.session_summaries(user_id, 6)[::-1]  # oldest first, newest last
        lifetime = store.latest_summary(user_id, "user")
        body = "\n\n".join(f"Session {s['session_id']}:\n{s['text']}" for s in sessions)
        if lifetime:
            body = f"Current lifetime summary:\n{lifetime['text']}\n\n{body}"
        text = _call(model, [{"role": "system", "content": LIFETIME_SUMMARY_PROMPT}, {"role": "user", "content": body}], usage)
        if text:
            store.add_summary(user_id, None, "user", text)
            made["lifetime_summary_created"] = True
    return made


def build_prompt(session_summary: str | None, lifetime_summary: str | None, window: list[dict],
                 message: str, episodes: list[dict], primer: str = SYSTEM_PRIMER) -> tuple[list[dict], dict]:
    """Prompt = system primer + long-term summaries + episodic facts (system message),
    then the short-term window, then the current message. Returns (messages, component texts)."""
    long_term = ""
    if lifetime_summary:
        long_term += f"Lifetime summary of this user:\n{lifetime_summary}\n"
    if session_summary:
        long_term += f"Summary of this session so far:\n{session_summary}\n"
    episodic = "\n".join(f"- {e['fact']}" for e in episodes)

    system = primer
    if long_term:
        system += "\n\n## Long-term memory\n" + long_term.strip()
    if episodic:
        system += "\n\n## Relevant facts from earlier messages\n" + episodic
    messages = [{"role": "system", "content": system}, *window, {"role": "user", "content": message}]
    parts = {
        "system_primer": primer,
        "long_term_summary": long_term,
        "short_term_window": "\n".join(m["content"] for m in window),
        "episodic_facts": episodic,
        "current_message": message,
    }
    return messages, parts


def append_usage_log(row: dict, path: Path | None) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def chat_turn(
    store,
    model,
    embedder,
    user_id: str,
    message: str,
    session_id: str | None = None,
    short_term_n: int | None = None,
    policy: str = "none",
    phase: str = "chat",
    run_id: str | None = None,
    log_path: Path | None = config.CHAT_USAGE_LOG,
) -> dict:
    """One POST /api/chat turn (steps numbered as in the HW6 PDF)."""
    started = time.perf_counter()
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    n = short_term_n or config.SHORT_TERM_N
    usage = {"aux_calls": 0, "aux_prompt_tokens": 0, "aux_completion_tokens": 0}

    # 1. save the user message
    msg_id = store.add_message(user_id, session_id, "user", message)
    turn = store.count_user_messages(user_id, session_id)
    # 2. short-term window (the current message is added separately below)
    window = select_window(store.recent_messages(user_id, session_id, n, exclude_id=msg_id), n, policy)
    # 3. latest session summary + lifetime summary
    session_doc = store.latest_summary(user_id, "session", session_id)
    lifetime_doc = store.latest_summary(user_id, "user")
    session_summary = session_doc["text"] if session_doc else None
    lifetime_summary = lifetime_doc["text"] if lifetime_doc else None
    # 4. top-k episodic facts by cosine similarity
    episodes = retrieve_episodes(store, embedder, user_id, message)
    # 5. compose the prompt and call the local model through the HW5 adapter
    messages, parts = build_prompt(session_summary, lifetime_summary, window, message, episodes)
    t0 = time.perf_counter()
    reply = model.chat(messages, [])
    model_latency_ms = (time.perf_counter() - t0) * 1000
    answer = (reply.get("content") or "").strip()
    # 6. save the assistant reply
    store.add_message(user_id, session_id, "assistant", answer)
    # 7. episodic facts from this user message (embedded and stored)
    facts = extract_and_store_facts(store, model, embedder, user_id, session_id, message, usage)
    # 8. session summary every M user messages, lifetime summary occasionally
    made = maybe_summarize(store, model, user_id, session_id, turn, usage)
    latency_ms = (time.perf_counter() - started) * 1000

    prompt_tokens = reply.get("prompt_tokens")
    completion_tokens = reply.get("completion_tokens")
    row = {
        "timestamp": now_utc().isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "phase": phase,
        "user_id": user_id,
        "session_id": session_id,
        "turn": turn,
        "short_term_n": n,
        "policy": policy,
        "model": getattr(model, "name", "unknown"),
        "embedding_model": getattr(embedder, "name", "unknown"),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_source": "ollama" if prompt_tokens is not None else "estimate_only",
        "prompt_tokens_est": approx_tokens("\n".join(m["content"] for m in messages)),
        "completion_tokens_est": approx_tokens(answer),
        "system_primer_tokens_est": approx_tokens(parts["system_primer"]),
        "long_term_summary_tokens_est": approx_tokens(parts["long_term_summary"]),
        "short_term_window_tokens_est": approx_tokens(parts["short_term_window"]),
        "episodic_facts_tokens_est": approx_tokens(parts["episodic_facts"]),
        "current_message_tokens_est": approx_tokens(parts["current_message"]),
        "window_messages": len(window),
        "episodes_retrieved": len(episodes),
        **usage,
        "model_latency_ms": round(model_latency_ms, 1),
        "latency_ms": round(latency_ms, 1),
        **made,
    }
    append_usage_log(row, log_path)

    return {
        "reply": answer,
        "user_id": user_id,
        "session_id": session_id,
        "turn": turn,
        "memory_used": {
            "short_term": {"count": len(window), "short_term_n": n, "policy": policy, "messages": window},
            "session_summary": session_summary,
            "lifetime_summary": lifetime_summary,
            "long_term_summary": parts["long_term_summary"] or None,
            "episodic_facts": episodes,
        },
        "memory_written": {"facts_extracted": facts, **made},
        "usage": row,
    }
