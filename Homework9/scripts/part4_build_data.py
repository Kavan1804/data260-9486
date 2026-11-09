#!/usr/bin/env python3
"""HW9 Part 4: build the reference dataset and the three input-only question files.

Listings are picked from s9486_rel with random.Random(VERIFY_SEED), skipping the listings used in Parts 1-3,
and each split gets its own listings (so test questions are about listings the system never saw in training).

  reference_data.json   ground truth for the Evaluator: listing facts, codes that do not exist, the fields the
                        database does not record, and for every question id which facts it asks about
  training_data.json    {"id", "question"} only - no answers
  validation_data.json  {"id", "question"} only
  test_data.json        {"id", "question"} only

Usage (repo root, MySQL running):  python Homework9/scripts/part4_build_data.py      (or make part4-data)
Run once; the files are committed and not regenerated after the test runs.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

from sqlalchemy import text  # noqa: E402

import config  # noqa: E402
from hw9.common import DATA, banner, footer, utc_now, write_json  # noqa: E402
from hw9.listing_store import ListingDatabaseWithCache  # noqa: E402

USED_ELSEWHERE = {
    "LST-00042",
    "LST-00117",
    "LST-00230",
    "LST-00305",
    "LST-00350",
    "LST-00418",
    "LST-00481",
    "LST-00527",
    "LST-00572",
    "LST-00640",
    "LST-00604",
    "LST-00753",
    "LST-00888",
}
NOT_RECORDED = ["monthly rent", "security deposit", "application fee", "lease length", "utilities"]

# (asks, template). {c} = listing code. Each split uses different wording where it can.
TRAIN = [
    (["landlord"], "Who is the landlord for listing {c}?"),
    (["city"], "Which city is listing {c} in?"),
    (["units", "landlord"], "For {c}, how many units are available and who is the landlord?"),
    (["rent"], "What is the monthly rent for listing {c}?"),
    (["landlord"], "Who should I contact as the landlord of {c}?"),
    (["address"], "What is the street address of listing {c}?"),
    (["deposit"], "How much is the security deposit at {c}?"),
    (["units", "landlord"], "Tell me the landlord and the number of open units for {c}."),
    (["home_type"], "What kind of home is listing {c}?"),
    (["rent"], "How much does {c} cost per month?"),
    (["company"], "Which property management company handles {c}?"),
    (["missing"], "Who is the landlord for listing {c}?"),
]
VALIDATION = [
    (["landlord"], "Which person manages listing {c}?"),
    (["units"], "How many vacant units does listing {c} have?"),
    (["units", "landlord"], "How many units can I still rent at {c}, and who is its landlord?"),
    (["lease_length"], "What is the minimum lease length at {c}?"),
    (["city"], "What city would I live in if I rent {c}?"),
    (["utilities"], "Are utilities included in the rent at {c}?"),
    (["company"], "What management company is behind listing {c}?"),
    (["address"], "Where exactly is listing {c}? Give the street address."),
    (["home_type"], "How many bedrooms does {c} have and what type of place is it?"),
    (["missing"], "How many units are available at listing {c}?"),
]
TEST = [
    (["landlord"], "Who is the landlord of listing {c}?"),
    (["units"], "How many units are available right now at {c}?"),
    (["units", "landlord"], "For listing {c}, who is the landlord and how many units are open?"),
    (["rent"], "What does listing {c} charge for rent each month?"),
    (["city"], "In which city is {c} located?"),
    (["application_fee"], "What is the application fee for {c}?"),
    (["company"], "Which company manages listing {c}?"),
    (["address"], "What is the address of {c}?"),
    (["deposit"], "What security deposit does {c} ask for?"),
    (["home_type"], "What type of home is {c}, and how many bedrooms?"),
    (["landlord", "company"], "Who is the landlord for {c} and which company do they work for?"),
    (["missing"], "What city is listing {c} in?"),
]
MISSING = {"train": "LST-07777", "validation": "LST-08123", "test": "LST-09090"}


def main() -> int:
    banner("Part 4 build reference + input datasets")
    store = ListingDatabaseWithCache()
    with store.engine.connect() as conn:
        codes = [c for (c,) in conn.execute(text("SELECT listing_code FROM listings WHERE listing_code < 'LST-05000'"))]
        for m in MISSING.values():
            assert conn.execute(text("SELECT COUNT(*) FROM listings WHERE listing_code = :c"), {"c": m}).scalar() == 0
    rng = random.Random(config.VERIFY_SEED)
    pool = sorted(set(codes) - USED_ELSEWHERE)
    picked = rng.sample(pool, len(TRAIN) + len(VALIDATION) + len(TEST))

    listings, questions = {}, {}
    out = {}
    i = 0
    for split, templates in (("train", TRAIN), ("validation", VALIDATION), ("test", TEST)):
        rows = []
        for n, (asks, tpl) in enumerate(templates, 1):
            code = MISSING[split] if asks == ["missing"] else picked[i]
            i += 1
            qid = f"{split[:2]}{n:02d}" if split != "validation" else f"va{n:02d}"
            rows.append({"id": qid, "question": tpl.format(c=code)})
            questions[qid] = {"listing_code": code, "asks": asks}
            if code not in MISSING.values():
                f = store.get_listing(code)
                listings[code] = {
                    k: f[k]
                    for k in (
                        "listing_code",
                        "title",
                        "address",
                        "city",
                        "available_units",
                        "landlord_name",
                        "landlord_company",
                    )
                }
        out[split] = rows
        print(f"{split:10} {len(rows)} questions")

    write_json(DATA / "training_data.json", out["train"])
    write_json(DATA / "validation_data.json", out["validation"])
    write_json(DATA / "test_data.json", out["test"])
    write_json(
        DATA / "reference_data.json",
        {
            "built_at": utc_now(),
            "source": f"{config.DB_NAME}.listings JOIN landlords, picked with random.Random({config.VERIFY_SEED})",
            "listings": listings,
            "missing_listing_codes": sorted(MISSING.values()),
            "not_recorded_fields": NOT_RECORDED,
            "questions": questions,
        },
    )
    print(f"reference_data.json: {len(listings)} listings, {len(questions)} question ids")
    for split in out:
        print(f"  {split}: e.g. {out[split][0]}")
    return 0


if __name__ == "__main__":
    code = main()
    footer("Part 4 datasets")
    sys.exit(code)
