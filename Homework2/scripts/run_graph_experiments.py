from __future__ import annotations
import json, random, statistics, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from realtygraph import build_workflow, initialize_state

class FakeModel:
    def __init__(self, rng: random.Random, invalid_attempts: int = 0): self.rng, self.remaining, self.calls = rng, invalid_attempts, 0
    def generate_json(self, prompt: str):
        self.calls += 1
        if self.remaining:
            self.remaining -= 1
            return {"tags": ["bad"], "summary": "This deliberately invalid output has too many words " * 10}
        return {"tags": ["user", "management", "backend"], "summary": "A concise user-management task summary."}

def run(seed: int, ceiling: int, invalid_attempts: int = 0):
    model = FakeModel(random.Random(seed), invalid_attempts)
    state = initialize_state("User management", "Create a user record", "student@example.com", "Tag this request", model, turn_ceiling=ceiling)
    start = time.perf_counter(); result = build_workflow().invoke(state); latency = (time.perf_counter() - start) * 1000
    return {"valid": bool(result.get("reviewer_feedback", {}).get("approved")), "attempts": model.calls, "turn_count": result.get("turn_count", 0), "latency_ms": round(latency, 3)}

def main():
    root = Path(__file__).resolve().parents[1]; out = root / "reports" / "hw02"; (out / "raw").mkdir(parents=True, exist_ok=True)
    cases = {"title": "User management", "content": "Add a user with name and email", "email": "student@example.com", "task": "Generate three useful tags and a concise summary."}
    (out / "cases").mkdir(exist_ok=True); (out / "cases" / "schema_input.json").write_text(json.dumps(cases, indent=2) + "\n")
    schema = [run(9486 + i, 10) for i in range(30)]
    ceilings = {str(c): [run(260000 + i, c) for i in range(20)] for c in (2, 10)}
    adversarial = [run(269486 + i, 2, invalid_attempts=99) for i in range(5)]
    for name, data in (("schema_runs.json", schema), ("ceiling_comparison.json", ceilings), ("adversarial_runs.json", adversarial)):
        (out / "raw" / name).write_text(json.dumps(data, indent=2, default=str) + "\n")
    print("Wrote HW2 experiment artifacts to", out)

if __name__ == "__main__": main()
