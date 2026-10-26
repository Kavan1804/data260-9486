#!/usr/bin/env python3
"""HW7 users-table migration for s9486_rel. Safe to re-run; it never drops data.

1. adds `username` (unique, NOT NULL) - existing HW4 users get the part of their email before '@'
2. adds `role` (reader | writer | moderator, default reader, CHECK constraint)
3. makes the HW4 columns `name` and `email` optional (HW7 users only need username/password/role)
4. creates or updates the three HW7 test users from the passwords in .env
   (HW7_READER_PASSWORD, HW7_WRITER_PASSWORD, HW7_MODERATOR_PASSWORD); only bcrypt hashes are stored
5. prints the table definition and the users (hash prefix only, never a password)

Usage (repo root):
    python scripts/migrate_hw07.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from hw5_common import banner  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from backend.app.database import engine  # noqa: E402
from backend.app.session_crud import hash_password, verify_password  # noqa: E402

TEST_USERS = {
    "s9486_reader": ("reader", "HW7_READER_PASSWORD"),
    "s9486_writer": ("writer", "HW7_WRITER_PASSWORD"),
    "s9486_moderator": ("moderator", "HW7_MODERATOR_PASSWORD"),
}


def columns(conn) -> dict:
    return {c["name"]: c for c in inspect(conn).get_columns("users")}


def main() -> int:
    banner("HW7 Part 1 users-table migration (s9486_rel)")
    missing = [env for _, env in TEST_USERS.values() if not os.getenv(env)]
    if missing:
        print(f"Missing in .env: {missing}. Add them (see .env.example) and re-run.")
        return 1

    with engine.begin() as conn:
        cols = columns(conn)
        if "username" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL AFTER id"))
            # Existing HW4 users: username = part of the email before '@' (+ id if that name is taken).
            conn.execute(text("UPDATE users SET username = SUBSTRING_INDEX(email, '@', 1) WHERE username IS NULL"))
            conn.execute(
                text(
                    "UPDATE users u JOIN (SELECT username FROM users GROUP BY username HAVING COUNT(*) > 1) d "
                    "ON u.username = d.username SET u.username = CONCAT(u.username, '_', u.id)"
                )
            )
            conn.execute(text("ALTER TABLE users MODIFY username VARCHAR(64) NOT NULL"))
            conn.execute(text("ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username)"))
            print("added users.username (unique)")
        if "role" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'reader' AFTER password_hash")
            )
            conn.execute(
                text("ALTER TABLE users ADD CONSTRAINT ck_users_role CHECK (role IN ('reader', 'writer', 'moderator'))")
            )
            print("added users.role (CHECK reader/writer/moderator, default reader)")
        cols = columns(conn)
        if not cols["name"]["nullable"]:
            conn.execute(text("ALTER TABLE users MODIFY name VARCHAR(255) NULL"))
            print("users.name is now optional")
        if not cols["email"]["nullable"]:
            conn.execute(text("ALTER TABLE users MODIFY email VARCHAR(255) NULL"))
            print("users.email is now optional")

        for username, (role, env) in TEST_USERS.items():
            password = os.environ[env]
            row = conn.execute(
                text("SELECT id, password_hash, role FROM users WHERE username = :u"), {"u": username}
            ).first()
            if row is None:
                conn.execute(
                    text("INSERT INTO users (username, password_hash, role) VALUES (:u, :h, :r)"),
                    {"u": username, "h": hash_password(password), "r": role},
                )
                print(f"created {username} ({role})")
            elif row.role != role or not verify_password(password, row.password_hash):
                conn.execute(
                    text("UPDATE users SET password_hash = :h, role = :r WHERE id = :id"),
                    {"h": hash_password(password), "r": role, "id": row.id},
                )
                print(f"updated {username} ({role}) to match .env")
            else:
                print(f"{username} ({role}) already up to date")

    with engine.connect() as conn:
        print("\nSHOW CREATE TABLE users:")
        print(conn.execute(text("SHOW CREATE TABLE users")).fetchone()[1])
        print("\nSELECT id, username, role, LEFT(password_hash, 7) AS hash_prefix, LENGTH(password_hash) FROM users:")
        for r in conn.execute(
            text("SELECT id, username, role, LEFT(password_hash, 7), LENGTH(password_hash) FROM users ORDER BY id")
        ):
            print(f"  {r[0]:>3}  {r[1]:<18} {r[2]:<10} {r[3]}...  ({r[4]} chars, bcrypt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
