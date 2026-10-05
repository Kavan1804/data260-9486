"""The three domain tools over s9486_rel: search, detail lookup, aggregate.

Each tool validates its inputs, calls the repository through call_with_retry,
and returns the {ok, data, error} envelope. None of them raise.
"""

from __future__ import annotations

import re

from .envelope import fail, ok
from .retry import RetryExhausted, RetryPolicy, call_with_retry

LISTING_CODE_RE = re.compile(r"^LST-\d{5}$")  # same format the FastAPI schema enforces


class InputError(ValueError):
    pass


def _check_keys(inputs: dict, allowed: set[str], required: set[str]) -> None:
    extra = sorted(set(inputs) - allowed)
    if extra:
        raise InputError(f"unexpected field(s): {', '.join(extra)}; allowed: {', '.join(sorted(allowed))}")
    missing = sorted(required - set(inputs))
    if missing:
        raise InputError(f"missing required field(s): {', '.join(missing)}")


def _int(inputs: dict, name: str, lo: int, hi: int, default: int | None = None) -> int:
    value = inputs.get(name, default)
    # LLMs often send numbers as strings ("5"); accept plain digit strings, nothing looser.
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"{name} must be an integer between {lo} and {hi} (got {value!r})")
    if not lo <= value <= hi:
        raise InputError(f"{name} must be between {lo} and {hi} (got {value})")
    return value


def _str(inputs: dict, name: str, lo: int, hi: int) -> str:
    value = inputs.get(name)
    if not isinstance(value, str):
        raise InputError(f"{name} must be a string of {lo}-{hi} characters (got {value!r})")
    value = value.strip()
    if not lo <= len(value) <= hi:
        raise InputError(f"{name} must be {lo}-{hi} characters after trimming (got {len(value)})")
    return value


def _run(label: str, fn, policy: RetryPolicy, attempts_log: list | None):
    try:
        return call_with_retry(fn, policy, attempts_log=attempts_log), None
    except RetryExhausted as exc:
        return None, fail(f"Storage unavailable: {label} failed after {len(exc.attempts)} attempts "
                          f"(last error: {exc.attempts[-1]['error']})")


def search_listings(inputs: dict, repo, policy: RetryPolicy, attempts_log: list | None = None) -> dict:
    """Search listings whose title or address contains `query`."""
    try:
        _check_keys(inputs, {"query", "limit", "min_units"}, {"query"})
        query = _str(inputs, "query", 2, 80)
        limit = _int(inputs, "limit", 1, 20, default=5)
        min_units = _int(inputs, "min_units", 0, 500, default=0)
    except InputError as exc:
        return fail(f"Invalid input for search_listings: {exc}")
    rows, error = _run("search_listings", lambda: repo.search(query, limit, min_units), policy, attempts_log)
    if error:
        return error
    return ok({"query": query, "min_units": min_units, "count": len(rows), "listings": rows})


def get_listing(inputs: dict, repo, policy: RetryPolicy, attempts_log: list | None = None) -> dict:
    """Detail lookup by unique listing_code (format LST-12345)."""
    try:
        _check_keys(inputs, {"listing_code"}, {"listing_code"})
        code = _str(inputs, "listing_code", 1, 20).upper()
        if not LISTING_CODE_RE.fullmatch(code):
            raise InputError(f"listing_code must match LST- followed by 5 digits, e.g. LST-00042 (got {code!r})")
    except InputError as exc:
        return fail(f"Invalid input for get_listing: {exc}")
    row, error = _run("get_listing", lambda: repo.get_by_code(code), policy, attempts_log)
    if error:
        return error
    if row is None:
        return fail(f"No listing found with listing_code {code}")
    return ok(row)


def landlord_portfolio_stats(inputs: dict, repo, policy: RetryPolicy, attempts_log: list | None = None) -> dict:
    """Aggregate: listing count and available-unit totals for one landlord."""
    try:
        _check_keys(inputs, {"landlord_id"}, {"landlord_id"})
        landlord_id = _int(inputs, "landlord_id", 1, 2_147_483_647)
    except InputError as exc:
        return fail(f"Invalid input for landlord_portfolio_stats: {exc}")
    row, error = _run("landlord_portfolio_stats", lambda: repo.landlord_stats(landlord_id), policy, attempts_log)
    if error:
        return error
    if row is None:
        return fail(f"No landlord found with id {landlord_id}")
    return ok(row)
