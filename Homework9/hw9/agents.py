"""HW9 Part 4: Answering Agent + Evaluator Agent, reusable lessons, and the four system variants.

Communication: the two agents run in one process and pass plain dicts (no shared state):
    AnsweringAgent.answer(question, lessons, feedback) -> {"answer", "lessons_used", "seconds", ...}
    EvaluatorAgent.evaluate(qid, answer)               -> {"result": PASS|REVISE, "explanation", "feedback", "tags"}
run_question() is the loop between them: at most 2 answer attempts, then it stops and reports the final result.

Answering Agent = llama3.2:3b through the HW8 adapter (kafka_agents/llm.py MODEL) + its own MySQL lookup of the
                   listing record, plus a get_landlord tool it may call (Ollama tool calling).
Evaluator Agent  = rule checks against reference_data.json only (it never sees the database), so PASS/REVISE is
                   the same every time for the same answer.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

from hw9.common import DATA, log

LESSONS_FILE = DATA / "lessons.json"
REFERENCE_FILE = DATA / "reference_data.json"
MAX_ATTEMPTS = 2
CODE = re.compile(r"\bLST-\d{5}\b")

# ---------------------------------------------------------------- Answering Agent

ANSWER_SYSTEM = (
    "You are the Answering Agent of a rental-housing helper for SJSU students. Answer the student's question in "
    "one or two sentences using the listing record you are given. You can call the get_landlord tool."
)
LANDLORD_TOOL = {
    "type": "function",
    "function": {
        "name": "get_landlord",
        "description": "Look up a landlord in the s9486_rel landlords table by landlord_id.",
        "parameters": {
            "type": "object",
            "properties": {"landlord_id": {"type": "integer", "description": "landlord_id from the listing record"}},
            "required": ["landlord_id"],
        },
    },
}
MAX_TOOL_ROUNDS = 2


def question_topics(question: str) -> set[str]:
    """What a question is about, from its wording only (the Answering Agent cannot see the reference data).
    Used to pick which lessons are relevant."""
    q = question.lower()
    topics = set()
    if re.search(r"\bunits?\b|vacan|open unit|available", q):
        topics.add("units")
    if re.search(r"landlord|manages listing|which person|who manages|contact", q):
        topics.add("landlord")
    if re.search(r"compan|management", q):
        topics.add("company")
    if re.search(r"\bcity\b|located|which town", q):
        topics.add("city")
    if re.search(r"address|street|where exactly", q):
        topics.add("address")
    if re.search(r"kind of home|type of (home|place)|bedroom", q):
        topics.add("home_type")
    if re.search(r"rent\b|cost|charge|deposit|fee|lease length|utilities|per month|each month", q):
        topics.add("money_or_terms")
    return topics or {"other"}


class AnsweringAgent:
    """llama3.2:3b with the listing record as my HW4 API returns it (ListingOut: landlord_id, no landlord name)
    and one tool, get_landlord(landlord_id). The model decides itself whether to call the tool."""

    def __init__(self, store, chat=None):
        self.store = store  # ListingDatabaseWithCache (MySQL lookups)
        if chat is None:
            from kafka_agents.llm import MODEL  # the HW8 adapter (OllamaModel, llama3.2:3b, seed 9486)

            chat = MODEL.chat
        self.chat = chat

    def lookup(self, question: str) -> str:
        """The agent's retrieval: the listings row for each LST code in the question (ListingOut fields)."""
        codes = sorted(set(CODE.findall(question.upper())))
        if not codes:
            return "No listing code was given in the question."
        parts = []
        for code in codes:
            f = self.store.get_listing(code)
            if f is None:
                parts.append(f"{code}: no listing with this code exists in the database.")
            else:
                keys = ("id", "listing_code", "title", "address", "available_units", "landlord_id")
                parts.append(json.dumps({k: f[k] for k in keys}))
        return "\n".join(parts)

    def get_landlord(self, landlord_id) -> dict:
        try:
            row = self.store.get_landlord(int(landlord_id))
        except (TypeError, ValueError):  # the model sometimes passes "null" when there is no listing
            return {"error": f"landlord_id must be a number, got {landlord_id!r}"}
        return row or {"error": f"no landlord with id {landlord_id}"}

    def answer(self, question: str, lessons: list[dict] | None = None, feedback: dict | None = None) -> dict:
        system = ANSWER_SYSTEM
        if lessons:
            system += "\n\nLessons from earlier mistakes (follow them):\n" + "\n".join(
                f"- {lesson['correction']}" for lesson in lessons
            )
        user = f"Question: {question}\n\nListing record from the s9486_rel database:\n{self.lookup(question)}"
        if feedback:
            user += (
                f"\n\nYour previous answer was: {feedback['previous_answer']}\n"
                f"The Evaluator Agent said REVISE: {feedback['feedback']}\nWrite a corrected answer."
            )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        start = time.perf_counter()
        tools_called = []
        reply = self.chat(messages, tools=[LANDLORD_TOOL])
        for _ in range(MAX_TOOL_ROUNDS):
            calls = [c for c in reply.get("tool_calls") or [] if c.get("name") == "get_landlord"]
            if not calls:
                break
            for c in calls:
                result = self.get_landlord((c.get("arguments") or {}).get("landlord_id", 0))
                tools_called.append({"tool": "get_landlord", "arguments": c.get("arguments"), "result": result})
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.get("content") or "",
                        "tool_calls": [{"function": {"name": c["name"], "arguments": c.get("arguments") or {}}}],
                    }
                )
                messages.append({"role": "tool", "content": json.dumps(result)})
            reply = self.chat(messages, tools=[LANDLORD_TOOL])
        return {
            "answer": (reply.get("content") or "").strip(),
            "seconds": round(time.perf_counter() - start, 2),
            "lessons_used": [lesson["lesson_id"] for lesson in lessons or []],
            "tools_called": tools_called,
        }


