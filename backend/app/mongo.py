"""HW6: PyMongo connection for the s9486_doc database.

One lazy MongoClient (pattern from the course FastAPI/PyMongo demo). The first
request that needs MongoDB creates the collections with $jsonSchema validators,
so the MySQL part of the app still starts when MongoDB is down; those requests
get a 503 instead.
"""

from __future__ import annotations

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, PyMongoError

from config import MONGO_TIMEOUT_MS, MONGODB_DB, MONGODB_URI

from .doc_schema import PROPERTY_TYPES, STATUSES, TITLE_MAX

LISTINGS = "listings"  # Part 1 document view of the HW5 domain
MESSAGES = "messages"  # Part 2 short-term memory
SUMMARIES = "summaries"  # Part 2 long-term memory
EPISODES = "episodes"  # Part 2 episodic memory

_DATE = {"bsonType": "date"}
_STR = {"bsonType": "string"}

VALIDATORS: dict[str, dict] = {
    LISTINGS: {
        "bsonType": "object",
        "required": ["title", "status", "property_type", "available_from", "created_at", "updated_at"],
        "properties": {
            "title": {"bsonType": "string", "minLength": 1, "maxLength": TITLE_MAX},
            "description": {"bsonType": ["string", "null"], "maxLength": 2000},
            "status": {"enum": list(STATUSES)},
            "property_type": {"enum": list(PROPERTY_TYPES)},
            "available_from": _DATE,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    },
    MESSAGES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "role", "content", "created_at"],
        "properties": {
            "user_id": _STR,
            "session_id": _STR,
            "role": {"enum": ["user", "assistant"]},
            "content": _STR,
            "created_at": _DATE,
        },
    },
    SUMMARIES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "scope", "text", "created_at"],
        "properties": {
            "user_id": _STR,
            "session_id": {"bsonType": ["string", "null"]},  # null for the lifetime summary
            "scope": {"enum": ["session", "user"]},
            "text": _STR,
            "created_at": _DATE,
        },
    },
    EPISODES: {
        "bsonType": "object",
        "required": ["user_id", "session_id", "fact", "importance", "embedding", "created_at"],
        "properties": {
            "user_id": _STR,
            "session_id": _STR,
            "fact": {"bsonType": "string", "minLength": 1, "maxLength": 200},
            "importance": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 1},
            "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
            "created_at": _DATE,
        },
    },
}

INDEXES: dict[str, list] = {
    LISTINGS: [[("created_at", DESCENDING)]],
    MESSAGES: [[("user_id", ASCENDING), ("session_id", ASCENDING), ("created_at", ASCENDING)]],
    SUMMARIES: [[("user_id", ASCENDING), ("scope", ASCENDING), ("created_at", DESCENDING)]],
    EPISODES: [[("user_id", ASCENDING), ("created_at", DESCENDING)]],
}

_client: MongoClient | None = None
_ready: set[str] = set()


def get_client() -> MongoClient:
    global _client
    if _client is None:
        # tz_aware so datetimes come back as UTC-aware, matching what we store.
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT_MS, tz_aware=True)
    return _client


def ensure_collections(db: Database) -> None:
    """Create each collection with its validator, or refresh the validator if it already exists. Safe to re-run."""
    existing = set(db.list_collection_names())
    for name, schema in VALIDATORS.items():
        validator = {"$jsonSchema": schema}
        if name in existing:
            db.command("collMod", name, validator=validator, validationLevel="strict")
        else:
            try:
                db.create_collection(name, validator=validator, validationLevel="strict")
            except CollectionInvalid:  # created by a concurrent request
                pass
        for keys in INDEXES.get(name, []):
            db[name].create_index(keys)


def get_db(db_name: str = MONGODB_DB) -> Database:
    db = get_client()[db_name]
    if db_name not in _ready:
        ensure_collections(db)
        _ready.add(db_name)
    return db


def mongo_db() -> Database:
    """FastAPI dependency. Tests override it to point at a throwaway database."""
    try:
        return get_db()
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable at {MONGODB_URI}: {type(exc).__name__}")
