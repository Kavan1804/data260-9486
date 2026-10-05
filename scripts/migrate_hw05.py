#!/usr/bin/env python3
"""HW5 schema migration for s9486_rel. Safe to re-run; it never drops data.

1. creates any missing tables (landlords) with create_all
2. adds the new listings columns as nullable
3. seeds N_LANDLORDS landlords (random.Random(SEED)) if the table is empty
4. backfills existing HW4 listings: listing_code = LST-<id 5 digits>,
   landlord_id chosen with random.Random(SEED), available_units default 1
5. tightens the columns: NOT NULL, unique listing_code, FK ON DELETE RESTRICT,
   CHECK available_units >= 0

Usage (repo root):
    python scripts/migrate_hw05.py
"""

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from config import DB_NAME, N_LANDLORDS, SEED  # noqa: E402

FIRST = ["Alicia", "Brandon", "Carmen", "Deepak", "Elena", "Farah", "Gabriel", "Hana", "Isaac", "Jasmine",
         "Kevin", "Leila", "Marcus", "Neha", "Oscar", "Paula", "Quinn", "Rosa", "Tariq", "Vivian"]
LAST = ["Alvarez", "Bennett", "Chowdhury", "Dang", "Estrada", "Fischer", "Gupta", "Huang", "Iyer", "Jensen",
        "Kaur", "Larsen", "Morales", "Nakamura", "Okafor", "Park", "Reyes", "Shah", "Tran", "Vasquez"]
COMPANIES = ["Bay Area Rentals LLC", "Silicon Valley Property Mgmt", "Santa Clara Homes", "Rose Garden Realty",
             "Willow Glen Residential", "Downtown SJ Apartments", "Peninsula Leasing Co", "Campbell Rental Group"]

NEW_COLUMNS = {
    "listing_code": "ALTER TABLE listings ADD COLUMN listing_code VARCHAR(9) NULL AFTER address",
    "available_units": "ALTER TABLE listings ADD COLUMN available_units INT NOT NULL DEFAULT 1 AFTER listing_code",
    "landlord_id": "ALTER TABLE listings ADD COLUMN landlord_id INT NULL AFTER available_units",
    "created_at": "ALTER TABLE listings ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "updated_at": ("ALTER TABLE listings ADD COLUMN updated_at DATETIME NOT NULL "
                   "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
}


def log(msg: str) -> None:
    print(f"[migrate_hw05] {msg}", flush=True)


def constraint_names(conn, table: str) -> set[str]:
    rows = conn.execute(text(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :t"), {"db": DB_NAME, "t": table})
    return {r[0] for r in rows}


def main() -> None:
    if not os.getenv("DATABASE_URL"):
        sys.exit("DATABASE_URL missing. Create .env (repo root) from .env.example.")

    server = create_engine(make_url(os.environ["DATABASE_URL"]).set(database=""))
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))
    server.dispose()

    from backend.app import models  # noqa: F401  (registers tables)
    from backend.app.database import Base, engine

    existing_tables = set(inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine)  # only creates missing tables
    created = sorted(set(inspect(engine).get_table_names()) - existing_tables)
    log(f"create_all: new tables {created or 'none'}")

    with engine.begin() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("listings")}
        for name, ddl in NEW_COLUMNS.items():
            if name not in cols:
                conn.execute(text(ddl))
                log(f"added listings.{name}")

        n_landlords = conn.execute(text("SELECT COUNT(*) FROM landlords")).scalar()
        if n_landlords == 0:
            rng = random.Random(SEED)
            firsts, lasts = rng.sample(FIRST, N_LANDLORDS), rng.sample(LAST, N_LANDLORDS)
            rows = [{"full_name": f"{f} {l}", "company": rng.choice(COMPANIES),
                     "email": f"{f.lower()}.{l.lower()}@example.com"} for f, l in zip(firsts, lasts)]
            conn.execute(text("INSERT INTO landlords (full_name, company, email) VALUES (:full_name, :company, :email)"), rows)
            log(f"seeded {len(rows)} landlords with SEED={SEED}")
        else:
            log(f"landlords already has {n_landlords} rows - left unchanged")

        filled = conn.execute(text(
            "UPDATE listings SET listing_code = CONCAT('LST-', LPAD(id, 5, '0')) WHERE listing_code IS NULL")).rowcount
        log(f"backfilled listing_code on {filled} listings")

        landlord_ids = [r[0] for r in conn.execute(text("SELECT id FROM landlords ORDER BY id"))]
        missing = [r[0] for r in conn.execute(text("SELECT id FROM listings WHERE landlord_id IS NULL ORDER BY id"))]
        if missing:
            rng = random.Random(SEED)
            conn.execute(text("UPDATE listings SET landlord_id = :lid WHERE id = :id"),
                         [{"id": i, "lid": rng.choice(landlord_ids)} for i in missing])
        log(f"assigned landlord_id on {len(missing)} listings")

        # Tighten constraints only after every row has values.
        listing_cols = {c["name"]: c for c in inspect(conn).get_columns("listings")}
        if listing_cols["listing_code"]["nullable"]:
            conn.execute(text("ALTER TABLE listings MODIFY listing_code VARCHAR(9) NOT NULL"))
        if listing_cols["landlord_id"]["nullable"]:
            conn.execute(text("ALTER TABLE listings MODIFY landlord_id INT NOT NULL"))

        names = constraint_names(conn, "listings")
        if "uq_listings_listing_code" not in names:
            conn.execute(text("ALTER TABLE listings ADD CONSTRAINT uq_listings_listing_code UNIQUE (listing_code)"))
            log("added UNIQUE uq_listings_listing_code")
        if "fk_listings_landlord" not in names:
            index_names = {i["name"] for i in inspect(conn).get_indexes("listings")}
            if "ix_listings_landlord_id" not in index_names:
                conn.execute(text("CREATE INDEX ix_listings_landlord_id ON listings (landlord_id)"))
            conn.execute(text(
                "ALTER TABLE listings ADD CONSTRAINT fk_listings_landlord FOREIGN KEY (landlord_id) "
                "REFERENCES landlords (id) ON DELETE RESTRICT ON UPDATE CASCADE"))
            log("added FOREIGN KEY fk_listings_landlord (ON DELETE RESTRICT)")
        if "ck_listings_available_units" not in names:
            conn.execute(text(
                "ALTER TABLE listings ADD CONSTRAINT ck_listings_available_units CHECK (available_units >= 0)"))
            log("added CHECK ck_listings_available_units")

        summary = conn.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT landlord_id), SUM(listing_code IS NULL) FROM listings")).one()
        log(f"listings={summary[0]}, distinct landlords used={summary[1]}, null codes={summary[2] or 0}")
        log(f"tables: {', '.join(sorted(inspect(conn).get_table_names()))}")


if __name__ == "__main__":
    main()
