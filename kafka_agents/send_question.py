#!/usr/bin/env python3
"""Sends one question to s9486_inbox and waits for the matching final message on s9486_final.

Run:  python kafka_agents/send_question.py ["your question"]      (or make send-question)
The correlation_id is created here once; the final message must come back with the same value.
Saves the final JSON to reports/hw08/raw/final_message.json (and appends to final_messages.jsonl).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition  # noqa: E402

import config  # noqa: E402
from kafka_agents.base import now_iso  # noqa: E402
from kafka_service.common import bootstrap, from_bytes, log, to_bytes, where  # noqa: E402

DEFAULT_QUESTION = "I am a student moving to San Jose. What should I check before signing a lease for an apartment?"
RAW = config.HW8_REPORT_DIR / "raw"


async def send_and_wait(question: str, timeout_s: float, wait: bool = True) -> dict | None:
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap())
    consumer = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
    await producer.start()
    await consumer.start()
    try:
        # Start reading s9486_final from its current end *before* sending, so the answer cannot be missed.
        parts = await producer.partitions_for(config.TOPIC_FINAL)
        tps = [TopicPartition(config.TOPIC_FINAL, p) for p in sorted(parts)]
        consumer.assign(tps)
        await consumer.seek_to_end(*tps)
        for tp in tps:
            await consumer.position(tp)

        cid = str(uuid.uuid4())
        msg = {
            "correlation_id": cid,
            "question": question,
            "sent_at": now_iso(),
            "trace": [{"agent": "send_question", "wrote": config.TOPIC_INBOX, "sent_at": now_iso()}],
        }
        sent = await producer.send_and_wait(config.TOPIC_INBOX, to_bytes(msg), key=cid.encode())
        log("send_question", f"sent question to {where(sent)} correlation_id={cid}")
        log("send_question", f"question = {question!r}")
        if not wait:
            return None

        log("send_question", f"waiting up to {timeout_s:.0f}s for correlation_id={cid} on {config.TOPIC_FINAL}")
        async with asyncio.timeout(timeout_s):
            async for record in consumer:
                try:
                    final = from_bytes(record.value)
                except ValueError:
                    continue
                if final.get("correlation_id") == cid:
                    log("send_question", f"received final from {where(record)} correlation_id={cid}")
                    return final
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--no-save", action="store_true", help="do not write raw/final_message.json (verify_hw08.py)")
    args = ap.parse_args()
    try:
        final = asyncio.run(send_and_wait(args.question, args.timeout, wait=not args.no_wait))
    except TimeoutError:
        log("send_question", "no final message in time (are planner, writer and reviewer running?)")
        return 1
    if final is None:
        return 0
    print(json.dumps(final, indent=2, ensure_ascii=False), flush=True)
    if args.no_save:
        return 0
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "final_message.json").write_text(json.dumps(final, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (RAW / "final_messages.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(final, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
