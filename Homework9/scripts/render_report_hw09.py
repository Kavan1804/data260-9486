#!/usr/bin/env python3
"""Render the HW9 report (reports/hw09/report.pdf and Kumar_HW9.pdf).

Same layout as the HW5-HW8 reports (reuses scripts/render_report_hw05.py). Short code snippets are cut straight
out of the source files (between two marker lines), tables come from reports/hw09/raw/ and METRICS.md, and a
screenshot that does not exist yet is shown as a red MISSING box. Main headings 14 pt bold, subheadings 12 pt
bold, body 11 pt.

Usage (repo root):
    make report-hw09                                   # commit hash = HEAD
    COMMIT_HASH=<sha> python Homework9/scripts/render_report_hw09.py
"""

from __future__ import annotations

import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for config

import config  # noqa: E402
from hw9.common import DATA, RAW, REPORT_DIR, ROOT  # noqa: E402

# Loaded after hw9.common, which puts scripts/ on sys.path.
r5 = importlib.import_module("render_report_hw05")

r5.SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW9.pdf"
CSS = r5.CSS.replace("Homework 5", "Homework 9") + (
    ".missing { border: 2px dashed #ef4444; color: #b91c1c; padding: 10pt; margin: 6pt 0 12pt 0; }\n"
    ".cmd { white-space: pre-wrap; font-size: 8pt; line-height: 1.3; break-inside: avoid; }\n"
    ".src { font-size: 8.5pt; color: #6b7280; margin: 6pt 0 0 0; }\n"
)
HARDWARE = "MacBook Air with Apple M1 chip (8 GB unified memory)"
r5.CROPS = {}
MISSING: list[str] = []


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def fig(d, name: str, caption: str, width: str = "100%") -> None:
    if (r5.SHOTS / f"{name}.png").exists():
        d.fig(name, caption, width=width)
    else:
        MISSING.append(name)
        d.add(f"<div class='missing'><b>MISSING SCREENSHOT ({html.escape(name)}.png):</b> {html.escape(caption)}</div>")


def block(d, text: str) -> None:
    d.add(f"<div class='cmd'>{html.escape(text.rstrip())}</div>")


def code(d, path: str, start: str, end: str | None = None, note: str = "") -> None:
    """A short snippet from a real file: from the first line containing `start` to the next line containing `end`."""
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    i = next(k for k, line in enumerate(lines) if start in line)
    j = next((k for k in range(i + 1, len(lines)) if end and end in lines[k]), i)
    d.add(f"<p class='src'>{html.escape(path)}, lines {i + 1}-{j + 1}{(' - ' + html.escape(note)) if note else ''}</p>")
    block(d, "\n".join(lines[i : j + 1]))


def metrics_section(marker: str) -> str:
    text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
    a = text.index(f"<!-- {marker}:start -->") + len(f"<!-- {marker}:start -->")
    body = text[a : text.index(f"<!-- {marker}:end -->")]
    out, table = [], []

    def flush():
        if table:
            out.append(
                ("table", [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table if "---" not in ln])
            )
            table.clear()

    for line in body.strip().splitlines():
        if line.strip().startswith("|"):
            table.append(line)
        else:
            flush()
            if line.strip():
                out.append(("p", line.strip().removeprefix("- ")))
    flush()
    doc = r5.Doc(Path(tempfile.gettempdir()))
    for kind, val in out:
        doc.table(val) if kind == "table" else doc.p(val)
    return "".join(doc.parts)


def notes(heading: str) -> str:
    """One '### heading' block of the hand-written Notes in METRICS.md, as HTML paragraphs/bullets."""
    text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
    text = text[text.index("## Notes") :]
    a = text.index(f"### {heading}")
    b = text.find("\n### ", a + 4)
    body = text[a : b if b > 0 else None].split("\n", 1)[1]
    lines: list[str] = []
    for ln in body.splitlines():
        ln = re.sub(r"^\s*\d+\.\s+", "- ", ln)  # numbered items -> bullets
        if ln.startswith("  ") and ln.strip() and lines and lines[-1].strip():
            lines[-1] += " " + ln.strip()  # wrapped bullet line
        elif ln.startswith("**") and not ln.rstrip().endswith("**"):
            lines += ["", ln]  # "**Label.** text" starts its own paragraph
        else:
            lines.append(ln)
    return r5.md_paragraphs("\n".join(lines), skip_title=False)


