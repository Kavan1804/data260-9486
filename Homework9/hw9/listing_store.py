"""MySQL (s9486_rel) + Redis access for the HW9 listing entity.

Adapted from the DatabaseWithCache class in Homework9/demo.py, but for the real HW4-HW8 `listings` table in
MySQL instead of the demo's SQLite users table. The Part 1 method is increment_listing_views(); the other
methods are the reads/writes the semantic cache and the agents need.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text

from hw9.common import key, log, redis_client

SYNC_EVERY = 10  # Part 1: persist the Redis count to MySQL every 10 views

LISTING_SQL = text(
    "SELECT l.id, l.listing_code, l.title, l.address, l.available_units, l.landlord_id, l.updated_at, "
    "d.full_name AS landlord_name, d.company AS landlord_company "
    "FROM listings l JOIN landlords d ON d.id = l.landlord_id WHERE l.listing_code = :code"
)


def city_of(address: str) -> str:
    """'5239 Almaden Blvd, Sunnyvale, CA' -> 'Sunnyvale'."""
    parts = [p.strip() for p in address.split(",")]
    return parts[-2] if len(parts) >= 3 else ""


class ListingDatabaseWithCache:
    def __init__(self, redis=None, engine=None):
        if engine is None:
            from backend.app.database import engine as default_engine

            engine = default_engine
        self.engine = engine
        self.redis_client = redis or redis_client()
        self.on_log = lambda msg: log("listing_store", msg)  # the Part 1 demo swaps this to print in order

    # ---------- Part 1 ----------
    def increment_listing_views(self, listing_id: int) -> int:
        """Count one view in Redis (INCR) and write the count to listings.view_count every 10th view."""
        count = self.redis_client.incr(key("views", "listing", listing_id))
        if count % SYNC_EVERY == 0:
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE listings SET view_count = :count WHERE id = :id"), {"count": count, "id": listing_id}
                )
            self.on_log(f"✓ Synced views to database (listings.id={listing_id}, view_count={count})")
        return count

    def db_view_count(self, listing_id: int) -> int:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT view_count FROM listings WHERE id = :id"), {"id": listing_id}).scalar_one()

    def reset_views(self, listing_id: int) -> None:
        """Start the demo from 0 in both places (only this listing's key and row)."""
        self.redis_client.delete(key("views", "listing", listing_id))
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE listings SET view_count = 0 WHERE id = :id"), {"id": listing_id})

    # ---------- reads/writes used by the semantic cache (Part 2-3) and the agents (Part 4) ----------
    def get_listing(self, code: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(LISTING_SQL, {"code": code}).mappings().first()
        if row is None:
            return None
        facts = dict(row)
        facts["city"] = city_of(facts["address"])
        facts["updated_at"] = str(facts["updated_at"])
        return facts

    def get_landlord(self, landlord_id: int) -> dict | None:
        """Part 4 Answering Agent tool: one landlords row."""
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    text("SELECT id AS landlord_id, full_name, company FROM landlords WHERE id = :id"),
                    {"id": landlord_id},
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def fingerprint(self, code: str) -> str:
        """Data-version marker for one listing: a short hash of the fields an answer can depend on.
        Any change to the row (by this code or by raw SQL) gives a different value."""
        facts = self.get_listing(code)
        if facts is None:
            return "missing"
        raw = "|".join(
            str(facts[f])
            for f in ("listing_code", "title", "address", "available_units", "landlord_name", "landlord_company")
        )
        return hashlib.sha1(raw.encode()).hexdigest()[:12]

    def set_available_units(self, code: str, units: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE listings SET available_units = :u WHERE listing_code = :code"), {"u": units, "code": code}
            )
