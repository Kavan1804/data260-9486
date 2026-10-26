#!/usr/bin/env python3
"""HW7 smoke test. Writes reports/hw07/verification.json.

Checks behavior, not wording: config values, Ruff, the MySQL users table (username/role, bcrypt only),
FastAPI on PORT_BASE, JWT login 200/401, missing/invalid token 401, reader create 403, writer create 201,
writer delete 403, moderator delete 200, list 200, the hand-written agent loop on the nonexistent-ID case
and on fixed task A through the Reflexion path, the read-only csv_sql contract, the calculator, the saved
pricing snapshot hash, the 10-command safety gate, the offline test suites, and the raw evidence files.

It starts the backend if it is not running, creates one temporary landlord (deleted again), and never
edits application code. Usage (repo root):  make verify-hw07   (or python Homework7/scripts/verify_hw07.py)
After the final commit and `git tag hw7`, re-run so commit_hash is the tagged commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests
from hw7_common import BASE_URL, FIXTURES, RAW, REPORT_DIR, ROOT, banner, write_json

import config

OUT = REPORT_DIR / "verification.json"
REQUIRED = [
    "config.py",
    "requirements.txt",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    ".env.example",
    "Makefile",
    "AGENT.md",
    "backend/app/security.py",
    "backend/app/main.py",
    "scripts/migrate_hw07.py",
    "domain_tools/agent.py",
    "domain_tools/validation.py",
    "domain_tools/fixed_tasks.py",
    "domain_tools/reflexion.py",
    "bikeshare/tools.py",
    "bikeshare/pricing.py",
    "bikeshare/agent.py",
    "agent_tools/file_tools.py",
    "agent_tools/safety_gate.py",
    "frontend/src/pages/BikeShare.jsx",
    "Homework7/fixtures/agent_tasks.json",
    "Homework7/fixtures/hostile_pricing.html",
    "Homework7/fixtures/bikeshare/scenario_membership_wins.csv",
    "Homework7/fixtures/bikeshare/scenario_payperuse_wins.csv",
    "Homework7/tests/run_hw7_tests.py",
    "reports/hw07/RUN_LOG.txt",
    "reports/hw07/METRICS.md",
    "reports/hw07/AI_USE.md",
    "reports/hw07/THREAT_MODEL.md",
]
RAW_FILES = [
    "auth_demo.json",
    "reliability_attempts.csv",
    "reliability_attempts.json",
    "error_recovery.json",
    "reflexion_comparison.csv",
    "reflexion_comparison.json",
    "reflections.jsonl",
    "bikeshare_membership_wins.json",
    "bikeshare_payperuse_wins.json",
    "pricing_snapshot_membership_wins.txt",
    "pricing_snapshot_membership_wins.json",
    "pricing_snapshot_payperuse_wins.txt",
    "pricing_snapshot_payperuse_wins.json",
    "bikeshare_trip_summary_membership_wins.json",
    "bikeshare_trip_summary_payperuse_wins.json",
    "injection_results.csv",
    "injection_traces.json",
    "safety_gate_results.csv",
    "safety_gate_v1_false_allows.json",
    "file_tools_integration.json",
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


def build_payload(checks: list[dict]) -> dict:
    passed = sum(c["passed"] for c in checks)
    return {
        "homework": "HW7",
        "sid4": config.SID4,
        "prefix": config.PREFIX,
        "port_base": config.PORT_BASE,
        "domain_id": config.DOMAIN_ID,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "commit_hash": git("rev-parse", "HEAD"),
        "tag_hw7_commit": git("rev-list", "-n", "1", "hw7"),
        "working_tree_clean": git("status", "--porcelain") == "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": {
            "model": config.OLLAMA_MODEL,
            "ollama_url": config.OLLAMA_URL,
            "agent_framework_part4": "LangGraph create_react_agent + langchain-ollama ChatOllama",
            "jwt_algorithm": config.JWT_ALGORITHM,
            "access_token_expire_minutes": config.ACCESS_TOKEN_EXPIRE_MINUTES,
            "roles": list(config.ROLES),
            "mysql_db": config.DB_NAME,
        },
        "checks": checks,
        "summary": {"passed": passed, "total": len(checks), "all_passed": passed == len(checks)},
    }


def main() -> int:
    banner("HW7 self-check (verify_hw07)")
    http = requests.Session()
    started = None

    @check("required_files")
    def _():
        missing = [f for f in REQUIRED if not (ROOT / f).exists()]
        return not missing, f"missing: {missing}" if missing else f"{len(REQUIRED)} files present"

    @check("config_values")
    def _():
        expected = {
            "SID4": 9486,
            "PORT_BASE": 8486,
            "PREFIX": "s9486",
            "SEED": 9486,
            "VERIFY_SEED": 269486,
            "DOMAIN_ID": 6,
            "DB_NAME": "s9486_rel",
        }
        actual = {k: getattr(config, k) for k in expected}
        return actual == expected and bool(config.JWT_SECRET_KEY), json.dumps(actual)

    @check("ruff_check_and_format")
    def _():
        lint = subprocess.run([str(ROOT / ".venv/bin/ruff"), "check", "."], cwd=ROOT, capture_output=True, text=True)
        fmt = subprocess.run(
            [str(ROOT / ".venv/bin/ruff"), "format", "--check", "."], cwd=ROOT, capture_output=True, text=True
        )
        return lint.returncode == 0 and fmt.returncode == 0, (lint.stdout.strip().splitlines() or ["?"])[-1] + " | " + (
            fmt.stdout.strip().splitlines() or ["?"]
        )[-1]

    @check("mysql_users_table_hashed_passwords")
    def _():
        from sqlalchemy import inspect, text

        from backend.app.database import engine

        cols = {c["name"] for c in inspect(engine).get_columns("users")}
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT username, role, password_hash FROM users")).fetchall()
        hashed = all(r[2].startswith("$2") and len(r[2]) == 60 for r in rows)
        roles = sorted({r[1] for r in rows})
        ok = {"id", "username", "password_hash", "role"} <= cols and hashed and set(config.ROLES) <= set(roles)
        return ok, f"{len(rows)} users, roles {roles}, all bcrypt hashes: {hashed}"

    if not backend_up():
        started = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(config.PORT_BASE)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            if backend_up():
                break
            time.sleep(0.5)

    try:

        @check("fastapi_responds_on_port_base")
        def _():
            r = http.get(f"{BASE_URL}/health", timeout=5)
            return (
                r.status_code == 200,
                f"GET {BASE_URL}/health -> {r.status_code} (started by script: {started is not None})",
            )

        tok = {}

        @check("login_valid_200_invalid_401")
        def _():
            codes = []
            for role in config.ROLES:
                r = http.post(
                    f"{BASE_URL}/auth/login",
                    json={"username": f"s9486_{role}", "password": os.environ[f"HW7_{role.upper()}_PASSWORD"]},
                    timeout=10,
                )
                codes.append(r.status_code)
                tok[role] = {"Authorization": f"Bearer {r.json().get('access_token')}"}
            bad = http.post(f"{BASE_URL}/auth/login", json={"username": "s9486_reader", "password": "nope"}, timeout=10)
            return codes == [
                200,
                200,
                200,
            ] and bad.status_code == 401, f"valid -> {codes}, wrong password -> {bad.status_code}"

        @check("missing_and_invalid_token_401")
        def _():
            a = http.get(f"{BASE_URL}/auth/me", timeout=10).status_code
            b = http.get(f"{BASE_URL}/auth/me", headers={"Authorization": "Bearer abc.def.ghi"}, timeout=10).status_code
            c = http.get(f"{BASE_URL}/auth/me", headers=tok["reader"], timeout=10)
            return [a, b, c.status_code] == [401, 401, 200] and c.json()["role"] == "reader", f"{a}, {b}, me={c.json()}"

        @check("role_checks_create_delete_list")
        def _():
            body = {
                "full_name": "HW7 Verify",
                "company": "Verify Co",
                "email": f"verify.{config.VERIFY_SEED}.{int(time.time())}@example.com",
            }
            reader_create = http.post(f"{BASE_URL}/landlords", json=body, headers=tok["reader"], timeout=10).status_code
            w = http.post(f"{BASE_URL}/landlords", json=body, headers=tok["writer"], timeout=10)
            lid = w.json().get("id")
            writer_delete = http.delete(f"{BASE_URL}/landlords/{lid}", headers=tok["writer"], timeout=10).status_code
            mod_delete = http.delete(f"{BASE_URL}/landlords/{lid}", headers=tok["moderator"], timeout=10).status_code
            listing = http.get(f"{BASE_URL}/listings?limit=1", headers=tok["reader"], timeout=10).status_code
            codes = [reader_create, w.status_code, writer_delete, mod_delete, listing]
            return codes == [
                403,
                201,
                403,
                200,
                200,
            ], f"reader POST, writer POST, writer DELETE, moderator DELETE, GET -> {codes}"
    finally:
        if started:
            started.terminate()

    @check("agent_loop_error_recovery_nonexistent_id")
    def _():
        from domain_tools.agent import OllamaModel, run_agent
        from domain_tools.fixed_tasks import load_tasks, verify_error_recovery

        s = run_agent(
            load_tasks()["error_recovery"]["prompt"],
            model=OllamaModel(model=config.OLLAMA_MODEL),
            log_path=None,
            require_tool=True,
        )
        v = verify_error_recovery(s)
        return v["passed"], f"stop={s['stop_reason']}, tool calls={s['tool_calls']}, tool error={v['tool_error']!r}"

    @check("agent_loop_completes_task_A_with_reflexion")
    def _():
        from domain_tools.agent import OllamaModel
        from domain_tools.execute import default_repository
        from domain_tools.reflexion import ReflectionStore, run_with_reflexion

        model = OllamaModel(
            model=config.OLLAMA_MODEL, num_ctx=config.OLLAMA_NUM_CTX, temperature=0.7, seed=config.VERIFY_SEED
        )
        out = run_with_reflexion(
            "A", model, default_repository(), user_id="verify", run_id="verify-A", store=ReflectionStore()
        )
        ok = out["stop_reason"] in ("success", "budget_exhausted", "human_review") and out["tool_calls"] >= 2
        return ok, (
            f"clean stop={out['stop_reason']}, attempts={out['attempts']}, tool calls={out['tool_calls']}, "
            f"verifier passed={out['passed']}"
        )

    @check("csv_sql_read_only_and_calculator")
    def _():
        from bikeshare.tools import TripStore, calculator, csv_sql

        store = TripStore.from_path(FIXTURES / "bikeshare" / "scenario_payperuse_wins.csv")
        refused = [
            not csv_sql(store, q)["success"]
            for q in ("DROP TABLE trips", "SELECT 1; DELETE FROM trips", "PRAGMA table_info(trips)")
        ]
        n = csv_sql(store, "SELECT COUNT(*) AS n FROM trips")["data"]["rows"][0]["n"]
        calc_ok = calculator("29 * 48")["data"]["value"] == 1392 and not calculator("2**8")["success"]
        return all(refused) and n == 510 and calc_ok, f"non-SELECT refused {refused}, rows {n}, calculator ok {calc_ok}"

    @check("pricing_snapshots_hash_match")
    def _():
        out = []
        for name in ("membership_wins", "payperuse_wins"):
            meta = json.loads((RAW / f"pricing_snapshot_{name}.json").read_text(encoding="utf-8"))
            text = (RAW / f"pricing_snapshot_{name}.txt").read_text(encoding="utf-8")
            out.append(hashlib.sha256(text.encode("utf-8")).hexdigest() == meta["sha256"])
        return all(out), f"SHA-256 matches saved text: {out}"

    @check("safety_gate_10_commands")
    def _():
        from agent_tools.safety_gate import confirm_bash

        allow = ["ls -la", "grep -n DEBUG *.py", "cat a.py", "python3 -m py_compile a.py", "echo ok > out.txt"]
        block = ["rm -rf build", "sudo ls", "chmod 777 a.py", "echo x > /etc/hosts", "cat a > ~/.bashrc"]
        a = [confirm_bash(c)["allowed"] for c in allow]
        b = [not confirm_bash(c)["allowed"] for c in block]
        return all(a) and all(b), f"{sum(a)}/5 allowed, {sum(b)}/5 blocked"

    for script in (
        "tests/run_offline_tests.py",
        "Homework6/tests/run_hw6_tests.py",
        "Homework7/tests/run_hw7_tests.py",
    ):

        @check(f"offline_tests:{script}")
        def _(script=script):
            p = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, timeout=600)
            return p.returncode == 0, (p.stdout.strip().splitlines() or ["no output"])[-1]

    @check("raw_evidence_files")
    def _():
        missing = [f for f in RAW_FILES if not (RAW / f).exists()]
        return not missing, f"missing: {missing}" if missing else f"{len(RAW_FILES)} raw files present"

    payload = build_payload(results)
    write_json(OUT, payload)
    s = payload["summary"]
    print(f"\n{s['passed']}/{s['total']} checks passed -> {OUT.relative_to(ROOT)} (commit {payload['commit_hash']})")
    return 0 if s["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
