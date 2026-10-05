#!/usr/bin/env python3
"""Show EXPLAIN for the inquiry lookups before and after adding one index.

The index is declared in backend/app/models.py, so a fresh create_all already
has it. To capture a real "before" plan this script drops only that index
(no data is touched), runs EXPLAIN, recreates it, and runs EXPLAIN again.

Usage (from Homework4/, after seeding):
    python scripts/explain_index.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent))  # HW5 moved backend/ to the repo root

from sqlalchemy import text  # noqa: E402

from backend.app.database import engine  # noqa: E402
from backend.app.models import INQUIRY_INDEX_NAME  # noqa: E402
from config import DB_NAME  # noqa: E402

RAW = ROOT / "reports" / "hw04" / "raw"
INDEX_DDL = f"CREATE INDEX {INQUIRY_INDEX_NAME} ON listing_inquiries (listing_id)"

QUERIES = {
    # what the naive endpoint runs once per listing
    "naive_per_listing": "SELECT id, listing_id, renter_name, message FROM listing_inquiries WHERE listing_id = 7 ORDER BY id",
    # what selectinload runs once per page (page_size = 10)
    "fixed_selectin_page10": "SELECT id, listing_id, renter_name, message FROM listing_inquiries "
    "WHERE listing_id IN (1,2,3,4,5,6,7,8,9,10) ORDER BY id",
}


def index_exists(conn) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = :db AND table_name = 'listing_inquiries' AND index_name = :idx"
            ),
            {"db": DB_NAME, "idx": INQUIRY_INDEX_NAME},
        ).scalar()
    )


def explain_all(conn) -> dict:
    conn.execute(text("ANALYZE TABLE listing_inquiries"))
    out = {}
    for name, sql in QUERIES.items():
        rows = conn.execute(text(f"EXPLAIN {sql}")).mappings().all()
        out[name] = {"sql": sql, "plan": [dict(r) for r in rows]}
    return out


def fmt(plans: dict) -> str:
    cols = ["table", "type", "possible_keys", "key", "key_len", "ref", "rows", "filtered", "Extra"]
    lines = []
    for name, p in plans.items():
        lines.append(f"-- {name}\nEXPLAIN {p['sql']};")
        lines.append(" | ".join(cols))
        for r in p["plan"]:
            lines.append(" | ".join(str(r.get(c)) for c in cols))
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with engine.begin() as conn:
        if index_exists(conn):
            print(f"[{stamp}] {INQUIRY_INDEX_NAME} exists - dropping it to capture the 'before' plan.")
            conn.execute(text(f"DROP INDEX {INQUIRY_INDEX_NAME} ON listing_inquiries"))

        before = explain_all(conn)
        conn.execute(text(INDEX_DDL))
        after = explain_all(conn)
        create_table = conn.execute(text("SHOW CREATE TABLE listing_inquiries")).fetchone()[1]

    report = (
        f"EXPLAIN before/after - run at {stamp}\n\n"
        f"===== BEFORE (no index on listing_inquiries.listing_id) =====\n{fmt(before)}\n"
        f"===== INDEX ADDED =====\n{INDEX_DDL};\n\n"
        f"===== AFTER =====\n{fmt(after)}\n"
        f"===== SHOW CREATE TABLE listing_inquiries =====\n{create_table}\n"
    )
    print(report)
    (RAW / "explain_before_after.txt").write_text(report, encoding="utf-8")
    (RAW / "explain_before_after.json").write_text(
        json.dumps({"run_at": stamp, "index_ddl": INDEX_DDL, "before": before, "after": after}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Saved {RAW / 'explain_before_after.txt'} and .json")


if __name__ == "__main__":
    main()