def json_lines(obj, limit: int | None = None) -> str:
    s = json.dumps(obj, indent=2, ensure_ascii=False)
    lines = s.splitlines()
    return "\n".join(lines[:limit] + (["  ..."] if limit and len(lines) > limit else []))


# ---------------------------------------------------------------- sections


def section0(d, commit: str):
    d.add("<h1>DATA 260 Homework 9</h1>")
    d.add("<div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table(
        [
            ["GitHub repository", config.REPO_URL],
            ["SID4", "9486"],
            ["PREFIX", f"{config.PREFIX} (every Redis key and index starts with s9486:)"],
            ["SEED / VERIFY_SEED", f"{config.SEED} / {config.VERIFY_SEED}"],
            ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME} (primary entity: Listing, MySQL s9486_rel)"],
            ["Hardware", HARDWARE],
            ["Local model", f"{config.OLLAMA_MODEL} (Ollama) through the HW8 adapter; embeddings all-minilm (384-d)"],
            ["Redis", "redis:8.2.2 in Docker (container s9486_redis), vector index with FT.CREATE, cosine"],
            ["Tagged commit hash", f"{commit} (tag hw9)"],
        ],
        header=False,
        cls="kv",
    )
    d.p(
        "HW9 adds caching in front of my HW8 system. The new code is in `Homework9/hw9/` (library), "
        "`Homework9/scripts/` (one script per part, run with `make`), `Homework9/data/` (cache cases and Part 4 "
        "datasets) and `Homework9/tests/`. Results are in `reports/hw09/` (`RUN_LOG.txt`, `raw/`, `METRICS.md`, "
        "`AI_USE.md`, `verification.json`). A cache miss goes through the unchanged HW8 Kafka pipeline (planner -> "
        "writer -> reviewer)."
    )
    fig(d, "p0_services", "`make hw9-ps`: Redis 8.2.2, Kafka and the two Ollama models (llama3.2:3b, all-minilm).")


def part1(d):
    d.h2("Part 1. Redis View Counter")
    d.p(
        "The one new method is `increment_listing_views(listing_id)` on my `ListingDatabaseWithCache` class (adapted "
        "from the demo's DatabaseWithCache, but for my MySQL `listings` table). It runs `INCR` on "
        "`s9486:views:listing:<id>` and writes the count to the new `listings.view_count` column every 10th view."
    )
    code(d, "Homework9/hw9/listing_store.py", "def increment_listing_views", "return count")
    d.add(metrics_section("part1-table"))
    fig(d, "p1_counter", "`make counter-demo`: Access #1-#25, synced to MySQL at 10 and 20, Redis 25 vs MySQL 20.")
    d.add(notes("Part 1"))


def part2(d):
    d.h2("Part 2. Semantic Response Cache")
    d.p(
        "The cache sits in front of the HW8 pipeline (`Homework9/hw9/ingress.py`). For each query: embed it with "
        "all-minilm, run a KNN search on the Redis vector index (`s9486:idx:semcache`, FLAT, COSINE, 384 dims; "
        "similarity = 1 - distance), and compare with the 0.85 threshold. A hit returns the stored final answer "
        "without calling the pipeline. A miss looks up the listing facts the question mentions in MySQL, runs the "
        "HW8 pipeline, and stores the query, embedding, final answer and a data-version marker in a Redis HASH. "
        "Every response has `is_cached`, `similarity` and `latency_ms`, and the timings of each step."
    )
    code(d, "Homework9/hw9/semantic_cache.py", "def nearest", "return entry, round")
    code(d, "Homework9/hw9/ingress.py", "if entry is not None and sim >= threshold:", 'reason = "stale (data-version')
    d.h3("Results (12 queries: 5 new, 3 exact duplicates, 4 paraphrases)")
    d.add(metrics_section("part2-table"))
    fig(d, "p2_cache", "`make show-run T=cache-demo`: results table, hit rate and cached vs non-cached latency.")
    d.add(notes("Part 2"))


