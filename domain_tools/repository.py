"""Storage access for the domain tools.

The tools only depend on the three methods below, so tests pass an
InMemoryListingRepository and never touch MySQL.
"""

from __future__ import annotations

import os
from typing import Protocol


class ListingRepository(Protocol):
    def search(self, query: str, limit: int, min_units: int) -> list[dict]: ...
    def get_by_code(self, listing_code: str) -> dict | None: ...
    def landlord_stats(self, landlord_id: int) -> dict | None: ...


def _listing_row(listing: dict, landlord: dict | None) -> dict:
    return {
        "listing_code": listing["listing_code"],
        "title": listing["title"],
        "address": listing["address"],
        "available_units": listing["available_units"],
        "landlord_id": listing["landlord_id"],
        "landlord_name": landlord["full_name"] if landlord else None,
    }


class InMemoryListingRepository:
    """Test fixture / dependency-injection stand-in for MySQL."""

    def __init__(self, listings: list[dict], landlords: list[dict]):
        self.listings = listings
        self.landlords = {l["id"]: l for l in landlords}

    def search(self, query: str, limit: int, min_units: int) -> list[dict]:
        q = query.lower()
        hits = [l for l in sorted(self.listings, key=lambda l: l["id"])
                if (q in l["title"].lower() or q in l["address"].lower()) and l["available_units"] >= min_units]
        return [_listing_row(l, self.landlords.get(l["landlord_id"])) for l in hits[:limit]]

    def get_by_code(self, listing_code: str) -> dict | None:
        for l in self.listings:
            if l["listing_code"] == listing_code:
                landlord = self.landlords.get(l["landlord_id"])
                row = _listing_row(l, landlord)
                row["id"] = l["id"]
                row["landlord_company"] = landlord["company"] if landlord else None
                return row
        return None

    def landlord_stats(self, landlord_id: int) -> dict | None:
        landlord = self.landlords.get(landlord_id)
        if not landlord:
            return None
        units = [l["available_units"] for l in self.listings if l["landlord_id"] == landlord_id]
        return _stats_row(landlord, len(units), sum(units), min(units, default=None), max(units, default=None))


def _stats_row(landlord: dict, count: int, total: int | None, lo: int | None, hi: int | None) -> dict:
    total = int(total or 0)
    return {
        "landlord_id": landlord["id"],
        "full_name": landlord["full_name"],
        "company": landlord["company"],
        "listing_count": count,
        "total_available_units": total,
        "avg_units_per_listing": round(total / count, 2) if count else 0.0,
        "min_units": lo,
        "max_units": hi,
    }


class MySQLListingRepository:
    """Reads s9486_rel directly. SQLAlchemy is imported lazily so offline tests
    never need a database driver or DATABASE_URL."""

    def __init__(self, url: str | None = None, timeout_s: float = 2.0):
        from sqlalchemy import create_engine

        url = url or os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL missing. Create .env (repo root) from .env.example.")
        t = max(1, int(round(timeout_s)))
        # Driver-level timeouts so a hung MySQL cannot block a tool call forever.
        self.engine = create_engine(
            url, pool_pre_ping=True,
            connect_args={"connect_timeout": t, "read_timeout": t, "write_timeout": t},
        )

    def _rows(self, sql: str, params: dict) -> list[dict]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]

    def search(self, query: str, limit: int, min_units: int) -> list[dict]:
        like = f"%{query}%"
        rows = self._rows(
            "SELECT l.listing_code, l.title, l.address, l.available_units, l.landlord_id, "
            "d.full_name AS landlord_name FROM listings l JOIN landlords d ON d.id = l.landlord_id "
            "WHERE (l.title LIKE :q OR l.address LIKE :q) AND l.available_units >= :m "
            "ORDER BY l.id LIMIT :n",
            {"q": like, "m": min_units, "n": limit},
        )
        return rows

    def get_by_code(self, listing_code: str) -> dict | None:
        rows = self._rows(
            "SELECT l.id, l.listing_code, l.title, l.address, l.available_units, l.landlord_id, "
            "d.full_name AS landlord_name, d.company AS landlord_company "
            "FROM listings l JOIN landlords d ON d.id = l.landlord_id WHERE l.listing_code = :c",
            {"c": listing_code},
        )
        return rows[0] if rows else None

    def landlord_stats(self, landlord_id: int) -> dict | None:
        rows = self._rows(
            "SELECT d.id, d.full_name, d.company, COUNT(l.id) AS n, SUM(l.available_units) AS total, "
            "MIN(l.available_units) AS lo, MAX(l.available_units) AS hi "
            "FROM landlords d LEFT JOIN listings l ON l.landlord_id = d.id WHERE d.id = :i GROUP BY d.id",
            {"i": landlord_id},
        )
        if not rows:
            return None
        r = rows[0]
        return _stats_row(r, int(r["n"]), r["total"], r["lo"], r["hi"])
