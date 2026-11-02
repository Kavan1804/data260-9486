#!/usr/bin/env python3
"""HW8 Part 1 demo: CREATE_LISTING -> GET_LISTING through Kafka, logged step by step.

The demo is the Kafka client. It creates one correlation_id, sends CREATE_LISTING to s9486_entity_requests,
waits for the worker's answer on s9486_entity_responses, then sends GET_LISTING for the new listing_id.
After each response it prints the worker container's own log lines for that correlation_id
(docker logs s9486_worker), so the client and worker sides show up in one place and in order.

--via api sends the same two requests through the FastAPI wrapper on 127.0.0.1:8486 instead, and also
prints the API container's lines (docker logs s9486_api).

Usage (repo root, `make kafka-up` first):
    python Homework8/homework_demo.py            # Kafka client
    python Homework8/homework_demo.py --via api  # through FastAPI
Writes reports/hw08/raw/part1_demo_<via>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

import httpx  # noqa: E402
from hw8_common import BASE_URL, RAW, banner, docker_logs, footer, utc_now, write_json  # noqa: E402

import config  # noqa: E402
from kafka_service import messages  # noqa: E402
from kafka_service.common import stamp  # noqa: E402
from kafka_service.rpc import KafkaRPC  # noqa: E402

LISTING = {
    "title": "Sunny 2BR near SJSU",
    "address": "125 E San Fernando St, San Jose, CA",
    "listing_code": "LST-94861",
    "available_units": 2,
    "landlord_id": 6,
}


def step(n: int, text: str) -> None:
    print(f"\n--- Step {n}: {text}", flush=True)


def worker_lines(cid: str, since: tuple[str, str], container: str = "s9486_worker") -> list[str]:
    """The container's lines for this correlation_id, plus the offset-commit line right after the reply.

    since = (UTC time for docker --since, local ms timestamp). docker only filters to the second, so lines are
    also compared with the timestamp at the start of each log line.
    """
    picked: list[str] = []
    for line in docker_logs(container, since[0]):
        if line[:23] < since[1]:
            continue
        if cid in line:
            picked.append(line)
        elif picked and "sent response" in picked[-1] and "committed offset" in line:
            picked.append(line)
    return picked


def show_container(label: str, lines: list[str]) -> None:
    if not lines:
        print(f"    ({label}: no lines found - is it running in Docker?)")
    for line in lines:
        print(f"    {label} | {line}")


class KafkaClient:
    """The demo talks to Kafka itself (KafkaRPC from kafka_service/rpc.py)."""

    def __init__(self):
        self.rpc = KafkaRPC(name="client", quiet=True)

    async def start(self):
        await self.rpc.start()

    async def stop(self):
        await self.rpc.stop()

    async def send(self, operation: str, data, cid: str) -> tuple[dict, dict, dict, list[str], list[str]]:
        r = await self.rpc.request(operation, data, cid)
        return (
            r.request,
            r.response,
            {"request": r.request_meta, "response": r.response_meta},
            [r.sent_line],
            [r.received_line],
        )


class ApiClient:
    """Same calls through the FastAPI wrapper; the API builds the Kafka message with our correlation_id."""

    def __init__(self):
        self.http = httpx.AsyncClient(base_url=BASE_URL, timeout=20)

    async def start(self):
        (await self.http.get("/health")).raise_for_status()

    async def stop(self):
        await self.http.aclose()

    async def send(self, operation: str, data, cid: str) -> tuple[dict, dict, dict, list[str], list[str]]:
        if operation == messages.CREATE:
            sent = f"{stamp()} [client] HTTP POST {BASE_URL}/api/kafka/listings correlation_id={cid}"
            r = await self.http.post("/api/kafka/listings", json={"correlation_id": cid, "data": data})
        else:
            sent = (
                f"{stamp()} [client] HTTP GET {BASE_URL}/api/kafka/listings/{data['listing_id']} X-Correlation-ID={cid}"
            )
            r = await self.http.get(f"/api/kafka/listings/{data['listing_id']}", headers={"X-Correlation-ID": cid})
        body = r.json()
        kafka = body.pop("kafka", {})
        got = f"{stamp()} [client] HTTP {r.status_code} from API correlation_id={body.get('correlation_id')}"
        request = messages.build_request(operation, data, cid)  # what the API sent (same fields, same id)
        return request, body, kafka, [sent], [got]


async def one_operation(client, operation: str, data, cid: str, via: str, first_step: int) -> dict:
    since = (utc_now(), stamp())
    request, response, kafka, sent_lines, got_lines = await client.send(operation, data, cid)
    await asyncio.sleep(0.5)  # let docker logs catch up
    api_lines = worker_lines(cid, since, "s9486_api") if via == "api" else []

    step(first_step, f"{operation} request message sent to {config.TOPIC_REQUESTS}")
    show_container("client", sent_lines)
    if via == "api":
        show_container("api   ", [ln for ln in api_lines if "sent request" in ln or "HTTP request" in ln])
    print("    request message:")
    print("    " + json.dumps(request, indent=2).replace("\n", "\n    "))

    w_lines = worker_lines(cid, since)
    step(first_step + 1, "worker received the request")
    show_container("worker", [ln for ln in w_lines if "received request" in ln])
    step(first_step + 2, "worker processed the request")
    show_container("worker", [ln for ln in w_lines if " processing " in ln or " processed " in ln])
    step(first_step + 3, f"worker sent the response to {config.TOPIC_RESPONSES}")
    show_container("worker", [ln for ln in w_lines if "sent response" in ln or "committed offset" in ln])

    who = "FastAPI and returned to the client" if via == "api" else "client"
    step(first_step + 4, f"response received by the {who}")
    if via == "api":
        show_container("api   ", [ln for ln in api_lines if "received response" in ln or "returning HTTP" in ln])
    show_container("client", got_lines)
    print("    response message:")
    print("    " + json.dumps(response, indent=2).replace("\n", "\n    "))
    return {"operation": operation, "request": request, "response": response, "kafka": kafka, "worker_log": w_lines}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--via", choices=["kafka", "api"], default="kafka")
    via = ap.parse_args().via

    banner(f"Part 1 Kafka request/response demo (via {via})")
    client = KafkaClient() if via == "kafka" else ApiClient()
    await client.start()
    try:
        step(1, "create one correlation_id (used for both requests)")
        cid = messages.new_correlation_id()
        print(f"    correlation_id = {cid}")

        create = await one_operation(client, messages.CREATE, LISTING, cid, via, first_step=2)
        listing_id = create["response"].get("listing_id")
        step(7, "extract the generated listing_id from the CREATE_LISTING response")
        print(f"    listing_id = {listing_id}")
        if not create["response"].get("success") or not listing_id:
            print("    CREATE_LISTING failed, stopping")
            return 1

        # Step 1 creates one correlation_id for the whole demo, so the GET reuses it unchanged.
        get = await one_operation(client, messages.GET, {"listing_id": listing_id}, cid, via, first_step=8)
    finally:
        await client.stop()

    listing = get["response"].get("listing", {})
    step(13, "retrieved listing")
    for k, v in listing.items():
        print(f"    {k:16} {v}")

    ids = [
        ("client created", cid),
        ("CREATE request", create["request"]["correlation_id"]),
        ("CREATE response", create["response"].get("correlation_id")),
        ("GET request", get["request"]["correlation_id"]),
        ("GET response", get["response"].get("correlation_id")),
    ]
    preserved = all(v == cid for _, v in ids)
    same_fields = all(listing.get(k) == v for k, v in LISTING.items())
    step(14, "correlation_id check")
    for label, value in ids:
        print(f"    {label:16} {value}")
    print(f"    correlation_id unchanged everywhere: {preserved}")
    print(f"    GET returned the same fields that were created: {same_fields}")

    write_json(
        RAW / f"part1_demo_{via}.json",
        {
            "run_at": utc_now(),
            "via": via,
            "correlation_id": cid,
            "listing_id": listing_id,
            "create": create,
            "get": get,
            "correlation_id_preserved": preserved,
            "get_matches_create": same_fields,
        },
    )
    return 0 if preserved and same_fields and get["response"].get("success") else 1


if __name__ == "__main__":
    code = asyncio.run(main())
    footer("homework_demo.py")
    sys.exit(code)
