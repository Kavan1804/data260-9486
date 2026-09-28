#!/usr/bin/env python3
"""HW4 smoke test. Writes Homework4/verification.json.

Starts the backend on PORT_BASE if it is not already running, creates a
temporary user and a temporary listing (both removed at the end), and checks
behavior: login, HTTP-only opaque cookie, protected routes, CRUD, and both
N+1 endpoints. It never edits application source files.

Usage (from Homework4/):
    make verify-hw04
    # or: python scripts/verify_hw04.py
"""

import json
import os
import random
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

BASE_URL = f"http://localhost:{config.PORT_BASE}"
OUT = ROOT / "verification.json"
RAW = ROOT / "reports" / "hw04" / "raw"

REQUIRED_FILES = [
    "config.py", "rag.py", "requirements.txt", ".env.example", "Makefile",
    "backend/app/main.py", "backend/app/database.py", "backend/app/models.py",
    "backend/app/crud.py", "backend/app/session_crud.py", "backend/app/schema.py",
    "backend/app/query_counter.py",
    "scripts/init_db.py", "scripts/seed_n1.py", "scripts/measure_n1.py", "scripts/explain_index.py",
    "frontend/package.json", "frontend/src/app.jsx", "frontend/src/pages/Login.jsx",
    "frontend/src/pages/Home.jsx", "frontend/src/pages/CreateRecord.jsx",
    "frontend/src/pages/UpdateRecord.jsx", "frontend/src/pages/DeleteRecord.jsx",
    "frontend/src/api/listingsApi.js",
    "reports/hw04/RUN_LOG.txt", "reports/hw04/METRICS.md", "reports/hw04/AI_USE.md",
]

results: list[dict] = []


def check(name: str):
    def wrap(fn):
        try:
            passed, details = fn()
        except Exception as exc:  # recorded as a failure instead of crashing
            passed, details = False, f"{type(exc).__name__}: {exc}"
        results.append({"check": name, "passed": bool(passed), "details": details})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {details}")
        return passed
    return wrap


