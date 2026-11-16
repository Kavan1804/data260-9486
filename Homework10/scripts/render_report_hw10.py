#!/usr/bin/env python3
"""Render the HW10 report (reports/hw10/report.pdf and Kumar_HW10.pdf).

Same layout as the HW5-HW9 reports (reuses scripts/render_report_hw05.py): short code snippets cut from the source
files, tables from reports/hw10/raw/ and METRICS.md, red MISSING boxes for screenshots not taken yet.
Main headings 14 pt bold, subheadings 12 pt bold, body 11 pt. Must stay under 35 pages.

Usage (repo root):
    make report-hw10                                   # commit hash = HEAD
    COMMIT_HASH=<sha> python Homework10/scripts/render_report_hw10.py
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
from hw10.analysis import by_trace, journey  # noqa: E402
from hw10.common import RAW, REPORT_DIR, ROOT, read_spans  # noqa: E402
from hw10.judge import JUDGE_SETTINGS  # noqa: E402

r5 = importlib.import_module("render_report_hw05")

r5.SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW10.pdf"
CSS = r5.CSS.replace("Homework 5", "Homework 10") + (
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
                out.append(("p", line.strip()))
    flush()
    doc = r5.Doc(Path(tempfile.gettempdir()))
    for kind, val in out:
        doc.table(val) if kind == "table" else doc.p(val)
    return "".join(doc.parts)


def notes(heading: str) -> str:
    text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
    text = text[text.index("## Notes") :]
    a = text.index(f"### {heading}")
    b = text.find("\n### ", a + 4)
    body = text[a : b if b > 0 else None].split("\n", 1)[1]
    lines: list[str] = []
    for ln in body.splitlines():
        ln = re.sub(r"^\s*\d+\.\s+", "- ", ln)
        if ln.startswith("  ") and ln.strip() and lines and lines[-1].strip():
            lines[-1] += " " + ln.strip()
        elif ln.startswith("**") and not ln.rstrip().endswith("**"):
            lines += ["", ln]
        else:
            lines.append(ln)
    return r5.md_paragraphs("\n".join(lines), skip_title=False)


# ---------------------------------------------------------------- sections


def section0(d, commit: str):
    d.add("<h1>DATA 260 Homework 10</h1>")
    d.add("<div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table(
        [
            ["GitHub repository", config.REPO_URL],
            ["SID4 / PREFIX", f"9486 / {config.PREFIX}"],
            ["SEED / VERIFY_SEED", f"{config.SEED} / {config.VERIFY_SEED}"],
            ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME} (primary entity: Listing, MySQL s9486_rel)"],
            ["Hardware", HARDWARE],
            ["System under test", "HW8 Kafka planner -> writer -> reviewer (llama3.2:3b) behind the HW9 Redis cache"],
            [
                "Judge",
                f"deepeval GEval with a local judge: {JUDGE_SETTINGS['model']} in Ollama, temperature "
                f"{JUDGE_SETTINGS['temperature']}, num_ctx {JUDGE_SETTINGS['num_ctx']}, 1-5 rubric",
            ],
            ["Tagged commit hash", f"{commit} (tag hw10)"],
        ],
        header=False,
        cls="kv",
    )
    d.p(
        "New code: `Homework10/hw10/` (judge, evaluator, traced ingress, analysis), `Homework10/scripts/` (one script "
        "per part, run with `make`), `Homework10/dashboard/app.py` (Streamlit), `Homework10/data/` (frozen eval "
        "cases and my labels) and `kafka_agents/tracing.py` (spans). Evidence is in `reports/hw10/` "
        "(`RUN_LOG.txt`, `raw/spans.jsonl`, `raw/*.json`, `METRICS.md`, `AI_USE.md`, `verification.json`)."
    )


def part1(d):
    d.h2("Part 1. Streamlit Operations Dashboard")
    d.p(
        "`make dashboard` starts `Homework10/dashboard/app.py` on port 8501. It only reads the evidence files and "
        "Redis; it does not run the pipeline. File reads use `@st.cache_data(ttl=30)` and the Redis connection uses "
        "`@st.cache_resource`, so a page refresh does not reopen Redis or re-parse the span log."
    )
    code(d, "Homework10/dashboard/app.py", "@st.cache_data(ttl=30)", "return out")
    d.h3("1.1 Summary page")
    d.add(metrics_section("summary"))
    fig(d, "d1_summary", "Summary page: requests, hit vs miss, error rate, latency, time window and data source.")
    d.h3("1.2 Evaluation page")
    fig(
        d,
        "d2_evaluation",
        "Evaluation page: Part 2 scores by stage and Part 3 judge validation (Spearman, MAD, repeatability).",
    )
    d.h3("1.3 Trace lookup page")
    fig(
        d,
        "d3_trace",
        "Trace lookup page with the cache-miss trace: every stage in order with start, end, duration, "
        "status and error.",
    )


def part2(d):
    d.h2("Part 2. Automated Evaluation of the Kafka Pipeline")
    d.p(
        "After a question flows through the pipeline, the evaluator reads `s9486_tasks` (plan), `s9486_drafts` (draft) "
        "and `s9486_final` (final answer) from the offsets saved before the question was sent, and keeps the "
        "messages whose `correlation_id` is the request's trace_id. It keeps each original message with its "
        "topic/partition/offset/timestamp. Malformed JSON is skipped and counted; the read has a 30 s limit, and the "
        "three GEval calls run under one deadline (300 s) with a 90 s HTTP timeout each, so a bad message or a down "
        "judge ends as an `evaluation` span with status error instead of a hang (this happened once for real when "
        "Docker stopped responding: the request was recorded as an error and the run continued)."
    )
    code(d, "Homework10/hw10/evaluator.py", "if not isinstance(msg, dict) or msg.get", "}")
    code(d, "Homework10/hw10/judge.py", "def metric(", "_include_g_eval_suffix=False")
    d.h3("Results for the end-to-end test question")
    d.add(metrics_section("part2"))
    d.h3("Scores by stage over the 50 evaluated requests")
    d.add(metrics_section("stage-scores"))
    d.h3("What the scores say about coordination")
    d.add(notes("Coordination"))


def part3(d):
    d.h2("Part 3. Validating the Judge")
    v = load("judge_validation.json")
    frozen = "; ".join(f"`{Path(k).name}` first committed {c}" for k, c in v["frozen_commits"].items())
    d.p(
        f"`eval_cases.json` holds 20 real Writer drafts from my system (llama3.2:3b drafts from the HW8/HW9 runs, read "
        f"from `s9486_drafts`, one per distinct question, picked with VERIFY_SEED). I labeled each draft's helpfulness "
        f"1-5 by hand in `human_labels.csv` and committed both files before any judge score existed ({frozen}). The "
        f"judge run started {v['run_at']} and the script refuses to run if either file is uncommitted or changed. "
        f"Settings: {json.dumps(v['judge'])}."
    )
    d.add(metrics_section("judge"))
    d.p(
        "Raw per-case data (case, trace_id, question, human label, the 3 judge scores, run-1 reason): "
        "`reports/hw10/raw/judge_validation_cases.csv`."
    )
    d.h3("Would I trust this judge to gate a deployment?")
    d.add(notes("Judge trust"))


def part4(d):
    d.h2("Part 4. Distributed Tracing and Latency")
    d.h3("4.1 Trace propagation")
    d.p(
        "The trace_id is created once, at the cache lookup, and is sent as the HW8 `correlation_id`, so the inbox, "
        "tasks, drafts and final messages, the agents' spans and the evaluation all carry the same id (no second id). "
        "Every stage appends one JSON span to `raw/spans.jsonl`: `cache_lookup` (with `cache: hit|miss`), "
        "`pipeline`, `planner`, `writer`, `reviewer` (written by the agents, with `queue_wait_ms` = time the message "
        "waited on its input topic, from the Kafka record timestamp), `cache_store`, `evaluation`, and `request`."
    )
    code(
        d,
        "kafka_agents/base.py",
        "produced_ms = getattr(record",
        'write_span(cid, self.name, span_start, time.time(), "ok"',
    )
    ex = load("trace_examples.json")["traces"]
    span = next(s for s in journey(by_trace(read_spans())[ex["miss"]]) if s["stage"] == "writer")
    block(d, "one span from raw/spans.jsonl (Writer, cache-miss trace):\n" + json.dumps(span, indent=1))
    d.h3("4.2 Trace examples (hit, successful miss, failed)")
    d.add(metrics_section("traces"))
    d.h3("4.3 Stage latency over 50 confirmed cache misses")
    d.add(metrics_section("latency"))
    d.add(notes("Latency"))


def verification(d):
    d.h2("Verification and Run Notes")
    v = json.loads((REPORT_DIR / "verification.json").read_text(encoding="utf-8"))
    d.p(
        f"`make verify-hw10` re-checks the saved evidence: {v['passed']}/{v['total']} checks passed (commit "
        f"`{v['commit']}`{', uncommitted changes' if v['dirty_tree'] else ''}). `make test-hw10` runs the automated "
        "checks (no model calls)."
    )
    d.table(
        [["Check", "Result"]] + [[c["check"], "PASS" if c["ok"] else "FAIL"] for c in v["checks"]],
        widths=["80%", "20%"],
    )
    d.add(notes("Run notes"))


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
            f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW10 - Kavan Siddesh</title>"
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
    shutil.copy(OUT_PDF, NAMED_PDF)
    print(
        f"wrote {OUT_PDF.relative_to(ROOT)} and {NAMED_PDF.relative_to(ROOT)} (commit {commit[:12]}, "
        f"{d.fig_no} figures)"
    )
    if MISSING:
        print(f"DRAFT - MISSING screenshots shown as red boxes: {', '.join(dict.fromkeys(MISSING))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
