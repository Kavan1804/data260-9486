#!/usr/bin/env python3
"""HW5 smoke test. Writes reports/hw05/verification.json.

Checks behavior, not wording: config values, FastAPI on PORT_BASE, the MySQL
schema (FK RESTRICT, unique fields), CRUD + error codes for both entities,
both MCP servers starting over STDIO and answering a tool call, the safety
rule, the offline test suite, and that the raw evidence files are complete.

It starts the backend if it is not running, uses a temporary user, landlord
and listing (all removed at the end), and never edits application code.

Usage (repo root):
    make verify-hw05            # or: python scripts/verify_hw05.py
After `git tag hw5`, re-run so commit_hash is the tagged commit.
"""

from __future__ import annotations

import asyncio
import csv
import json
import random
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime

import requests

from hw5_common import RAW, REPORT_DIR, ROOT, banner

import config

BASE_URL = f"http://localhost:{config.PORT_BASE}"
OUT = REPORT_DIR / "verification.json"

REQUIRED_FILES = [
    "config.py", "requirements.txt", ".env.example", "Makefile", "README.md",
    "backend/app/main.py", "backend/app/models.py", "backend/app/schema.py", "backend/app/crud.py",
    "frontend/package.json", "frontend/src/store/store.js", "frontend/src/features/listings/listingsSlice.js",
    "frontend/src/pages/Home.jsx", "frontend/src/pages/CreateRecord.jsx", "frontend/src/pages/UpdateRecord.jsx",
    "mcp_servers/meals_server.py", "mcp_servers/domain_server.py",
    "domain_tools/envelope.py", "domain_tools/execute.py", "domain_tools/retry.py", "domain_tools/faults.py",
    "domain_tools/safety.py", "domain_tools/agent.py", "tests/run_offline_tests.py",
    "scripts/migrate_hw05.py", "scripts/run_retry_experiment.py", "scripts/run_agent_scenarios.py",
    "reports/hw05/RUN_LOG.txt", "reports/hw05/METRICS.md", "reports/hw05/AI_USE.md", "reports/hw05/REFLECTION.md",
]

results: list[dict] = []


def check(name: str):
    def wrap(fn):
        try:
            passed, details = fn()
        except Exception as exc:  # recorded as a failure instead of crashing
            passed, details = False, f"{type(exc).__name__}: {exc}"
        results.append({"check": name, "passed": bool(passed), "details": details})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {details}", flush=True)
        return passed
    return wrap


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def backend_up() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=2).status_code == 200
    except requests.RequestException:
        return False


