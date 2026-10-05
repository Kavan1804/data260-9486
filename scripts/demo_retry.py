#!/usr/bin/env python3
"""Part 3: show the three retry outcomes against the real s9486_rel data.

Faults are scripted so each case is exact:
  1. success on the first attempt
  2. first attempt fails, retry succeeds
  3. every allowed attempt fails -> clean {ok: false} envelope, no crash

Usage (repo root):  python scripts/demo_retry.py
"""

import json

from hw5_common import RAW, banner

from domain_tools.execute import DEFAULT_POLICY, default_repository, execute_tool
from domain_tools.faults import FaultyRepository, ScriptedInjector

CASES = [
    ("1. success on first attempt", [False]),
    ("2. fail, then retry succeeds", [True, False]),
    ("3. all retries fail", [True, True, True]),
]
TOOL, INPUTS = "get_listing", {"listing_code": "LST-00042"}


def main() -> int:
    banner("Part 3 - retry demonstration")
    p = DEFAULT_POLICY
    print(f"policy: max_attempts={p.max_attempts}, backoff={p.base_delay_s * 1000:.0f} ms x2 "
          f"(cap {p.max_delay_s * 1000:.0f} ms), timeout={p.timeout_s:.1f} s per attempt")
    print(f"call: execute_tool({TOOL!r}, {json.dumps(INPUTS)})\n")
    repo = default_repository()
    execute_tool(TOOL, INPUTS, repo=repo)  # warm the MySQL connection (not shown)
    records = []
    for label, script in CASES:
        attempts: list = []
        result = json.loads(execute_tool(TOOL, INPUTS, repo=FaultyRepository(repo, ScriptedInjector(script)),
                                         attempts_log=attempts))
        print(label)
        for a in attempts:
            print(f"   attempt {a['attempt']}: wait {a['delay_before_s'] * 1000:5.0f} ms -> {a['outcome']:17s}"
                  f" {a['latency_ms']:7.2f} ms  {a['error'] or ''}")
        shown = {"ok": result["ok"], "data": {"listing_code": result["data"]["listing_code"]} if result["ok"] else None,
                 "error": result["error"]}
        print(f"   result: {json.dumps(shown)}\n")
        records.append({"case": label, "fault_script": script, "attempts": attempts, "result": result})
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "retry_demo.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("saved reports/hw05/raw/retry_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