def part3(d):
    d.h2("Part 3. Threshold Economics and Stale Answers")
    d.h3("3.1 Labeled test set (cache_cases.yaml)")
    log = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%h %ci %s", "--", "Homework9/data/cache_cases.yaml"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sweep = load("sweep_summary.json")
    d.p(
        f"40 cases (10 exact, 10 paraphrase, 10 similar-but-different, 10 unrelated) against 10 seed queries. "
        f"Committed before the sweep: `{log}`. The sweep recorded the file's sha256 "
        f"(`{sweep['cases_sha256'][:16]}...`) and `make verify-hw09` checks it matches that commit."
    )
    yaml_lines = (DATA / "cache_cases.yaml").read_text(encoding="utf-8").splitlines()
    pick = [ln for ln in yaml_lines if any(f"id: {i}," in ln for i in ("A01", "E01", "P01", "S01", "U01"))]
    block(d, "\n".join(pick))
    d.h3("3.2 Threshold sweep")
    d.add(metrics_section("sweep-table"))
    fig(d, "p3_sweep", "`make show-run T=sweep`: the threshold table and the false hit from the logged sweep.")
    d.add(notes("Part 3.2 - what the sweep shows"))
    d.h3("3.3 One false hit in full")
    d.add(metrics_section("false-hit"))
    d.add(notes("Part 3.3 - why the false hit happens"))
    d.h3("3.4 Cost model and threshold choice")
    d.add(notes("Part 3.4 - cost model and the threshold I would ship"))
    d.h3("3.5 Stale answer and invalidation")
    st = load("stale_demo.json")
    d.p(
        f'Query: "{st["query"]}" (depends on the `listings` row of {st["listing_code"]}). I cached it, then ran '
        f"`UPDATE listings SET available_units = 0`, asked again with the version check off (stale hit) and on "
        f"(invalidated and refreshed). The row was set back to {st['original_units']} afterwards."
    )
    code(d, "Homework9/hw9/listing_store.py", "def fingerprint", "return hashlib")
    d.add(metrics_section("stale-table"))
    fig(d, "p3_stale", "`make show-run T=stale-demo`: stale hit with the check off, then STALE -> miss -> refresh.")
    d.add(notes("Part 3.5 - invalidation trade-off"))
    d.h3("Labeling notes")
    d.add(notes("Labeling notes (Part 3.1)"))


