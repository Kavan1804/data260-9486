"""Part 5: run_agent(user_input) - a small tool-calling loop over execute_tool.

The model (local Ollama, or MockModel in tests) proposes a tool call; the harness
runs it through execute_tool (one call per step), feeds the JSON result back,
and stops on
  completed     - the model answers without asking for a tool
  safety_block  - execute_tool refused a call under the fair-housing rule
  max_steps     - the turn counter reached max_steps
  model_error   - the model could not be reached / returned garbage
Every step, tool call, input, result, and the stop reason is appended to a
JSONL log (reports/hw05/raw/agent_runs.jsonl by default).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

import config

from .execute import TOOL_SPECS, execute_tool
from .safety import SAFETY_ERROR_PREFIX

DEFAULT_LOG = Path(config.ROOT) / "reports" / "hw05" / "raw" / "agent_runs.jsonl"

SYSTEM_PROMPT = (
    "You are a rental-listing assistant for the s9486 listings database. "
    "Use the tools to look up real data; never invent listings, codes, or numbers. "
    "Tools: search_listings(query, limit, min_units) finds listings by words in the title or address; "
    "get_listing(listing_code) returns one listing, codes look like LST-00042; "
    "landlord_portfolio_stats(landlord_id) returns counts for one landlord. "
    "Call one tool at a time. When you have enough information, answer in 2-4 sentences without calling a tool."
)

OLLAMA_TOOLS = [
    {"type": "function", "function": {"name": n, "description": s["description"], "parameters": s["schema"]}}
    for n, s in TOOL_SPECS.items()
]


class Model(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"content": str, "tool_calls": [{"name": str, "arguments": dict}]}."""


class OllamaModel:
    def __init__(self, model: str = config.LLM_MODEL, url: str = config.OLLAMA_URL, timeout_s: float = 180.0):
        self.name = model
        self.url = url.rstrip("/") + "/api/chat"
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        import httpx

        body = {
            "model": self.name,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0, "seed": config.SEED},
        }
        resp = httpx.post(self.url, json=body, timeout=self.timeout_s)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            calls.append({"name": fn.get("name"), "arguments": fn.get("arguments", {})})
        return {"content": msg.get("content", ""), "tool_calls": calls}


class MockModel:
    """Offline stand-in. By default it asks for the same search on every turn,
    so the only way the loop can end is the max_steps ceiling."""

    name = "MockModel"

    def __init__(self, replies: list[dict] | None = None):
        self.replies = list(replies) if replies else None
        self.calls = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls += 1
        if self.replies:
            return self.replies.pop(0)
        return {"content": "", "tool_calls": [{"name": "search_listings", "arguments": {"query": "San Jose"}}]}


class _JsonlLog:
    def __init__(self, path: Path | None, run_id: str):
        self.path = path
        self.run_id = run_id
        self.events: list[dict] = []
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: str, **fields: Any) -> None:
        rec = {"run_id": self.run_id, "ts": datetime.now().isoformat(timespec="milliseconds"), "event": event, **fields}
        self.events.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")


def _classify_text(content: str) -> tuple[str | None, dict | None]:
    """Guards for small models that put JSON in the text channel instead of tool_calls.
    Returns ("tool_call_as_text", call) for {"name": <tool>, "parameters"/"arguments": {...}},
    ("fabricated_tool_result", None) for a made-up {ok, data, error} envelope, else (None, None)."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    if not text.startswith("{"):
        return None, None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(obj, dict):
        return None, None
    if obj.get("name") in TOOL_SPECS:
        args = obj.get("parameters", obj.get("arguments", {}))
        return "tool_call_as_text", {"name": obj["name"], "arguments": args}
    if {"ok", "data"} <= set(obj):
        return "fabricated_tool_result", None
    return None, None


def run_agent(
    user_input: str,
    *,
    model: Model | None = None,
    max_steps: int = config.AGENT_MAX_STEPS,
    executor: Callable[[str, Any], str] = execute_tool,
    log_path: Path | None = DEFAULT_LOG,
    scenario: str | None = None,
) -> dict:
    """Run the loop and return a summary dict (also logged as the final "stop" event)."""
    model = model or OllamaModel()
    log = _JsonlLog(log_path, run_id=uuid.uuid4().hex[:12])
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_input}]
    log("run_start", scenario=scenario, model=model.name, max_steps=max_steps, user_input=user_input)

    started = time.perf_counter()
    turn = 0
    tool_calls = 0
    stop_reason = "max_steps"
    final_answer = None

    while turn < max_steps:
        turn += 1
        t0 = time.perf_counter()
        try:
            reply = model.chat(messages, OLLAMA_TOOLS)
        except Exception as exc:  # noqa: BLE001 - recorded as the stop reason
            log("step", step=turn, error=f"{type(exc).__name__}: {exc}")
            stop_reason = "model_error"
            final_answer = f"Model error: {type(exc).__name__}: {exc}"
            break
        content = reply.get("content", "") or ""
        requested = reply.get("tool_calls") or []
        text_kind = None
        if not requested:
            text_kind, text_call = _classify_text(content)
            if text_kind == "tool_call_as_text":
                requested = [text_call]
        # One tool call per step, so the turn counter (and max_steps) counts tool work.
        # Extra calls the model batched into the same reply are logged and dropped;
        # the model can ask for them again on the next step.
        calls, ignored = requested[:1], requested[1:]
        log("step", step=turn, model_latency_ms=round((time.perf_counter() - t0) * 1000, 1),
            content=content, requested_tools=[c.get("name") for c in requested],
            ignored_tool_calls=[{"tool": c.get("name"), "inputs": c.get("arguments")} for c in ignored],
            text_guard=text_kind)

        if text_kind == "fabricated_tool_result":
            # The model wrote a tool result itself instead of calling the tool: not an answer.
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": "That is not a real tool result. Call the tool to get real "
                                                        "data, or answer in plain sentences from results you received."})
            continue

        if not calls:
            stop_reason = "completed"
            final_answer = content
            break

        call = calls[0]
        messages.append({"role": "assistant", "content": reply.get("content", ""),
                         "tool_calls": [{"function": {"name": call.get("name"), "arguments": call.get("arguments")}}]})
        tool_calls += 1
        result_json = executor(call.get("name"), call.get("arguments"))
        result = json.loads(result_json)
        is_blocked = (not result["ok"]) and str(result["error"]).startswith(SAFETY_ERROR_PREFIX)
        log("tool_call", step=turn, tool=call.get("name"), inputs=call.get("arguments"),
            result=result, safety_blocked=is_blocked)
        messages.append({"role": "tool", "content": result_json})
        if is_blocked:
            stop_reason = "safety_block"
            final_answer = f"I can't run that search. {result['error']}"
            break

    summary = {
        "run_id": log.run_id,
        "scenario": scenario,
        "model": model.name,
        "user_input": user_input,
        "steps": turn,
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
        "max_steps": max_steps,
        "final_answer": final_answer,
        "duration_s": round(time.perf_counter() - started, 2),
    }
    log("stop", **{k: v for k, v in summary.items() if k != "run_id"})
    return summary
