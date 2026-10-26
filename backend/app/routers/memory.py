"""HW6 Part 2: POST /api/chat, GET /api/memory/{user_id}, GET /api/aggregate/{user_id}.

Messages that start with /memory, /compact, /dream or /help are Part 4 file-memory
commands: they are answered by backend.app.file_memory and are not stored as chat messages.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .. import file_memory, memory_logic
from ..doc_schema import ChatRequest
from ..mongo import mongo_db

router = APIRouter(prefix="/api", tags=["HW6 chat memory (MongoDB)"])


def get_store(db: Database = Depends(mongo_db)):
    return memory_logic.MongoMemoryStore(db)


@lru_cache
def get_chat_model():
    return memory_logic.default_model()


@lru_cache
def get_embedder():
    return memory_logic.default_embedder()


def _message_out(m: dict) -> dict:
    return {"session_id": m["session_id"], "role": m["role"], "content": m["content"], "created_at": m["created_at"]}


def _summary_out(s: dict | None) -> dict | None:
    if not s:
        return None
    return {"scope": s["scope"], "session_id": s.get("session_id"), "text": s["text"], "created_at": s["created_at"]}


def _episode_out(e: dict) -> dict:
    vec = e.get("embedding") or []
    return {
        "session_id": e.get("session_id"),
        "fact": e["fact"],
        "importance": e["importance"],
        "embedding_model": e.get("embedding_model"),
        "embedding_dim": len(vec),
        "embedding_preview": [round(x, 4) for x in vec[:4]],
        "created_at": e["created_at"],
    }


@router.post("/chat")
def chat(payload: ChatRequest, store=Depends(get_store), model=Depends(get_chat_model), embedder=Depends(get_embedder)):
    try:
        if file_memory.is_command(payload.message):
            recent = (
                store.recent_messages(payload.user_id, payload.session_id, 16)
                if payload.session_id
                else store.user_messages(payload.user_id, 16)
            )
            recent = [{"role": m["role"], "content": m["content"]} for m in recent]
            return {
                "user_id": payload.user_id,
                "session_id": payload.session_id,
                **file_memory.handle_command(payload.message, model, recent),
            }
        return memory_logic.chat_turn(
            store,
            model,
            embedder,
            payload.user_id,
            payload.message,
            session_id=payload.session_id,
            short_term_n=payload.short_term_n,
            policy=payload.policy,
            phase=payload.phase,
            run_id=payload.run_id,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error during chat: {type(exc).__name__}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - usually Ollama not running or the model name is wrong
        raise HTTPException(
            status_code=502,
            detail=f"Model call failed ({type(exc).__name__}: {exc}). Is Ollama running and is OLLAMA_MODEL pulled?",
        )


@router.get("/memory/{user_id}")
def memory(user_id: str, store=Depends(get_store)):
    try:
        return {
            "user_id": user_id,
            "messages": [_message_out(m) for m in store.user_messages(user_id, 16)],
            "latest_session_summary": _summary_out(store.latest_summary(user_id, "session")),
            "latest_lifetime_summary": _summary_out(store.latest_summary(user_id, "user")),
            "episodes": [_episode_out(e) for e in store.episodes(user_id, 20)],
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while reading memory: {type(exc).__name__}")


@router.get("/aggregate/{user_id}")
def aggregate(user_id: str, store=Depends(get_store)):
    try:
        return {
            "user_id": user_id,
            "daily_message_counts": store.daily_counts(user_id),
            "recent_summaries": [_summary_out(s) for s in store.recent_summaries(user_id, 5)],
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail=f"Database error while aggregating: {type(exc).__name__}")
