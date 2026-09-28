import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.orm import Session

from config import SESSION_TTL_MINUTES

from .models import SessionToken


def utcnow() -> datetime:
    # MySQL DATETIME has no timezone, so everything is stored as naive UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session(db: Session, user_id: int) -> SessionToken:
    now = utcnow()
    row = SessionToken(
        id=secrets.token_hex(32),  # 256-bit random token, no user data inside
        user_id=user_id,
        created_at=now,
        expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session(db: Session, token: str) -> SessionToken | None:
    s = db.get(SessionToken, token)
    if not s:
        return None
    if s.expires_at < utcnow():
        db.delete(s)
        db.commit()
        return None
    return s


def delete_session(db: Session, token: str) -> bool:
    s = db.get(SessionToken, token)
    if not s:
        return False
    db.delete(s)
    db.commit()
    return True
