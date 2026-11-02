"""Local model call for the agents: the same Ollama adapter (llama3.2:3b) used since HW5."""

from __future__ import annotations

import json
import time

import config
from domain_tools.agent import OllamaModel

MODEL = OllamaModel(
    model=config.OLLAMA_MODEL,
    url=config.OLLAMA_URL,
    timeout_s=180.0,
    num_ctx=config.AGENT_NUM_CTX,
    temperature=0.2,
    seed=config.SEED,
)


def ask(system: str, user: str, as_json: bool = False) -> tuple[str | dict, float]:
    """Returns (text or parsed JSON, seconds). Bad JSON raises ValueError, so the agent loop retries it."""
    start = time.time()
    reply = MODEL.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=[],
        fmt="json" if as_json else None,
    )
    seconds = round(time.time() - start, 2)
    text = (reply.get("content") or "").strip()
    if not as_json:
        return text, seconds
    try:
        return json.loads(text), seconds
    except json.JSONDecodeError as exc:
        raise ValueError(f"model did not return JSON: {text[:120]!r}") from exc
