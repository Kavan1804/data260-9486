"""HW6 Part 1: MongoDB CRUD for listing documents at /api/listings.

Status codes: 201 create, 200 read/update/delete, 400 malformed id or empty
update, 404 missing record, 422 invalid body (Pydantic, or the MongoDB
$jsonSchema validator), 500 other database errors, 503 MongoDB unreachable.
"""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import DESCENDING
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, PyMongoError, WriteError

from ..doc_schema import ListingDocCreate, ListingDocOut, ListingDocUpdate
from ..mongo import LISTINGS, mongo_db

router = APIRouter(prefix="/api/listings", tags=["HW6 listing documents (MongoDB)"])

DOC_VALIDATION_FAILED = 121  # MongoDB error code when a write breaks the $jsonSchema


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid id format: {value!r} is not a 24-character hex ObjectId")


def serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title"),
        "description": doc.get("description"),
        "status": doc.get("status"),
        "property_type": doc.get("property_type"),
        "available_from": doc.get("available_from"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def db_error(action: str, exc: PyMongoError) -> HTTPException:
    if isinstance(exc, WriteError) and exc.code == DOC_VALIDATION_FAILED:
        return HTTPException(status_code=422, detail=f"Document failed MongoDB schema validation while {action}")
    if isinstance(exc, ConnectionFailure):
        return HTTPException(status_code=503, detail=f"MongoDB unavailable while {action}")
    return HTTPException(status_code=500, detail=f"Database error while {action}")


@router.post("", response_model=ListingDocOut, status_code=status.HTTP_201_CREATED)
def create_listing_doc(payload: ListingDocCreate, db: Database = Depends(mongo_db)):
    doc = payload.model_dump()
    doc["created_at"] = doc["updated_at"] = now_utc()
    try:
        res = db[LISTINGS].insert_one(doc)
        return serialize(db[LISTINGS].find_one({"_id": res.inserted_id}))
    except PyMongoError as exc:
        raise db_error("creating the listing", exc)


@router.get("", response_model=list[ListingDocOut])
def list_listing_docs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(mongo_db),
):
    try:
        docs = db[LISTINGS].find().sort("created_at", DESCENDING).skip(skip).limit(limit)
        return [serialize(d) for d in docs]
    except PyMongoError as exc:
        raise db_error("fetching listings", exc)


@router.get("/{doc_id}", response_model=ListingDocOut)
def get_listing_doc(doc_id: str, db: Database = Depends(mongo_db)):
    oid = to_object_id(doc_id)
    try:
        doc = db[LISTINGS].find_one({"_id": oid})
    except PyMongoError as exc:
        raise db_error("fetching the listing", exc)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Listing document {doc_id} not found")
    return serialize(doc)


@router.put("/{doc_id}", response_model=ListingDocOut)
def update_listing_doc(doc_id: str, payload: ListingDocUpdate, db: Database = Depends(mongo_db)):
    oid = to_object_id(doc_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    updates["updated_at"] = now_utc()
    try:
        res = db[LISTINGS].update_one({"_id": oid}, {"$set": updates})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Listing document {doc_id} not found")
        return serialize(db[LISTINGS].find_one({"_id": oid}))
    except PyMongoError as exc:
        raise db_error("updating the listing", exc)


@router.delete("/{doc_id}", response_model=ListingDocOut)
def delete_listing_doc(doc_id: str, db: Database = Depends(mongo_db)):
    # Returns the deleted document, like the HW5 DELETE routes.
    oid = to_object_id(doc_id)
    try:
        doc = db[LISTINGS].find_one_and_delete({"_id": oid})
    except PyMongoError as exc:
        raise db_error("deleting the listing", exc)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Listing document {doc_id} not found")
    return serialize(doc)
