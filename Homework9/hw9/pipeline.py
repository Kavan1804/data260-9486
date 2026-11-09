"""The HW8 agent path behind the cache: s9486_inbox -> planner -> writer -> reviewer -> s9486_final.

KafkaPipeline reuses kafka_agents/send_question.send_and_wait (unchanged HW8 code). running_agents() starts
the three unchanged HW8 agents as child processes (same commands as `make planner/writer/reviewer`) so the
HW9 scripts do not need four terminals; each agent's output goes to reports/hw09/raw/agent_logs/.
"""

from __future__ import annotations

import asyncio
import sys
import time
from contextlib import contextmanager

from hw9.common import RAW, ROOT, log

sys.path.insert(0, str(ROOT / "Homework8" / "scripts"))

AGENT_LOGS = RAW / "agent_logs"


class KafkaPipeline:
    name = "hw8-kafka"

    def __init__(self, timeout_s: float = 400):
        self.timeout_s = timeout_s
        self.calls = 0

    def __call__(self, question: str) -> dict:
        from kafka_agents.send_question import send_and_wait

        self.calls += 1
        final = asyncio.run(send_and_wait(question, self.timeout_s))
        if not final:
            raise RuntimeError("no final message from the HW8 pipeline")
        return final


@contextmanager
def running_agents():
    """Start planner, writer and reviewer (llm mode, normal consumer groups) and stop them afterwards."""
    from hw8_common import Proc

    AGENT_LOGS.mkdir(parents=True, exist_ok=True)
    agents = [
        Proc(n, [f"kafka_agents/{n}.py"], AGENT_LOGS / f"{n}.log", echo=False)
        for n in ("planner", "writer", "reviewer")
    ]
    try:
        start = time.time()
        for a in agents:
            if not a.wait_for("ready:", timeout=90):
                raise RuntimeError(f"{a.name} did not join its consumer group (is Kafka up? make hw9-up)")
        log("pipeline", f"HW8 agents ready (planner, writer, reviewer) in {time.time() - start:.1f}s")
        from hw9.embeddings import EMBED_MODEL, warm_up

        log("pipeline", f"warm-up: {EMBED_MODEL} loaded in {warm_up()}s (not part of any measured latency)")
        yield agents
    finally:
        for a in agents:
            a.stop()
        log("pipeline", "HW8 agents stopped")
