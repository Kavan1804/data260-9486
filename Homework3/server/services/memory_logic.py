from typing import List, Tuple, Dict
import os, json
from .openai_client import get_client, response_model
from .embeddings import embed_texts, top_k_by_embedding
from ..dbimpl import sql as db
from .redis_cache import get_short_term, set_short_term

SHORT_TERM_N = 8
SUMMARIZE_EVERY_USER_MSGS =3

SYSTEM_PRIMER = (
    "You are a helpful teaching assistant inside a demo app that showcases memory. "
    "Keep answers concise and friendly. If the user asks about what the app remembers, explain short-term, long-term, and episodic memory briefly."
)

def _build_context(user_key: str, session_key: str) -> Tuple[List[Dict,], str, List[str]]:
    # short-term from redis or DB
    st = get_short_term(session_key)
    if not st:
        st = db.fetch_recent_messages(session_key, limit=SHORT_TERM_N * 2)
    st = st[-SHORT_TERM_N:]
    # long-term summaries
    lt_session = db.latest_summary(user_key, session_key, scope="session")
    lt_user = db.latest_summary(user_key, None, scope="user")
    long_term_text = ""
    if lt_user:
        long_term_text += f"User lifetime summary:\n{lt_user}\n\n"
    if lt_session:
        long_term_text += f"This session summary:\n{lt_session}\n\n"
    # episodic
    episodes = db.fetch_all_episodes(user_key)
    epi_texts = [e["fact"] for e in episodes]
    return st, long_term_text.strip(), epi_texts

def extract_and_store_episodes(user_key: str, session_key: str, user_text: str):
    client = get_client()
    model = response_model()
    messages = [
        {"role": "system", "content": "Extract up to three brief, factual 'episodes' (facts, preferences, commitments) from the user's message. Output JSON list of objects with keys: fact, importance (0..1). Only include high-signal facts likely useful later."},
        {"role": "user", "content": user_text}
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=250
    )
    import re
    text = (resp.choices[0].message.content or "").strip()

    raw = text
    if "```" in raw:
        parts = raw.split("```")
        # try to grab the middle block if present
        raw = parts[1] if len(parts) >= 2 else raw
    # pull out the first JSON array
    m = re.search(r"\[.*\]", raw, flags=re.S)
    raw_json = m.group(0) if m else raw

    try:
        data = json.loads(raw_json)
        facts = [f for f in data if isinstance(f, dict) and "fact" in f]
    except Exception:
        facts = []
    if not facts:
        return
    # embed and store
    emb = embed_texts([f["fact"] for f in facts])
    for (f, e) in zip(facts, emb):
        importance = float(f.get("importance", 0.5))
        db.save_episode(user_key, session_key, f["fact"], importance, e)

def maybe_summarize(user_key: str, session_key: str):
    # Summarize every N user turns
    user_count = db.count_user_messages(session_key, role="user")
    if user_count % SUMMARIZE_EVERY_USER_MSGS != 0:
        return
    client = get_client()
    model = response_model()
    recent = db.fetch_recent_messages(session_key, limit=100)
    messages = [
        {"role":"system","content":"Summarize the recent conversation in 5-7 bullet points. Capture goals, decisions, preferences, and next steps. Keep it concise but specific."},
        {"role":"user","content": "\n\n".join([f"{m['role']}: {m['content']}" for m in recent])}
    ]
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=400)
    summary_text = (resp.choices[0].message.content or "").strip()

    if summary_text:
        db.save_summary(user_key, session_key, scope="session", text=summary_text)
        # Occasionally refresh the user lifetime summary using session summaries
        lifetime_src = db.latest_summary(user_key, None, scope="user")
        combined = (lifetime_src + "\n\n" if lifetime_src else "") + summary_text
        prompt2 = [
            {"role":"system","content":"Condense the provided session summaries into a single, up-to-date lifetime profile. Keep under 200 words."},
            {"role":"user","content": combined}
        ]
        resp2 = client.chat.completions.create(model=model, messages=prompt2, temperature=0.2, max_tokens=300)
        lt = (resp2.choices[0].message.content or "").strip()
        if lt:
            db.save_summary(user_key, session_key="", scope="user", text=lt)

def generate_reply(user_key: str, session_key: str, user_message: str):
    # Persist the user message
    db.ensure_user_and_session(user_key, session_key)
    db.save_message(user_key, session_key, "user", user_message)

    # Episode extraction (best-effort, non-blocking semantics here but we run inline)
    extract_and_store_episodes(user_key, session_key, user_message)

    # Build memory context
    st, long_term, episodic_texts = _build_context(user_key, session_key)

    # Retrieve top episodic items relevant to this user message
    # Retrieve top-k episodic items relevant to this user message
    episodes_full = db.fetch_all_episodes(user_key)
    episodic_hits = top_k_by_embedding(user_message, episodes_full, k=5)
    episodic_use = [e["fact"] for e in episodic_hits]

    system = SYSTEM_PRIMER + "\n\n" + (f"Long-term memory: {long_term}" if long_term else "")
    messages = [{"role":"system","content":system}]
    for m in st[-8:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role":"user","content": user_message})
    if episodic_use:
        messages.append({"role":"system","content":"Relevant episodic facts: " + "; ".join(episodic_use)})

    client = get_client()
    model = response_model()
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.6, max_tokens=500)
    reply = (resp.choices[0].message.content or "").strip()


    # Save assistant reply
    db.save_message(user_key, session_key, "assistant", reply)

    # Update short-term cache
    st2 = (st + [{"role":"user","content":user_message},{"role":"assistant","content":reply}])[-8:]
    set_short_term(session_key, st2, ttl_seconds=1800)

    # Maybe summarize
    maybe_summarize(user_key, session_key)

    return reply, st2, long_term, episodic_use