def part4(d):
    d.h2("Part 4. Self-Improving Multi-Agent System")
    d.p(
        "**Answering Agent:** llama3.2:3b through the HW8 adapter. It looks up the listing record in MySQL the way my "
        "HW4 API returns it (with `landlord_id`, no landlord name) and can call a `get_landlord` tool (Ollama tool "
        "calling). **Evaluator Agent:** checks the answer against `reference_data.json` only, with rules per fact "
        "(units, landlord, company, city, address, home type, 'not in the data', 'no such listing'), and returns "
        "PASS or REVISE, a short explanation, feedback and failure tags."
    )
    code(d, "Homework9/hw9/agents.py", "for _ in range(MAX_TOOL_ROUNDS):", "reply = self.chat(messages, tools")
    code(d, "Homework9/hw9/agents.py", "for attempt in range(1, max_attempts + 1):", "feedback = {")
    d.h3("Datasets")
    ref = json.loads((DATA / "reference_data.json").read_text(encoding="utf-8"))
    code_ = next(iter(ref["listings"]))
    block(
        d,
        "reference_data.json (31 listings, 3 missing codes, 5 not-recorded fields, 34 question ids):\n"
        + json_lines({"listings": {code_: ref["listings"][code_]}, "questions": {"tr01": ref["questions"]["tr01"]}})
        + "\n\ntraining_data.json (12) / validation_data.json (10) / test_data.json (12), questions only:\n"
        + "\n".join(
            json.dumps(json.loads((DATA / f).read_text())[0])
            for f in ("training_data.json", "validation_data.json", "test_data.json")
        ),
    )
    d.h3("4.1 One complete revision sequence (controlled bad first answer)")
    rev = load("revision_demo.json")
    rows = [["Question", f"{rev['id']}: {rev['question']}"]]
    for h in rev["history"]:
        ev = h["evaluation"]
        who = "Initial answer (written on purpose, incomplete)" if h.get("controlled") else "Revised answer"
        rows.append([who, h["answer"]])
        rows.append([f"Evaluator (attempt {h['attempt']})", f"{ev['result']} - {ev['explanation']}"])
        if ev["feedback"]:
            rows.append(["Feedback", ev["feedback"]])
    rows += [["Attempts", f"{rev['attempts']} (max 2)"], ["Final response", rev["final_answer"]]]
    d.table(rows, header=False, widths=["26%", "74%"])
    fig(d, "p4_revision", "`make show-run T=revision-demo`: REVISE with feedback, then PASS on attempt 2.")
    d.h3("4.2 Lessons and reuse")
    lessons = json.loads((DATA / "lessons.json").read_text(encoding="utf-8"))
    code(d, "Homework9/scripts/part4_train.py", "if len(seen[tag]) == REPEAT", "f\"{lesson['correction']}\"")
    block(d, "lessons.json:\n" + json_lines(lessons, 30))
    tr = {r["id"]: r for r in load("part4_training.json")["results"]}
    later = tr.get("tr08")
    if later:
        h = later["history"][0]
        d.p(
            f'Reuse: tr03 ("{tr["tr03"]["question"]}") left out the unit count on its first answer, so '
            f'`lesson_001` was created. The later related question tr08 ("{later["question"]}") loaded '
            f'{later["lessons_loaded"]} and passed on its first answer: "{h["answer"]}"'
        )
    fig(d, "p4_train", "`make show-run T=part4-train`: lesson created after tr03, loaded by later questions, gate.")
    d.h3("4.3 Validation before keeping a lesson")
    d.add(metrics_section("lessons-table"))
    code(d, "Homework9/hw9/agents.py", "keep = len(failing_after)", "keep = len(failing_after)")
    d.h3("4.4 Four variants on the unchanged test_data.json")
    d.add(metrics_section("variants-table"))
    fig(d, "p4_variants", "`make show-run T=variants`: the results table for the four variants.")
    d.add(notes("Part 4"))
    d.h3("Agent communication, stopping condition and validation")
    d.bullets(
        [
            "The agents talk by passing plain dicts in one process: the Answering Agent returns {answer, "
            "lessons_used, tools_called}, the Evaluator returns {result, explanation, feedback, tags}. On REVISE, "
            "the feedback and the previous answer go back into the Answering Agent's next prompt.",
            "Stopping: the loop ends on PASS or after the 2nd attempt, whatever the result (`MAX_ATTEMPTS = 2`, "
            "enforced in run_question even if a caller asks for more).",
            "Lessons are loaded before answering when the question's topic matches the lesson's `applies_to`; "
            "`use_count` goes up each time. A lesson is kept only if validation failures do not go up, nothing that "
            "passed starts failing, and no question gets a made-up value. test_data.json is only read by the "
            "variants script, with lessons.json opened read-only.",
        ]
    )


def verification(d):
    d.h2("Verification")
    v = json.loads((REPORT_DIR / "verification.json").read_text(encoding="utf-8"))
    d.p(
        f"`make verify-hw09` re-checks the saved evidence against the live system: {v['passed']}/{v['total']} checks "
        f"passed (commit `{v['commit']}`{', uncommitted changes' if v['dirty_tree'] else ''}). `make test-hw9` runs "
        "the automated checks (no model calls)."
    )
    d.table(
        [["Check", "Result"]] + [[c["check"], "PASS" if c["ok"] else "FAIL"] for c in v["checks"]],
        widths=["80%", "20%"],
    )
    fig(d, "p5_verify", "`make test-hw9` and `make verify-hw09`.")


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
        for section in (section0, part1, part2, part3, part4, verification, ai_use):
            section(d, commit) if section is section0 else section(d)
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
            f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW9 - Kavan Siddesh</title>"
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
        f"wrote {OUT_PDF.relative_to(ROOT)} and {NAMED_PDF.relative_to(ROOT)} "
        f"(commit {commit[:12]}, {d.fig_no} figures)"
    )
    if MISSING:
        print(f"DRAFT - MISSING screenshots shown as red boxes: {', '.join(dict.fromkeys(MISSING))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
