#!/usr/bin/env python3
"""Part 5 I: one allowed and one blocked call through execute_tool (real data).

Usage (repo root):  python scripts/demo_safety.py
"""

import json

from hw5_common import RAW, banner

from domain_tools.contracts import SAFETY_ALLOWED, SAFETY_BLOCKED
from domain_tools.execute import execute_tool


def main() -> int:
    banner("Part 5 - fair-housing safety rule in execute_tool")
    records = []
    for label, (name, inputs) in [("ALLOWED", SAFETY_ALLOWED), ("BLOCKED", SAFETY_BLOCKED)]:
        raw = execute_tool(name, inputs)
        result = json.loads(raw)
        print(f"{label}: execute_tool({name!r}, {json.dumps(inputs)})")
        if result["ok"]:
            codes = [l["listing_code"] for l in result["data"]["listings"]]
            print(f"  -> ok=true, error=null, {result['data']['count']} listings: {codes}\n")
        else:
            print(f"  -> {raw}\n")
        records.append({"case": label, "tool": name, "inputs": inputs, "result": result})
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "safety_demo.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("saved reports/hw05/raw/safety_demo.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
