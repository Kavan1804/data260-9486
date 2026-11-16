"""HW10 Part 4: the HW9 semantic cache in front of the HW8 pipeline, with one trace_id for the whole request.

ask(query):
  trace_id = new uuid4, made once here. It is the Kafka correlation_id (no second id), so the agents' spans,
  the plan/draft/final messages and the evaluation all carry the same value.
  cache_lookup span  embedding + Redis KNN + data-version check; attr cache = "hit" | "miss"
  hit  -> request span (path "hit") and return; the pipeline and the evaluator are not run.
  miss -> pipeline span (send to s9486_inbox ... final received); the planner/writer/reviewer spans are written
          by the agents themselves (kafka_agents/base.py); cache_store span; evaluation span (Part 2 evaluator);
          request span (path "miss").
  If no final arrives in time (e.g. a stage sent the message to the dead-letter topic) the pipeline span and
  the request span get status "error", and the dead-letter record (failing stage + error) is attached.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import config
from hw9.embeddings import embed
from hw9.ingress import facts_block, listing_codes
from hw10.evaluator import TOPICS, collect, end_offsets, evaluate
from kafka_agents.tracing import write_span


class TracedQA:
    def __init__(self, cache, store, judge=None, run_evaluation: bool = True):
        self.cache = cache  # hw9 RedisSemanticCache (namespace s9486:hw10:*)
        self.store = store  # hw9 ListingDatabaseWithCache
        self.judge = judge
        self.run_evaluation = run_evaluation

    def data_version(self, codes: list[str]) -> str:
        return ";".join(f"{c}@{self.store.fingerprint(c)}" for c in codes) if codes else "none"

    def ask(
        self,
        query: str,
        store_on_miss: bool = True,
        fail_stage: str | None = None,
        final_timeout_s: float = 400,
        threshold: float | None = None,
    ) -> dict:
        threshold = self.cache.threshold if threshold is None else threshold
        trace_id = str(uuid.uuid4())
        t0 = time.time()

        # ---- cache_lookup
        vec = embed(query)
        entry, sim = self.cache.nearest(vec)
        hit = entry is not None and sim >= threshold
        if hit and entry["data_version"] != "none":
            hit = self.data_version(entry["depends_on"].split(",")) == entry["data_version"]
        t1 = time.time()
        write_span(
            trace_id,
            "cache_lookup",
            t0,
            t1,
            "ok",
            None,
            cache="hit" if hit else "miss",
            similarity=sim,
            matched_query=entry["query"] if entry else None,
            query=query,
        )
        out = {"trace_id": trace_id, "query": query, "similarity": sim, "is_cached": hit}

        if hit:
            out.update(answer=entry["answer"], path="hit", status="ok", latency_ms=round((t1 - t0) * 1000, 1))
            write_span(trace_id, "request", t0, time.time(), "ok", None, path="hit", query=query)
            return out

        # ---- pipeline (HW8 Kafka path), same trace_id as correlation_id
        from kafka_agents.send_question import send_and_wait

        codes = listing_codes(query)
        question = query if not codes else f"{query}\n\n{facts_block(self.store, codes)}"
        watch = [*TOPICS.values(), config.TOPIC_DEAD_LETTER]
        start_offsets = asyncio.run(end_offsets(watch))
        t2 = time.time()
        test = {"fail_stage": fail_stage} if fail_stage else None
        try:
            final = asyncio.run(send_and_wait(question, final_timeout_s, correlation_id=trace_id, test=test))
            error = None if final else "no final message"
        except TimeoutError:
            final, error = None, f"no final message within {final_timeout_s:.0f}s"
        t3 = time.time()
        dead = self._dead_letter(trace_id, start_offsets) if error else None
        if dead:
            error += f"; dead-letter record from {dead['failed_agent']}: {dead['error']}"
        write_span(
            trace_id, "pipeline", t2, t3, "error" if error else "ok", error, final_received_ms=round(t3 * 1000, 1)
        )

        if error:
            out.update(
                path="miss",
                status="error",
                error=error,
                failed_stage=dead and dead["failed_agent"],
                latency_ms=round((time.time() - t0) * 1000, 1),
            )
            write_span(trace_id, "request", t0, time.time(), "error", error, path="miss", query=query)
            return out

        # ---- cache_store
        if store_on_miss:
            t4 = time.time()
            self.cache.store(
                query, vec, final.get("answer", ""), self.data_version(codes), codes, final.get("status", "")
            )
            write_span(trace_id, "cache_store", t4, time.time(), "ok")

        # ---- evaluation (Part 2 evaluator, bounded)
        evaluation = None
        if self.run_evaluation:
            collected = collect(trace_id, {t: start_offsets[t] for t in TOPICS.values()})
            evaluation = evaluate(trace_id, collected, self.judge)

        status = "ok" if (evaluation is None or evaluation["status"] == "ok") else "error"
        err = None if status == "ok" else f"evaluation: {evaluation['error']}"
        write_span(trace_id, "request", t0, time.time(), status, err, path="miss", query=query)
        out.update(
            answer=final.get("answer", ""),
            path="miss",
            status=status,
            error=err,
            evaluation=evaluation,
            reviewer_status=final.get("status"),
            latency_ms=round((time.time() - t0) * 1000, 1),
        )
        return out

    @staticmethod
    def _dead_letter(trace_id: str, start: dict) -> dict | None:
        from aiokafka import AIOKafkaConsumer, TopicPartition

        from kafka_service.common import bootstrap

        async def go():
            c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
            await c.start()
            try:
                parts = start[config.TOPIC_DEAD_LETTER]
                tps = [TopicPartition(config.TOPIC_DEAD_LETTER, p) for p in parts]
                c.assign(tps)
                for tp in tps:
                    c.seek(tp, parts[tp.partition])
                async with asyncio.timeout(10):
                    batch = await c.getmany(timeout_ms=3000, max_records=200)
                for recs in batch.values():
                    for r in recs:
                        try:
                            m = json.loads(r.value)
                        except (ValueError, TypeError):
                            continue
                        if m.get("correlation_id") == trace_id:
                            return m
            except TimeoutError:
                return None
            finally:
                await c.stop()
            return None

        return asyncio.run(go())
