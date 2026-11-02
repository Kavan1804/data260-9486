"""Small helpers shared by the HW8 Kafka programs (worker, RPC client, agents, failure tests)."""

from __future__ import annotations

import json
import sys
from datetime import datetime

import config


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def log(component: str, text: str) -> None:
    """One timestamped line per event, e.g. `2026-11-02 10:15:03.120 [worker] received ...`.

    Every line goes to stdout with flush=True so `docker logs` and the Makefile `tee` see it right away.
    """
    print(f"{stamp()} [{component}] {text}", file=sys.stdout, flush=True)


def to_bytes(message: dict) -> bytes:
    return json.dumps(message).encode("utf-8")


def from_bytes(raw: bytes | None) -> dict:
    """Decode a message value. Raises ValueError for anything that is not a JSON object."""
    if raw is None:
        raise ValueError("message has no value")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("message value is not a JSON object")
    return value


def short(message: dict, limit: int = 400) -> str:
    """Compact JSON for log lines (long LLM text is cut so a line stays readable)."""
    text = json.dumps(message, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


def where(record) -> str:
    """topic/partition/offset of a consumed record or a send() result."""
    return f"topic={record.topic} partition={record.partition} offset={record.offset}"


def bootstrap() -> str:
    return config.KAFKA_BOOTSTRAP
