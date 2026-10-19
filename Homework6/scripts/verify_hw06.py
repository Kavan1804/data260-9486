#!/usr/bin/env python3
"""HW6 smoke test. Writes reports/hw06/verification.json.

Checks behavior, not wording: config values, MongoDB reachable with the
validated collections, FastAPI on PORT_BASE, one listing-document CRUD cycle
(+ 422/400/404), two POST /api/chat turns, GET /api/memory and
GET /api/aggregate, a file-memory command, the consolidation fixture, and the
offline test suites.

It starts the backend if it is not running (MySQL DATABASE_URL must be set,
because the HW5 app imports it), uses a temporary listing document and a
temporary chat user (all removed at the end), and never edits application code.

Usage (repo root):
    make verify-hw06            # or: python Homework6/scripts/verify_hw06.py
After `git tag hw6`, re-run so commit_hash is the tagged commit.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from hw6_common import BASE_URL, FIXTURES, REPORT_DIR, ROOT, banner, write_json

import config

OUT = REPORT_DIR / "verification.json"

REQUIRED_FILES = [
    "config.py", "requirements.txt", ".env.example", "Makefile", "AGENT.md", "MEMORY.md",
    "backend/app/main.py", "backend/app/mongo.py", "backend/app/doc_schema.py", "backend/app/memory_logic.py",
    "backend/app/file_memory.py", "backend/app/routers/listing_docs.py", "backend/app/routers/memory.py",
    "domain_tools/agent.py", "Homework6/README_HW6.md", "Homework6/memory_probes.yaml",
    "Homework6/fixtures/conversation_30.json", "Homework6/fixtures/MEMORY_original_55.md",
    "Homework6/tests/run_hw6_tests.py", "Homework6/scripts/run_memory_experiments.py",
    "Homework6/scripts/score_probes.py", "Homework6/scripts/memory_cost.py",
    "reports/hw06/METRICS.md", "reports/hw06/AI_USE.md",
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
        "homework": "HW6",
        "sid4": config.SID4,
        "prefix": config.PREFIX,
        "port_base": config.PORT_BASE,
        "domain_id": config.DOMAIN_ID,
        "seed": config.SEED,
        "verify_seed": config.VERIFY_SEED,
        "commit_hash": git("rev-parse", "HEAD"),
        "tag_hw6_commit": git("rev-list", "-n", "1", "hw6"),
        "working_tree_clean": git("status", "--porcelain") == "",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": {
            "ollama_model": config.OLLAMA_MODEL,
            "ollama_embed_model": config.OLLAMA_EMBED_MODEL or "hash-bow-256 (local fallback, no embedding model set)",
            "ollama_num_ctx": config.OLLAMA_NUM_CTX,
            "mongodb_uri": config.MONGODB_URI,
            "mongodb_db": config.MONGODB_DB,
            "short_term_n": config.SHORT_TERM_N,
            "summarize_every_user_msgs": config.SUMMARIZE_EVERY_USER_MSGS,
            "episodic_top_k": config.EPISODIC_TOP_K,
        },
        "checks": checks,
        "summary": {"passed": passed, "total": len(checks), "all_passed": passed == len(checks)},
    }


def main() -> int:
    banner("HW6 self-check (verify_hw06)")
    http = requests.Session()
    user_id = f"verify-{config.VERIFY_SEED}"
    session_id = f"verify-session-{config.VERIFY_SEED}"
    started = None
    state: dict = {}

    @check("required_files")
    def _():
        missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
        return not missing, f"missing: {missing}" if missing else f"{len(REQUIRED_FILES)} files present"

    @check("python_compiles")
    def _():
        files = [p for d in ("backend", "domain_tools", "Homework6/scripts", "Homework6/tests")
                 for p in (ROOT / d).rglob("*.py")]
        for p in files:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        return True, f"{len(files)} files compiled"

    @check("config_values")
    def _():
        expected = {"SID4": 9486, "PORT_BASE": 8486, "PREFIX": "s9486", "SEED": 9486, "VERIFY_SEED": 269486,
                    "DOMAIN_ID": 6, "MONGODB_DB": "s9486_doc"}
        actual = {k: getattr(config, k) for k in expected}
        return actual == expected, str(actual)

    @check("mongodb_ping_and_validators")
    def _():
        from backend.app.mongo import VALIDATORS, get_db

        db = get_db()
        db.command("ping")
        infos = {c["name"]: c for c in db.list_collections()}
        with_validator = [n for n in VALIDATORS if "$jsonSchema" in infos.get(n, {}).get("options", {}).get("validator", {})]
        return len(with_validator) == len(VALIDATORS), f"{config.MONGODB_URI}/{config.MONGODB_DB}: {with_validator}"

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
            r = http.get(f"{BASE_URL}/health", timeout=5)
            return r.status_code == 200, f"GET {BASE_URL}/health -> {r.status_code} (started by script: {started is not None})"

        @check("listing_doc_crud")
        def _():
            body = {"title": f"Verify listing {config.VERIFY_SEED}", "description": "temporary verify_hw06 document",
                    "property_type": "studio", "available_from": "2026-12-01T09:00:00Z"}
            c = http.post(f"{BASE_URL}/api/listings", json=body, timeout=10)
            doc_id = c.json().get("id") if c.status_code == 201 else None
            state["doc_id"] = doc_id
            one = http.get(f"{BASE_URL}/api/listings/{doc_id}", timeout=10)
            many = http.get(f"{BASE_URL}/api/listings", timeout=10)
            upd = http.put(f"{BASE_URL}/api/listings/{doc_id}", json={"status": "pending"}, timeout=10)
            dele = http.delete(f"{BASE_URL}/api/listings/{doc_id}", timeout=10)
            gone = http.get(f"{BASE_URL}/api/listings/{doc_id}", timeout=10)
            codes = [c.status_code, one.status_code, many.status_code, upd.status_code, dele.status_code, gone.status_code]
            ok = (codes == [201, 200, 200, 200, 200, 404] and c.json().get("status") == "available"
                  and any(d["id"] == doc_id for d in many.json()) and upd.json().get("status") == "pending")
            if ok:
                state.pop("doc_id")
            return ok, f"POST/GET/GET all/PUT/DELETE/GET -> {codes}"

        @check("listing_doc_validation_errors")
        def _():
            bad_enum = http.post(f"{BASE_URL}/api/listings", json={"title": "x", "property_type": "castle",
                                                                    "available_from": "2026-12-01"}, timeout=10)
            missing = http.post(f"{BASE_URL}/api/listings", json={"property_type": "studio"}, timeout=10)
            bad_id = http.get(f"{BASE_URL}/api/listings/not-an-id", timeout=10)
            codes = [bad_enum.status_code, missing.status_code, bad_id.status_code]
            return codes == [422, 422, 400], f"invalid enum / missing fields / malformed id -> {codes}"

        @check("chat_reply_and_memory_used")
        def _():
            msgs = ["My name is Verify and my budget is $2,000 per month.", "What budget did I mention?"]
            bodies = []
            for m in msgs:
                r = http.post(f"{BASE_URL}/api/chat", json={"user_id": user_id, "session_id": session_id, "message": m,
                                                           "run_id": "verify_hw06"}, timeout=600)
                if r.status_code != 200:
                    return False, f"POST /api/chat -> {r.status_code}: {r.text[:200]}"
                bodies.append(r.json())
            last = bodies[-1]
            used = last["memory_used"]
            ok = (all(b["reply"].strip() for b in bodies) and used["short_term"]["count"] >= 2
                  and {"session_summary", "lifetime_summary", "episodic_facts"} <= set(used)
                  and "latency_ms" in last["usage"])
            return ok, (f"2 replies; window on turn 2 = {used['short_term']['count']} msgs; "
                        f"prompt_tokens = {last['usage']['prompt_tokens']}; latency = {last['usage']['latency_ms']} ms")

        @check("memory_endpoint")
        def _():
            r = http.get(f"{BASE_URL}/api/memory/{user_id}", timeout=30)
            body = r.json()
            keys = {"messages", "latest_session_summary", "latest_lifetime_summary", "episodes"}
            return (r.status_code == 200 and keys <= set(body) and len(body["messages"]) >= 4,
                    f"-> {r.status_code}; {len(body.get('messages', []))} messages, {len(body.get('episodes', []))} episodes")

        @check("aggregate_endpoint")
        def _():
            r = http.get(f"{BASE_URL}/api/aggregate/{user_id}", timeout=30)
            body = r.json()
            total = sum(d["messages"] for d in body.get("daily_message_counts", []))
            return r.status_code == 200 and total >= 4, f"-> {r.status_code}; daily counts {body.get('daily_message_counts')}"

        @check("file_memory_help_command")
        def _():
            r = http.post(f"{BASE_URL}/api/chat", json={"user_id": user_id, "message": "/help"}, timeout=30)
            reply = r.json().get("reply", "")
            return r.status_code == 200 and all(c in reply for c in ("/memory", "/compact", "/dream")), f"-> {r.status_code}"
    finally:
        if started:
            started.terminate()

    @check("consolidation_fixture")
    def _():
        from backend.app import file_memory

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "MEMORY.md"
            original = (FIXTURES / "MEMORY_original_55.md").read_text(encoding="utf-8")
            path.write_text(original, encoding="utf-8")
            result = file_memory.handle_command("/compact", path=path)
            checks = file_memory.verify_consolidation(original, path.read_text(encoding="utf-8"), result["report"])
        failed = [c["check"] for c in checks if not c["passed"]]
        return len(original.splitlines()) == 55 and not failed, result["reply"] + (f"; failed: {failed}" if failed else "")

    for script in ("tests/run_offline_tests.py", "Homework6/tests/run_hw6_tests.py"):
        @check(f"offline_tests:{script}")
        def _(script=script):
            p = subprocess.run([sys.executable, script], cwd=ROOT, capture_output=True, text=True, timeout=300)
            tail = (p.stdout.strip().splitlines() or ["no output"])[-1]
            return p.returncode == 0, tail

    @check("cleanup_temp_data")
    def _():
        from backend.app.mongo import EPISODES, LISTINGS, MESSAGES, SUMMARIES, get_db

        db = get_db()
        removed = {c: db[c].delete_many({"user_id": user_id}).deleted_count for c in (MESSAGES, SUMMARIES, EPISODES)}
        if state.get("doc_id"):
            from bson import ObjectId

            removed[LISTINGS] = db[LISTINGS].delete_many({"_id": ObjectId(state["doc_id"])}).deleted_count
        return True, f"removed {removed}"

    payload = build_payload(results)
    write_json(OUT, payload)
    s = payload["summary"]
    print(f"\n{s['passed']}/{s['total']} checks passed -> {OUT.relative_to(ROOT)} (commit {payload['commit_hash']})")
    return 0 if s["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