# ---------------------------------------------------------------- Evaluator Agent

# "not explicitly stated", "not directly provided", "isn't mentioned" ... (added after training question tr04 was
# marked REVISE for "not explicitly stated in the provided listing data", which is a correct answer)
NOT_RECORDED_RE = re.compile(
    r"\b(not|n't|no)\s+(\w+\s+)?(stated|listed|provided|included|specified|mentioned|available|given|recorded|"
    r"shown|indicated|found|contain|contained|include|specify|mention|list)\b"
)
NOT_RECORDED_PHRASES = (
    "not listed",
    "not available",
    "not provided",
    "not included",
    "not specified",
    "not mentioned",
    "no information",
    "doesn't include",
    "does not include",
    "doesn't have",
    "does not have",
    "don't have",
    "do not have",
    "unknown",
    "not in the",
    "isn't listed",
    "is not listed",
    "not recorded",
    "doesn't list",
    "does not list",
    "not given",
    "doesn't mention",
    "does not mention",
    "doesn't specify",
    "does not specify",
    "not stated",
    "unable to",
    "can't find",
    "cannot find",
    "no data",
    "not shown",
    "isn't provided",
    "isn't available",
    "isn't included",
)
NOT_FOUND_PHRASES = (
    "no listing",
    "not exist",
    "doesn't exist",
    "does not exist",
    "not found",
    "couldn't find",
    "could not find",
    "can't find",
    "cannot find",
    "no record",
    "isn't a listing",
    "is not a listing",
    "not in the database",
    "no such listing",
    "unable to find",
)
NUMBER_WORDS = {0: ("0", "zero", "no units", "none"), 1: ("1", "one"), 2: ("2", "two"), 3: ("3", "three")}
STREET_ABBR = {"st": "street", "ave": "avenue", "blvd": "boulevard", "rd": "road", "dr": "drive"}
HOME_TYPES = ("apartment", "house", "condo", "loft", "townhouse", "studio")
NOT_RECORDED_ASKS = {"rent", "deposit", "application_fee", "lease_length", "utilities"}

# failure tag -> (failure_pattern, correction) used when a repeated failure becomes a lesson
LESSON_TEXT = {
    "missing_fact:landlord": (
        "The answer does not give the landlord's full name.",
        "The listing record only has landlord_id. When the question asks who the landlord is or who manages a "
        "listing, call get_landlord with that landlord_id and give the full_name it returns.",
    ),
    "missing_fact:company": (
        "The answer does not name the landlord's property company.",
        "The listing record only has landlord_id. For the management company, call get_landlord with that "
        "landlord_id and give the company it returns, exactly as written.",
    ),
    "missing_fact:units": (
        "The answer omits the number of available units.",
        "When the question asks about available or open units, state the available_units number from the listing.",
    ),
    "missing_fact:city": (
        "The answer does not name the listing's city.",
        "For city questions, give the city from the address (the part after the street).",
    ),
    "missing_fact:address": (
        "The answer does not give the full street address.",
        "For address questions, copy the street address exactly as in the address field.",
    ),
    "missing_fact:home_type": (
        "The answer does not give the bedroom count and type of home.",
        "For 'what kind of home' questions, give the bedroom count and the home type from the title.",
    ),
    "unsupported_claim": (
        "The answer gives a price, fee or term that is not in the listing data.",
        "Rent, deposit, fees, lease length and utilities are not in the listing data. Never estimate them; say the "
        "listing data does not include that information.",
    ),
    "missing_not_recorded": (
        "The answer does not say that the asked field is missing from the data.",
        "If the listing data has no field for what was asked, say clearly that the listing data does not include it.",
    ),
    "invented_listing": (
        "The answer describes a listing code that does not exist.",
        "If the listing data says the code does not exist, say that no listing with that code was found.",
    ),
}


