

import argparse, json, os, re, sys, time
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Optional: students can expand/modify this
STOP = {
    "the", "and", "for", "that", "with", "this", "from", "into", "than", "your", "you",
    "are", "was", "were", "have", "has", "had", "use", "used", "using", "about", "how",
    "can", "will", "more", "less", "very", "over", "under", "their", "there", "then",
    "our", "out", "on", "in", "of", "to", "by", "a", "an", "is", "it", "as",
}

STOP.update({
    "help", "helps", "remain", "remains", "occur", "occurs",
    "when", "while", "also", "through",
})


# -------------------------
# Text cleanup + extraction
# -------------------------

def strip_code_and_md(s: str) -> str:
    text = str(s)
    text = re.sub(r"```(?:json)?\s*(.*?)```", r"\1", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("`", "")
    text = re.sub(r"^\s*(?:#{1,6}|[-*+])\s*", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def extract_json_block(text: str) -> str:
    cleaned = strip_code_and_md(text)
    decoder = json.JSONDecoder()

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(obj, dict):
                return json.dumps(obj)
        except json.JSONDecodeError:
            continue

    return json.dumps({"message": cleaned})




def tokens(txt: str) -> List[str]:
    words = re.findall(r"[a-z]+(?:-[a-z]+)*", str(txt).lower())
    return [word for word in words if len(word) > 1 and word not in STOP]


def ngrams(words: List[str], n: int) -> Iterable[Tuple[str, ...]]:
    """
    TODO: Yield word n-grams from a token list.
    """
    for i in range(max(0, len(words) - n + 1)):
        yield tuple(words[i:i + n])


def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    def raw_words(text: str) -> List[str]:
        return re.findall(r"[a-z]+(?:-[a-z]+)*", str(text).lower())

    results = []

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        if candidate and candidate not in results:
            results.append(candidate)

    title_words = [word for word in raw_words(title) if word not in STOP]
    if 2 <= len(title_words) <= 4:
        add(" ".join(title_words))

    for text in (title, content):
        words = raw_words(text)
        for size in (2, 3):
            for group in ngrams(words, size):
                if all(word not in STOP and len(word) > 1 for word in group):
                    add(" ".join(group))

    ranked_words = Counter(tokens(title + " " + content)).most_common()
    for word, _ in ranked_words:
        add(word)

    return results[:maxn]


# -------------------------
# Output schema coercion
# -------------------------

def coerce_reply(raw_obj: Any, title: str, content: str, strict: bool) -> Dict[str, Any]:
    obj = raw_obj if isinstance(raw_obj, dict) else {}
    data = obj.get("data")
    data = data if isinstance(data, dict) else {}

    def limit_words(value: Any, limit: int) -> str:
        cleaned = strip_code_and_md(str(value or ""))
        return " ".join(cleaned.split()[:limit])

    thought = limit_words(obj.get("thought", ""), 40)

    message = limit_words(obj.get("message", ""), 60)
    if not message:
        message = "Proposal reviewed; tags and summary prepared."

    candidates = phrase_candidates(title, content)
    candidate_lookup = {candidate.lower(): candidate for candidate in candidates}

    supplied_tags = data.get("tags", [])
    if not isinstance(supplied_tags, list):
        supplied_tags = []

    valid_tags = []
    for tag in supplied_tags:
        cleaned = strip_code_and_md(str(tag)).lower().strip(".,;:!?")
        if cleaned in candidate_lookup and cleaned not in valid_tags:
            valid_tags.append(cleaned)

    ordered = []
    if strict:
        ordered.extend(tag for tag in valid_tags if " " in tag)
        ordered.extend(tag for tag in candidates if " " in tag)

    ordered.extend(valid_tags)
    ordered.extend(candidates)

    tags = []

    for tag in ordered:
        normalized = tag.lower().strip()
        if not normalized or normalized in tags:
            continue

        candidate_words = set(normalized.split())
        too_similar = False

        for selected in tags:
            selected_words = set(selected.split())
            overlap = len(candidate_words & selected_words)
            smaller = min(len(candidate_words), len(selected_words))

            if smaller and overlap / smaller >= 0.67:
                too_similar = True
                break

        if not too_similar:
            tags.append(normalized)

        if len(tags) == 3:
            break

    for tag in ordered:
        normalized = tag.lower().strip()
        if len(tags) == 3:
            break
        if normalized and normalized not in tags:
            tags.append(normalized)

    while len(tags) < 3:
        fallback = tokens(title + " " + content)
        tag = fallback[len(tags) % len(fallback)] if fallback else "topic"
        tags.append(tag)

    summary = limit_words(data.get("summary", ""), 25)
    if not summary:
        summary = limit_words(content, 25) or limit_words(title, 25) or "Summary unavailable"

    summary = summary.replace("...", "")
    summary = summary.rstrip(".!?") + "."

    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        raw_issues = [raw_issues]

    issues = [
        limit_words(issue, 30)
        for issue in raw_issues
        if limit_words(issue, 30)
    ]

    return {
        "thought": thought,
        "message": message,
        "data": {
            "tags": tags[:3],
            "summary": summary,
            "issues": issues,
        },
    }


def parse_and_coerce(text: str, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """
    TODO:
      - extract_json_block()
      - json.loads()
      - coerce_reply()
      - handle JSON parse failures gracefully
    """
    try:
        obj = json.loads(extract_json_block(text))
    except Exception:
        obj = {"message": strip_code_and_md(text)}
    return coerce_reply(obj, title, content, strict)


# -------------------------
# Agent wrapper
# -------------------------

@dataclass
class SimpleAgent:
    name: str
    system: str
    model: Any  # LangChain ChatModel

    def respond(
    self,
    conversation: List[Dict[str, str]],
    task: str,
    title: str,
    content: str,
    strict: bool,
    ) -> Dict[str, Any]:
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system),
            (
            "human",
            "Task:\n{task}\n\n"
            "Title:\n{title}\n\n"
            "Content:\n{content}\n\n"
            "Conversation so far:\n{history}\n\n"
            "Allowed tag candidates:\n{candidates}\n\n"
            "Strict mode: {strict}\n\n"
            "Return only one JSON object. Do not use markdown or code fences. "
            "Include thought, message, and data. "
            "Data must contain exactly three tags, a summary of at most "
            "25 words, and an issues array. Select tags only from the allowed "
            "candidates. Keep message at or below 60 words."
        ),
    ])

        history_text = "\n".join(
            f'{message["role"]}: {message["content"]}'
            for message in conversation
            ) or "(empty)"

        chain = prompt | self.model | StrOutputParser()

        raw = chain.invoke({
            "task": task,
            "title": title,
            "content": content,
            "history": history_text,
            "candidates": ", ".join(phrase_candidates(title, content)),
            "strict": strict,
        })

        return parse_and_coerce(raw, title, content, strict)


