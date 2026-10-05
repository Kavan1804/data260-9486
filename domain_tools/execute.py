"""Part 4: execute_tool(name, inputs) - the single safe entry point for the agent.

It looks up the tool, applies the Part 5 safety rule, runs the tool with the
retry policy, and always returns the {ok, data, error} envelope as a JSON
string. It never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import config

from . import tools
from .envelope import fail
from .retry import RetryPolicy
from .safety import check_safety

log = logging.getLogger("domain_tools")

DEFAULT_POLICY = RetryPolicy(
    max_attempts=config.RETRY_MAX_ATTEMPTS,
    base_delay_s=config.RETRY_BASE_DELAY_S,
    max_delay_s=config.RETRY_MAX_DELAY_S,
    timeout_s=config.CALL_TIMEOUT_S,
)

# JSON input schemas: used for the MCP tool docs, the Ollama tool list, and TOOL_CONTRACTS.md.
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "search_listings": {
        "fn": tools.search_listings,
        "description": "Search rental listings whose title or address contains the query text "
                       "(e.g. a city, street, or feature such as 'parking'). Returns up to `limit` listings.",
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 80,
                          "description": "Text to find in the listing title or address"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "min_units": {"type": "integer", "minimum": 0, "maximum": 500, "default": 0},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "get_listing": {
        "fn": tools.get_listing,
        "description": "Get full details of one listing by its unique listing_code, format LST-12345.",
        "schema": {
            "type": "object",
            "properties": {"listing_code": {"type": "string", "pattern": "^LST-\\d{5}$",
                                            "description": "Unique code such as LST-00042"}},
            "required": ["listing_code"],
            "additionalProperties": False,
        },
    },
    "landlord_portfolio_stats": {
        "fn": tools.landlord_portfolio_stats,
        "description": "Aggregate statistics for one landlord: number of listings, total and "
                       "average available units.",
        "schema": {
            "type": "object",
            "properties": {"landlord_id": {"type": "integer", "minimum": 1,
                                           "description": "Numeric landlord id"}},
            "required": ["landlord_id"],
            "additionalProperties": False,
        },
    },
}

_default_repo = None


def set_default_repository(repo) -> None:
    """Dependency injection hook (tests, experiments)."""
    global _default_repo
    _default_repo = repo


def default_repository():
    global _default_repo
    if _default_repo is None:
        from .repository import MySQLListingRepository

        _default_repo = MySQLListingRepository(timeout_s=config.CALL_TIMEOUT_S)
    return _default_repo


def execute_tool(
    name: str,
    inputs: Any,
    *,
    repo=None,
    policy: RetryPolicy | None = None,
    attempts_log: list | None = None,
) -> str:
    try:
        result = _execute(name, inputs, repo, policy or DEFAULT_POLICY, attempts_log)
    except Exception as exc:  # noqa: BLE001 - last line of defence: never crash the caller
        log.exception("execute_tool(%s) failed", name)
        result = fail(f"Internal error in {name}: {type(exc).__name__}: {exc}")
    return json.dumps(result, default=str)


def _execute(name, inputs, repo, policy, attempts_log) -> dict:
    spec = TOOL_SPECS.get(name) if isinstance(name, str) else None
    if spec is None:
        return fail(f"Unknown tool {name!r}; available tools: {', '.join(TOOL_SPECS)}")
    if isinstance(inputs, str):  # models sometimes send arguments as a JSON string
        try:
            inputs = json.loads(inputs) if inputs.strip() else {}
        except json.JSONDecodeError as exc:
            return fail(f"inputs for {name} must be a JSON object: {exc.msg}")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        return fail(f"inputs for {name} must be a JSON object, got {type(inputs).__name__}")

    blocked = check_safety(name, inputs)
    if blocked:
        log.warning("safety rule blocked %s %s", name, inputs)
        return fail(blocked)

    return spec["fn"](inputs, repo if repo is not None else default_repository(), policy, attempts_log)