def _norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return " ".join(STREET_ABBR.get(w, w) for w in s.split())


class EvaluatorAgent:
    def __init__(self, reference_path: Path = REFERENCE_FILE):
        self.ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))

    def evaluate(self, qid: str, answer: str) -> dict:
        q = self.ref["questions"][qid]
        code, asks = q["listing_code"], q["asks"]
        a = answer.lower()
        problems: list[tuple[str, str]] = []  # (tag, feedback sentence)

        if asks == ["missing"]:
            if not any(p in a for p in NOT_FOUND_PHRASES):
                problems.append(
                    ("invented_listing", f"{code} does not exist in the reference data; say no listing was found.")
                )
        elif set(asks) & NOT_RECORDED_ASKS:
            field = asks[0].replace("_", " ")
            if re.search(r"\$\s?\d|\d[\d,]*\s?(dollars|usd|per month|/month|a month|months?\b)", a):
                problems.append(
                    ("unsupported_claim", f"The {field} is not in the listing data, but the answer gives a value.")
                )
            if not (any(p in a for p in NOT_RECORDED_PHRASES) or NOT_RECORDED_RE.search(a)):
                problems.append(("missing_not_recorded", f"Say that the listing data does not include the {field}."))
        else:
            f = self.ref["listings"][code]
            for ask in asks:
                if ask == "units":
                    words = NUMBER_WORDS.get(f["available_units"], (str(f["available_units"]),))
                    if not any(re.search(rf"\b{re.escape(w)}\b", a) for w in words):
                        problems.append(("missing_fact:units", f"State the available units: {f['available_units']}."))
                elif ask == "landlord":
                    if f["landlord_name"].lower() not in a:
                        problems.append(("missing_fact:landlord", f"The landlord is {f['landlord_name']}."))
                elif ask == "company":
                    if _norm(f["landlord_company"]) not in _norm(answer):
                        problems.append(("missing_fact:company", f"The company is {f['landlord_company']}."))
                elif ask == "city":
                    if f["city"].lower() not in a:
                        problems.append(("missing_fact:city", f"The listing is in {f['city']}."))
                elif ask == "address":
                    street = f["address"].split(",")[0]
                    if _norm(street) not in _norm(answer):
                        problems.append(("missing_fact:address", f"The street address is {street}."))
                elif ask == "home_type":
                    title = f["title"].lower()
                    kind = next((t for t in HOME_TYPES if t in title), "")
                    beds = re.search(r"(\d)br", title)
                    ok_kind = kind in a
                    ok_beds = True
                    if beds:
                        n = beds.group(1)
                        word = {"1": "one", "2": "two", "3": "three", "4": "four"}[n]
                        ok_beds = bool(re.search(rf"\b({n}\s?-?\s?(br|bed|bedroom)|{word}[ -]bedroom)", a))
                    if not (ok_kind and ok_beds):
                        problems.append(("missing_fact:home_type", f"The title says: {f['title']}."))
            for other in set(CODE.findall(answer.upper())) - {code}:
                problems.append(("wrong_listing", f"The answer mentions {other}, but the question is about {code}."))

        if not problems:
            return {
                "result": "PASS",
                "explanation": "All facts the question asks for match the reference data.",
                "feedback": "",
                "tags": [],
            }
        return {
            "result": "REVISE",
            "explanation": "; ".join(sorted({t for t, _ in problems})),
            "feedback": " ".join(msg for _, msg in problems),
            "tags": sorted({t for t, _ in problems}),
        }


# ---------------------------------------------------------------- lessons


