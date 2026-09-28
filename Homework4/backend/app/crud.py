from sqlalchemy.orm import Session, selectinload

from . import models, schema


def create_listing(db: Session, payload: schema.ListingCreate) -> models.Listing:
    listing = models.Listing(title=payload.title, address=payload.address)
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def get_listings(db: Session, skip: int = 0, limit: int | None = None):
    query = db.query(models.Listing).order_by(models.Listing.id.desc()).offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def get_listing(db: Session, listing_id: int) -> models.Listing | None:
    return db.get(models.Listing, listing_id)


def update_listing(db: Session, listing_id: int, payload: schema.ListingUpdate):
    listing = get_listing(db, listing_id)
    if not listing:
        return None
    listing.title = payload.title
    listing.address = payload.address
    db.commit()
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
        items.append({"id": listing.id, "title": listing.title, "address": listing.address, "inquiries": inquiries})
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
