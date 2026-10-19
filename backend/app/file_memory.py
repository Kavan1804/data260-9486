"""HW6 Part 4: file-based memory with AGENT.md (instructions) and MEMORY.md (facts).

MEMORY.md fact lines look like
    - [user.budget] Budget is $2,400 per month (seen: 2026-10-01, source: user)
The key in brackets is what lets consolidation tell a duplicate (same key, same
text) from a contradiction (same key, different text).

Consolidation is deterministic, so it can be checked:
  * duplicates   - merged into one line with "merged: N"
  * contradictions - newest "seen" date wins; the losing value is written to
                   "## Resolved contradictions" (never silently dropped)
  * review flags - a resolution is flagged in "## Needs review" when the rule is
                   probably wrong: a user-stated fact lost to an inferred/dream fact,
                   or both sides have the same date (file order decided)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

HEADER = "# MEMORY.md - durable facts learned from previous conversations"
FORMAT_NOTE = "<!-- Format: - [key] fact (seen: YYYY-MM-DD, source: user|inferred|dream) -->"
STAMP_RE = re.compile(r"<!--\s*last_consolidated:\s*(?P<ts>[^ ]+)\s*-->")
FACT_RE = re.compile(r"^-\s+(?:\[(?P<key>[^\]]+)\]\s*)?(?P<value>.*?)\s*(?:\((?P<meta>[^()]*:[^()]*)\))?\s*$")
SOURCE_RANK = {"user": 3, "dream": 2, "inferred": 1}

DREAM_PROMPT = (
    "From the conversation below, list at most 5 durable facts worth remembering in future sessions "
    "(user preferences, budget, dates, decisions, project rules). Skip small talk. "
    'Reply with JSON only: {"facts": [{"key": "user.budget", "fact": "short sentence", '
    '"source": "user|inferred"}]}. Keys are lower-case, dot-separated topics.'
)

HELP_TEXT = """Commands (file-based memory, AGENT.md + MEMORY.md):
/memory   show MEMORY.md, its line count, last consolidation time, and whether consolidation is due
/compact  consolidate MEMORY.md (merge duplicates, resolve contradictions) and report counts before/after
/dream    pick durable facts from the recent conversation and append them to MEMORY.md
/help     show this help"""


@dataclass
class Fact:
    key: str | None
    value: str
    seen: str
    source: str
    merged: int
    line_no: int


# ---------- loading + prompt ----------

def load_text(path: Path) -> str:
    """Return the file contents, or an empty string when the file does not exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_agent_md(path: Path = config.AGENT_MD) -> str:
    """Load AGENT.md (durable project and agent instructions)."""
    return load_text(path)


def load_memory_md(path: Path = config.MEMORY_MD) -> str:
    """Load MEMORY.md (durable facts from earlier conversations)."""
    return load_text(path)


def build_system_prompt(base: str, agent_text: str, memory_text: str) -> str:
    """Append AGENT.md and MEMORY.md to a base system prompt."""
    parts = [base.strip()]
    if agent_text.strip():
        parts.append("## Project instructions (AGENT.md)\n" + agent_text.strip())
    if memory_text.strip():
        parts.append("## Remembered facts (MEMORY.md)\n" + memory_text.strip())
    return "\n\n".join(parts)


# ---------- consolidation checks ----------

def content_lines(text: str) -> list[str]:
    """Non-empty lines that are not HTML comments (multi-line comments included)."""
    lines, in_comment = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.startswith("<!--"):
            in_comment = "-->" not in line
            continue
        if line:
            lines.append(line)
    return lines


def count_memory_lines(text: str) -> int:
    """Count the non-empty, non-comment lines of MEMORY.md."""
    return len(content_lines(text))


