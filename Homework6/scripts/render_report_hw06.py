#!/usr/bin/env python3
"""Render the HW6 report (reports/hw06/report.pdf and Kumar_HW6.pdf).

Same layout as the HW5 report and reuses its helpers (scripts/render_report_hw05.py):
configuration table first, one section per part, labeled screenshots, and result
tables built from reports/hw06/raw/. No source code (it is in the GitHub repository).
Main headings 14 pt bold, subheadings 12 pt bold, body 11 pt.

Screenshots come from reports/hw06/screenshots/; only the copies in the PDF are
cropped (macOS menu bar, dock, VS Code panel tabs and status bar removed).

Usage (repo root):
    make report-hw06                                   # commit hash = HEAD
    COMMIT_HASH=<sha> python Homework6/scripts/render_report_hw06.py
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from hw6_common import PROBES_YAML, RAW, REPORT_DIR, ROOT, SETTINGS

import config

# Loaded after the hw*_common import, which puts scripts/ on sys.path (a plain import would be sorted above it).
r5 = importlib.import_module("render_report_hw05")

r5.SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW6.pdf"
CSS = r5.CSS.replace("Homework 5", "Homework 6")
HARDWARE = "MacBook Air with Apple M1 chip (8 GB unified memory)"

COMPASS = (0.0, 0.03, 1.0, 0.89)  # drop the macOS menu bar and the dock
r5.CROPS = {
    "mongo_": COMPASS,
    "episodes": COMPASS,
    "part1_crud": (0.0, 0.07, 0.952, 0.91),
    "part1_validation": (0.0, 0.06, 0.952, 0.63),
    "chat1": (0.0, 0.04, 0.952, 0.97),
    "chat2": (0.0, 0.08, 0.952, 0.975),
    "memory1": (0.0, 0.028, 0.97, 0.98),
    "memory2": (0.0, 0.028, 0.97, 0.985),
    "aggregate1": (0.0, 0.05, 0.952, 0.72),
    "memory_cost": (0.0, 0.10, 0.952, 0.965),
    "compact1": (0.0, 0.07, 0.952, 0.965),
    "compact2": (0.0, 0.055, 0.952, 0.965),
    "agent_md": (0.0, 0.05, 0.952, 0.97),
}


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- sections


def section0(d, commit: str):
    d.add("<h1>DATA 260 Homework 6</h1>")
    d.add("<div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table(
        [
            ["GitHub repository", config.REPO_URL],
            ["SID4", "9486"],
            ["PORT_BASE", str(config.PORT_BASE)],
            ["PREFIX", config.PREFIX],
            ["SEED", str(config.SEED)],
            ["VERIFY_SEED", str(config.VERIFY_SEED)],
            ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME}"],
            ["Hardware", HARDWARE],
            ["Local model", f"{config.OLLAMA_MODEL} (Ollama, temperature 0, num_ctx {config.OLLAMA_NUM_CTX})"],
            ["Embedding", "hash-bow-256 - my local hashed bag-of-words fallback (no Ollama embedding model installed)"],
            [
                "MongoDB",
                f"{config.MONGODB_DB} on {config.MONGODB_URI} (professor's long-term-memory docker-compose.yml)",
            ],
            ["Tagged commit hash", f"{commit} (tag hw6)"],
        ],
        header=False,
        cls="kv",
    )
    d.p(
        "Both collaborators (Sbnikitha, supriyaselvanganesan) have access to the repository. HW6 extends the same "
        "root-level application as HW5 (no separate copy); HW6 scripts, tests and fixtures are in `Homework6/`, and "
        "the results, `RUN_LOG.txt`, `raw/`, `METRICS.md`, `AI_USE.md` and `verification.json` are in `reports/hw06/`."
    )


def part1(d):
    d.h2("Part 1. MongoDB Document API")
    d.h3("I. Database")
    d.p(
        "I mapped my HW5 domain (rental listings) to a document collection `listings` in the database `s9486_doc`. "
        "The same rules are enforced twice: by the Pydantic schema in the API and by a `$jsonSchema` validator on "
        "the collection, so even a direct insert that breaks the rules is rejected by MongoDB."
    )
    d.table(
        [
            ["Field", "Type", "Rule"],
            ["title", "string, required", "1-100 characters"],
            ["description", "string, optional", "up to 2,000 characters, may be null"],
            ["status", "enum", "available | pending | rented, default available"],
            ["property_type", "enum, required", "studio | apartment | condo | house | townhouse"],
            ["available_from", "date/time, required", "ISO 8601 date or datetime (move-in date)"],
            ["created_at, updated_at", "date/time", "set by the server; updated_at changes on every PUT"],
        ],
        widths=["26%", "26%", "48%"],
    )
    d.fig("mongo_listings", "MongoDB Compass: s9486_doc.listings with three sample documents.")
    d.h3("II. API Implementation")
    d.p(
        "CRUD runs at `/api/listings` on port 8486 inside the existing FastAPI app, with the HW5 CORS middleware and "
        "FastAPI's JSON body parsing. The code is split into connection (`mongo.py`), schemas (`doc_schema.py`) and "
        "route handlers (`routers/listing_docs.py`); `config.py` holds the settings. Status codes: 201 create, "
        "200 read/update/delete, 400 malformed id or empty update, 404 missing, 422 invalid data, 500 database "
        "error, 503 MongoDB not reachable."
    )
    d.fig(
        "part1_crud",
        "Create (201), get all (200), get one (200), update status to rented (200), delete (200), "
        "then get the deleted id (404).",
    )
    d.h3("III. Data Validation")
    d.fig(
        "part1_validation",
        "Invalid enum and invalid date (422), missing required fields (422), title over "
        "100 characters (422), and a malformed id (400). Each error names the field.",
    )
    d.p(
        "The offline tests also cover a wrong data type (`title: 12345`), null in a required field on update and "
        "unknown fields, and the `--live` tests send every case to the real MongoDB (32/32 passed, RUN_LOG.txt)."
    )


def part2(d):
    transcript = load("chat_demo_transcript.json")
    d.h2("Part 2. Short-, Long-, and Episodic Memory")
    d.h3("MongoDB collections (same database s9486_doc)")
    d.table(
        [
            ["Collection", "Fields", "Used for"],
            ["messages", "user_id, session_id, role (user/assistant), content, created_at", "short-term window"],
            [
                "summaries",
                "user_id, session_id (null for lifetime), scope (session/user), text, created_at",
                "long-term memory",
            ],
            [
                "episodes",
                "user_id, session_id, fact, importance (0-1), embedding (256 floats), embedding_model, created_at",
                "episodic memory",
            ],
        ],
        widths=["15%", "60%", "25%"],
    )
    d.fig("mongo_messages", "messages for demo-user: 24 documents (12 user + 12 assistant).")
    d.fig(
        "mongo_summaries",
        "summaries: two session summaries (scope session) and the lifetime summary (scope user, session_id null).",
    )
    d.fig("episodes", "episodes: 11 extracted facts with importance and a 256-float embedding.")

    d.h3("Memory logic")
    d.table(
        [
            ["Step in POST /api/chat", "How I implemented it", "Function (backend/app/)"],
            [
                "Short-term memory",
                f"last SHORT_TERM_N = {config.SHORT_TERM_N} messages of the session, oldest first",
                "memory_logic.select_window",
            ],
            [
                "Session summary",
                f"every {config.SUMMARIZE_EVERY_USER_MSGS} user messages, up to 6 bullets "
                "(previous summary + last 10 messages)",
                "memory_logic.maybe_summarize",
            ],
            [
                "Lifetime summary",
                f"after every {config.LIFETIME_EVERY_SESSION_SUMMARIES}nd session summary, condenses the "
                "latest session summaries into scope user, session_id null",
                "memory_logic.maybe_summarize",
            ],
            [
                "Episode extraction",
                "up to 3 facts per user message as JSON with importance 0-1, then embedded and stored",
                "memory_logic.extract_and_store_facts",
            ],
            [
                "Retrieval",
                f"cosine similarity between the message embedding and stored episodes, top-k = {config.EPISODIC_TOP_K}",
                "memory_logic.retrieve_episodes",
            ],
            [
                "Prompt assembly",
                "system primer + lifetime and session summary + episodic facts, then the window, then "
                "the current message",
                "memory_logic.build_prompt",
            ],
            ["Model call", "HW5 Ollama adapter (OllamaModel) with llama3.2:3b", "memory_logic.chat_turn"],
        ],
        widths=["20%", "52%", "28%"],
    )

    d.h3("Conversation (12 messages, one session)")
    turns = [t["response"] for t in transcript]
    made = [t["turn"] for t in turns if t["memory_written"]["session_summary_created"]]
    life = [t["turn"] for t in turns if t["memory_written"]["lifetime_summary_created"]]
    d.p(
        f"I sent 12 messages as demo-user in session-1 with `make chat-demo`. The short-term window grew by two "
        f"messages per turn until it reached 12. Session summaries were written at turns {made[0]} and {made[1]}, "
        f"and the lifetime summary at turn {life[0]}. In turn 11 I asked for my cat's name and move-in date; the "
        f'retrieval returned "Pixel is a cat" and "March 1, 2027, moving date" and the reply was correct.'
    )
    d.fig("chat1", "Turns 1-5: replies, window size, extracted facts, tokens and latency (session summary at turn 5).")
    d.fig("chat2", "Turns 9-12: retrieved episodic facts with cosine scores, summaries in use, and the final summary.")
    d.h3("GET /api/memory/{user_id}")
    d.fig("memory1", "Last 16 messages (first part).")
    d.fig("memory2", "Latest session summary, latest lifetime summary and the episodic facts.")
    d.h3("GET /api/aggregate/{user_id}")
    d.fig("aggregate1", "Daily message counts (MongoDB $group by date) and the most recent summaries.")
    d.p(
        'Two things I noticed: the summaries start with "- -" because llama3.2 added its own bullet in front of '
        "mine, and the `embedding_preview` (first 4 of 256 values) is mostly 0.0 because the hash embedding only "
        "fills the buckets of words that appear in the fact."
    )


def part3(d):
    summary = {s["setting"]: s for s in load("memory_summary.json")["settings"]}
    scores = load("probe_scores.json")
    probes = yaml.safe_load(PROBES_YAML.read_text(encoding="utf-8"))["probes"]
    d.h2("Part 3. What Memory Costs")
    d.h3("1. Logging memory usage")
    rows = sum(1 for _ in (RAW / "chat_usage.jsonl").open())
    d.p(
        f"Every /api/chat request writes one JSON line to `raw/chat_usage.jsonl` ({rows} rows) and the experiment "
        "runner also saves `raw/turns_<setting>.csv`. Each row has: prompt and completion tokens (Ollama's "
        "`prompt_eval_count` / `eval_count`), the estimated tokens of the system primer, long-term summary, "
        "short-term window and episodic facts (characters / 4, since Ollama only reports a total), the tokens of the "
        "extra upkeep calls (fact extraction and summaries), latency in ms, SHORT_TERM_N, policy, user and session "
        "id, turn number and timestamp."
    )
    d.h3("2. Memory probes (memory_probes.yaml)")
    d.p(
        "I wrote five fixed questions before running anything. Each has keyword criteria; the share of criteria met "
        "gives the 1-5 score (5 = all, 4 = at least 2/3, 3 = at least 1/3, 2 = only an outdated value, 1 = nothing)."
    )
    t = [["Probe", "Question", "Expected", "Stated in turn"]]
    for p in probes:
        t.append([p["id"], p["question"], p["expected"], ", ".join(map(str, p["source_turns"]))])
    d.table(t, widths=["17%", "38%", "33%", "12%"])

    d.h3("3. Short-term memory sizes")
    d.p(
        "Each setting ran the same 30-message conversation (`Homework6/fixtures/conversation_30.json`) in a fresh "
        "session with a new user id, so no summary or fact carried over, and then the same five probes."
    )
    t = [["Setting", "Mean prompt tokens/turn", "Mean latency (ms)", "Probe quality (1-5)"]]
    for k in ("n4", "n12", "n30"):
        s = summary[k]
        t.append([s["name"], f"{s['mean_prompt_tokens']:.1f}", f"{s['mean_latency_ms']:,.0f}", f"{s['probe_mean']}"])
    s = summary["compress"]
    t.append(
        ["Compression policy", f"{s['mean_prompt_tokens']:.1f}", f"{s['mean_latency_ms']:,.0f}", f"{s['probe_mean']}"]
    )
    d.table(t)
    per = {(r["setting"], r["probe_id"]): r["score"] for r in scores["per_answer"]}
    t = [["Probe", "N=4", "N=12", "N=30", "Compression"]]
    for p in probes:
        t.append([p["id"]] + [str(per[(k, p["id"])]) for k in SETTINGS])
    d.table(t)
    d.fig(
        "memory_cost",
        "memory_cost.py output: summary table, estimated prompt composition, the compression "
        "comparison and the cost table.",
    )
    d.p(
        "Prompt size grew almost linearly with the window: the estimated window part went from about 333 tokens "
        "(N=4) to 843 (N=12) and 1,686 (N=30), while the primer (64), summaries (about 210-240) and episodic facts "
        "(about 30) stayed the same. More memory did not mean better answers: N=12 had the best probe score (4.6), "
        "N=30 was slightly worse (4.4) and took more than twice as long per turn, and N=4 lost only the reason "
        "behind the flooring preference (4.2), because the summaries and retrieved facts covered most of what "
        'had dropped out of the window. No setting recalled the name "Priya" from turn 1: the extractor never '
        "stored the name as a fact and the summaries left it out, which shows that facts only survive if the "
        "memory pipeline picks them up."
    )

    d.h3("4. Memory-saving policy: compression")
    base, comp = summary["n12"], summary["compress"]
    saved = base["mean_prompt_tokens"] - comp["mean_prompt_tokens"]
    d.p(
        f"My policy keeps SHORT_TERM_N = 12 but only the newest {config.COMPRESS_KEEP_RECENT} messages stay word for "
        f"word; older messages in the window are cut to {config.COMPRESS_MAX_CHARS} characters. Long assistant "
        "replies are what make the window expensive, and their first sentence usually carries the point."
    )
    d.table(
        [
            ["", "Mean prompt tokens/turn", "Probe quality"],
            ["SHORT_TERM_N=12 (baseline)", f"{base['mean_prompt_tokens']:.1f}", f"{base['probe_mean']}"],
            ["Compression (N=12)", f"{comp['mean_prompt_tokens']:.1f}", f"{comp['probe_mean']}"],
            [
                "Change",
                f"-{saved:.1f} ({100 * saved / base['mean_prompt_tokens']:.1f}% saved)",
                f"{comp['probe_mean'] - base['probe_mean']:+.1f}",
            ],
        ]
    )
    d.p(
        "The policy saved about a third of the prompt tokens per turn (and about 60% compared with N=30). The "
        "probe score dropped by 0.6, but all of it came from the budget question: both budget facts ($2,600 and "
        "the updated $2,900) were retrieved and the model picked the old one. The other four probes scored the "
        "same as N=12, so I think the loss is mostly because episodes have no rule that a newer value replaces an "
        "older one, not because of the clipping. With one run per setting this is a single question, so I would "
        "repeat the runs before drawing a strong conclusion."
    )

    d.h3("5. Estimated memory cost")
    best, worst = summary[load("memory_summary.json")["best"]], summary[load("memory_summary.json")["worst"]]
    t = [["Case", "Setting", "Input tokens/turn", "Output tokens/turn", "Cost, reply only", "Cost, with upkeep"]]
    for case, s in (("Best", best), ("Worst", worst)):
        t.append(
            [
                case,
                s["name"],
                f"{s['mean_prompt_tokens']:.1f} + {s['mean_aux_prompt_tokens']:.1f} upkeep",
                f"{s['mean_completion_tokens']:.1f} + {s['mean_aux_completion_tokens']:.1f} upkeep",
                f"${s['cost_reply_only']:,.2f}",
                f"${s['cost_with_upkeep']:,.2f}",
            ]
        )
    d.table(t, widths=["8%", "17%", "22%", "21%", "15%", "17%"])
    d.p(
        "Cost = 10,000 conversations x 30 turns x (input tokens x $1/M + output tokens x $5/M), using the measured "
        'means. "With upkeep" adds the fact-extraction and summary calls that run on every turn.'
    )
    d.p(
        "**How I picked best and worst:** best is the cheapest setting whose probe score is within 0.5 of the top "
        "score (4.6). N=4 (4.2) qualifies and is the cheapest. Compression is not cheaper than N=4 and scored 4.0, "
        "so it is out. Worst is the most expensive setting, N=30, which also did not beat N=12. Going from worst to "
        f"best saves about ${worst['cost_with_upkeep'] - best['cost_with_upkeep']:,.0f} per 10,000 conversations. "
        "The upkeep calls are about 40% of the cost at N=4, so they matter as much as the window size."
    )


def part4(d):
    rep = load("consolidation_report.json")["report"]
    agent = load("agent_md_check.json")
    d.h2("Part 4. File-Based Memory and Consolidation")
    d.h3("1. Memory files")
    counts = agent["agent_md"]["instructions_per_section"]
    d.p(
        "`AGENT.md` (repo root) is my HW1 AGENT.md expanded. The HW1 code-review rules are kept at the end, and new "
        "sections hold the durable project instructions. `MEMORY.md` holds facts as `- [key] fact (seen: date, "
        "source: user/inferred/dream)`, plus a `last_consolidated` timestamp in an HTML comment."
    )
    d.table(
        [
            ["AGENT.md section", "Instructions", "Example"],
            [
                "Project description",
                str(counts.get("Project description", 0)),
                "shared app for SID4 9486, extended in place every homework",
            ],
            [
                "Technology stack",
                str(counts.get("Technology stack", 0)),
                "FastAPI on 8486, MySQL s9486_rel, MongoDB s9486_doc, local Ollama only",
            ],
            [
                "Coding conventions",
                str(counts.get("Coding conventions", 0)),
                "type hints, docstrings, lines <= 120 chars, values from config.py, no print() in backend",
            ],
            [
                "Testing approach",
                str(counts.get("Testing approach", 0)),
                "plain-assert offline tests with fake models; MongoDB tests only with --live",
            ],
            [
                "Prohibited actions",
                str(counts.get("Prohibited actions", 0)),
                "no LangChain/OpenAI/Flask/Redis, never commit .env, never fabricate results",
            ],
            [
                "Code review (from HW1)",
                str(counts.get("Code review (from HW1 AGENT.md)", 0)),
                "bullet-only strict review answers",
            ],
        ],
        widths=["25%", "13%", "62%"],
    )
    d.h3("2. File-based memory functions (backend/app/file_memory.py)")
    d.table(
        [
            ["Function", "What it does"],
            ["load_agent_md / load_memory_md", "read the two Markdown files (empty string if missing)"],
            ["build_system_prompt", "adds AGENT.md and then MEMORY.md under their own headings to the system prompt"],
            ["read_last_consolidated", "reads the `<!-- last_consolidated: ... -->` timestamp (None if 'never')"],
            ["count_memory_lines", "counts non-empty, non-comment lines (multi-line comments included)"],
            [
                "needs_consolidation",
                f"true if more than {config.MEMORY_MAX_LINES} lines or last consolidation "
                f"older than {config.MEMORY_MAX_AGE_HOURS} h; returns the reasons",
            ],
        ],
        widths=["32%", "68%"],
    )
    d.h3("3. Memory commands")
    d.table(
        [
            ["Command", "What it does"],
            ["/memory", "shows MEMORY.md, its line count, last consolidation time and whether consolidation is due"],
            ["/compact", "consolidates MEMORY.md and reports the line/fact counts before and after"],
            ["/dream", "asks the local model for durable facts in the recent conversation and appends new ones"],
            ["/help", "lists the commands"],
        ],
        widths=["15%", "85%"],
    )
    d.p(
        'The commands work through POST /api/chat (a message starting with "/" is not stored as a chat message) '
        "and in the terminal chat `Homework6/scripts/file_memory_chat.py`, which loads both files into the system "
        "prompt on every turn."
    )

    d.h3("4. AGENT.md test")
    gen = agent["generated_function"]
    failed = [c["rule"] for c in gen["rules"] if not c["passed"]]
    passed_cases = sum(c["passed"] for c in gen.get("behavior", []))
    d.p(
        f"`agent_md_check.py` confirms AGENT.md has {agent['agent_md']['total_instructions']} instructions in all "
        "five required categories, and checks a function against the rules that can be tested automatically "
        "(type hints, docstring, line length, no hard-coded config, no print, no banned imports). My implemented "
        "`count_memory_lines` passes all of them. I also asked llama3.2:3b, with AGENT.md in its system prompt, to "
        f"generate `days_until_available()`. It failed {', '.join(failed)} and only {passed_cases} of "
        f"{len(gen.get('behavior', []))} behavior cases passed (it subtracts a date from a datetime). So the small "
        "model did not follow AGENT.md, and the check is what caught it."
    )
    d.fig(
        "agent_md",
        "AGENT.md check: implemented function passes; the model-generated function fails R6/R7 and two behavior cases.",
    )

    d.h3("5. Consolidation test")
    d.p(
        f"The test file `Homework6/fixtures/MEMORY_original_55.md` has 55 lines: 50 facts with heavy duplication "
        f"and 5 contradictions. Running /compact reduced it to {rep['after_total_lines']} lines "
        f"({rep['after_facts']} facts) in `reports/hw06/raw/MEMORY_consolidated.md`. Both files are committed."
    )
    d.fig(
        "compact1",
        "/compact reports the counts before (55 lines, 50 facts) and after (38 lines, 22 facts) and "
        "lists the merged duplicates.",
    )
    d.fig("compact2", "Flagged resolution, all six checks passing, and the start of the consolidated file.")
    flagged = {r["key"] for r in rep["needs_review"]}
    t = [["Key", "Kept (newest)", "Dropped (kept under Resolved contradictions)", "Correct?"]]
    verdict = {
        "user.bedrooms": "No - the user said 2 bedrooms twice; an inferred guess won only because it was newer",
        "user.pets": "Unclear - same date, so file order decided; needs the user to confirm",
    }
    for c in rep["contradictions_resolved"]:
        note = verdict.get(c["key"], "Yes - newer user statement")
        if c["key"] in flagged:
            note += " (flagged)"
        t.append(
            [
                c["key"],
                f"{c['kept']} ({c['kept_seen']}, {c['kept_source']})",
                f"{c['dropped']} ({c['dropped_seen']}, {c['dropped_source']})",
                note,
            ]
        )
    d.table(t, widths=["14%", "29%", "29%", "28%"])
    d.p(
        f"Duplicates were merged into one line with a `merged: N` count ({len(rep['duplicates_merged'])} duplicate "
        'lines). Each contradiction keeps the newest value and writes the losing one to a "Resolved '
        'contradictions" section, so nothing conflicting is deleted silently. The rule "newest wins" was wrong '
        "for `user.bedrooms`. My check detects this because the losing fact came from the user and the winner was "
        'only inferred, and it lists it under "Needs review" together with the `user.pets` tie.'
    )

    d.h3("6. MongoDB memory vs. file-based memory")
    d.table(
        [
            ["", "MongoDB memory (Part 2)", "File-based memory (AGENT.md / MEMORY.md)"],
            [
                "Inspectability",
                "Needs Compass, mongosh or the API; embeddings are not human-readable",
                "Plain Markdown I can open, edit and diff in Git",
            ],
            [
                "Persistence after a restart",
                "Yes, as long as the Docker volume is kept (removing the volume loses it)",
                "Yes, it is a file in the repository and is versioned in Git",
            ],
            [
                "Scalability across many sessions",
                "Good: per-user queries with indexes, top-k retrieval keeps the prompt small",
                "Poor: the whole file goes into every prompt and one file is "
                "shared by everyone; it needs consolidation to stay small",
            ],
            [
                "Facts that must not be forgotten",
                "Risky: summaries and the extractor can drop facts (the name in Part 3)",
                "Better: a rule written in AGENT.md is always in the prompt and only changes if someone edits it",
            ],
        ],
        widths=["22%", "39%", "39%"],
    )
    d.p(
        "For my app I would keep chat history, summaries and episodes in MongoDB, and put rules and facts that must "
        "never be lost (project rules, confirmed user requirements) in the files."
    )


def ai_use(d):
    d.h2("AI Use")
    d.add(r5.md_paragraphs((REPORT_DIR / "AI_USE.md").read_text(encoding="utf-8")))


def main() -> int:
    commit = (
        os.getenv("COMMIT_HASH")
        or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        d = r5.Doc(tmp)
        section0(d, commit)
        part1(d)
        part2(d)
        part3(d)
        part4(d)
        ai_use(d)
        font_dir = r5.find_font()
        font_css = ""
        if font_dir:
            for fam, f, w in [
                ("DejaVu Sans", "DejaVuSans.ttf", "normal"),
                ("DejaVu Sans", "DejaVuSans-Bold.ttf", "bold"),
                ("DejaVu Sans Mono", "DejaVuSansMono.ttf", "normal"),
            ]:
                if (Path(font_dir) / f).exists():
                    shutil.copy(Path(font_dir) / f, tmp / f)
                    font_css += f"@font-face {{ font-family: '{fam}'; src: url('{f}'); font-weight: {w}; }}\n"
        page = (
            f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW6 - Kavan Siddesh</title>"
            f"<style>{font_css}{CSS}</style></head><body>{''.join(d.parts)}</body></html>"
        )
        (tmp / "report.html").write_text(page, encoding="utf-8")
        subprocess.run(
            [
                r5.CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}",
                (tmp / "report.html").as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        if os.getenv("KEEP_HTML"):
            shutil.copytree(tmp, os.environ["KEEP_HTML"], dirs_exist_ok=True)
    shutil.copy(OUT_PDF, NAMED_PDF)
    print(
        f"wrote {OUT_PDF.relative_to(ROOT)} and {NAMED_PDF.relative_to(ROOT)}"
        f" (commit {commit[:12]}, {d.fig_no} figures)"
    )
    if d.missing:
        print(f"MISSING screenshots (left out): {', '.join(d.missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
