#!/usr/bin/env python3
"""HW9 Part 1 schema change: add listings.view_count (INT NOT NULL DEFAULT 0) to s9486_rel.

Safe to run more than once (it checks information_schema first). Existing rows get 0.
The HW4-HW8 code does not select this column, so it keeps working unchanged.

Usage (repo root):  python Homework9/scripts/migrate_hw09.py      (or make migrate-hw09)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

from sqlalchemy import text  # noqa: E402

import config  # noqa: E402
from hw9.common import banner, footer  # noqa: E402


def main() -> int:
    from backend.app.database import engine

    banner("migrate: add listings.view_count")
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = 'listings' AND COLUMN_NAME = 'view_count'"
            ),
            {"db": config.DB_NAME},
        ).scalar()
        if exists:
            print("listings.view_count already exists - nothing to do")
        else:
            conn.execute(text("ALTER TABLE listings ADD COLUMN view_count INT NOT NULL DEFAULT 0"))
            print("added listings.view_count INT NOT NULL DEFAULT 0")
        col = conn.execute(text("SHOW COLUMNS FROM listings LIKE 'view_count'")).one()
        print(f"column: {tuple(col)}")
    return 0


if __name__ == "__main__":
    code = main()
    footer("migrate")
    sys.exit(code)
