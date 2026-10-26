"""HW7 Part 2: check a model-proposed tool call before it runs.

validate_call(name, arguments) returns (kind, message):
  (None, "")                      - well-formed, safe to run
  ("unknown_tool", ...)           - the name is not one of TOOL_SPECS
  ("malformed_arguments", ...)    - arguments are not a JSON object (bad JSON string, list, number, ...)
  ("schema_validation", ...)      - JSON object, but it breaks the tool's JSON schema
                                    (missing/extra field, wrong type, out of range, bad pattern)

The checks follow the same JSON schemas the model is given (TOOL_SPECS), so the error message
tells the model exactly which field to fix. Digit strings for integer fields ("12") are accepted,
because the HW5 tools already accept them.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .execute import TOOL_SPECS

FAILURE_KINDS = ("unknown_tool", "malformed_arguments", "schema_validation", "text_instead_of_tool")


def parse_arguments(arguments: Any) -> tuple[dict | None, str]:
    """Return (dict, "") or (None, reason) when the arguments are not a JSON object."""
    if arguments is None:
        return {}, ""
    if isinstance(arguments, str):
        if not arguments.strip():
            return {}, ""
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return None, f"arguments are not valid JSON ({exc.msg} at position {exc.pos})"
    if not isinstance(arguments, dict):
        return None, f"arguments must be a JSON object, got {type(arguments).__name__}"
    return arguments, ""


def _check_field(name: str, value: Any, rule: dict) -> str | None:
    kind = rule.get("type")
    if kind == "string":
        if not isinstance(value, str):
            return f"'{name}' must be a string, got {type(value).__name__} {value!r}"
        text = value.strip()
        if len(text) < rule.get("minLength", 0) or len(text) > rule.get("maxLength", 10**9):
            return f"'{name}' must be {rule.get('minLength', 0)}-{rule.get('maxLength')} characters, got {len(text)}"
        if "pattern" in rule and not re.fullmatch(rule["pattern"].strip("^$"), text.upper()):
            return f"'{name}' must match {rule['pattern']} (example LST-00042), got {value!r}"
    elif kind == "integer":
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            value = int(value.strip())
        if isinstance(value, bool) or not isinstance(value, int):
            return f"'{name}' must be an integer, got {type(value).__name__} {value!r}"
        if value < rule.get("minimum", -(10**18)) or value > rule.get("maximum", 10**18):
            return f"'{name}' must be between {rule.get('minimum')} and {rule.get('maximum')}, got {value}"
    return None


def validate_call(name: Any, arguments: Any) -> tuple[str | None, str]:
    if not isinstance(name, str) or name not in TOOL_SPECS:
        return "unknown_tool", f"unknown tool {name!r}; the only tools are: {', '.join(TOOL_SPECS)}"
    args, why = parse_arguments(arguments)
    if args is None:
        return "malformed_arguments", f"{name}: {why}"
    schema = TOOL_SPECS[name]["schema"]
    props = schema["properties"]
    extra = sorted(set(args) - set(props))
    if extra and schema.get("additionalProperties") is False:
        return "schema_validation", f"{name}: unexpected field(s) {extra}; allowed fields: {sorted(props)}"
    missing = [f for f in schema.get("required", []) if f not in args]
    if missing:
        return "schema_validation", f"{name}: missing required field(s) {missing}"
    for field, value in args.items():
        problem = _check_field(field, value, props.get(field, {}))
        if problem:
            return "schema_validation", f"{name}: {problem}"
    return None, ""
