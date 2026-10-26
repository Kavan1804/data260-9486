#!/usr/bin/env python3
"""HW7 Part 1 demo: every required auth/role case against the running backend on PORT_BASE.

Logs in as the three seeded users (passwords come from .env and are never printed), then shows:
login 200 + token, bad login 401, /auth/me without token 401, invalid token 401, expired token 401,
reader create 403, writer create 201, writer delete 403, moderator delete 200, list/read 200.
The landlord and listing it creates are deleted again at the end.

Usage (repo root, backend running):  python Homework7/scripts/auth_demo.py [--only login,me,...]
Writes reports/hw07/raw/auth_demo.json.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
import requests
from hw7_common import BASE_URL, RAW, banner, write_json

import config

USERS = {
    "reader": ("s9486_reader", "HW7_READER_PASSWORD"),
    "writer": ("s9486_writer", "HW7_WRITER_PASSWORD"),
    "moderator": ("s9486_moderator", "HW7_MODERATOR_PASSWORD"),
}
results: list[dict] = []


def show(label: str, method: str, path: str, role: str | None, r: requests.Response, expect: int) -> dict:
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    shown = dict(body) if isinstance(body, dict) else body
    if isinstance(shown, dict) and "access_token" in shown:
        shown["access_token"] = shown["access_token"][:24] + "...(truncated)"
    if isinstance(shown, dict) and "items" in shown:
        shown = {k: v for k, v in shown.items() if k != "items"} | {"first_item": (body["items"] or [None])[0]}
    ok = r.status_code == expect
    print(f"[{'OK' if ok else 'UNEXPECTED'}] {label}")
    print(f"    {method} {path}  as {role or 'no token'}  ->  HTTP {r.status_code} (expected {expect})")
    print(f"    {shown}\n", flush=True)
    row = {
        "case": label,
        "method": method,
        "path": path,
        "as": role,
        "status": r.status_code,
        "expected": expect,
        "passed": ok,
    }
    results.append(row)
    return body


def login(role: str) -> str:
    username, env = USERS[role]
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": username, "password": os.environ[env]}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list: login,me,invalid,expired,create,delete,read")
    only = {x for x in ap.parse_args().only.split(",") if x}

    def want(name: str) -> bool:
        return not only or name in only

    banner("Part 1 JWT auth + role checks (s9486_rel users table)")
    tok = {role: login(role) for role in USERS}
    auth = {role: {"Authorization": f"Bearer {t}"} for role, t in tok.items()}

    if want("login"):
        u, env = USERS["writer"]
        r = requests.post(f"{BASE_URL}/auth/login", json={"username": u, "password": os.environ[env]}, timeout=10)
        show("Login with valid credentials returns a JWT", "POST", "/auth/login", u, r, 200)
        r = requests.post(f"{BASE_URL}/auth/login", json={"username": u, "password": "wrong-password"}, timeout=10)
        show("Login with a wrong password", "POST", "/auth/login", u, r, 401)
        r = requests.post(f"{BASE_URL}/auth/login", json={"username": "nobody_9486", "password": "x"}, timeout=10)
        show("Login with an unknown username", "POST", "/auth/login", "nobody_9486", r, 401)
    if want("me"):
        show(
            "GET /auth/me without a token",
            "GET",
            "/auth/me",
            None,
            requests.get(f"{BASE_URL}/auth/me", timeout=10),
            401,
        )
        r = requests.get(f"{BASE_URL}/auth/me", headers=auth["reader"], timeout=10)
        show("GET /auth/me with a valid token", "GET", "/auth/me", "reader", r, 200)
    if want("invalid"):
        bad = tok["reader"][:-4] + ("AAAA" if not tok["reader"].endswith("AAAA") else "BBBB")
        r = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {bad}"}, timeout=10)
        show("GET /auth/me with a tampered (invalid) token", "GET", "/auth/me", "tampered token", r, 401)
    if want("expired"):
        # Signed with the real secret but the expiry is 5 minutes in the past.
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        expired = jwt.encode(
            {"sub": "s9486_reader", "role": "reader", "exp": past},
            config.JWT_SECRET_KEY,
            algorithm=config.JWT_ALGORITHM,
        )
        r = requests.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {expired}"}, timeout=10)
        show("GET /auth/me with an expired token", "GET", "/auth/me", "expired token", r, 401)

    stamp = datetime.now().strftime("%H%M%S")
    landlord = {"full_name": "HW7 Demo Landlord", "company": "Demo Rentals", "email": f"hw7.demo.{stamp}@example.com"}
    created = {}
    if want("create") or want("delete"):
        r = requests.post(f"{BASE_URL}/landlords", json=landlord, headers=auth["reader"], timeout=10)
        show("Create landlord as reader", "POST", "/landlords", "reader", r, 403)
        r = requests.post(f"{BASE_URL}/landlords", json=landlord, headers=auth["writer"], timeout=10)
        created["landlord"] = show("Create landlord as writer", "POST", "/landlords", "writer", r, 201)
        listing = {
            "title": "HW7 demo studio",
            "address": "1 Demo St, San Jose, CA",
            "listing_code": f"LST-9{stamp[-4:]}",
            "available_units": 1,
            "landlord_id": created["landlord"]["id"],
        }
        r = requests.post(f"{BASE_URL}/listings", json=listing, headers=auth["reader"], timeout=10)
        show("Create listing as reader", "POST", "/listings", "reader", r, 403)
        r = requests.post(f"{BASE_URL}/listings", json=listing, headers=auth["moderator"], timeout=10)
        created["listing"] = show("Create listing as moderator", "POST", "/listings", "moderator", r, 201)
    if want("delete") and created:
        lid = created["listing"]["id"]
        r = requests.delete(f"{BASE_URL}/listings/{lid}", headers=auth["writer"], timeout=10)
        show("Delete listing as writer", "DELETE", f"/listings/{lid}", "writer", r, 403)
        r = requests.delete(f"{BASE_URL}/listings/{lid}", headers=auth["moderator"], timeout=10)
        show("Delete listing as moderator", "DELETE", f"/listings/{lid}", "moderator", r, 200)
    if want("read"):
        r = requests.get(f"{BASE_URL}/listings?limit=2", headers=auth["reader"], timeout=10)
        first_id = show("List listings as reader", "GET", "/listings?limit=2", "reader", r, 200)["items"][0]["id"]
        r = requests.get(f"{BASE_URL}/listings/{first_id}", headers=auth["reader"], timeout=10)
        show("Read one listing as reader", "GET", f"/listings/{first_id}", "reader", r, 200)
        r = requests.get(f"{BASE_URL}/listings?limit=2", timeout=10)
        show("List listings without a token", "GET", "/listings?limit=2", None, r, 401)

    # Clean up anything still left from this run (moderator can delete).
    if created.get("listing") and want("create") and not want("delete"):
        requests.delete(f"{BASE_URL}/listings/{created['listing']['id']}", headers=auth["moderator"], timeout=10)
    if created.get("landlord"):
        requests.delete(f"{BASE_URL}/landlords/{created['landlord']['id']}", headers=auth["moderator"], timeout=10)

    passed = sum(r["passed"] for r in results)
    print(f"{passed}/{len(results)} cases returned the expected status code")
    if not only:  # a partial --only run (for screenshots) must not replace the full evidence file
        write_json(RAW / "auth_demo.json", {"run_at": datetime.now().isoformat(timespec="seconds"), "cases": results})
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
