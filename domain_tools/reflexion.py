"""HW7 Part 3: bounded Reflexion on top of the hand-written run_agent (Part 2).

run_with_reflexion() runs one fixed task, checks it with the deterministic verifier
(domain_tools.fixed_tasks.verify), and on failure writes ONE short reflection and retries:

  * at most MAX_RETRIES (2) retries after the first attempt
  * a hard tool-call budget and token budget shared by all attempts; run_agent stops at the budget
  * stop reason is always one of: success, budget_exhausted, human_review

Reflections:
  * are built from the verifier evidence (failed check + the relevant tool call / observation), not from
    the model's reasoning, so no hidden chain-of-thought is stored - only a concise "what went wrong"
    and a "revised strategy"
  * are stored per (user_id, run_id) and only that pair can read them back
  * are untrusted data: they are cleaned, length-limited, and passed to run_agent as a separate labelled
    user message (run_agent's `notes`). They never touch SYSTEM_PROMPT, the tool list, or execute_tool's
    safety rule, so a reflection cannot change instructions, permissions or safety gates.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agent import run_agent
from .execute import execute_tool
from .fixed_tasks import load_tasks, verify

MAX_RETRIES = 2
TOOL_BUDGET = 10  # tool calls for all attempts of one task together
TOKEN_BUDGET = 9000  # prompt + completion tokens for all attempts of one task together
MAX_REFLECTION_CHARS = 400

# What to do differently when a given verifier check fails (kept short on purpose).
STRATEGY = {
    "searched_campbell": "Start by calling search_listings with query 'Campbell'.",
    "looked_up_first_result": "After the search, call get_listing with the FIRST listing_code from that result "
    "before answering; do not answer from the search result alone.",
    "answer_names_first_code": "Write the exact listing code (LST-xxxxx) of the first result in the answer.",
    "stats_for_landlord": "Call landlord_portfolio_stats with landlord_id 12 first.",
    "searched_for_example": "Then call search_listings with query 'San Jose' and limit 20 to find an example.",
    "answer_has_listing_count": "Quote the listing_count from the landlord_portfolio_stats result exactly.",
    "answer_has_example_of_landlord": "Choose a search result whose landlord_id is 12 and quote its exact listing "
    "code; never make up a code that no tool returned.",
    "searched_parking": "Start by calling search_listings with query 'parking'.",
    "looked_up_both": "Call get_listing two separate times, once for each of the first two codes from the search, "
    "before answering.",
    "answer_names_both": "Write both exact listing codes in the answer.",
    "stopped_early": "Finish the tool chain and then give a short final answer.",
}
_INJECTION_LIKE = re.compile(r"(ignore|override|disregard).{0,40}(instruction|system|rule|prompt)", re.I)


@dataclass
class Reflection:
    user_id: str
    run_id: str
    task: str
    attempt: int
    evidence: list[str]
    what_went_wrong: str
    revised_strategy: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def as_note(self) -> str:
        return clean(f"Attempt {self.attempt} failed: {self.what_went_wrong} Better: {self.revised_strategy}")


def clean(text: str) -> str:
    """Reflections are untrusted: one line, no control characters, no instruction-override phrases, capped."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = _INJECTION_LIKE.sub("[removed]", text)
    return " ".join(text.split())[:MAX_REFLECTION_CHARS]


class ReflectionStore:
    """In-memory store keyed by (user_id, run_id); optional JSONL copy for the report evidence."""

    def __init__(self, path: Path | None = None):
        self._items: dict[tuple[str, str], list[Reflection]] = {}
        self.path = path

    def add(self, r: Reflection) -> None:
        self._items.setdefault((r.user_id, r.run_id), []).append(r)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(r)) + "\n")

    def get(self, user_id: str, run_id: str) -> list[Reflection]:
        return list(self._items.get((user_id, run_id), []))


