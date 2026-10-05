#!/usr/bin/env python3
"""Start both MCP servers over STDIO (the same way the Inspector does), list
their tools, and call every tool. Results are saved for reports/hw05/raw/.

Usage (repo root):
    python scripts/mcp_calls.py            # meals + domain, writes raw/mcp_*_calls.json
    python scripts/mcp_calls.py --domain   # domain server only (no internet needed)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

from hw5_common import RAW, ROOT, banner

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from domain_tools.contracts import REJECTED, VALID

# Valid and intentionally invalid calls. The invalid domain calls are the
# rejected-input examples documented in TOOL_CONTRACTS.md (Part 3).
MEALS_CALLS = [
    ("search_meals_by_name", {"query": "Arrabiata", "limit": 5}, "valid"),
    ("meals_by_ingredient", {"ingredient": "chicken", "limit": 12}, "valid"),
    ("random_meal", {}, "valid"),
    ("meal_details", {"id": "52771"}, "valid"),
    ("search_meals_by_name", {"query": "zzzxqq", "limit": 5}, "no match"),
    ("meal_details", {"id": "abc"}, "invalid"),
]
DOMAIN_CALLS = [call for tool in VALID for call in ((tool, VALID[tool], "valid"), (tool, REJECTED[tool][0], "invalid"))]


def server_params(script: str) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_servers" / script)], cwd=str(ROOT))


def _payload(result) -> object:
    if result.structuredContent is not None:
        sc = result.structuredContent
        # FastMCP wraps non-object return types as {"result": ...}
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if len(texts) == 1 else texts
    except json.JSONDecodeError:
        return texts[0]


async def run_server(script: str, calls: list, timeout_s: float = 30.0) -> dict:
    out = {"server": script, "started_at": datetime.now().isoformat(timespec="seconds"), "tools": [], "calls": []}
    async with stdio_client(server_params(script)) as (read, write):
        async with ClientSession(read, write) as session:
            init = await asyncio.wait_for(session.initialize(), timeout_s)
            out["server_name"] = init.serverInfo.name
            listed = await asyncio.wait_for(session.list_tools(), timeout_s)
            out["tools"] = [{"name": t.name, "input_schema": t.inputSchema} for t in listed.tools]
            for name, args, kind in calls:
                start = time.perf_counter()
                try:
                    res = await asyncio.wait_for(session.call_tool(name, args), timeout_s)
                    record = {"tool": name, "arguments": args, "kind": kind, "is_error": bool(res.isError),
                              "result": _payload(res)}
                except Exception as exc:  # noqa: BLE001 - recorded, not raised
                    record = {"tool": name, "arguments": args, "kind": kind, "is_error": True,
                              "result": f"client error: {type(exc).__name__}: {exc}"}
                record["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
                out["calls"].append(record)
    return out


def summarize(run: dict) -> None:
    print(f"\n[{run['server_name']}] tools: {', '.join(t['name'] for t in run['tools'])}")
    for c in run["calls"]:
        res = c["result"]
        if isinstance(res, dict) and "ok" in res:
            short = f"ok={res['ok']} error={res['error']!r}" if not res["ok"] else f"ok=True data keys={list(res['data'])}"
        elif isinstance(res, dict):
            short = res.get("message") or f"keys={list(res)}"
        else:
            short = str(res)[:110]
        print(f"  {c['kind']:8s} {c['tool']}({json.dumps(c['arguments'])}) isError={c['is_error']} -> {short}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", action="store_true", help="domain server only")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    banner("Part 2 - MCP servers over STDIO")

    jobs = [("domain_server.py", DOMAIN_CALLS, "mcp_domain_calls.json")]
    if not args.domain:
        jobs.insert(0, ("meals_server.py", MEALS_CALLS, "mcp_meals_calls.json"))
    for script, calls, filename in jobs:
        run = asyncio.run(run_server(script, calls))
        summarize(run)
        if not args.no_save:
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / filename).write_text(json.dumps(run, indent=2, default=str) + "\n", encoding="utf-8")
            print(f"  saved reports/hw05/raw/{filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
