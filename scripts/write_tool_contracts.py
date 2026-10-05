#!/usr/bin/env python3
"""Part 3 step 18: write reports/hw05/TOOL_CONTRACTS.md.

For each domain tool: the JSON input schema (from TOOL_SPECS), the rejected
input used in Part 2B, and the error the MCP server actually returned for it
(read from raw/mcp_domain_calls.json, recorded by scripts/mcp_calls.py).

Usage (repo root):  python scripts/write_tool_contracts.py
"""

import json

from hw5_common import RAW, REPORT_DIR, banner

from domain_tools.contracts import REJECTED, VALID
from domain_tools.execute import TOOL_SPECS


def main() -> int:
    banner("Part 3 - tool contracts")
    recorded = json.loads((RAW / "mcp_domain_calls.json").read_text(encoding="utf-8"))
    by_call = {(c["tool"], json.dumps(c["arguments"], sort_keys=True)): c for c in recorded["calls"]}

    out = [
        "# Domain tool contracts (Part 3)",
        "",
        f"Server `{recorded['server_name']}`, recorded {recorded['started_at']} over MCP STDIO "
        "(`scripts/mcp_calls.py`, the same calls as the MCP Inspector screenshots).",
        "Every tool returns the envelope `{\"ok\": bool, \"data\": ..., \"error\": null | \"message\"}`.",
        "",
    ]
    for name, spec in TOOL_SPECS.items():
        bad, _, why = REJECTED[name]
        call = by_call.get((name, json.dumps(bad, sort_keys=True)))
        if call is None:
            raise SystemExit(f"no recorded call for rejected {name} input; run scripts/mcp_calls.py first")
        good = by_call[(name, json.dumps(VALID[name], sort_keys=True))]["result"]
        out += [
            f"## {name}",
            "",
            spec["description"],
            "",
            "Expected input schema:",
            "```json", json.dumps(spec["schema"], indent=2), "```",
            f"Valid example: `{json.dumps(VALID[name])}` -> ok = {str(good['ok']).lower()}",
            "",
            f"Rejected input: `{json.dumps(bad)}`",
            "",
            "Returned output:",
            "```json", json.dumps(call["result"], indent=2), "```",
            f"Why rejected: {why}.",
            "",
        ]
    path = REPORT_DIR / "TOOL_CONTRACTS.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path.relative_to(REPORT_DIR.parents[1])} for {len(TOOL_SPECS)} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
