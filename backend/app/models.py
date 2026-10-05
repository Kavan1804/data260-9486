from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.orm import foreign, relationship

from .database import Base

INQUIRY_INDEX_NAME = "ix_listing_inquiries_listing_id"
LISTING_CODE_PATTERN = r"^LST-\d{5}$"


def _created_at():
    return Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


def _updated_at():
    # ON UPDATE in the DDL covers raw SQL updates; onupdate covers ORM updates.
    return Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )


class Landlord(Base):
    """HW5 related entity: the landlord / property manager who owns listings."""

    __tablename__ = "landlords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(120), nullable=False)  # primary text field
    company = Column(String(160), nullable=False)  # secondary text field
    email = Column(String(255), nullable=False)  # unique field
    created_at = _created_at()
    updated_at = _updated_at()

    __table_args__ = (UniqueConstraint("email", name="uq_landlords_email"),)

    listings = relationship("Listing", back_populates="landlord", passive_deletes="all")


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)  # primary field
    address = Column(String(255), nullable=False)  # secondary field
    # HW5 columns. Existing HW4 rows are backfilled by scripts/migrate_hw05.py.
    listing_code = Column(String(9), nullable=False)  # unique field, e.g. LST-00001
    available_units = Column(Integer, nullable=False, default=1, server_default="1")
    # RESTRICT: MySQL refuses to delete a landlord that still owns listings.
    landlord_id = Column(
        Integer,
        ForeignKey("landlords.id", name="fk_listings_landlord", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = _created_at()
    updated_at = _updated_at()

    __table_args__ = (
        UniqueConstraint("listing_code", name="uq_listings_listing_code"),
        CheckConstraint("available_units >= 0", name="ck_listings_available_units"),
    )

    landlord = relationship("Landlord", back_populates="listings")

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
