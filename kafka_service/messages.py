"""Request/response message shapes for the Listing service (HW8 Part 1).

Request:  {"correlation_id", "reply_to", "operation", "data"}
Response: {"correlation_id", "success": true, ...}  or  {"correlation_id", "success": false, "error"}

The listing fields are checked with the same ListingCreate model the HW4-HW7 REST API uses, so a
listing that the Kafka worker accepts would also be accepted by POST /listings.
"""

from __future__ import annotations

import uuid

from pydantic import ValidationError

import config
from backend.app.schema import ListingCreate

CREATE = "CREATE_LISTING"
GET = "GET_LISTING"
OPERATIONS = (CREATE, GET)
REQUIRED_KEYS = ("correlation_id", "reply_to", "operation", "data")


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def build_request(operation: str, data: dict, correlation_id: str | None = None) -> dict:
    """The client creates the correlation_id once here; nothing downstream changes it."""
    return {
        "correlation_id": correlation_id or new_correlation_id(),
        "reply_to": config.TOPIC_RESPONSES,
        "operation": operation,
        "data": data,
    }


def error_response(correlation_id: str | None, error: str) -> dict:
    return {"correlation_id": correlation_id, "success": False, "error": error}


def validation_message(exc: ValidationError) -> str:
    """Pydantic errors as one short line, e.g. "title: String should have at least 1 character"."""
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "data"
        parts.append(f"{field}: {err['msg']}")
    return "; ".join(parts)


def validate_listing(data) -> tuple[dict | None, str | None]:
    """Return (clean listing fields, None) or (None, error message)."""
    if not isinstance(data, dict):
        return None, "data must be a JSON object"
    try:
        return ListingCreate.model_validate(data).model_dump(), None
    except ValidationError as exc:
        return None, f"Invalid listing data: {validation_message(exc)}"
