"""Shared consumer loop for the HW8 Planner, Writer and Reviewer.

Each agent is its own process. It reads one topic, does its step, writes the result to the next topic, and
only then commits the offset. Nothing calls another agent directly; every hand-off is a Kafka message.

Part 3 fixes live here, with a flag to turn each one off for the "before fix" runs:
  idempotency   skip a correlation_id this process already finished      (--no-idempotency)
  commit        commit the offset by hand after the output is sent        (--commit auto = auto-commit)
  poison        retry up to --max-retries, then send to s9486_dead_letter (--poison-handling none = crash)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRebalanceListener, TopicPartition  # noqa: E402
from aiokafka.errors import CommitFailedError  # noqa: E402

import config  # noqa: E402
from kafka_service.common import bootstrap, from_bytes, log, short, to_bytes, where  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def peek_correlation_id(raw: bytes | None) -> str | None:
    """correlation_id of a message, or None if it cannot be read (used for logs and the duplicate check)."""
    try:
        cid = from_bytes(raw).get("correlation_id")
    except (ValueError, UnicodeDecodeError):
        return None
    return cid if isinstance(cid, str) else None


def require(msg: dict, *fields: str) -> None:
    missing = [f for f in fields if not msg.get(f)]
    if missing:
        raise ValueError(f"message is missing {', '.join(missing)}")


class _ReadyListener(ConsumerRebalanceListener):
    """Logs partition assignment. The failure-test scripts wait for the "ready:" line before sending."""

    def __init__(self, agent: Agent):
        self.agent = agent

    async def on_partitions_revoked(self, revoked):
        if revoked:
            log(self.agent.label, f"partitions revoked {sorted(tp.partition for tp in revoked)}")

    async def on_partitions_assigned(self, assigned):
        parts = sorted(tp.partition for tp in assigned)
        log(
            self.agent.label, f"ready: group={self.agent.group} topic={self.agent.in_topic} assigned partitions={parts}"
        )


class Agent:
    name = "agent"
    in_topic = ""
    out_topic = ""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.label = args.instance or self.name
        self.group = args.group or f"{config.PREFIX}_{self.name}s"
        self.done: set[str] = set()  # correlation_ids finished by this process (idempotency)

    # ---- the agent's own step (runs in a thread so a slow LLM call does not block Kafka heartbeats) ----
    def handle(self, msg: dict) -> dict:
        raise NotImplementedError

    # ---- the shared loop ----
    async def run(self) -> None:
        a = self.args
        consumer = AIOKafkaConsumer(
            bootstrap_servers=bootstrap(),
            group_id=self.group,
            enable_auto_commit=a.commit == "auto",
            auto_commit_interval_ms=1000,
            auto_offset_reset=a.start_from,
            # A model call can take 30-60 s on my 8 GB Mac while it swaps. With the 10 s default the group
            # dropped the Writer mid-call, so allow 30 s without a heartbeat and 10 min between polls.
            session_timeout_ms=30000,
            heartbeat_interval_ms=5000,
            max_poll_interval_ms=600000,
        )
        consumer.subscribe([self.in_topic], listener=_ReadyListener(self))
        producer = AIOKafkaProducer(bootstrap_servers=bootstrap())
        # SIGTERM (Ctrl+C too) cancels this task, so the finally below leaves the group and closes cleanly.
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, asyncio.current_task().cancel)
        await producer.start()
        await consumer.start()
        log(
            self.label,
            f"started: reads {self.in_topic}, writes {self.out_topic}, mode={a.mode}, commit={a.commit}, "
            f"idempotency={'off' if a.no_idempotency else 'on'}, poison={a.poison_handling} (max {a.max_retries})",
        )
        try:
            async for record in consumer:
                await self.one_record(record, consumer, producer)
        finally:
            await consumer.stop()
            await producer.stop()
            log(self.label, "stopped")

    async def one_record(self, record, consumer, producer) -> None:
        a = self.args
        cid = peek_correlation_id(record.value)
        log(self.label, f"received from {where(record)} correlation_id={cid}")

        if not a.no_idempotency and cid and cid in self.done:
            log(self.label, f"duplicate correlation_id={cid}: already processed, skipping (no second output)")
            await self.commit(consumer, record)
            return

        msg, out, error = None, None, None
        for attempt in range(1, a.max_retries + 1):
            try:
                msg = from_bytes(record.value)
                started = time.time()
                out = await asyncio.to_thread(self.handle, msg)
                out["trace"] = msg.get("trace", []) + [
                    {
                        "agent": self.label,
                        "read": f"{record.topic}/{record.partition}/{record.offset}",
                        "done_at": now_iso(),
                    }
                ]
                self.record_processed(record, msg, started)
                break
            except Exception as exc:  # noqa: BLE001 - any failure counts as a failed attempt
                error = f"{type(exc).__name__}: {exc}"
                if a.poison_handling == "none":
                    # Before-fix behavior: no retry, no dead-letter, the process dies without committing.
                    log(
                        self.label,
                        f"FAILED on offset {record.offset}: {error} -> crash, exit code 1, nothing committed",
                    )
                    raise SystemExit(1) from exc
                log(self.label, f"attempt {attempt}/{a.max_retries} failed for offset {record.offset}: {error}")
                if attempt < a.max_retries:
                    await asyncio.sleep(0.5 * attempt)

        if out is None:
            dead = {
                "correlation_id": cid,
                "failed_agent": self.label,
                "source": {"topic": record.topic, "partition": record.partition, "offset": record.offset},
                "error": error,
                "attempts": a.max_retries,
                "raw_value": (record.value or b"").decode("utf-8", "replace")[:2000],
                "failed_at": now_iso(),
            }
            sent = await producer.send_and_wait(config.TOPIC_DEAD_LETTER, to_bytes(dead), key=(cid or "").encode())
            log(self.label, f"gave up after {a.max_retries} attempts -> moved to {where(sent)}")
            await self.commit(consumer, record)
            return

        key = (cid or "").encode()
        sent = await producer.send_and_wait(self.out_topic, to_bytes(out), key=key)
        log(self.label, f"sent to {where(sent)} correlation_id={cid} value={short(out, 300)}")
        if cid:
            self.done.add(cid)
        await self.commit(consumer, record)

    async def commit(self, consumer, record) -> None:
        """Manual mode: commit offset+1 for this partition, only after the output was sent (or DLQ'd)."""
        if self.args.commit != "manual":
            return
        try:
            await consumer.commit({TopicPartition(record.topic, record.partition): record.offset + 1})
        except CommitFailedError as exc:
            # The group rebalanced while we were working. The output is already sent, so Kafka will hand this
            # message out again; the duplicate check skips it then. Keep running instead of crashing.
            log(
                self.label,
                f"commit of offset {record.offset + 1} failed ({type(exc).__name__}, group rebalanced); "
                "the message will be redelivered and skipped as a duplicate",
            )
            return
        log(self.label, f"committed offset {record.offset + 1} for {record.topic} partition {record.partition}")

    def record_processed(self, record, msg: dict, started: float) -> None:
        """--record FILE: one JSON line per processed message (used by the Part 3 ordering test)."""
        if not self.args.record:
            return
        test = msg.get("test") or {}
        row = {
            "instance": self.label,
            "partition": record.partition,
            "offset": record.offset,
            "key": record.key.decode() if record.key else None,
            "correlation_id": msg.get("correlation_id"),
            "entity": test.get("entity"),
            "seq": test.get("seq"),
            "send_index": test.get("index"),
            "started_at": started,
            "processed_at": time.time(),
        }
        with open(self.args.record, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")


def parse_args(name: str, argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=f"HW8 {name} agent")
    ap.add_argument("--mode", choices=["llm", "fast"], default="llm", help="fast = fixed template, no model call")
    ap.add_argument("--group", help=f"consumer group (default {config.PREFIX}_{name}s)")
    ap.add_argument("--instance", help="name used in log lines, e.g. writer-1")
    ap.add_argument("--commit", choices=["manual", "auto"], default="manual")
    ap.add_argument("--no-idempotency", action="store_true")
    ap.add_argument("--poison-handling", choices=["retry-dlq", "none"], default="retry-dlq")
    ap.add_argument("--max-retries", type=int, default=config.WRITER_MAX_RETRIES)
    ap.add_argument("--work-seconds", type=float, default=0.0, help="extra sleep per message (fast mode)")
    ap.add_argument("--record", help="append one JSON line per processed message to this file")
    # Only used the first time a group starts (after that the committed offset wins). "latest" means a new
    # group does not replay old test messages; start the agents before sending a question.
    ap.add_argument("--from", dest="start_from", choices=["earliest", "latest"], default="latest")
    return ap.parse_args(argv)


def main(agent_cls: type[Agent]) -> None:
    agent = agent_cls(parse_args(agent_cls.name))
    try:
        asyncio.run(agent.run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
