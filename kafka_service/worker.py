"""HW8 Part 1 worker: consumes s9486_entity_requests and answers on the reply_to topic.

Listings live in a plain dict (self.store) as the assignment asks, so they are gone when the worker restarts.
The offset is committed only after the response has been sent (enable_auto_commit=False).

Part 3A switch: WORKER_IDEMPOTENCY=on (default) remembers every (correlation_id, operation) it already answered
and sends the saved response again instead of creating a second listing. WORKER_IDEMPOTENCY=off is the
"before fix" run. The key includes the operation because homework_demo.py uses one correlation_id for both
its CREATE and its GET, as the assignment steps describe.

Run:  python -m kafka_service.worker      (the docker-compose "worker" service runs the same command)
"""

from __future__ import annotations

import asyncio
import os
import uuid

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

import config
from kafka_service import messages
from kafka_service.common import bootstrap, from_bytes, log, short, to_bytes, where

GROUP_ID = f"{config.PREFIX}_entity_worker"
NAME = "worker"


class ListingWorker:
    def __init__(self, idempotent: bool = True):
        self.idempotent = idempotent
        self.store: dict[str, dict] = {}  # listing_id -> listing
        self.answered: dict[str, dict] = {}  # "correlation_id:operation" -> response already sent (idempotency)

    def handle(self, operation, data) -> dict:
        """Run one operation and return the response body (without correlation_id)."""
        if operation == messages.CREATE:
            listing, error = messages.validate_listing(data)
            if error:
                return {"success": False, "error": error}
            listing_id = str(uuid.uuid4())
            self.store[listing_id] = {"listing_id": listing_id, **listing}
            return {"success": True, "listing_id": listing_id, "message": "Listing created"}
        if operation == messages.GET:
            listing_id = data.get("listing_id") if isinstance(data, dict) else None
            if not isinstance(listing_id, str) or not listing_id.strip():
                return {"success": False, "error": "data.listing_id is required"}
            listing = self.store.get(listing_id.strip())
            if listing is None:
                return {"success": False, "error": "Listing not found"}
            return {"success": True, "listing": listing}
        return {"success": False, "error": "Unknown operation"}

    def process(self, raw: bytes | None) -> tuple[str, dict]:
        """Turn one raw request into (reply topic, response). Every response carries the request's correlation_id."""
        try:
            request = from_bytes(raw)
        except ValueError as exc:
            log(NAME, f"bad request (not JSON): {exc}")
            return config.TOPIC_RESPONSES, messages.error_response(None, "Request is not valid JSON")
        cid = request.get("correlation_id")
        missing = [k for k in messages.REQUIRED_KEYS if k not in request]
        if missing or not isinstance(cid, str) or not cid:
            return config.TOPIC_RESPONSES, messages.error_response(
                cid if isinstance(cid, str) else None, f"Request is missing: {', '.join(missing) or 'correlation_id'}"
            )
        reply_to = request["reply_to"]
        if reply_to != config.TOPIC_RESPONSES:
            return config.TOPIC_RESPONSES, messages.error_response(
                cid, f"reply_to must be {config.TOPIC_RESPONSES}, got {reply_to!r}"
            )

        key = f"{cid}:{request['operation']}"
        if self.idempotent and key in self.answered:
            log(
                NAME,
                f"duplicate correlation_id={cid} operation={request['operation']}: already answered, "
                "sending the saved response again (no new listing)",
            )
            return reply_to, self.answered[key]

        log(NAME, f"processing operation={request['operation']} correlation_id={cid} data={short(request['data'])}")
        response = {"correlation_id": cid, **self.handle(request["operation"], request["data"])}
        if self.idempotent:
            self.answered[key] = response
        log(NAME, f"processed correlation_id={cid} success={response['success']} listings_in_store={len(self.store)}")
        return reply_to, response


async def run() -> None:
    idempotent = os.getenv("WORKER_IDEMPOTENCY", "on").lower() != "off"
    worker = ListingWorker(idempotent=idempotent)
    consumer = AIOKafkaConsumer(
        config.TOPIC_REQUESTS,
        bootstrap_servers=bootstrap(),
        group_id=GROUP_ID,
        enable_auto_commit=False,  # commit by hand after the response is sent
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap())
    for attempt in range(1, 31):  # Kafka can take a few seconds to accept clients after the container starts
        try:
            await producer.start()
            await consumer.start()
            break
        except Exception as exc:  # noqa: BLE001 - any connection error just means "try again"
            log(NAME, f"Kafka not ready yet ({type(exc).__name__}), retry {attempt}/30")
            await asyncio.sleep(2)
    else:
        raise SystemExit("could not connect to Kafka")

    mode = "on" if idempotent else "off"
    log(NAME, f"bootstrap={bootstrap()} group={GROUP_ID} topic={config.TOPIC_REQUESTS} idempotency={mode}")
    log(NAME, "Consumer is ready and listening...")
    try:
        async for record in consumer:
            log(NAME, f"received request {where(record)} value={record.value.decode('utf-8', 'replace')[:400]}")
            reply_to, response = worker.process(record.value)
            key = (response["correlation_id"] or "").encode()
            sent = await producer.send_and_wait(reply_to, to_bytes(response), key=key)
            log(NAME, f"sent response to {where(sent)} value={short(response)}")
            await consumer.commit()
            log(NAME, f"committed offset {record.offset + 1} for partition {record.partition}")
    finally:
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(run())
