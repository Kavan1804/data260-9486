from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import models, schema

# MySQL error numbers raised through IntegrityError
DUPLICATE_KEY = 1062
FK_PARENT_IN_USE = 1451
FK_PARENT_MISSING = 1452
CHECK_VIOLATION = 3819

UNIQUE_FIELDS = {"uq_landlords_email": "email", "uq_listings_listing_code": "listing_code"}


class ConflictError(Exception):
    """Unique-constraint or still-referenced violation (HTTP 409)."""


class InvalidReferenceError(Exception):
    """Foreign key points at a row that does not exist (HTTP 422)."""


def _commit(db: Session) -> None:
    """Commit, turning MySQL constraint errors into the two domain errors above.
    The checks before each commit give friendlier messages; this is the backstop
    for races between the check and the write."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        code = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
        msg = str(exc.orig)
        if code == DUPLICATE_KEY:
            field = next((f for k, f in UNIQUE_FIELDS.items() if k in msg), "value")
            raise ConflictError(f"{field} must be unique; this value is already used") from exc
        if code == FK_PARENT_MISSING:
            raise InvalidReferenceError("landlord_id does not refer to an existing landlord") from exc
        if code == FK_PARENT_IN_USE:
            raise ConflictError("Landlord still has listings; reassign or delete them first") from exc
        if code == CHECK_VIOLATION:
            raise InvalidReferenceError("available_units must be 0 or more") from exc
        raise


def _page(db: Session, query, skip: int, limit: int) -> dict:
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return {"total": total, "skip": skip, "limit": limit, "items": query.offset(skip).limit(limit).all()}


# ---------- Landlords ----------

def get_landlord(db: Session, landlord_id: int) -> models.Landlord | None:
    return db.get(models.Landlord, landlord_id)


def _email_taken(db: Session, email: str, exclude_id: int | None = None) -> bool:
    q = db.query(models.Landlord.id).filter(models.Landlord.email == email)
    if exclude_id is not None:
        q = q.filter(models.Landlord.id != exclude_id)
    return db.query(q.exists()).scalar()


def create_landlord(db: Session, payload: schema.LandlordCreate) -> models.Landlord:
    if _email_taken(db, payload.email):
        raise ConflictError(f"email {payload.email} is already used by another landlord")
    landlord = models.Landlord(**payload.model_dump())
    db.add(landlord)
    _commit(db)
    db.refresh(landlord)
    return landlord


def list_landlords(db: Session, skip: int, limit: int) -> dict:
    return _page(db, db.query(models.Landlord).order_by(models.Landlord.id), skip, limit)


def update_landlord(db: Session, landlord_id: int, payload: schema.LandlordUpdate):
    landlord = get_landlord(db, landlord_id)
    if not landlord:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "email" in data and _email_taken(db, data["email"], exclude_id=landlord_id):
        raise ConflictError(f"email {data['email']} is already used by another landlord")
    for key, value in data.items():
        setattr(landlord, key, value)
    _commit(db)
    db.refresh(landlord)
    return landlord


def delete_landlord(db: Session, landlord_id: int):
    landlord = get_landlord(db, landlord_id)
    if not landlord:
        return None
    owned = db.scalar(select(func.count()).where(models.Listing.landlord_id == landlord_id))
    if owned:
        raise ConflictError(
            f"Landlord {landlord_id} still has {owned} listing(s); reassign or delete them first"
        )
    deleted = schema.LandlordOut.model_validate(landlord)
    db.delete(landlord)
    _commit(db)
    return deleted


def listings_for_landlord(db: Session, landlord_id: int, skip: int, limit: int):
    """Relationship query: every listing that belongs to one landlord."""
    if not get_landlord(db, landlord_id):
        return None
    query = db.query(models.Listing).filter(models.Listing.landlord_id == landlord_id).order_by(models.Listing.id)
    return _page(db, query, skip, limit)


# ---------- Listings ----------

def _code_taken(db: Session, code: str, exclude_id: int | None = None) -> bool:
    q = db.query(models.Listing.id).filter(models.Listing.listing_code == code)
    if exclude_id is not None:
        q = q.filter(models.Listing.id != exclude_id)
    return db.query(q.exists()).scalar()


def _check_listing_refs(db: Session, data: dict, exclude_id: int | None = None) -> None:
    if "landlord_id" in data and not get_landlord(db, data["landlord_id"]):
        raise InvalidReferenceError(f"landlord_id {data['landlord_id']} does not refer to an existing landlord")
    if "listing_code" in data and _code_taken(db, data["listing_code"], exclude_id):
        raise ConflictError(f"listing_code {data['listing_code']} is already used by another listing")


def create_listing(db: Session, payload: schema.ListingCreate) -> models.Listing:
    data = payload.model_dump()
    _check_listing_refs(db, data)
    listing = models.Listing(**data)
    db.add(listing)
    _commit(db)
    db.refresh(listing)
    return listing


def get_listings(db: Session, skip: int, limit: int) -> dict:
    # Newest first, as in HW4, so a created listing shows at the top of the Home page.
    return _page(db, db.query(models.Listing).order_by(models.Listing.id.desc()), skip, limit)


def get_listing(db: Session, listing_id: int) -> models.Listing | None:
    return db.get(models.Listing, listing_id)


def update_listing(db: Session, listing_id: int, payload: schema.ListingUpdate):
    listing = get_listing(db, listing_id)
    if not listing:
        return None
    data = payload.model_dump(exclude_unset=True)
    _check_listing_refs(db, data, exclude_id=listing_id)
    for key, value in data.items():
        setattr(listing, key, value)
    _commit(db)
    db.refresh(listing)
    return listing


def delete_listing(db: Session, listing_id: int):
    listing = get_listing(db, listing_id)
    if not listing:
        return None
    deleted = schema.ListingOut.model_validate(listing)
    # No FK cascade on listing_inquiries (see models.py), so clean up by hand.
    db.query(models.ListingInquiry).filter(models.ListingInquiry.listing_id == listing_id).delete()
    db.delete(listing)
    db.commit()
    return deleted


def list_listings_naive(db: Session, page: int, page_size: int) -> list[dict]:
    """Intentional N+1: one query for the page, then one query per listing."""
    listings = (
        db.query(models.Listing)
        .order_by(models.Listing.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for listing in listings:
        inquiries = (
            db.query(models.ListingInquiry)
            .filter(models.ListingInquiry.listing_id == listing.id)
            .order_by(models.ListingInquiry.id)
            .all()
        )
        row = schema.ListingOut.model_validate(listing).model_dump()
        items.append({**row, "inquiries": inquiries})
    return items


def list_listings_fixed(db: Session, page: int, page_size: int) -> list[models.Listing]:
    """selectinload fetches all inquiries for the page in one IN (...) query."""
    return (
        db.query(models.Listing)
        .options(selectinload(models.Listing.inquiries))
        .order_by(models.Listing.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()
