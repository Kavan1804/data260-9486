"""Request/response over Kafka (based on the DATA236 Demo 8 KafkaRPC, changed for the HW8 schema).

The caller sends a request to s9486_entity_requests and waits on a future keyed by correlation_id. One background
task reads s9486_entity_responses and resolves the future whose correlation_id matches.

Differences from the demo: the response consumer has no group (it reads every partition from the end), so the
FastAPI container and a host script can both wait for responses without stealing each other's messages, and the
correlation_id can be passed in by the caller so it is created only once.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition

import config
from kafka_service import messages
from kafka_service.common import bootstrap, from_bytes, log, short, stamp, to_bytes, where


@dataclass
class RpcResult:
    request: dict
    response: dict
    request_meta: dict  # where the request was written
    response_meta: dict  # where the response was read
    sent_line: str = ""  # the client's own log lines, so a demo can print them under the right step
    received_line: str = ""


def _meta(record) -> dict:
    return {"topic": record.topic, "partition": record.partition, "offset": record.offset}


class KafkaRPC:
    def __init__(self, name: str = "client", timeout_s: float = config.KAFKA_RPC_TIMEOUT_S, quiet: bool = False):
        self.name = name
        self.quiet = quiet  # homework_demo.py prints the lines itself, step by step
        self.timeout_s = timeout_s
        self.producer: AIOKafkaProducer | None = None
        self.consumer: AIOKafkaConsumer | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self.producer = AIOKafkaProducer(bootstrap_servers=bootstrap())
        self.consumer = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
        await self.producer.start()
        await self.consumer.start()
        try:
            parts = await self.producer.partitions_for(config.TOPIC_RESPONSES)  # waits for topic metadata
        except Exception as exc:
            await self.stop()
            raise RuntimeError(f"topic {config.TOPIC_RESPONSES} not found (run make kafka-topics): {exc}") from exc
        tps = [TopicPartition(config.TOPIC_RESPONSES, p) for p in sorted(parts)]
        self.consumer.assign(tps)
        await self.consumer.seek_to_end(*tps)
        for tp in tps:  # resolve the end position now, before any request is sent
            await self.consumer.position(tp)
        self._task = asyncio.create_task(self._listen())
        log(self.name, f"listening on {config.TOPIC_RESPONSES} partitions={sorted(parts)} (bootstrap={bootstrap()})")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def _listen(self) -> None:
        async for record in self.consumer:
            try:
                response = from_bytes(record.value)
            except ValueError:
                continue
            fut = self.pending.get(response.get("correlation_id"))
            if fut and not fut.done():
                fut.set_result((response, _meta(record)))

    async def request(self, operation: str, data, correlation_id: str | None = None) -> RpcResult:
        request = messages.build_request(operation, data, correlation_id)
        cid = request["correlation_id"]
        fut = asyncio.get_running_loop().create_future()
        self.pending[cid] = fut
        try:
            sent = await self.producer.send_and_wait(config.TOPIC_REQUESTS, to_bytes(request), key=cid.encode())
            sent_line = (
                f"{stamp()} [{self.name}] sent request to {where(sent)} operation={operation} correlation_id={cid}"
            )
            if not self.quiet:
                print(sent_line, flush=True)
                log(self.name, f"request message = {short(request)}")
            response, response_meta = await asyncio.wait_for(fut, self.timeout_s)
        except asyncio.TimeoutError:
            raise TimeoutError(f"no response for correlation_id={cid} within {self.timeout_s}s") from None
        finally:
            self.pending.pop(cid, None)
        m = response_meta
        received_line = (
            f"{stamp()} [{self.name}] received response from topic={m['topic']} partition={m['partition']} "
            f"offset={m['offset']} correlation_id={response['correlation_id']} success={response['success']}"
        )
        if not self.quiet:
            print(received_line, flush=True)
        return RpcResult(request, response, _meta(sent), response_meta, sent_line, received_line)
