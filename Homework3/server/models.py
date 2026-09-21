from pydantic import BaseModel, Field
from typing import List, Optional, Any

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str

class ChatResponse(BaseModel):
    reply: str
    used_short_term: List[ChatMessage] = Field(default_factory=list)
    used_long_term_summary: Optional[str] = None
    used_episodic: List[str] = Field(default_factory=list)

class MemoryView(BaseModel):
    short_term: List[ChatMessage] = Field(default_factory=list)
    long_term_session_summary: Optional[str] = None
    long_term_user_summary: Optional[str] = None
    episodic: List[str] = Field(default_factory=list)

class AggregateView(BaseModel):
    by_day: Any
    recent_summaries: List[str] = Field(default_factory=list)
