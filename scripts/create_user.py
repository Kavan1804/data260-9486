#!/usr/bin/env python3
"""Add a login user to s9486_rel (password stored as a bcrypt hash, never plain text).

HW7: users log in with a username and have a role (reader, writer or moderator).
Run scripts/migrate_hw07.py first.

Usage (repo root):  python scripts/create_user.py
"""

import getpass
import sys

from hw5_common import banner  # noqa: F401  (puts the repo root on sys.path)

from backend.app import crud, models
from backend.app.database import SessionLocal
from backend.app.session_crud import hash_password


def main() -> None:
    username = input("Username: ").strip()
    role = input("Role (reader/writer/moderator) [reader]: ").strip().lower() or "reader"
    password = getpass.getpass("Password: ")
    if not username or not password:
        sys.exit("Username and password are required.")
    if role not in models.USER_ROLES:
        sys.exit(f"Role must be one of {models.USER_ROLES}.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    if len(password.encode("utf-8")) > 72:
        sys.exit("Password must be at most 72 bytes (bcrypt limit).")
    with SessionLocal() as db:
        if crud.get_user_by_username(db, username):
            print(f"User {username} already exists - left unchanged.")
            return
        db.add(models.User(username=username, role=role, password_hash=hash_password(password)))
        db.commit()
    print(f"Created user {username} ({role}).")


if __name__ == "__main__":
    main()
