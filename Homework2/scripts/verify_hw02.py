from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from user_management_app.main import User, app, users
from realtygraph import build_workflow, initialize_state

class SmokeModel:
    def generate_json(self, prompt): return {"tags": ["user", "testing", "fastapi"], "summary": "Smoke test output for the user management graph."}

def check(name, fn):
    try: fn(); return {"check": name, "passed": True}
    except Exception as e: return {"check": name, "passed": False, "error": str(e)}

def main():
    client = TestClient(app); users[:] = [User(id=1, name="Alice", email="alice@example.com"), User(id=2, name="Bob", email="bob@example.com")]
    results = [
        check("GET / responds", lambda: (_ for _ in ()).throw(AssertionError()) if client.get("/").status_code != 200 else None),
        check("API returns two users", lambda: (_ for _ in ()).throw(AssertionError()) if len(client.get("/api/users").json()) != 2 else None),
        check("Search matches email", lambda: (_ for _ in ()).throw(AssertionError()) if len(client.get("/api/users?search=alice@").json()) != 1 else None),
        check("Create and update ID 1", lambda: (_ for _ in ()).throw(AssertionError()) if client.post("/api/users", json={"name":"Cara","email":"cara@example.com"}).status_code != 201 or client.put("/api/users/1", json={"name":"Alicia","email":"alicia@example.com"}).json()["name"] != "Alicia" else None),
        check("Delete highest ID", lambda: (_ for _ in ()).throw(AssertionError()) if client.delete("/api/users/highest").json()["id"] != 3 else None),
        check("Graph completes with valid proposal", lambda: (_ for _ in ()).throw(AssertionError()) if not build_workflow().invoke(initialize_state("t", "c", "e", "task", SmokeModel())).get("reviewer_feedback", {}).get("approved") else None),
    ]
    out = Path(__file__).resolve().parents[1] / "reports" / "hw02"; out.mkdir(parents=True, exist_ok=True)
    payload = {"homework": 2, "SID4": 9486, "commit_hash": os.getenv("COMMIT_HASH", "local-uncommitted"), "model": "qwen3:4b via src/model_client.py (documented substitute for qwen3:8b)", "SEED": 9486, "VERIFY_SEED": 269486, "checks": results, "passed": all(x["passed"] for x in results)}
    (out / "verification.json").write_text(json.dumps(payload, indent=2) + "\n"); print(json.dumps(payload, indent=2)); raise SystemExit(0 if payload["passed"] else 1)

if __name__ == "__main__": main()
