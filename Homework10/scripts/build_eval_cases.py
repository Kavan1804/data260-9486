#!/usr/bin/env python3
"""HW10 Part 3.1: freeze 20 Writer drafts from my system into Homework10/data/eval_cases.json.

The drafts are read from the s9486_drafts Kafka topic: real llama3.2:3b Writer outputs from my HW8/HW9 runs (made
before HW10 existed). Only LLM-mode drafts, one per distinct question, then 20 picked with
random.Random(VERIFY_SEED). Each case keeps the original message and its Kafka metadata so the evaluation can
be reproduced. No labels and no judge scores are written here.

Usage (repo root, Kafka running):  python Homework10/scripts/build_eval_cases.py      (or make eval-cases)
Refuses to overwrite an existing eval_cases.json (the file is frozen once it is committed).
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

import config  # noqa: E402
from hw10.common import DATA, banner, footer, utc_now, write_json  # noqa: E402

OUT = DATA / "eval_cases.json"


async def read_drafts() -> list[dict]:
    from aiokafka import AIOKafkaConsumer, TopicPartition

    from kafka_service.common import bootstrap

    c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
    await c.start()
    try:
        parts = c.partitions_for_topic(config.TOPIC_DRAFTS) or {0}
        tps = [TopicPartition(config.TOPIC_DRAFTS, p) for p in sorted(parts)]
        c.assign(tps)
        await c.seek_to_beginning(*tps)
        rows = []
        async with asyncio.timeout(60):
            while True:
                batch = await c.getmany(timeout_ms=3000, max_records=500)
                if not batch:
                    break
                for recs in batch.values():
                    for r in recs:
                        try:
                            msg = json.loads(r.value)
                        except (ValueError, TypeError):
                            continue
                        rows.append(
                            {
                                "msg": msg,
                                "kafka": {
                                    "topic": r.topic,
                                    "partition": r.partition,
                                    "offset": r.offset,
                                    "timestamp_ms": r.timestamp,
                                },
                            }
                        )
        return rows
    finally:
        await c.stop()


def main() -> int:
    banner("Part 3.1 freeze 20 Writer drafts -> eval_cases.json")
    if OUT.exists():
        print(f"{OUT.name} already exists - it is frozen, not rebuilding")
        return 0
    rows = asyncio.run(read_drafts())
    seen, pool = set(), []
    for row in rows:
        m = row["msg"]
        if (m.get("writer") or {}).get("mode") != "llm" or not m.get("draft"):
            continue
        q = m["question"].split("\n")[0].strip()
        if q in seen:
            continue
        seen.add(q)
        pool.append(row)
    print(f"{len(rows)} messages on {config.TOPIC_DRAFTS}, {len(pool)} distinct LLM drafts")
    picked = random.Random(config.VERIFY_SEED).sample(pool, 20)
    picked.sort(key=lambda r: r["kafka"]["offset"])
    cases = []
    for i, row in enumerate(picked, 1):
        m = row["msg"]
        cases.append(
            {
                "case_id": f"c{i:02d}",
                "trace_id": m["correlation_id"],
                "question": m["question"].split("\n")[0].strip(),
                "question_with_facts": m["question"],
                "plan": m.get("plan", []),
                "draft": m["draft"],
                "writer": m.get("writer"),
                "kafka": row["kafka"],
            }
        )
    write_json(
        OUT,
        {
            "frozen_at": utc_now(),
            "source": f"{config.TOPIC_DRAFTS} (HW8/HW9 runs)",
            "seed": config.VERIFY_SEED,
            "cases": cases,
        },
    )
    for c in cases:
        print(f"  {c['case_id']} offset {c['kafka']['offset']:>3}  {c['question'][:80]}")
    print(f"wrote {OUT.relative_to(OUT.parents[2])} ({len(cases)} drafts, no labels, no judge scores)")
    return 0


if __name__ == "__main__":
    code = main()
    footer("eval cases")
    sys.exit(code)
