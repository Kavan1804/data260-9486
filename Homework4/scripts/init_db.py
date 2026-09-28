#!/usr/bin/env python3
"""Create the s9486_rel database and all HW4 tables without touching existing data.

Usage (from Homework4/):
    python scripts/init_db.py                 # create database + tables if missing
    python scripts/init_db.py --create-user   # also add a login user (prompts for password)
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from config import DB_NAME  # noqa: E402


def ensure_database() -> None:
    server_url = make_url(os.environ["DATABASE_URL"]).set(database="")
    server_engine = create_engine(server_url)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`"))
    server_engine.dispose()


def create_user() -> None:
    from backend.app import crud, models
    from backend.app.database import SessionLocal
    from backend.app.session_crud import hash_password

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-user", action="store_true")
    args = parser.parse_args()

    # config.py already loaded Homework4/.env
    if not os.getenv("DATABASE_URL"):
        sys.exit("DATABASE_URL missing. Create Homework4/.env from .env.example.")

    ensure_database()

    from backend.app import models  # noqa: F401  (registers tables on Base)
    from backend.app.database import Base, engine

    # create_all only issues CREATE TABLE for tables that do not exist yet.
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    print(f"Database {DB_NAME} ready. Tables: {', '.join(sorted(tables))}")

    if args.create_user:
        create_user()


if __name__ == "__main__":
    main()