def commit_hash() -> str:
    if os.getenv("COMMIT_HASH"):
        return os.environ["COMMIT_HASH"]
    try:
        return subprocess.run(
            ["git", "rev-parse", "--verify", "hw4^{commit}"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "PENDING - tag hw4 not created yet"


def backend_up() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def main() -> int:
    started = None
    rng = random.Random(config.VERIFY_SEED)
    http = requests.Session()
    temp_email = f"verify-{config.VERIFY_SEED}@example.com"
    temp_password = secrets.token_urlsafe(16)
    state: dict = {}

    @check("required_files")
    def _():
        missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
        return not missing, f"missing: {missing}" if missing else "all required files present"

    @check("python_compiles")
    def _():
        files = [p for p in ROOT.rglob("*.py") if not {".venv", "node_modules", "DATA236_demo4"} & set(p.parts)]
        for p in files:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        return True, f"{len(files)} files compiled"

    @check("config_values")
    def _():
        ok = (
            config.SID4 == 9486 and config.PORT_BASE == 8486 and config.PREFIX == "s9486"
            and config.SEED == 9486 and config.VERIFY_SEED == 269486 and config.DOMAIN_ID == 6
            and config.DB_NAME == "s9486_rel"
        )
        return ok, f"PORT_BASE={config.PORT_BASE}, DB_NAME={config.DB_NAME}, DOMAIN_ID={config.DOMAIN_ID}"

    @check("db_session_variable_name")
    def _():
        src = (ROOT / "backend/app/database.py").read_text(encoding="utf-8")
        return bool(re.search(r"^SessionLocal\s*=", src, re.M)), "SessionLocal defined in database.py"

    if not backend_up():
        started = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(config.PORT_BASE)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            if backend_up():
                break
            time.sleep(0.5)

    try:
        @check("backend_responds_on_port_base")
        def _():
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            return r.status_code == 200, f"GET {BASE_URL}/health -> {r.status_code}"

        @check("create_temp_user")
        def _():
            from backend.app import models
            from backend.app.database import SessionLocal
            from backend.app.session_crud import hash_password

            with SessionLocal() as db:
                db.query(models.User).filter(models.User.email == temp_email).delete()
                db.add(models.User(name="HW4 verify", email=temp_email, password_hash=hash_password(temp_password)))
                db.commit()
            return True, f"temporary user {temp_email}"

        @check("unauthenticated_requests_rejected")
        def _():
            codes = [requests.get(f"{BASE_URL}{p}", timeout=5).status_code
                     for p in ("/listings", "/listings/naive", "/listings/fixed", "/auth/me")]
            codes.append(requests.post(f"{BASE_URL}/listings", json={"title": "x", "address": "y"}, timeout=5).status_code)
            return all(c == 401 for c in codes), f"status codes without cookie: {codes}"

        @check("wrong_password_rejected")
        def _():
            r = requests.post(f"{BASE_URL}/auth/login", json={"email": temp_email, "password": "wrong-password"}, timeout=5)
            return r.status_code == 401, f"-> {r.status_code}"

        @check("login_works")
        def _():
            r = http.post(f"{BASE_URL}/auth/login", json={"email": temp_email, "password": temp_password}, timeout=5)
            state["set_cookie"] = r.headers.get("set-cookie", "")
            return r.status_code == 200 and r.json().get("email") == temp_email, f"-> {r.status_code}"

        @check("session_cookie_http_only_and_opaque")
        def _():
            raw = state["set_cookie"]
            token = http.cookies.get(config.SESSION_COOKIE_NAME, "")
            state["token"] = token
            http_only = "httponly" in raw.lower()
            opaque = bool(re.fullmatch(r"[0-9a-f]{64}", token)) and "verify" not in token
            return http_only and opaque, f"HttpOnly={http_only}, token is 64 hex chars={opaque}"

        @check("session_stored_server_side")
        def _():
            from backend.app import models
            from backend.app.database import SessionLocal

            token = http.cookies.get(config.SESSION_COOKIE_NAME, "")
            with SessionLocal() as db:
                row = db.get(models.SessionToken, token)
                return row is not None and row.expires_at > row.created_at, "token found in sessions table"

        @check("authenticated_requests_work")
        def _():
            r = http.get(f"{BASE_URL}/auth/me", timeout=5)
            r2 = http.get(f"{BASE_URL}/listings", params={"limit": 5}, timeout=5)
            return r.status_code == 200 and r2.status_code == 200 and isinstance(r2.json(), list), \
                f"/auth/me -> {r.status_code}, /listings -> {r2.status_code}"

        @check("crud_create_read_update_delete")
        def _():
            title = f"Verify listing {rng.randint(1000, 9999)}"
            c = http.post(f"{BASE_URL}/listings", json={"title": title, "address": "1 Verify St, San Jose, CA"}, timeout=5)
            lid = c.json()["id"]
            g = http.get(f"{BASE_URL}/listings/{lid}", timeout=5)
            u = http.put(f"{BASE_URL}/listings/{lid}", json={"title": title + " updated", "address": "2 Verify St"}, timeout=5)
            d = http.delete(f"{BASE_URL}/listings/{lid}", timeout=5)
            gone = http.get(f"{BASE_URL}/listings/{lid}", timeout=5)
            bad = http.post(f"{BASE_URL}/listings", json={"title": "", "address": ""}, timeout=5)
            ok = (c.status_code == 201 and g.json()["title"] == title and u.json()["title"].endswith("updated")
                  and d.status_code == 200 and gone.status_code == 404 and bad.status_code == 422)
            return ok, (f"POST {c.status_code}, GET {g.status_code}, PUT {u.status_code}, DELETE {d.status_code}, "
                        f"GET after delete {gone.status_code}, invalid POST {bad.status_code}")

        for version in ("naive", "fixed"):
            @check(f"{version}_endpoint_returns_data")
            def _(version=version):
                r = http.get(f"{BASE_URL}/listings/{version}", params={"page_size": 10}, timeout=10)
                body = r.json()
                state[version] = body
                has_related = any(item["inquiries"] for item in body["items"])
                return (r.status_code == 200 and body["count"] == 10 and has_related), \
                    f"items={body['count']}, includes inquiries={has_related}, X-SQL-Count={r.headers.get('X-SQL-Count')}"

        @check("naive_and_fixed_return_same_data")
        def _():
            return state["naive"]["items"] == state["fixed"]["items"], "identical items for page 1, size 10"

        @check("logout_invalidates_session")
        def _():
            http.post(f"{BASE_URL}/auth/logout", timeout=5)
            # replay the old token directly: it must be gone from the sessions table
            r = requests.get(f"{BASE_URL}/auth/me", cookies={config.SESSION_COOKIE_NAME: state.get("token", "")}, timeout=5)
            return r.status_code == 401, f"/auth/me with the old token after logout -> {r.status_code}"

        @check("n1_raw_data_180_requests")
        def _():
            path = RAW / "n1_requests.json"
            if not path.exists():
                return False, "PENDING: run scripts/measure_n1.py"
            n = len(json.loads(path.read_text())["requests"])
            return n == 180, f"{n} recorded requests"

        @check("rag_raw_outputs_present")
        def _():
            names = ["retrieved_chunks.txt", "no_rag.jsonl", "basic_rag.jsonl", "context_rag.jsonl",
                     "k_sweep.jsonl", "evaluation_table.md"]
            missing = [n for n in names if not (RAW / n).exists()]
            return not missing, f"PENDING: run rag.py (missing {missing})" if missing else "all RAG outputs present"
    finally:
        try:
            from backend.app import models
            from backend.app.database import SessionLocal

            with SessionLocal() as db:
                db.query(models.User).filter(models.User.email == temp_email).delete()
                db.commit()
        except Exception:
            pass
        if started:
            started.terminate()
            started.wait(timeout=10)

    payload = {
        "homework": 4,
        "sid4": config.SID4,
        "commit_hash": commit_hash(),
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "configuration": {
            "port_base": config.PORT_BASE,
            "prefix": config.PREFIX,
            "domain_id": config.DOMAIN_ID,
            "domain": config.DOMAIN_NAME,
            "database": config.DB_NAME,
            "hardware": config.HARDWARE,
            "llm_model": config.LLM_MODEL,
            "embedding_model": config.EMBEDDING_MODEL_NAME,
            "chunk_size": config.CHUNK_SIZE,
            "chunk_overlap": config.CHUNK_OVERLAP,
            "top_k": config.TOP_K,
        },
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "checks": results,
        "passed": sum(r["passed"] for r in results),
        "failed": sum(not r["passed"] for r in results),
        "all_passed": all(r["passed"] for r in results),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT}: {payload['passed']} passed, {payload['failed']} failed")
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
