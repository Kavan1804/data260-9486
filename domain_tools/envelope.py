"""The one response envelope used by every domain tool, the domain MCP server,
and execute_tool: {"ok": bool, "data": ..., "error": None | str}."""

from typing import Any

ENVELOPE_KEYS = ("ok", "data", "error")


def ok(data: Any) -> dict:
    return {"ok": True, "data": data, "error": None}


def fail(message: str) -> dict:
    return {"ok": False, "data": None, "error": message}


def is_envelope(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and tuple(value) == ENVELOPE_KEYS
        and isinstance(value["ok"], bool)
        and (value["error"] is None) == value["ok"]
        and (value["ok"] or value["data"] is None)
    )
