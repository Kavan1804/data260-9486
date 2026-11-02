"""HW8 Part 1: API wrapper that turns HTTP calls into Kafka requests for the Listing worker.

POST /api/kafka/listings              -> CREATE_LISTING
GET  /api/kafka/listings/{listing_id} -> GET_LISTING
POST /api/kafka/requests              -> any operation (used to show the "Unknown operation" error)

The caller may send its own correlation_id (body field, or X-Correlation-ID header on GET). If it does, the
API uses that exact value; otherwise the API creates one. The JSON returned is the worker's response as-is,
plus a "kafka" field that says where the request and response were written.

The Kafka client starts on the first request, so `make backend` still works when Kafka is not running.
These routes do not need a JWT: they only touch the worker's in-memory dict, not MySQL.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from kafka_service import messages
from kafka_service.common import log
from kafka_service.rpc import KafkaRPC

router = APIRouter(prefix="/api/kafka", tags=["kafka"])
_rpc: KafkaRPC | None = None
_lock = asyncio.Lock()


class CreateListingIn(BaseModel):
    correlation_id: str | None = None
    data: Any


class KafkaRequestIn(BaseModel):
    correlation_id: str | None = None
    operation: str
    data: Any = None


async def _client() -> KafkaRPC:
    global _rpc
    async with _lock:
        if _rpc is None:
            rpc = KafkaRPC(name="api")
            try:
                await rpc.start()
            except Exception as exc:
                await rpc.stop()
                raise HTTPException(status_code=503, detail=f"Kafka is not reachable: {exc}") from exc
            _rpc = rpc
    return _rpc


async def shutdown() -> None:
    if _rpc is not None:
        await _rpc.stop()


async def _call(operation: str, data, correlation_id: str | None) -> JSONResponse:
    rpc = await _client()
    log("api", f"HTTP request -> {operation} correlation_id={correlation_id or '(api creates one)'}")
    try:
        result = await rpc.request(operation, data, correlation_id)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    response = result.response
    if response["success"]:
        code = 201 if operation == messages.CREATE else 200
    else:
        code = 404 if response.get("error") == "Listing not found" else 400
    log("api", f"returning HTTP {code} to caller correlation_id={response['correlation_id']}")
    body = {**response, "kafka": {"request": result.request_meta, "response": result.response_meta}}
    return JSONResponse(status_code=code, content=body)


@router.post("/listings")
async def create_listing(payload: CreateListingIn):
    return await _call(messages.CREATE, payload.data, payload.correlation_id)


@router.get("/listings/{listing_id}")
async def get_listing(listing_id: str, x_correlation_id: str | None = Header(default=None)):
    return await _call(messages.GET, {"listing_id": listing_id}, x_correlation_id)


@router.post("/requests")
async def raw_request(payload: KafkaRequestIn):
    return await _call(payload.operation, payload.data, payload.correlation_id)
