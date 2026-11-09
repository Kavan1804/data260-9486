"""Local model call for the agents: the same Ollama adapter (llama3.2:3b) used since HW5.

HW9 fix: with format=json and seed 9486, llama3.2:3b sometimes never stops on some questions (it keeps writing
escaped Cyrillic text), so the Planner hung for 3 x 180 s. Replies are now capped at AGENT_NUM_PREDICT tokens,
and if a JSON reply is unusable the call is tried once more with seed+1 before the error goes to the agent loop.
"""

from __future__ import annotations

import json
import time

import config
from domain_tools.agent import OllamaModel
from kafka_service.common import log

MODEL = OllamaModel(
    model=config.OLLAMA_MODEL,
    url=config.OLLAMA_URL,
    timeout_s=180.0,
    num_ctx=config.AGENT_NUM_CTX,
    temperature=0.2,
    seed=config.SEED,
    num_predict=config.AGENT_NUM_PREDICT,
)


def _call(system: str, user: str, as_json: bool, seed: int | None = None) -> str:
    reply = MODEL.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=[],
        fmt="json" if as_json else None,
        seed=seed,
    )
    return (reply.get("content") or "").strip()


def ask(system: str, user: str, as_json: bool = False) -> tuple[str | dict, float]:
    """Returns (text or parsed JSON, seconds). Bad JSON (twice) raises ValueError, so the agent loop retries it."""
    start = time.time()
    text = _call(system, user, as_json)
    if not as_json:
        return text, round(time.time() - start, 2)
    try:
        return json.loads(text), round(time.time() - start, 2)
    except json.JSONDecodeError:
        log("llm", f"unusable JSON with seed {config.SEED} ({text[:60]!r}...), trying once with seed {config.SEED + 1}")
    text = _call(system, user, as_json, seed=config.SEED + 1)
    try:
        return json.loads(text), round(time.time() - start, 2)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return JSON: {text[:120]!r}") from exc
