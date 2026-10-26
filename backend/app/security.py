"""HW7 Part 1: JWT bearer auth and role checks (adapted from the DATA 236 Demo 7 project).

Differences from the demo: users come from the MySQL `users` table instead of a fake dict,
passwords are checked with the bcrypt helper the app already had since HW4, and every auth
failure is a 401 (missing token, bad signature, expired token, unknown user) while a valid
token with the wrong role is a 403.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY

from . import crud, models
from .database import get_db

# auto_error=False so a missing header becomes our own 401 (FastAPI's default would be 403).
bearer_scheme = HTTPBearer(auto_error=False)


def _secret() -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not set. Add it to .env (see .env.example).")
    return JWT_SECRET_KEY


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def create_access_token(username: str, role: str, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    """Signed HS256 token with the username (sub), role and an expiry time."""
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": role, "iat": now, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def authenticate(db: Session, username: str, password: str) -> models.User | None:
    """Fetch the user from MySQL and check the bcrypt hash. None means wrong username or password."""
    from .session_crud import verify_password  # bcrypt helper from HW4

    user = crud.get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), db: Session = Depends(get_db)
) -> models.User:
    """Dependency for any authenticated route: a valid, unexpired token for a user that still exists."""
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise unauthorized("Not authenticated: missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise unauthorized("Invalid token")
    user = crud.get_user_by_username(db, payload.get("sub") or "")
    if user is None:
        raise unauthorized("Invalid token: user no longer exists")
    return user


def require_roles(*allowed: str) -> Callable[..., models.User]:
    """Dependency factory: 403 when the token is valid but the role is not in `allowed`.
    The role is read from MySQL, not from the token, so a role change takes effect right away."""

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not allowed here; requires one of: {', '.join(allowed)}",
            )
        return user

    return checker


# Role sets used by the domain routes (HW7 Part 1 II).
any_role = get_current_user
can_write = require_roles("writer", "moderator")
can_delete = require_roles("moderator")