def write_reflection(user_id: str, run_id: str, task: str, attempt: int, summary: dict, verdict: dict) -> Reflection:
    failed = [c for c in verdict["checks"] if not c["passed"]]
    evidence = [f"verifier check '{c['check']}' failed: {c['detail']}" for c in failed]
    if summary["tool_log"]:
        last = summary["tool_log"][-1]
        evidence.append(f"last tool call: {last['tool']}({json.dumps(last['inputs'], default=str)}) ok={last['ok']}")
    evidence.append(f"stop_reason={summary['stop_reason']}, tool_calls={summary['tool_calls']}")
    names = [c["check"] for c in failed] or ["stopped_early"]
    wrong = "; ".join(f"{c['check'].replace('_', ' ')} was not satisfied" for c in failed) or (
        f"the run stopped with {summary['stop_reason']}"
    )
    if verdict["failure_kinds"]:
        wrong += f" (failure type: {', '.join(verdict['failure_kinds'])})"
    strategy = " ".join(STRATEGY.get(n, STRATEGY["stopped_early"]) for n in names)
    return Reflection(user_id, run_id, task, attempt, [clean(e) for e in evidence], clean(wrong + "."), clean(strategy))


def run_with_reflexion(
    task_id: str,
    model,
    repo,
    *,
    user_id: str,
    run_id: str,
    store: ReflectionStore,
    max_retries: int = MAX_RETRIES,
    tool_budget: int = TOOL_BUDGET,
    token_budget: int = TOKEN_BUDGET,
    max_steps: int = 8,
    log_path: Path | None = None,
    on_event: Callable[[str], None] | None = None,
    executor: Callable = execute_tool,
) -> dict:
    say = on_event or (lambda _line: None)
    prompt = load_tasks()["tasks"][task_id]["prompt"]
    started = time.perf_counter()
    used_tools = used_tokens = 0
    attempts = []
    stop_reason = "human_review"
    for attempt in range(1 + max_retries):
        left_tools, left_tokens = tool_budget - used_tools, token_budget - used_tokens
        if left_tools <= 0 or left_tokens <= 0:
            stop_reason = "budget_exhausted"
            break
        notes = [r.as_note() for r in store.get(user_id, run_id)]
        if notes:
            say(f"  [reflexion] retry {attempt} with {len(notes)} stored reflection(s)")
        s = run_agent(
            prompt,
            model=model,
            max_steps=max_steps,
            log_path=log_path,
            scenario=f"{task_id}-reflexion",
            require_tool=True,
            tool_budget=left_tools,
            token_budget=left_tokens,
            notes=notes or None,
            on_event=on_event,
            executor=executor,
        )
        used_tools += s["tool_calls"]
        used_tokens += s["prompt_tokens"] + s["completion_tokens"]
        v = verify(task_id, s, repo)
        attempts.append({"attempt": attempt, "summary": s, "verdict": v})
        say(
            f"  [reflexion] attempt {attempt}: verifier {'PASS' if v['passed'] else 'FAIL'}, "
            f"stop={s['stop_reason']}, budget used {used_tools}/{tool_budget} tools, "
            f"{used_tokens}/{token_budget} tokens"
        )
        if v["passed"]:
            stop_reason = "success"
            break
        if s["stop_reason"] == "budget_exhausted" or used_tools >= tool_budget or used_tokens >= token_budget:
            stop_reason = "budget_exhausted"
            break
        if attempt == max_retries:
            stop_reason = "human_review"
            break
        r = write_reflection(user_id, run_id, task_id, attempt, s, v)
        store.add(r)
        say(f"  [reflection] wrong: {r.what_went_wrong}")
        say(f"  [reflection] strategy: {r.revised_strategy}")
    final = attempts[-1] if attempts else None
    return {
        "task": task_id,
        "user_id": user_id,
        "run_id": run_id,
        "stop_reason": stop_reason,
        "attempts": len(attempts),
        "retries": max(len(attempts) - 1, 0),
        "tool_calls": used_tools,
        "tokens": used_tokens,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "passed": bool(final and final["verdict"]["passed"]),
        "answer_correct": bool(final and final["verdict"]["answer_correct"]),
        "unsupported_claims": final["verdict"]["unsupported_claims"] if final else [],
        "final_answer": final["summary"]["final_answer"] if final else None,
        "attempt_details": attempts,
        "reflections": [asdict(r) for r in store.get(user_id, run_id)],
    }
