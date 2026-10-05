#!/usr/bin/env python3
"""Deterministically seed 5,000 listings and 200 related inquiries (SEED = 9486).

The 200 inquiries are attached to the first 200 listing ids, so every page
measured in Part 3 (page 1 at sizes 10/50/200) has related data to return.

Usage (from Homework4/, after scripts/init_db.py):
    python scripts/seed_n1.py           # refuses if listings already has rows
    python scripts/seed_n1.py --reset   # empties listings + listing_inquiries first
"""

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent))  # HW5 moved backend/ to the repo root

from sqlalchemy import func, insert, select, text  # noqa: E402

from backend.app.database import SessionLocal  # noqa: E402
from backend.app.models import Listing, ListingInquiry  # noqa: E402
from config import N_INQUIRIES, N_LISTINGS, SEED  # noqa: E402

ADJECTIVES = ["Sunny", "Modern", "Quiet", "Spacious", "Cozy", "Renovated", "Bright", "Charming", "Updated", "Furnished"]
UNIT_TYPES = ["1BR Apartment", "2BR Apartment", "Studio", "3BR House", "2BR Townhouse", "4BR House", "Loft", "1BR Condo"]
FEATURES = ["near SJSU", "with parking", "with in-unit laundry", "near light rail", "with balcony", "pet friendly", "with yard", "near downtown"]
STREETS = ["San Carlos St", "Santa Clara St", "4th St", "Market St", "Alameda", "Park Ave", "Willow St", "Lincoln Ave", "Almaden Blvd", "Taylor St"]
CITIES = ["San Jose, CA", "Santa Clara, CA", "Sunnyvale, CA", "Campbell, CA", "Milpitas, CA", "Mountain View, CA"]
FIRST = ["Alex", "Priya", "Jordan", "Wei", "Maria", "Sam", "Aisha", "Diego", "Nina", "Omar", "Lena", "Ravi"]
LAST = ["Nguyen", "Patel", "Garcia", "Kim", "Singh", "Lopez", "Chen", "Brown", "Rao", "Silva"]
QUESTIONS = [
    "Is this unit still available for next month?",
    "Are utilities included in the rent?",
    "Can I schedule a viewing this weekend?",
    "Is there a lease option shorter than 12 months?",
    "How much is the security deposit?",
    "Are pets allowed in this listing?",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete existing listings and inquiries first")
    args = parser.parse_args()

    rng = random.Random(SEED)

    with SessionLocal() as db:
        existing = db.scalar(select(func.count()).select_from(Listing))
        if existing and not args.reset:
            sys.exit(f"listings already has {existing} rows. Re-run with --reset to reseed.")
        if args.reset:
            # TRUNCATE also resets AUTO_INCREMENT so ids are 1..5000 on every run.
            db.execute(text("TRUNCATE TABLE listing_inquiries"))
            db.execute(text("TRUNCATE TABLE listings"))
            db.commit()

        listings = [
            {
                "title": f"{rng.choice(ADJECTIVES)} {rng.choice(UNIT_TYPES)} {rng.choice(FEATURES)}",
                "address": f"{rng.randint(10, 9999)} {rng.choice(STREETS)}, {rng.choice(CITIES)}",
            }
            for _ in range(N_LISTINGS)
        ]
        db.execute(insert(Listing), listings)
        db.commit()

        first_ids = db.scalars(select(Listing.id).order_by(Listing.id).limit(N_INQUIRIES)).all()
        inquiries = [
            {
                "listing_id": rng.choice(first_ids),
                "renter_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                "message": rng.choice(QUESTIONS),
            }
            for _ in range(N_INQUIRIES)
        ]
        db.execute(insert(ListingInquiry), inquiries)
        db.commit()

        n_listings = db.scalar(select(func.count()).select_from(Listing))
        n_inquiries = db.scalar(select(func.count()).select_from(ListingInquiry))
        n_linked = db.scalar(select(func.count(func.distinct(ListingInquiry.listing_id))))
    print(f"SEED={SEED}: listings={n_listings}, listing_inquiries={n_inquiries}, listings with >=1 inquiry={n_linked}")


if __name__ == "__main__":
    main()
