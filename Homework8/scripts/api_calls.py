#!/usr/bin/env python3
"""HW8 Part 1 error cases through the FastAPI wrapper (127.0.0.1:8486 -> Kafka -> worker -> Kafka -> API).

Each call sends its own correlation_id and checks that the error response echoes it unchanged.
Usage (repo root, `make kafka-up` first):  python Homework8/scripts/api_calls.py
Writes reports/hw08/raw/part1_error_cases.json
"""

from __future__ import annotations

import json
import sys
import uuid

import httpx
from hw8_common import BASE_URL, RAW, banner, footer, utc_now, write_json

GOOD = {
    "title": "Studio by Diridon Station",
    "address": "65 Cahill St, San Jose, CA",
    "listing_code": "lst-94862",
    "available_units": 1,
    "landlord_id": 3,
}
CASES = [
    ("valid CREATE_LISTING", "POST", "/api/kafka/listings", {"data": GOOD}, True),
    ("missing title", "POST", "/api/kafka/listings", {"data": {k: v for k, v in GOOD.items() if k != "title"}}, False),
    ("empty address", "POST", "/api/kafka/listings", {"data": {**GOOD, "address": "   "}}, False),
    ("bad listing_code", "POST", "/api/kafka/listings", {"data": {**GOOD, "listing_code": "ABC-1"}}, False),
    ("negative available_units", "POST", "/api/kafka/listings", {"data": {**GOOD, "available_units": -2}}, False),
    ("data is not an object", "POST", "/api/kafka/listings", {"data": "hello"}, False),
    ("unknown listing_id", "GET", "/api/kafka/listings/00000000-0000-0000-0000-000000000000", None, False),
    (
        "unknown operation",
        "POST",
        "/api/kafka/requests",
        {"operation": "DELETE_LISTING", "data": {"listing_id": "x"}},
        False,
    ),
]


def main() -> int:
    banner("Part 1 error cases through FastAPI on 8486")
    rows = []
    with httpx.Client(base_url=BASE_URL, timeout=20) as http:
        for label, method, path, body, expect_success in CASES:
            cid = str(uuid.uuid4())
            if method == "GET":
                r = http.get(path, headers={"X-Correlation-ID": cid})
            else:
                r = http.post(path, json={**body, "correlation_id": cid})
            out = r.json()
            out.pop("kafka", None)
            ok = out.get("success") is expect_success and out.get("correlation_id") == cid
            print(f"[{'OK' if ok else 'UNEXPECTED'}] {label}: {method} {path} -> HTTP {r.status_code}")
            print(f"    sent correlation_id={cid}")
            print(f"    {json.dumps(out)}\n", flush=True)
            rows.append(
                {"case": label, "http_status": r.status_code, "sent_correlation_id": cid, "response": out, "ok": ok}
            )
    passed = sum(r["ok"] for r in rows)
    print(f"{passed}/{len(rows)} cases gave the expected success flag and echoed the same correlation_id")
    write_json(RAW / "part1_error_cases.json", {"run_at": utc_now(), "cases": rows})
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    code = main()
    footer("Part 1 error cases")
    sys.exit(code)
