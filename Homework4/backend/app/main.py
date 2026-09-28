import time

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from config import (
    DOMAIN_NAME,
    FRONTEND_ORIGINS,
    PORT_BASE,
    SESSION_COOKIE_NAME,
    SESSION_TTL_MINUTES,
)

from . import crud, models, schema
from .database import get_db
from .query_counter import count_queries
from .session_crud import create_session, delete_session, get_session, verify_password

app = FastAPI(title=f"DATA 260 HW4 - {DOMAIN_NAME}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-SQL-Count", "X-Handler-Time-ms"],
)


def require_session(request: Request, db: Session = Depends(get_db)) -> models.SessionToken:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login required")
    s = get_session(db, token)
    if not s:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return s


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Listing not found")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Auth ----------

@app.post("/auth/login", response_model=schema.UserOut)
def login(payload: schema.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    s = create_session(db, user_id=user.id)
    # Cookie holds only the random token; user data stays in MySQL.
    # secure=False because the local dev setup is plain http://localhost.
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=s.id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_TTL_MINUTES * 60,
        path="/",
    )
    return user


@app.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(db, token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"message": "logged out"}


@app.get("/auth/me", response_model=schema.UserOut)
def me(session: models.SessionToken = Depends(require_session), db: Session = Depends(get_db)):
    user = db.get(models.User, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


# ---------- Part 3: N+1 list endpoints ----------
# Declared before /listings/{listing_id} so "naive"/"fixed" are not parsed as ids.

def _page_response(version: str, page: int, page_size: int, loader, db: Session, response: Response):
    start = time.perf_counter()
    with count_queries() as sql_count:
        items = loader(db, page, page_size)
        # Serialize inside the block so any lazy load would also be counted.
        body = schema.ListingPage(
            version=version,
            page=page,
            page_size=page_size,
            count=len(items),
            items=[schema.ListingWithInquiries.model_validate(i) for i in items],
        )
    response.headers["X-SQL-Count"] = str(sql_count[0])
    response.headers["X-Handler-Time-ms"] = f"{(time.perf_counter() - start) * 1000:.3f}"
    return body


@app.get("/listings/naive", response_model=schema.ListingPage)
def list_naive(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    return _page_response("naive", page, page_size, crud.list_listings_naive, db, response)


@app.get("/listings/fixed", response_model=schema.ListingPage)
def list_fixed(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    return _page_response("fixed", page, page_size, crud.list_listings_fixed, db, response)


# ---------- Part 2: listing CRUD (all protected) ----------

@app.post("/listings", response_model=schema.ListingOut, status_code=status.HTTP_201_CREATED)
def add_listing(payload: schema.ListingCreate, db: Session = Depends(get_db), _session=Depends(require_session)):
    return crud.create_listing(db, payload)


@app.get("/listings", response_model=list[schema.ListingOut])
def list_listings(
    skip: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    return crud.get_listings(db, skip, limit)


@app.get("/listings/{listing_id}", response_model=schema.ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db), _session=Depends(require_session)):
    listing = crud.get_listing(db, listing_id)
    if not listing:
        raise not_found()
    return listing


@app.put("/listings/{listing_id}", response_model=schema.ListingOut)
def edit_listing(
    listing_id: int,
    payload: schema.ListingUpdate,
    db: Session = Depends(get_db),
    _session=Depends(require_session),
):
    listing = crud.update_listing(db, listing_id, payload)
    if not listing:
        raise not_found()
    return listing


@app.delete("/listings/{listing_id}", response_model=schema.ListingOut)
def remove_listing(listing_id: int, db: Session = Depends(get_db), _session=Depends(require_session)):
    listing = crud.delete_listing(db, listing_id)
    if not listing:
        raise not_found()
    return listing


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=PORT_BASE, reload=True)