class LessonStore:
    """lessons.json: a list of {lesson_id, failure_pattern, correction, created_at, use_count, ...}.
    Extra fields: tag (evaluator failure tag), applies_to (question topics), status (candidate/kept/rejected),
    source (which training questions failed), validation (before/after numbers)."""

    def __init__(self, path: Path = LESSONS_FILE, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        self.lessons: list[dict] = json.loads(self.path.read_text()) if self.path.exists() else []

    def save(self) -> None:
        if not self.read_only:
            self.path.write_text(json.dumps(self.lessons, indent=2) + "\n", encoding="utf-8")

    def create(self, tag: str, topics: set[str], source: list[str]) -> dict:
        pattern, correction = LESSON_TEXT[tag]
        lesson = {
            "lesson_id": f"lesson_{len(self.lessons) + 1:03d}",
            "failure_pattern": pattern,
            "correction": correction,
            "created_at": date.today().isoformat(),
            "use_count": 0,
            "tag": tag,
            "applies_to": sorted(topics),
            "status": "candidate",
            "source": source,
        }
        self.lessons.append(lesson)
        self.save()
        return lesson

    def relevant(self, question: str, statuses: tuple[str, ...]) -> list[dict]:
        topics = question_topics(question)
        return [x for x in self.lessons if x["status"] in statuses and topics & set(x["applies_to"])]

    def mark_used(self, lessons: list[dict]) -> None:
        for lesson in lessons:
            lesson["use_count"] += 1
        if lessons:
            self.save()


GUARDED_TAGS = {"unsupported_claim", "invented_listing"}


def gate_decision(before: dict[str, dict], after: dict[str, dict]) -> dict:
    """Part 4.3 rule. before/after map question id -> {"result": PASS|REVISE, "tags": [...]} on the validation set.
    Keep the lesson only if failures do not go up, nothing that passed now fails, and no question gets a new
    made-up value / invented listing."""
    failing_before = sorted(k for k, v in before.items() if v["result"] != "PASS")
    failing_after = sorted(k for k, v in after.items() if v["result"] != "PASS")
    broke = sorted(k for k, v in before.items() if v["result"] == "PASS" and after[k]["result"] != "PASS")
    new_bad = sorted(
        k for k, v in after.items() if set(v["tags"]) & GUARDED_TAGS and not set(before[k]["tags"]) & GUARDED_TAGS
    )
    keep = len(failing_after) <= len(failing_before) and not broke and not new_bad
    return {
        "failing_before": failing_before,
        "failing_after": failing_after,
        "previously_correct_now_wrong": broke,
        "new_unsupported_answers": new_bad,
        "decision": "kept" if keep else "rejected",
    }


# ---------------------------------------------------------------- the loop + variants

VARIANTS = {
    # name: (max attempts, which lesson statuses are loaded)
    "baseline": (1, ()),
    "evaluator_repair": (MAX_ATTEMPTS, ()),
    "lesson_memory": (MAX_ATTEMPTS, ("candidate", "kept", "rejected")),  # every saved lesson, no validation
    "validated_improvement": (MAX_ATTEMPTS, ("kept",)),  # only lessons that passed validation
}


def run_question(
    qid: str,
    question: str,
    answerer: AnsweringAgent,
    evaluator: EvaluatorAgent,
    max_attempts: int = MAX_ATTEMPTS,
    lessons: LessonStore | None = None,
    statuses: tuple[str, ...] = (),
    forced_first_answer: str | None = None,
    quiet: bool = False,
) -> dict:
    """Answer -> evaluate -> (revise -> evaluate). Stops after max_attempts (never more than 2)."""
    max_attempts = min(max_attempts, MAX_ATTEMPTS)
    start = time.perf_counter()
    loaded = lessons.relevant(question, statuses) if (lessons and statuses) else []
    if loaded and lessons:
        lessons.mark_used(loaded)
        if not quiet:
            log("answering", f"{qid} loaded lessons {[x['lesson_id'] for x in loaded]}")
    attempts = []
    feedback = None
    for attempt in range(1, max_attempts + 1):
        if attempt == 1 and forced_first_answer is not None:
            out = {"answer": forced_first_answer, "seconds": 0.0, "lessons_used": [], "controlled": True}
        else:
            out = answerer.answer(question, loaded, feedback)
        verdict = evaluator.evaluate(qid, out["answer"])
        attempts.append({"attempt": attempt, **out, "evaluation": verdict})
        if not quiet:
            log("evaluator", f"{qid} attempt {attempt}: {verdict['result']} {verdict['explanation']}")
        if verdict["result"] == "PASS":
            break
        feedback = {"previous_answer": out["answer"], "feedback": verdict["feedback"]}
    final = attempts[-1]
    return {
        "id": qid,
        "question": question,
        "final_answer": final["answer"],
        "final_result": final["evaluation"]["result"],
        "attempts": len(attempts),
        "lessons_loaded": [x["lesson_id"] for x in loaded],
        "latency_s": round(time.perf_counter() - start, 2),
        "history": attempts,
    }
