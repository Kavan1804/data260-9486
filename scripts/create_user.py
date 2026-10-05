#!/usr/bin/env python3
"""Add a login user to s9486_rel (password stored as a bcrypt hash, never plain text).

Usage (repo root):  python scripts/create_user.py
"""

import getpass
import sys

from hw5_common import banner  # noqa: F401  (puts the repo root on sys.path)

from backend.app import crud, models
from backend.app.database import SessionLocal
from backend.app.session_crud import hash_password


def main() -> None:
    name = input("Name: ").strip()
    email = input("Email: ").strip().lower()
    password = getpass.getpass("Password: ")
    if not name or not email or not password:
        sys.exit("Name, email and password are all required.")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    if len(password.encode("utf-8")) > 72:
        sys.exit("Password must be at most 72 bytes (bcrypt limit).")
    with SessionLocal() as db:
        if crud.get_user_by_email(db, email):
            print(f"User {email} already exists - left unchanged.")
            return
        db.add(models.User(name=name, email=email, password_hash=hash_password(password)))
        db.commit()
    print(f"Created user {email}.")


if __name__ == "__main__":
    main()
