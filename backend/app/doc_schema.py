"""HW6 Pydantic schemas: Part 1 listing documents (MongoDB) and Part 2 chat memory.

The MongoDB "listings" document is the document-oriented view of the HW5 domain
(rental housing listings): a short title, optional description, two enums, a
required move-in date, and created/updated timestamps.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

TITLE_MAX = 100
STATUSES = ("available", "pending", "rented")
PROPERTY_TYPES = ("studio", "apartment", "condo", "house", "townhouse")

Status = Literal["available", "pending", "rented"]
PropertyType = Literal["studio", "apartment", "condo", "house", "townhouse"]
DocTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_MAX)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
UserKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ListingDocCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: DocTitle
    description: Optional[Description] = None
    status: Status = "available"
    property_type: PropertyType
    available_from: datetime  # ISO 8601, e.g. 2026-11-01T09:00:00Z


class ListingDocUpdate(BaseModel):
    """PUT body: only the fields that are sent are changed (same rule as HW5 PartialUpdate)."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[DocTitle] = None
    description: Optional[Description] = None
    status: Optional[Status] = None
    property_type: Optional[PropertyType] = None
    available_from: Optional[datetime] = None

    @model_validator(mode="after")
    def _no_null_required_fields(self):
        nulls = [f for f in self.model_fields_set if f != "description" and getattr(self, f) is None]
        if nulls:
            raise ValueError(f"these fields cannot be null: {sorted(nulls)}")
        return self


class ListingDocOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: Status
    property_type: PropertyType
    available_from: datetime
    created_at: datetime
    updated_at: datetime


# ---------- Part 2: chat memory ----------

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UserKey
    session_id: Optional[UserKey] = None  # a new session id is generated when omitted
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    # Part 3 experiment knobs; normal clients leave them out and get the config defaults.
    short_term_n: Optional[int] = Field(None, ge=1, le=50)
    policy: Literal["none", "compress"] = "none"
    phase: Literal["chat", "conversation", "probe"] = "chat"
    run_id: Optional[str] = Field(None, max_length=64)
