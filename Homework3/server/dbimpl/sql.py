from __future__ import annotations
import os, json, datetime as dt
from typing import List, Optional, Tuple
from sqlalchemy import create_engine, Integer, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy.sql import func

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite")
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/memory.db")

def _build_url():
    if DB_BACKEND == "postgres":
        host = os.getenv("POSTGRES_HOST", "postgres")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "memorydb")
        user = os.getenv("POSTGRES_USER", "memory")
        pw = os.getenv("POSTGRES_PASSWORD", "memorypw")
        return f"postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}"
    # default sqlite
    os.makedirs(os.path.dirname(SQLITE_PATH), exist_ok=True)
    return f"sqlite:///{SQLITE_PATH}"

engine = create_engine(_build_url(), echo=False, future=True)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SessionRec(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_key: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    user_key: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Summary(Base):
    __tablename__ = "summaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[str] = mapped_column(String(128), index=True)
    user_key: Mapped[str] = mapped_column(String(128), index=True)
    scope: Mapped[str] = mapped_column(String(16))  # "session" or "user"
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Episode(Base):
    __tablename__ = "episodes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_key: Mapped[str] = mapped_column(String(128), index=True)
    session_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fact: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column()  # 0..1
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of floats
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

def init_db():
    Base.metadata.create_all(engine)

def get_session() -> Session:
    return Session(engine)

def save_message(user_key: str, session_key: str, role: str, content: str):
    with get_session() as s:
        s.add(Message(user_key=user_key, session_key=session_key, role=role, content=content))
        s.commit()

def fetch_recent_messages(session_key: str, limit: int = 20):
    with get_session() as s:
        rows = s.query(Message).filter(Message.session_key==session_key).order_by(Message.id.desc()).limit(limit).all()
        rows = list(reversed(rows))
        return [{"role": r.role, "content": r.content} for r in rows]

def count_user_messages(session_key: str, role: Optional[str] = "user"):
    with get_session() as s:
        q = s.query(Message).filter(Message.session_key==session_key)
        if role:
            q = q.filter(Message.role==role)
        return q.count()

def save_summary(user_key: str, session_key: str, scope: str, text: str):
    with get_session() as s:
        s.add(Summary(user_key=user_key, session_key=session_key, scope=scope, text=text))
        s.commit()

def latest_summary(user_key: str, session_key: Optional[str], scope: str) -> Optional[str]:
    with get_session() as s:
        q = s.query(Summary).filter(Summary.user_key==user_key, Summary.scope==scope)
        if session_key:
            q = q.filter(Summary.session_key==session_key)
        row = q.order_by(Summary.id.desc()).first()
        return row.text if row else None

def save_episode(user_key: str, session_key: Optional[str], fact: str, importance: float, embedding: Optional[list]):
    with get_session() as s:
        s.add(Episode(user_key=user_key, session_key=session_key, fact=fact, importance=importance, embedding=json.dumps(embedding) if embedding else None))
        s.commit()

def fetch_all_episodes(user_key: str):
    with get_session() as s:
        eps = s.query(Episode).filter(Episode.user_key==user_key).order_by(Episode.id.desc()).all()
        out = []
        for e in eps:
            emb = json.loads(e.embedding) if e.embedding else None
            out.append({"fact": e.fact, "importance": e.importance, "embedding": emb, "created_at": e.created_at.isoformat()})
        return out

def aggregate_counts_by_day(user_key: str):
    with get_session() as s:
        rows = s.query(Message).filter(Message.user_key==user_key).all()
        by_day = {}
        for r in rows:
            day = r.created_at.date().isoformat()
            by_day[day] = by_day.get(day, 0) + 1
        return by_day

def ensure_user_and_session(user_key: str, session_key: str):
    with get_session() as s:
        u = s.query(User).filter(User.user_key==user_key).first()
        if not u:
            s.add(User(user_key=user_key))
        sess = s.query(SessionRec).filter(SessionRec.session_key==session_key).first()
        if not sess:
            s.add(SessionRec(session_key=session_key, user_key=user_key))
        s.commit()
