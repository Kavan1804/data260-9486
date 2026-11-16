"""Starting the three HW8 agents for HW10 runs, with tracing on (same commands as `make planner/writer/reviewer`)."""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager

from hw10.common import RAW, ROOT, enable_tracing

sys.path.insert(0, str(ROOT / "Homework8" / "scripts"))


def log(who: str, msg: str) -> None:
    from datetime import datetime

    print(f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3] + f" [{who}] {msg}", flush=True)


@contextmanager
def running_agents():
    """Planner, Writer, Reviewer as child processes; they inherit TRACE_SPANS_FILE and write their own spans."""
    from hw8_common import Proc

    enable_tracing()
    logs = RAW / "agent_logs"
    logs.mkdir(parents=True, exist_ok=True)
    agents = [
        Proc(n, [f"kafka_agents/{n}.py"], logs / f"{n}.log", echo=False) for n in ("planner", "writer", "reviewer")
    ]
    try:
        start = time.time()
        for a in agents:
            if not a.wait_for("ready:", timeout=90):
                raise RuntimeError(f"{a.name} did not join its consumer group (is Kafka up? make hw10-up)")
        log(
            "agents", f"planner, writer, reviewer ready in {time.time() - start:.1f}s (spans -> {RAW.name}/spans.jsonl)"
        )
        from hw9.embeddings import warm_up

        log("agents", f"warm-up: embedding model loaded in {warm_up()}s (not timed)")
        yield agents
    finally:
        for a in agents:
            a.stop()
        log("agents", "stopped")


def make_qa(namespace: str = "hw10", run_evaluation: bool = True):
    from hw9.common import redis_client
    from hw9.listing_store import ListingDatabaseWithCache
    from hw9.semantic_cache import RedisSemanticCache
    from hw10.judge import OllamaJudge
    from hw10.traced_ingress import TracedQA

    r = redis_client()
    cache = RedisSemanticCache(r, namespace, threshold=0.85)
    return TracedQA(cache, ListingDatabaseWithCache(r), OllamaJudge(), run_evaluation), cache