def main() -> int:
    banner("HW5 self-check (verify_hw05)")
    rng = random.Random(config.VERIFY_SEED)
    http = requests.Session()
    temp_email = f"verify-{config.VERIFY_SEED}@example.com"
    temp_password = secrets.token_urlsafe(16)
    landlord_email = f"verify.landlord.{config.VERIFY_SEED}@example.com"
    listing_code = f"LST-{rng.randint(90000, 99999)}"
    started = None

    @check("required_files")
    def _():
        missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
        return not missing, f"missing: {missing}" if missing else f"{len(REQUIRED_FILES)} files present"

    @check("python_compiles")
    def _():
        skip = {".venv", "node_modules", "DATA236_Demo5", "Homework1", "Homework2", "Homework3", "Homework4"}
        files = [p for p in ROOT.rglob("*.py") if not skip & set(p.relative_to(ROOT).parts)]
        for p in files:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        return True, f"{len(files)} files compiled"

    @check("config_values")
    def _():
        expected = {"SID4": 9486, "PORT_BASE": 8486, "PREFIX": "s9486", "SEED": 9486,
                    "VERIFY_SEED": 269486, "DOMAIN_ID": 6, "DB_NAME": "s9486_rel"}
        actual = {k: getattr(config, k) for k in expected}
        derived = (config.PORT_BASE == 8000 + config.SID4 % 900 and config.VERIFY_SEED == 260000 + config.SID4
                   and config.DOMAIN_ID == config.SID4 % 8)
        return actual == expected and derived, json.dumps(actual)

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
        @check("fastapi_responds_on_port_base")
        def _():
            r = requests.get(f"{BASE_URL}/health", timeout=5)
            return r.status_code == 200, f"GET {BASE_URL}/health -> {r.status_code} (started by script: {started is not None})"

        @check("mysql_schema_constraints")
        def _():
            from sqlalchemy import inspect, text

            from backend.app.database import engine

            insp = inspect(engine)
            landlord_cols = {c["name"] for c in insp.get_columns("landlords")}
            listing_cols = {c["name"]: c for c in insp.get_columns("listings")}
            with engine.connect() as conn:
                rule = conn.execute(text(
                    "SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = :db AND CONSTRAINT_NAME = 'fk_listings_landlord'"),
                    {"db": config.DB_NAME}).scalar()
                uniques = {r[0] for r in conn.execute(text(
                    "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = :db "
                    "AND CONSTRAINT_TYPE = 'UNIQUE'"), {"db": config.DB_NAME})}
            ok = ({"id", "full_name", "company", "email", "created_at", "updated_at"} <= landlord_cols
                  and {"listing_code", "available_units", "landlord_id", "created_at", "updated_at"} <= set(listing_cols)
                  and not listing_cols["landlord_id"]["nullable"] and rule == "RESTRICT"
                  and {"uq_landlords_email", "uq_listings_listing_code"} <= uniques)
            return ok, f"fk_listings_landlord ON DELETE {rule}; unique: {sorted(uniques & {'uq_landlords_email', 'uq_listings_listing_code'})}"

        @check("temp_user_and_login")
        def _():
            from backend.app import models
            from backend.app.database import SessionLocal
            from backend.app.session_crud import hash_password

            with SessionLocal() as db:
                stale = db.query(models.Landlord).filter(models.Landlord.email == landlord_email).first()
                if stale:
                    db.query(models.Listing).filter(models.Listing.landlord_id == stale.id).delete()
                    db.delete(stale)
                db.query(models.Listing).filter(models.Listing.listing_code == listing_code).delete()
                db.query(models.User).filter(models.User.email == temp_email).delete()
                db.add(models.User(name="HW5 verify", email=temp_email, password_hash=hash_password(temp_password)))
                db.commit()
            r = http.post(f"{BASE_URL}/auth/login", json={"email": temp_email, "password": temp_password}, timeout=5)
            return r.status_code == 200, f"login -> {r.status_code}"

        state: dict = {}

        @check("landlord_crud_and_errors")
        def _():
            c = http.post(f"{BASE_URL}/landlords", json={"full_name": "Verify Landlord", "company": "Verify Co",
                                                         "email": landlord_email}, timeout=5)
            state["landlord_id"] = lid = c.json()["id"]
            lst = http.get(f"{BASE_URL}/landlords", params={"skip": 0, "limit": 5}, timeout=5).json()
            g = http.get(f"{BASE_URL}/landlords/{lid}", timeout=5)
            u = http.put(f"{BASE_URL}/landlords/{lid}", json={"company": "Verify Co 2"}, timeout=5)
            dup = http.post(f"{BASE_URL}/landlords", json={"full_name": "Dup", "company": "x", "email": landlord_email}, timeout=5)
            bad = http.post(f"{BASE_URL}/landlords", json={"full_name": "Bad", "company": "x", "email": "not-an-email"}, timeout=5)
            missing = http.get(f"{BASE_URL}/landlords/999999999", timeout=5)
            ok = (c.status_code == 201 and set(lst) == {"total", "skip", "limit", "items"} and len(lst["items"]) <= 5
                  and g.status_code == 200 and u.json()["company"] == "Verify Co 2" and dup.status_code == 409
                  and bad.status_code == 422 and missing.status_code == 404)
            return ok, (f"POST {c.status_code}, list total={lst['total']}, GET {g.status_code}, PUT {u.status_code}, "
                        f"dup email {dup.status_code}, bad email {bad.status_code}, missing {missing.status_code}")

        @check("listing_crud_relationship_and_errors")
        def _():
            lid = state["landlord_id"]
            body = {"title": "Verify unit", "address": "1 Verify St, San Jose, CA", "listing_code": listing_code,
                    "landlord_id": lid}
            c = http.post(f"{BASE_URL}/listings", json=body, timeout=5)
            state["listing_id"] = xid = c.json()["id"]
            page = http.get(f"{BASE_URL}/listings", params={"limit": 3}, timeout=5).json()
            g = http.get(f"{BASE_URL}/listings/{xid}", timeout=5)
            u = http.put(f"{BASE_URL}/listings/{xid}", json={"available_units": 4}, timeout=5)
            rel = http.get(f"{BASE_URL}/landlords/{lid}/listings", timeout=5).json()
            dup = http.post(f"{BASE_URL}/listings", json=body, timeout=5)
            badcode = http.post(f"{BASE_URL}/listings", json={**body, "listing_code": "ABC"}, timeout=5)
            badfk = http.post(f"{BASE_URL}/listings", json={**body, "listing_code": "LST-00000", "landlord_id": 999999999}, timeout=5)
            restrict = http.delete(f"{BASE_URL}/landlords/{lid}", timeout=5)
            ok = (c.status_code == 201 and c.json()["available_units"] == 1 and len(page["items"]) <= 3
                  and g.status_code == 200 and u.json()["available_units"] == 4
                  and [i["id"] for i in rel["items"]] == [xid] and dup.status_code == 409
                  and badcode.status_code == 422 and badfk.status_code == 422 and restrict.status_code == 409)
            return ok, (f"POST {c.status_code} (default units {c.json()['available_units']}), GET {g.status_code}, "
                        f"PUT {u.status_code}, relationship ids {[i['id'] for i in rel['items']]}, dup code {dup.status_code}, "
                        f"bad code {badcode.status_code}, bad landlord_id {badfk.status_code}, "
                        f"delete landlord with listing {restrict.status_code}")

        @check("delete_listing_then_landlord")
        def _():
            d1 = http.delete(f"{BASE_URL}/listings/{state['listing_id']}", timeout=5)
            gone = http.get(f"{BASE_URL}/listings/{state['listing_id']}", timeout=5)
            d2 = http.delete(f"{BASE_URL}/landlords/{state['landlord_id']}", timeout=5)
            ok = d1.status_code == 200 and gone.status_code == 404 and d2.status_code == 200
            return ok, f"DELETE listing {d1.status_code}, GET after {gone.status_code}, DELETE landlord {d2.status_code}"

        @check("unauthenticated_requests_rejected")
        def _():
            codes = [requests.get(f"{BASE_URL}{p}", timeout=5).status_code for p in ("/landlords", "/listings", "/landlords/1/listings")]
            return all(c == 401 for c in codes), f"without cookie: {codes}"
    finally:
        try:
            from backend.app import models
            from backend.app.database import SessionLocal

            with SessionLocal() as db:
                db.query(models.Listing).filter(models.Listing.listing_code == listing_code).delete()
                db.query(models.Landlord).filter(models.Landlord.email == landlord_email).delete()
                db.query(models.User).filter(models.User.email == temp_email).delete()
                db.commit()
        except Exception:
            pass
        if started:
            started.terminate()
            started.wait(timeout=10)

    from mcp_calls import DOMAIN_CALLS, run_server

    @check("mcp_meals_server_starts_and_responds")
    def _():
        run = asyncio.run(run_server("meals_server.py", [("search_meals_by_name", {"query": "Arrabiata", "limit": 3}, "valid")]))
        names = sorted(t["name"] for t in run["tools"])
        call = run["calls"][0]
        res = call["result"]
        ok = (names == sorted(["search_meals_by_name", "meals_by_ingredient", "random_meal", "meal_details"])
              and not call["is_error"] and isinstance(res, dict) and res.get("count", 0) >= 1
              and {"id", "name", "area", "category", "thumb"} <= set(res["results"][0]))
        return ok, f"server '{run['server_name']}', tools {names}, search_meals_by_name -> count={res.get('count') if isinstance(res, dict) else res}"

    @check("mcp_domain_server_starts_and_responds")
    def _():
        run = asyncio.run(run_server("domain_server.py", DOMAIN_CALLS))
        names = sorted(t["name"] for t in run["tools"])
        envelopes = [c["result"] for c in run["calls"]]
        valid_ok = all(e["ok"] for c, e in zip(run["calls"], envelopes) if c["kind"] == "valid")
        invalid_clean = all(e["ok"] is False and e["data"] is None and e["error"]
                            for c, e in zip(run["calls"], envelopes) if c["kind"] == "invalid")
        ok = names == sorted(["search_listings", "get_listing", "landlord_portfolio_stats"]) and valid_ok and invalid_clean
        return ok, f"server '{run['server_name']}', tools {names}, valid calls ok={valid_ok}, invalid calls clean envelope={invalid_clean}"

    @check("safety_rule_blocks_without_exception")
    def _():
        from domain_tools.contracts import SAFETY_BLOCKED
        from domain_tools.execute import execute_tool

        r = json.loads(execute_tool(*SAFETY_BLOCKED))
        return r["ok"] is False and r["data"] is None and "fair-housing" in r["error"], r["error"][:90]

    @check("offline_tests_pass")
    def _():
        p = subprocess.run([sys.executable, "tests/run_offline_tests.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        m = re.search(r"(\d+)/(\d+) tests passed", p.stdout)
        ok = p.returncode == 0 and m and m.group(1) == m.group(2) and int(m.group(2)) >= 8
        return ok, m.group(0) if m else p.stdout[-200:]

    @check("retry_raw_data_150_calls_reproducible")
    def _():
        from domain_tools.faults import FaultInjector

        rows = list(csv.DictReader((RAW / "retry_calls.csv").open(encoding="utf-8")))
        per_rate = {r: [x for x in rows if float(x["failure_rate"]) == r] for r in config.FAILURE_RATES}
        replay_ok = True
        for rate, calls in per_rate.items():
            inj = FaultInjector(rate, config.VERIFY_SEED)
            for row in calls:
                expected = []
                for _ in range(int(row["attempts"])):
                    try:
                        inj.check()
                        expected.append("-")
                    except Exception:
                        expected.append("F")
                replay_ok &= ";".join(expected) == row["injected_failures"]
        counts = {f"{r:.0%}": len(c) for r, c in per_rate.items()}
        return len(rows) == 150 and all(len(c) == 50 for c in per_rate.values()) and replay_ok, \
            f"{len(rows)} calls {counts}; failure decisions replay from VERIFY_SEED: {replay_ok}"

    @check("agent_runs_logged")
    def _():
        events = [json.loads(line) for line in (RAW / "agent_runs.jsonl").read_text(encoding="utf-8").splitlines()]
        stops = [e for e in events if e["event"] == "stop"]
        reasons = sorted({e["stop_reason"] for e in stops})
        ok = len(stops) >= 4 and all(e["model"] == config.LLM_MODEL for e in stops) and any(e["event"] == "tool_call" for e in events)
        return ok, f"{len(stops)} runs with {config.LLM_MODEL}, stop reasons {reasons}"

    @check("mcp_raw_outputs_present")
    def _():
        files = ["mcp_meals_calls.json", "mcp_domain_calls.json"]
        missing = [f for f in files if not (RAW / f).exists()]
        return not missing, f"missing {missing}" if missing else "both MCP call recordings present"

    @check("metrics_and_reflection_filled")
    def _():
        metrics = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
        words = len(re.findall(r"\b[\w'-]+\b", (REPORT_DIR / "REFLECTION.md").read_text(encoding="utf-8")))
        ok = "PENDING" not in metrics and 200 <= words <= 300
        return ok, f"METRICS pending sections: {metrics.count('PENDING')}; REFLECTION words: {words}"

    @check("ollama_model_available")
    def _():
        tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5).json()
        names = [m["name"] for m in tags.get("models", [])]
        return config.LLM_MODEL in names, f"{config.LLM_MODEL} in ollama list: {config.LLM_MODEL in names}"

    tag_commit = git("rev-parse", "--verify", "hw5^{commit}")
    head = git("rev-parse", "HEAD")
    payload = {
        "homework": 5,
        "sid4": config.SID4,
        "commit_hash": tag_commit or head,
        "tag": "hw5" if tag_commit else None,
        "head_commit": head,
        "head_is_tagged_commit": bool(tag_commit) and tag_commit == head,
        "working_tree_clean": git("status", "--porcelain", "--untracked-files=no") == "",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "configuration": {
            "port_base": config.PORT_BASE,
            "prefix": config.PREFIX,
            "domain_id": config.DOMAIN_ID,
            "domain": config.DOMAIN_NAME,
            "database": config.DB_NAME,
            "hardware": config.HARDWARE,
            "llm_model": config.LLM_MODEL,
            "agent_max_steps": config.AGENT_MAX_STEPS,
            "retry": {"max_attempts": config.RETRY_MAX_ATTEMPTS, "base_delay_s": config.RETRY_BASE_DELAY_S,
                      "max_delay_s": config.RETRY_MAX_DELAY_S, "timeout_s": config.CALL_TIMEOUT_S},
            "failure_rates": config.FAILURE_RATES,
            "calls_per_rate": config.CALLS_PER_RATE,
        },
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "checks": results,
        "passed": sum(r["passed"] for r in results),
        "failed": sum(not r["passed"] for r in results),
        "all_passed": all(r["passed"] for r in results),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\ncommit {payload['commit_hash']} (tag hw5: {bool(tag_commit)}, HEAD is tagged commit: {payload['head_is_tagged_commit']})")
    print(f"Wrote {OUT.relative_to(ROOT)}: {payload['passed']} passed, {payload['failed']} failed")
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
