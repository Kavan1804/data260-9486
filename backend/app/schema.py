from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from .models import LISTING_CODE_PATTERN

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
# Unique-field formats: listing codes look like LST-00042. Input is trimmed and
# upper-cased before the pattern check, so "lst-00042" is accepted as LST-00042.
ListingCode = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=LISTING_CODE_PATTERN),
]
Units = Annotated[int, Field(ge=0, le=500)]
LandlordId = Annotated[int, Field(gt=0)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Company = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
# EmailStr keeps the user's case in the local part; store emails lower-case so uniqueness is case-insensitive.
Email = Annotated[EmailStr, AfterValidator(lambda v: v.lower())]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    skip: int
    limit: int
    items: list[T]


class PartialUpdate(BaseModel):
    """Base for PUT bodies: only the fields that are sent are changed, and a sent field may not be null."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_fields(self):
        if not self.model_fields_set:
            raise ValueError("Send at least one field to update")
        nulls = sorted(f for f in self.model_fields_set if getattr(self, f) is None)
        if nulls:
            raise ValueError(f"Fields cannot be null: {', '.join(nulls)}")
        return self


# ---------- Landlords (HW5 related entity) ----------

class LandlordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: FullName
    company: Company
    email: Email


class LandlordUpdate(PartialUpdate):
    full_name: FullName | None = None
    company: Company | None = None
    email: Email | None = None


class LandlordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    company: str
    email: str
    created_at: datetime
    updated_at: datetime


# ---------- Listings (primary entity) ----------

class ListingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    address: Address
    listing_code: ListingCode
    available_units: Units = 1
    landlord_id: LandlordId


class ListingUpdate(PartialUpdate):
    title: Title | None = None
    address: Address | None = None
    listing_code: ListingCode | None = None
    available_units: Units | None = None
    landlord_id: LandlordId | None = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    address: str
    listing_code: str
    available_units: int
    landlord_id: int
    created_at: datetime
    updated_at: datetime


class InquiryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    renter_name: str
    message: str


class ListingWithInquiries(ListingOut):
    inquiries: list[InquiryOut]


class ListingPage(BaseModel):
    version: str
    page: int
    page_size: int
    count: int
    items: list[ListingWithInquiries]


class LoginRequest(BaseModel):
    email: EmailStr
    # bcrypt only uses the first 72 bytes and bcrypt>=5 rejects longer input
    password: Annotated[str, StringConstraints(min_length=1, max_length=72)]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
