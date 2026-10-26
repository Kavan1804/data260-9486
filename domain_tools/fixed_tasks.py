"""HW7 Part 2/3: the three fixed verification tasks and a deterministic verifier.

verify(task_id, summary, repo) looks only at things that can be checked exactly:
  - which tools were called with which inputs (summary["tool_log"])
  - what those tools returned (the observations)
  - listing codes and numbers in the final answer
and compares them with the truth read from the repository (MySQL s9486_rel in real runs).

It returns:
  passed            - all strict checks passed (tool chain + answer)
  checks            - each check with passed/detail (this is the "evidence" a reflection quotes)
  answer_correct    - a looser, answer-only check (accepts "LST 00017", ignores which tools were used);
                      strict=False but answer_correct=True marks a possible verifier false rejection
  failure_kinds     - DOCX categories: malformed_arguments, unknown_tool, text_instead_of_tool, lost_chain
  unsupported_claims- listing codes / numbers in the answer that no tool observation or the prompt contains
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import config

TASKS_FILE = Path(config.ROOT) / "Homework7" / "fixtures" / "agent_tasks.json"
CODE_RE = re.compile(r"LST-\d{5}")
LOOSE_CODE_RE = re.compile(r"LST[\s_-]?(\d{5})", re.I)
NUMBER_RE = re.compile(r"\b\d{2,}\b")
# Raw failure kinds from run_agent -> the four DOCX categories (schema failures are bad arguments too).
CATEGORY = {
    "malformed_arguments": "malformed_arguments",
    "schema_validation": "malformed_arguments",
    "unknown_tool": "unknown_tool",
    "text_instead_of_tool": "text_instead_of_tool",
}


def load_tasks() -> dict:
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def _codes(text: str) -> set[str]:
    return set(CODE_RE.findall((text or "").upper()))


def _loose_codes(text: str) -> set[str]:
    return {f"LST-{d}" for d in LOOSE_CODE_RE.findall(text or "")}


def _numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall((text or "").replace(",", "")))


def _all_ints(text: str) -> set[str]:
    """Every whole number in the text (also 1-digit ones), for comparing a count with the truth."""
    return set(re.findall(r"\b\d+\b", (text or "").replace(",", "")))


def _calls(summary: dict, tool: str, ok_only: bool = True) -> list[dict]:
    return [t for t in summary.get("tool_log", []) if t["tool"] == tool and (t["ok"] or not ok_only)]


def _arg(call: dict, key: str) -> str:
    inputs = call.get("inputs")
    if isinstance(inputs, str):
        try:
            inputs = json.loads(inputs)
        except json.JSONDecodeError:
            return ""
    return str((inputs or {}).get(key, ""))


def _first_search(summary: dict, query: str) -> list[dict]:
    for c in _calls(summary, "search_listings"):
        if query.lower() in _arg(c, "query").lower():
            return c["observation"]["data"]["listings"]
    return []


def unsupported_claims(summary: dict) -> list[str]:
    """Codes and 2+ digit numbers in the answer that appear in no tool observation and not in the prompt."""
    seen = json.dumps([t["observation"] for t in summary.get("tool_log", [])], default=str).replace(",", "")
    seen += " " + summary.get("user_input", "")
    answer = summary.get("final_answer") or ""
    claims = sorted(_codes(answer)) + sorted(_numbers(answer) - _numbers(" ".join(_codes(answer))))
    return [c for c in claims if c not in seen.upper() and c not in seen]


def verify(task_id: str, summary: dict, repo) -> dict:
    task = load_tasks()["tasks"][task_id]
    answer = summary.get("final_answer") or ""
    checks: list[tuple[str, bool, str]] = []

    if task_id == "A":
        listings = _first_search(summary, task["search_query"])
        first = listings[0]["listing_code"] if listings else None
        truth = repo.search(task["search_query"], 5, 0)[0]["listing_code"]
        looked = [_arg(c, "listing_code").upper() for c in _calls(summary, "get_listing")]
        checks += [
            (
                "searched_campbell",
                bool(listings),
                f"search_listings(query~'{task['search_query']}') results: {[x['listing_code'] for x in listings]}",
            ),
            ("looked_up_first_result", first is not None and first in looked, f"first={first}, get_listing={looked}"),
            (
                "answer_names_first_code",
                first is not None and first in _codes(answer),
                f"answer codes={sorted(_codes(answer))}",
            ),
        ]
        answer_correct = truth in _loose_codes(answer)
    elif task_id == "B":
        lid = task["landlord_id"]
        stats = repo.landlord_stats(lid)
        stat_calls = [c for c in _calls(summary, "landlord_portfolio_stats") if _arg(c, "landlord_id") == str(lid)]
        example_codes = [c for c in _codes(answer) if (repo.get_by_code(c) or {}).get("landlord_id") == lid]
        loose_examples = [c for c in _loose_codes(answer) if (repo.get_by_code(c) or {}).get("landlord_id") == lid]
        checks += [
            (
                "stats_for_landlord",
                bool(stat_calls),
                f"landlord_portfolio_stats(landlord_id={lid}) calls ok: {len(stat_calls)}",
            ),
            ("searched_for_example", bool(_calls(summary, "search_listings")), "search_listings called"),
            (
                "answer_has_listing_count",
                str(stats["listing_count"]) in _all_ints(answer),
                f"truth listing_count={stats['listing_count']}, answer numbers={sorted(_numbers(answer))}",
            ),
            (
                "answer_has_example_of_landlord",
                bool(example_codes),
                f"answer codes={sorted(_codes(answer))}, owned by landlord {lid}: {example_codes}",
            ),
        ]
        answer_correct = str(stats["listing_count"]) in _all_ints(answer) and bool(loose_examples)
    elif task_id == "C":
        listings = _first_search(summary, task["search_query"])
        first_two = [x["listing_code"] for x in listings[:2]]
        truth_two = [x["listing_code"] for x in repo.search(task["search_query"], 5, 0)[:2]]
        looked = [_arg(c, "listing_code").upper() for c in _calls(summary, "get_listing")]
        checks += [
            ("searched_parking", bool(listings), f"search results: {[x['listing_code'] for x in listings]}"),
            (
                "looked_up_both",
                len(first_two) == 2 and all(c in looked for c in first_two),
                f"first two={first_two}, get_listing={looked}",
            ),
            (
                "answer_names_both",
                len(first_two) == 2 and set(first_two) <= _codes(answer),
                f"answer codes={sorted(_codes(answer))}",
            ),
        ]
        answer_correct = set(truth_two) <= _loose_codes(answer)
    else:
        raise ValueError(f"unknown task {task_id}")

    passed = all(ok for _, ok, _ in checks) and summary.get("stop_reason") == "completed"
    kinds = sorted({CATEGORY[f["kind"]] for f in summary.get("failures", []) if f["kind"] in CATEGORY})
    # Lost multi-step chain: the model gave a final answer but skipped part of the required tool chain.
    chain_checks = [ok for name, ok, _ in checks if not name.startswith("answer_")]
    if summary.get("stop_reason") == "completed" and not all(chain_checks):
        kinds.append("lost_chain")
    return {
        "task": task_id,
        "passed": passed,
        "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks],
        "answer_correct": answer_correct,
        "failure_kinds": kinds,
        "unsupported_claims": unsupported_claims(summary),
    }


def verify_error_recovery(summary: dict) -> dict:
    """The nonexistent-ID case passes when get_listing ran, returned ok=false, and the agent still answered."""
    calls = [t for t in summary.get("tool_log", []) if t["tool"] == "get_listing"]
    tool_failed_cleanly = bool(calls) and not calls[-1]["ok"] and bool(calls[-1]["error"])
    answered = summary.get("stop_reason") == "completed" and bool((summary.get("final_answer") or "").strip())
    return {
        "passed": tool_failed_cleanly and answered,
        "tool_error": calls[-1]["error"] if calls else None,
        "stop_reason": summary.get("stop_reason"),
        "answer": summary.get("final_answer"),
    }
