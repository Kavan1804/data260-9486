from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class ListingCreate(BaseModel):
    title: Title
    address: Address


class ListingUpdate(ListingCreate):
    pass


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    address: str


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