# -------------------------
# CLI entrypoint
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Your Blog Title Here")
    ap.add_argument("--content", default="Your blog post content goes here.")
    ap.add_argument("--email", default="student@example.com")
    ap.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:4b"))
    ap.add_argument("--base_url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    # Initialize Ollama chat model (students can adjust params)
    try:
        llm = ChatOllama(
            model=args.model,
            temperature=0.0,
            base_url=args.base_url,
            reasoning=False,
            num_predict=256,
            num_ctx=2048,
            format="json",  # asks Ollama to produce JSON when supported
        )
    except Exception:
        print(
            "Failed to initialize ChatOllama. Is Ollama running and the model available?\n"
            "Try: `ollama serve` and `ollama pull <your-model-tag>`.",
            file=sys.stderr,
        )
        raise

    # Define three agents (Planner -> Reviewer -> Finalizer)
    planner = SimpleAgent(
        name="Planner",
        system="Propose exactly 3 distinct, topical tags (prefer multi-word phrases) and a one-line summary for the blog post.",
        model=llm,
    )
    reviewer = SimpleAgent(
        name="Reviewer",
        system=(
            "Validate: tags topical and not generic; summary ≤ 25 words; no code or markdown. "
            "If issues, list in data.issues; otherwise echo cleaned tags/summary."
        ),
        model=llm,
    )
    finalizer = SimpleAgent(
        name="Finalizer",
        system=(
            "Use reviewer feedback to finalize. Output exactly 3 tags in data.tags and the final summary in data.summary. "
            "Set data.issues to []."
        ),
        model=llm,
    )

    task = (
        f'Given blog title "{args.title}" and content "{args.content}", produce exactly 3 topical tags '
        f'and a one-sentence summary in your own words. Email is {args.email}.'
    )

    transcript: List[Dict[str, str]] = []

    # Planner
    t0 = time.time()
    a = planner.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Planner", "content": json.dumps(a)})
    print(f"\n--- Planner ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(a, indent=2)}")

    # Reviewer
    t0 = time.time()
    b = reviewer.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Reviewer", "content": json.dumps(b)})
    print(f"\n--- Reviewer ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(b, indent=2)}")

    # Finalizer
    final = finalizer.respond(transcript, task, args.title, args.content, args.strict)
    print(f"\n Finalized Output \n{json.dumps(final, indent=2)}")

    # Publish package
    package = {
        "title": args.title,
        "email": args.email,
        "content": args.content,
        "agents": {"transcript": transcript, "final": final.get("data", {})},
        "submissionDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(f"\n Publish Package \n{json.dumps(package, indent=2)}")


if __name__ == "__main__":
    main()