def read_last_consolidated(text: str) -> datetime | None:
    """Timestamp from <!-- last_consolidated: ISO-8601 -->; None when missing or 'never'."""
    match = STAMP_RE.search(text)
    if not match:
        return None
    try:
        ts = datetime.fromisoformat(match.group("ts").replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def needs_consolidation(text: str, now: datetime | None = None) -> tuple[bool, list[str]]:
    """Due when there are more than MEMORY_MAX_LINES content lines or the last consolidation is too old."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    count = count_memory_lines(text)
    if count > config.MEMORY_MAX_LINES:
        reasons.append(f"{count} non-empty, non-comment lines > {config.MEMORY_MAX_LINES}")
    last = read_last_consolidated(text)
    if last is None:
        reasons.append("no recorded consolidation time")
    elif now - last > timedelta(hours=config.MEMORY_MAX_AGE_HOURS):
        hours = (now - last).total_seconds() / 3600
        reasons.append(f"last consolidated {hours:.1f} h ago > {config.MEMORY_MAX_AGE_HOURS} h")
    return bool(reasons), reasons


# ---------- consolidation ----------

def normalize(value: str) -> str:
    """Lower-case, drop punctuation and repeated spaces, so trivially different wordings match."""
    return " ".join(re.sub(r"[^a-z0-9$ ]", " ", value.lower()).split())


def parse_meta(meta: str | None) -> dict[str, str]:
    """Parse 'seen: 2026-10-01, source: user, merged: 2' into a dict."""
    out = {}
    for part in (meta or "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def split_sections(text: str) -> dict[str, list[str]]:
    """Map '## heading' -> its lines. Lines before the first heading go under ''."""
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def parse_fact_lines(lines: list[str]) -> list[Fact]:
    """Parse '- [key] value (seen: ..., source: ...)' lines; other lines are ignored."""
    facts = []
    for i, line in enumerate(lines):
        m = FACT_RE.match(line.strip())
        if not m or not line.strip().startswith("-") or not m.group("value"):
            continue
        meta = parse_meta(m.group("meta"))
        facts.append(Fact(key=(m.group("key") or "").strip().lower() or None, value=m.group("value").strip(),
                          seen=meta.get("seen", ""), source=meta.get("source", "inferred").lower(),
                          merged=int(meta.get("merged", "1") or 1), line_no=i))
    return facts


def format_fact(f: Fact) -> str:
    """Render a Fact as one MEMORY.md line."""
    meta = [f"seen: {f.seen}" if f.seen else "", f"source: {f.source}", f"merged: {f.merged}" if f.merged > 1 else ""]
    key = f"[{f.key}] " if f.key else ""
    return f"- {key}{f.value} ({', '.join(m for m in meta if m)})"


def _newer(a: Fact, b: Fact) -> bool:
    """True when fact a should win over fact b: newer seen date, then later in the file."""
    return (a.seen, a.line_no) > (b.seen, b.line_no)


def consolidate(text: str, now: datetime | None = None) -> tuple[str, dict]:
    """Merge duplicate facts, resolve contradictions (newest wins, loser kept), flag doubtful resolutions."""
    now = now or datetime.now(timezone.utc)
    sections = split_sections(text)
    facts = parse_fact_lines(sections.get("Facts", []))

    merged: dict[tuple, Fact] = {}
    duplicates: list[dict] = []
    for f in facts:
        ident = (f.key, normalize(f.value)) if f.key else (None, normalize(f.value))
        if ident in merged:
            keep = merged[ident]
            duplicates.append({"key": f.key, "value": keep.value, "line": f.line_no})
            keep.merged += f.merged
            keep.seen = max(keep.seen, f.seen)
            if SOURCE_RANK.get(f.source, 0) > SOURCE_RANK.get(keep.source, 0):
                keep.source = f.source
            keep.line_no = max(keep.line_no, f.line_no)
        else:
            merged[ident] = Fact(**vars(f))

    by_key: dict[str | None, list[Fact]] = {}
    for f in merged.values():
        by_key.setdefault(f.key, []).append(f)

    kept: list[Fact] = []
    contradictions: list[dict] = []
    review: list[dict] = []
    for key, group in by_key.items():
        if key is None or len(group) == 1:
            kept.extend(group)
            continue
        winner = group[0]
        for f in group[1:]:
            if _newer(f, winner):
                winner = f
        kept.append(winner)
        for loser in group:
            if loser is winner:
                continue
            item = {"key": key, "kept": winner.value, "kept_seen": winner.seen, "kept_source": winner.source,
                    "dropped": loser.value, "dropped_seen": loser.seen, "dropped_source": loser.source,
                    "rule": "newest seen date wins"}
            contradictions.append(item)
            if SOURCE_RANK.get(loser.source, 0) > SOURCE_RANK.get(winner.source, 0):
                review.append({**item, "why": f"a {loser.source}-stated fact lost to a {winner.source} fact; "
                                              "newest-wins ignored where the fact came from"})
            elif loser.seen == winner.seen:
                review.append({**item, "why": "same seen date, so file order decided"})

    kept.sort(key=lambda f: (f.key or "~", f.line_no))
    resolved_lines = [line for line in sections.get("Resolved contradictions", []) if line.strip()]
    resolved_lines += [f'- [{c["key"]}] kept "{c["kept"]}" ({c["kept_seen"]}, {c["kept_source"]}) over '
                       f'"{c["dropped"]}" ({c["dropped_seen"]}, {c["dropped_source"]}); rule: {c["rule"]}'
                       for c in contradictions]
    review_lines = [line for line in sections.get("Needs review", []) if line.strip()]
    review_lines += [f'- [{r["key"]}] CHECK: kept "{r["kept"]}" over "{r["dropped"]}" - {r["why"]}' for r in review]

    out = [HEADER, f"<!-- last_consolidated: {now.isoformat(timespec='seconds')} -->", FORMAT_NOTE, "", "## Facts"]
    out += [format_fact(f) for f in kept]
    if resolved_lines:
        out += ["", "## Resolved contradictions", *resolved_lines]
    if review_lines:
        out += ["", "## Needs review", *review_lines]
    for name, body in sections.items():  # any other section is carried over unchanged
        if name not in ("", "Facts", "Resolved contradictions", "Needs review"):
            out += ["", f"## {name}", *[line for line in body if line.strip()]]
    new_text = "\n".join(out) + "\n"

    report = {
        "before_total_lines": len(text.splitlines()),
        "before_content_lines": count_memory_lines(text),
        "before_facts": len(facts),
        "after_total_lines": len(new_text.splitlines()),
        "after_content_lines": count_memory_lines(new_text),
        "after_facts": len(kept),
        "duplicates_merged": duplicates,
        "contradictions_resolved": contradictions,
        "needs_review": review,
    }
    return new_text, report


def verify_consolidation(original: str, consolidated: str, report: dict) -> list[dict]:
    """Objective checks for Part 4.5 (used by the tests and the consolidation demo)."""
    lines = consolidated.splitlines()
    kept_values = {normalize(f.value) for f in parse_fact_lines(split_sections(consolidated).get("Facts", []))}
    lost = [c for c in report["contradictions_resolved"]
            if normalize(c["dropped"]) not in normalize(consolidated)]
    checks = [
        ("fewer_than_40_lines", len(lines) < 40, f"{len(lines)} lines"),
        ("duplicates_merged", len(report["duplicates_merged"]) >= 3 and len(kept_values) == report["after_facts"],
         f"{len(report['duplicates_merged'])} duplicate lines merged"),
        ("contradictions_resolved_explicitly", len(report["contradictions_resolved"]) >= 3
         and "## Resolved contradictions" in consolidated, f"{len(report['contradictions_resolved'])} resolved"),
        ("no_silent_deletion", not lost, f"dropped values missing from file: {[c['dropped'] for c in lost]}"),
        ("incorrect_resolutions_flagged", len(report["needs_review"]) >= 1 and "## Needs review" in consolidated,
         f"{len(report['needs_review'])} flagged"),
        ("timestamp_recorded", read_last_consolidated(consolidated) is not None, "last_consolidated set"),
    ]
    return [{"check": n, "passed": bool(p), "details": d} for n, p, d in checks]


# ---------- /dream ----------

def dream(model, recent_messages: list[dict], path: Path = config.MEMORY_MD, today: str | None = None) -> list[str]:
    """Ask the model for durable facts in the recent conversation and append new ones to MEMORY.md."""
    today = today or datetime.now(timezone.utc).date().isoformat()
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages if not m["content"].startswith("/"))
    if not transcript:
        return []
    reply = model.chat([{"role": "system", "content": DREAM_PROMPT}, {"role": "user", "content": transcript}], [],
                       fmt="json")
    try:
        items = json.loads((reply.get("content") or "").strip()).get("facts", [])
    except (json.JSONDecodeError, AttributeError):
        items = []

    text = load_text(path) or f"{HEADER}\n<!-- last_consolidated: never -->\n{FORMAT_NOTE}\n\n## Facts\n"
    existing = {normalize(f.value) for f in parse_fact_lines(split_sections(text).get("Facts", []))}
    added = []
    for item in items[:5]:
        if not isinstance(item, dict) or not str(item.get("fact", "")).strip():
            continue
        key = re.sub(r"[^a-z0-9_.]", "", str(item.get("key", "misc")).lower()) or "misc"
        value = " ".join(str(item["fact"]).split())[:160]
        if normalize(value) in existing:
            continue
        existing.add(normalize(value))
        source = "user" if item.get("source") == "user" else "dream"
        added.append(format_fact(Fact(key, value, today, source, 1, 0)))
    if added:
        sections = split_sections(text)
        sections["Facts"] = [line for line in sections.get("Facts", []) if line.strip()] + added
        path.write_text(join_sections(sections), encoding="utf-8")
    return added


def join_sections(sections: dict[str, list[str]]) -> str:
    """Inverse of split_sections: the preamble, then each '## heading' with its non-empty lines."""
    out = "\n".join(sections.get("", [])).rstrip("\n") + "\n"
    for name, body in sections.items():
        if name:
            out += f"\n## {name}\n" + "".join(f"{line}\n" for line in body if line.strip())
    return out


# ---------- commands ----------

def is_command(message: str) -> bool:
    """True for the four memory commands."""
    return message.strip().split(" ")[0].lower() in {"/memory", "/compact", "/dream", "/help"}


def handle_command(message: str, model=None, recent_messages: list[dict] | None = None,
                   path: Path = config.MEMORY_MD) -> dict:
    """Run /memory, /compact, /dream or /help and return {"command", "reply", ...details}."""
    command = message.strip().split(" ")[0].lower()
    if command == "/help":
        return {"command": command, "reply": HELP_TEXT}

    if command == "/memory":
        text = load_text(path)
        due, reasons = needs_consolidation(text)
        last = read_last_consolidated(text)
        reply = (f"{path.name}: {count_memory_lines(text)} non-empty, non-comment lines; "
                 f"last consolidated: {last.isoformat() if last else 'never'}; "
                 f"consolidation due: {'yes (' + '; '.join(reasons) + ')' if due else 'no'}\n\n{text}")
        return {"command": command, "reply": reply, "lines": count_memory_lines(text), "consolidation_due": due,
                "reasons": reasons, "agent_md_lines": count_memory_lines(load_agent_md())}

    if command == "/compact":
        text = load_text(path)
        new_text, report = consolidate(text)
        path.write_text(new_text, encoding="utf-8")
        reply = (f"/compact: before {report['before_total_lines']} lines ({report['before_content_lines']} content lines, "
                 f"{report['before_facts']} facts) -> after {report['after_total_lines']} lines "
                 f"({report['after_content_lines']} content lines, {report['after_facts']} facts); "
                 f"{len(report['duplicates_merged'])} duplicates merged, "
                 f"{len(report['contradictions_resolved'])} contradictions resolved, "
                 f"{len(report['needs_review'])} flagged for review")
        return {"command": command, "reply": reply, "report": report}

    if command == "/dream":
        if model is None:
            return {"command": command, "reply": "/dream needs a model; none was provided"}
        added = dream(model, recent_messages or [], path)
        reply = f"/dream added {len(added)} fact(s) to {path.name}" + ("".join(f"\n{a}" for a in added))
        return {"command": command, "reply": reply, "added": added}

    return {"command": command, "reply": f"Unknown command {command}. Try /help."}
