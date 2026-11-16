"""HW10 Part 2: collect the Planner plan, Writer draft and Reviewer final for one correlation_id, then GEval them.

collect(): reads s9486_tasks, s9486_drafts and s9486_final from offsets saved *before* the question was sent and
keeps the messages whose correlation_id matches (the join key). Original message + Kafka metadata are kept.
Malformed JSON is counted and skipped. Bounded: the read stops after `timeout_s`.
evaluate(): Plan Quality, Writer Helpfulness and Final Answer Helpfulness with the local judge, all inside one
deadline (`deadline_s`); if the judge is down or slow the result is status "error" instead of a hang.
Final-vs-Draft Improvement is the difference of the two answer scores plus an interpretation.
"""

from __future__ import annotations

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import config
from hw10.judge import JUDGE_SETTINGS, OllamaJudge, score
from kafka_agents.tracing import write_span

TOPICS = {"plan": config.TOPIC_TASKS, "draft": config.TOPIC_DRAFTS, "final": config.TOPIC_FINAL}


async def end_offsets(topics: list[str]) -> dict[str, dict[int, int]]:
    """Current end offset of every partition (saved before a question is sent, so collect() starts there)."""
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition

    from kafka_service.common import bootstrap

    prod = AIOKafkaProducer(bootstrap_servers=bootstrap())  # partitions_for() waits for metadata (HW8 lesson)
    c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None)
    await prod.start()
    await c.start()
    try:
        out = {}
        for t in topics:
            parts = await prod.partitions_for(t)
            ends = await c.end_offsets([TopicPartition(t, p) for p in sorted(parts)])
            out[t] = {tp.partition: off for tp, off in ends.items()}
        return out
    finally:
        await c.stop()
        await prod.stop()


async def _collect(trace_id: str, start: dict[str, dict[int, int]], timeout_s: float) -> dict:
    from aiokafka import AIOKafkaConsumer, TopicPartition

    from kafka_service.common import bootstrap

    c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
    await c.start()
    found: dict[str, dict] = {}
    malformed = 0
    try:
        tps = [TopicPartition(t, p) for t, parts in start.items() for p in parts]
        c.assign(tps)
        for tp in tps:
            c.seek(tp, start[tp.topic][tp.partition])
        ends = await c.end_offsets(tps)

        async def behind() -> bool:
            for tp in tps:
                if await c.position(tp) < ends[tp]:
                    return True
            return False

        async with asyncio.timeout(timeout_s):
            while await behind():
                batch = await c.getmany(timeout_ms=1000, max_records=200)
                for recs in batch.values():
                    for r in recs:
                        try:
                            msg = json.loads(r.value)
                        except (ValueError, TypeError):
                            malformed += 1
                            continue
                        if not isinstance(msg, dict) or msg.get("correlation_id") != trace_id:
                            continue
                        found[r.topic] = {
                            "message": msg,
                            "kafka": {
                                "topic": r.topic,
                                "partition": r.partition,
                                "offset": r.offset,
                                "timestamp_ms": r.timestamp,
                            },
                        }
    finally:
        await c.stop()
    return {name: found.get(topic) for name, topic in TOPICS.items()} | {"malformed_skipped": malformed}


def collect(trace_id: str, start: dict[str, dict[int, int]], timeout_s: float = 30) -> dict:
    """Never raises: a Kafka error or the timeout gives {"collect_error": ...} and evaluate() reports it."""
    try:
        return asyncio.run(_collect(trace_id, start, timeout_s))
    except Exception as exc:  # noqa: BLE001
        return {"plan": None, "draft": None, "final": None, "collect_error": f"{type(exc).__name__}: {exc}"[:300]}


def interpret(draft: int | None, final: int | None, same_text: bool, review: dict) -> str:
    if draft is None or final is None:
        return "Not scored."
    diff = final - draft
    if same_text:
        base = (
            "The Reviewer approved the draft and passed it on unchanged (final answer = draft text), so the final "
            "answer cannot be better than the draft"
        )
        if diff == 0:
            return base + "; the judge gave both the same score."
        return base + f"; the judge still scored them {diff:+d} apart, which is judge noise, not an improvement."
    if diff > 0:
        return f"The final answer scored {diff:+d} over the draft: the Reviewer's change helped."
    if diff < 0:
        return f"The final answer scored {diff:+d} under the draft: the Reviewer's change made it worse."
    return "The Reviewer changed the text but the judge scored it the same."


def evaluate(trace_id: str, collected: dict, judge: OllamaJudge | None = None, deadline_s: float = 300) -> dict:
    """Run the four criteria for one trace. Writes an `evaluation` span. Never waits longer than deadline_s."""
    judge = judge or OllamaJudge()
    start = time.time()
    result = {"trace_id": trace_id, "judge": JUDGE_SETTINGS, "status": "ok", "error": None}
    missing = [k for k in ("plan", "draft", "final") if not collected.get(k)]
    if missing:
        why = collected.get("collect_error") or f"missing {', '.join(missing)} message(s) for this trace_id"
        result.update(status="error", error=why)
        write_span(trace_id, "evaluation", start, time.time(), "error", result["error"])
        return result
    plan_msg, draft_msg, final_msg = (collected[k]["message"] for k in ("plan", "draft", "final"))
    question = plan_msg.get("question", "")
    plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(plan_msg.get("plan", []), 1))
    draft, final = draft_msg.get("draft", ""), final_msg.get("answer", "")

    def run_all() -> dict:
        return {
            "plan_quality": score("Plan Quality", judge, question, plan_text),
            "writer_helpfulness": score("Writer Helpfulness", judge, question, draft),
            "final_helpfulness": score("Final Answer Helpfulness", judge, question, final),
        }

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        scores = pool.submit(run_all).result(timeout=deadline_s)
    except FutureTimeout:
        result.update(status="error", error=f"judge did not finish within {deadline_s:.0f}s")
    except Exception as exc:  # noqa: BLE001 - judge down, bad JSON, HTTP error: report, do not crash
        result.update(status="error", error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    if result["status"] == "ok":
        same = " ".join(draft.split()) == " ".join(final.split())
        d, f = scores["writer_helpfulness"]["score"], scores["final_helpfulness"]["score"]
        result.update(
            plan_quality={"score": scores["plan_quality"]["score"], "reason": scores["plan_quality"]["reason"]},
            writer_helpfulness={**scores["writer_helpfulness"], "trace_id": trace_id},
            final_helpfulness={**scores["final_helpfulness"], "final_answer": final},
            improvement={
                "draft_score": d,
                "final_score": f,
                "difference": None if d is None or f is None else f - d,
                "final_equals_draft": same,
                "reviewer": {k: final_msg.get("review", {}).get(k) for k in ("approved", "notes")},
                "interpretation": interpret(d, f, same, final_msg.get("review", {})),
            },
        )
    result["inputs"] = {
        "question": question,
        "plan": plan_msg.get("plan", []),
        "draft": draft,
        "final_answer": final,
        "kafka": {k: collected[k]["kafka"] for k in ("plan", "draft", "final")},
        "malformed_skipped": collected.get("malformed_skipped", 0),
    }
    result["judge_calls"] = getattr(judge, "calls", None)
    end = time.time()
    span_scores = {
        k: result.get(k, {}).get("score") for k in ("plan_quality", "writer_helpfulness", "final_helpfulness")
    }
    write_span(trace_id, "evaluation", start, end, result["status"], result["error"], scores=span_scores)
    result["seconds"] = round(end - start, 2)
    return result
