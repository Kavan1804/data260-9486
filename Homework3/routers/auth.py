import time
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND

from config import DOMAIN_NAME, IDLE_TIMEOUT_SECONDS

# Behaves like a mini FastAPI app; wired into main.py with app.include_router()
router = APIRouter()

templates = Jinja2Templates(directory="templates")

# Hardcoded credentials for local manual verification only.
# A real deployment would check a user database with hashed passwords.
VALID_USERNAME = "admin"
VALID_PASSWORD = "password"


def _session_status(request: Request):
    """Return ("active", user), ("expired", None), or ("none", None).

    Idle timeout is not something Starlette's SessionMiddleware tracks on its
    own (max_age is a fixed cookie lifetime, not an idle window), so the last
    active time is stored inside the session and checked on every request to
    a protected route.
    """
    user = request.session.get("user")
    if not user:
        return "none", None

    last_active = request.session.get("last_active")
    if last_active is None or time.time() - last_active > IDLE_TIMEOUT_SECONDS:
        request.session.clear()
        return "expired", None

    request.session["last_active"] = time.time()  # sliding idle window
    return "active", user


@router.get("/")
def home(request: Request):
    _, user = _session_status(request)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"user": user, "domain_name": DOMAIN_NAME},
    )


@router.get("/login")
def login_page(request: Request, error: Optional[str] = None, expired: Optional[str] = None):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "domain_name": DOMAIN_NAME,
            "show_invalid_alert": error == "1",
            "show_expired_alert": expired == "1",
        },
    )


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == VALID_USERNAME and password == VALID_PASSWORD:
        request.session["user"] = username
        request.session["last_active"] = time.time()
        return RedirectResponse(url="/dashboard", status_code=HTTP_302_FOUND)

    # Invalid credentials: redirect back with a flag the template turns into
    # a Bootstrap alert, instead of silently reloading the empty form.
    return RedirectResponse(url="/login?error=1", status_code=HTTP_302_FOUND)


@router.get("/dashboard")
def dashboard(request: Request):
    status, user = _session_status(request)

    if status == "expired":
        return RedirectResponse(url="/login?expired=1", status_code=HTTP_302_FOUND)
    if status == "none":
        return RedirectResponse(url="/login", status_code=HTTP_302_FOUND)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "domain_name": DOMAIN_NAME,
            "idle_timeout": IDLE_TIMEOUT_SECONDS,
        },
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=HTTP_302_FOUND)
