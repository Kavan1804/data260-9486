import time

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_MINUTES, DOMAIN_NAME, FRONTEND_ORIGINS, PORT_BASE

from . import crud, models, schema
from .database import get_db
from .query_counter import count_queries
from .routers import bikeshare, listing_docs, memory
from .security import any_role, authenticate, can_delete, can_write, create_access_token

app = FastAPI(title=f"DATA 260 - {DOMAIN_NAME}")

# HW6: MongoDB routes under /api (listing documents, chat memory). They do not use the
# MySQL session cookie so they can be exercised from cURL/Postman as the HW6 PDF describes.
app.include_router(listing_docs.router)
app.include_router(memory.router)
# HW7 Part 4: bike-share ReAct agent for the /bikeshare page.
app.include_router(bikeshare.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-SQL-Count", "X-Handler-Time-ms"],
)


def not_found(entity: str = "Listing", entity_id: int | None = None) -> HTTPException:
    suffix = f" {entity_id}" if entity_id is not None else ""
    return HTTPException(status_code=404, detail=f"{entity}{suffix} not found")


@app.exception_handler(crud.ConflictError)
def conflict_handler(_request: Request, exc: crud.ConflictError):
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(crud.InvalidReferenceError)
def invalid_reference_handler(_request: Request, exc: crud.InvalidReferenceError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


# Shared pagination parameters for every list endpoint.
def page_params(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)) -> tuple[int, int]:
    return skip, limit


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Auth (HW7: JWT bearer tokens; the HW4 session cookie is kept only at the hw4 tag) ----------


@app.post("/auth/login", response_model=schema.TokenOut)
def login(payload: schema.LoginRequest, db: Session = Depends(get_db)):
    # Same message for unknown user and wrong password, so the response does not reveal which one it was.
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=401, detail="Invalid username or password", headers={"WWW-Authenticate": "Bearer"}
        )
    token = create_access_token(user.username, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "role": user.role,
    }


@app.get("/auth/me", response_model=schema.UserOut)
def me(user: models.User = Depends(any_role)):
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
    _user=Depends(any_role),
):
    return _page_response("naive", page, page_size, crud.list_listings_naive, db, response)


@app.get("/listings/fixed", response_model=schema.ListingPage)
def list_fixed(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=500),
    db: Session = Depends(get_db),
    _user=Depends(any_role),
):
    return _page_response("fixed", page, page_size, crud.list_listings_fixed, db, response)


# ---------- HW5: landlord CRUD + relationship query (all protected) ----------


@app.post("/landlords", response_model=schema.LandlordOut, status_code=status.HTTP_201_CREATED)
def add_landlord(payload: schema.LandlordCreate, db: Session = Depends(get_db), _user=Depends(can_write)):
    return crud.create_landlord(db, payload)


@app.get("/landlords", response_model=schema.Page[schema.LandlordOut])
def list_landlords(page=Depends(page_params), db: Session = Depends(get_db), _user=Depends(any_role)):
    return crud.list_landlords(db, *page)


@app.get("/landlords/{landlord_id}", response_model=schema.LandlordOut)
def get_landlord(landlord_id: int, db: Session = Depends(get_db), _user=Depends(any_role)):
    landlord = crud.get_landlord(db, landlord_id)
    if not landlord:
        raise not_found("Landlord", landlord_id)
    return landlord


@app.put("/landlords/{landlord_id}", response_model=schema.LandlordOut)
def edit_landlord(
    landlord_id: int,
    payload: schema.LandlordUpdate,
    db: Session = Depends(get_db),
    _user=Depends(can_write),
):
    landlord = crud.update_landlord(db, landlord_id, payload)
    if not landlord:
        raise not_found("Landlord", landlord_id)
    return landlord


@app.delete("/landlords/{landlord_id}", response_model=schema.LandlordOut)
def remove_landlord(landlord_id: int, db: Session = Depends(get_db), _user=Depends(can_delete)):
    landlord = crud.delete_landlord(db, landlord_id)  # 409 while the landlord still owns listings
    if not landlord:
        raise not_found("Landlord", landlord_id)
    return landlord


@app.get("/landlords/{landlord_id}/listings", response_model=schema.Page[schema.ListingOut])
def landlord_listings(
    landlord_id: int,
    page=Depends(page_params),
    db: Session = Depends(get_db),
    _user=Depends(any_role),
):
    result = crud.listings_for_landlord(db, landlord_id, *page)
    if result is None:
        raise not_found("Landlord", landlord_id)
    return result


# ---------- Listing CRUD (all protected) ----------


@app.post("/listings", response_model=schema.ListingOut, status_code=status.HTTP_201_CREATED)
def add_listing(payload: schema.ListingCreate, db: Session = Depends(get_db), _user=Depends(can_write)):
    return crud.create_listing(db, payload)


@app.get("/listings", response_model=schema.Page[schema.ListingOut])
def list_listings(page=Depends(page_params), db: Session = Depends(get_db), _user=Depends(any_role)):
    return crud.get_listings(db, *page)


@app.get("/listings/{listing_id}", response_model=schema.ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db), _user=Depends(any_role)):
    listing = crud.get_listing(db, listing_id)
    if not listing:
        raise not_found("Listing", listing_id)
    return listing


@app.put("/listings/{listing_id}", response_model=schema.ListingOut)
def edit_listing(
    listing_id: int,
    payload: schema.ListingUpdate,
    db: Session = Depends(get_db),
    _user=Depends(can_write),
):
    listing = crud.update_listing(db, listing_id, payload)
    if not listing:
        raise not_found("Listing", listing_id)
    return listing


@app.delete("/listings/{listing_id}", response_model=schema.ListingOut)
def remove_listing(listing_id: int, db: Session = Depends(get_db), _user=Depends(can_delete)):
    listing = crud.delete_listing(db, listing_id)
    if not listing:
        raise not_found("Listing", listing_id)
    return listing


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=PORT_BASE, reload=True)
