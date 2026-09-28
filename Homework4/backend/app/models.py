from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import foreign, relationship

from .database import Base

INQUIRY_INDEX_NAME = "ix_listing_inquiries_listing_id"


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)  # primary field
    address = Column(String(255), nullable=False)  # secondary field

    inquiries = relationship(
        "ListingInquiry",
        primaryjoin=lambda: Listing.id == foreign(ListingInquiry.listing_id),
        order_by=lambda: ListingInquiry.id,
        viewonly=True,
    )


class ListingInquiry(Base):
    """Related test data for the Part 3 N+1 experiment (200 rows)."""

    __tablename__ = "listing_inquiries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # No FOREIGN KEY constraint on purpose: InnoDB silently adds an index to
    # every FK column, which would hide the before/after EXPLAIN in Part 3.
    # The seed script only inserts listing_ids that exist.
    listing_id = Column(Integer, nullable=False)
    renter_name = Column(String(120), nullable=False)
    message = Column(Text, nullable=False)

    __table_args__ = (Index(INQUIRY_INDEX_NAME, "listing_id"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)


class SessionToken(Base):
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)  # opaque session token
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)  # naive UTC
    expires_at = Column(DateTime, nullable=False)  # naive UTC
