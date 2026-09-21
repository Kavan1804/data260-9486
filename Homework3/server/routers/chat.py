from fastapi import APIRouter, HTTPException
from ..models import ChatRequest, ChatResponse
from ..services.memory_logic import generate_reply

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.user_id or not req.message:
        raise HTTPException(status_code=400, detail="user_id and message required")
    session_id = req.session_id or req.user_id  # default: 1:1 session
    reply, st_used, lt, epi = generate_reply(req.user_id, session_id, req.message)
    return ChatResponse(reply=reply, used_short_term=st_used, used_long_term_summary=lt or None, used_episodic=epi)
