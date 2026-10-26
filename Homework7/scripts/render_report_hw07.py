#!/usr/bin/env python3
"""Render the HW7 report (reports/hw07/report.pdf and Kumar_HW7.pdf).

Same layout as the HW5/HW6 reports (reuses scripts/render_report_hw05.py): configuration table first, one
section per part, labeled screenshots, tables built from reports/hw07/raw/. HW7 also asks for short code
snippets, so they are cut straight from the real source files (never retyped). A screenshot that does not
exist yet is shown as a clearly marked MISSING box, so a draft never pretends to have evidence it does not.
Main headings 14 pt bold, subheadings 12 pt bold, body 11 pt.

Usage (repo root):
    make report-hw07                                   # commit hash = HEAD
    COMMIT_HASH=<sha> python Homework7/scripts/render_report_hw07.py
"""

from __future__ import annotations

import ast
import csv
import html
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hw7_common import FIXTURES, RAW, REPORT_DIR, ROOT

import config
from bikeshare.tools import TOOL_SCHEMAS

# Loaded after the hw*_common import, which puts scripts/ on sys.path (a plain import would be sorted above it).
r5 = importlib.import_module("render_report_hw05")

r5.SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW7.pdf"
CSS = r5.CSS.replace("Homework 5", "Homework 7") + (
    ".missing { border: 2px dashed #ef4444; color: #b91c1c; padding: 10pt; margin: 6pt 0 12pt 0; }\n"
    ".cmd { white-space: pre-wrap; font-size: 8.5pt; }\n"
)
HARDWARE = "MacBook Air with Apple M1 chip (8 GB unified memory)"
r5.CROPS = {}  # set per screenshot below once the real screenshots exist
MISSING: list[str] = []


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def rows(name: str) -> list[dict]:
    with (RAW / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig(d, name: str, caption: str, width: str = "100%") -> None:
    if (r5.SHOTS / f"{name}.png").exists():
        d.fig(name, caption, width=width)
    else:
        MISSING.append(name)
        d.add(f"<div class='missing'><b>MISSING SCREENSHOT ({html.escape(name)}.png):</b> {html.escape(caption)}</div>")


def code(d, text: str) -> None:
    d.add(f"<div class='cmd'>{html.escape(text.rstrip())}</div>")


def func_src(path: str, name: str, max_lines: int = 40) -> str:
    src = (ROOT / path).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            lines = ast.get_source_segment(src, node).splitlines()
            more = f"\n    ... ({len(lines) - max_lines} more lines in {path})" if len(lines) > max_lines else ""
            return "\n".join(lines[:max_lines]) + more
    raise KeyError(f"{name} not in {path}")


def between(path: str, start: str, end: str) -> str:
    src = (ROOT / path).read_text(encoding="utf-8")
    i = src.index(start)
    return src[i : src.index(end, i)].rstrip()


# ---------------------------------------------------------------- sections


def section0(d, commit: str):
    d.add("<h1>DATA 260 Homework 7</h1>")
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
            ["Local model", f"{config.OLLAMA_MODEL} (Ollama); Part 4 agent framework: LangGraph + langchain-ollama"],
            ["Tagged commit hash", f"{commit} (tag hw7)"],
        ],
        header=False,
        cls="kv",
    )
    d.p(
        "Both collaborators (Sbnikitha, supriyaselvanganesan) have access to the repository. HW7 extends the same "
        "root-level application as HW5/HW6; HW7 scripts, tests and fixtures are in `Homework7/` and the results "
        "(`RUN_LOG.txt`, `raw/`, `METRICS.md`, `AI_USE.md`, `THREAT_MODEL.md`, `verification.json`) in `reports/hw07/`."
    )


def part1(d):
    d.h2("Part 1. JWT Authentication, Roles, and Linting")
    d.h3("I-III. Login, roles and the MySQL users table")
    d.p(
        "I replaced the HW4 session cookie with JWT bearer tokens on my existing `/listings` and `/landlords` routes "
        "(the session version stays at the hw4 tag). `scripts/migrate_hw07.py` added `username` (unique) and `role` "
        "(CHECK reader/writer/moderator) to my existing `users` table and created three test users. Only bcrypt hashes "
        "are stored. Login fetches the user from MySQL, checks the hash, and only then signs the token."
    )
    code(d, func_src("backend/app/security.py", "get_current_user", 18))
    code(d, func_src("backend/app/security.py", "require_roles", 14))
    code(d, between("backend/app/main.py", '@app.post("/auth/login"', "# ----------"))
    demo = load("auth_demo.json")["cases"]
    t = [["Case", "Request", "As", "Status"]]
    t += [[c["case"], f"{c['method']} {c['path']}", c["as"] or "no token", str(c["status"])] for c in demo]
    d.table(t, widths=["40%", "28%", "17%", "15%"])
    d.h3("IV. Expected behavior")
    fig(d, "p1_login", "POST /auth/login: valid credentials return a JWT (200); a wrong password returns 401.")
    fig(d, "p1_me_401", "GET /auth/me without a token returns 401.")
    fig(d, "p1_token_401", "GET /auth/me with an invalid (tampered) or expired token returns 401.")
    fig(d, "p1_create", "POST /landlords as reader returns 403; as writer (or moderator) returns 201.")
    fig(d, "p1_delete", "DELETE /listings/{id} as writer returns 403; as moderator returns 200.")
    fig(d, "p1_list", "GET /listings with a valid token returns 200.")
    d.h3("V. Linting (Ruff + pre-commit)")
    code(d, (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    fig(
        d,
        "p1_lint",
        "Commit attempt: pre-commit runs Ruff and fails on the lint errors, the issues are fixed, and "
        "the next commit passes.",
    )


def part2(d):
    att = rows("reliability_attempts.csv")
    er = load("error_recovery.json")
    d.h2("Part 2. Hand-written Agent Loop")
    d.p(
        "`run_agent` (HW5) now checks every proposed call before it runs. An unknown tool, malformed arguments or a "
        "schema failure is sent back once with the exact problem, and the loop stops with `repair_limit` after two "
        "repairs in a row fail. It logs every tool call (name and inputs) and returns the total number of calls."
    )
    code(d, between("domain_tools/agent.py", "        call = calls[0]", "        if is_blocked:"))
    code(d, func_src("domain_tools/validation.py", "validate_call", 26))
    d.h3("I. Verification tasks")
    tasks = json.loads((FIXTURES / "agent_tasks.json").read_text(encoding="utf-8"))["tasks"]
    d.table([["Task", "Fixed prompt"]] + [[k, v["prompt"]] for k, v in tasks.items()], widths=["8%", "92%"])
    fig(
        d,
        "p2_tasks",
        "The agent running tasks A, B and C with no follow-up prompting: tool calls with inputs, "
        "final answer and total tool calls.",
    )
    d.h3("II. Error recovery")
    d.p(
        f"Asked for LST-99999, `get_listing` returned `{er['check']['tool_error']}` and the agent answered "
        f'(stop reason `{er["summary"]["stop_reason"]}`): "{(er["summary"]["final_answer"] or "")[:220]}"'
    )
    fig(d, "p2_error", "Nonexistent listing id handled without crashing.")
    d.h3("III. Reliability (21 attempts)")
    d.add(_metrics_section("part2-table"))
    lost = sum("lost_chain" in a["failure_kinds"] for a in att)
    one = sum(a["tool_calls"] == "1" for a in att)
    d.p(
        f"The repair path fixed every malformed call (all were `min_units: null`), so well-formed calls went up to "
        f"100%. The real problem was the chain: in {one} of {len(att)} attempts llama3.2:3b made one tool call "
        f"and then answered from that result, so {lost} attempts are lost multi-step chains and the strict "
        "verifier passed none. "
        "I checked that my message format was not the cause by also sending Ollama's `tool_name` field; the model "
        "still stopped after one call."
    )


def _metrics_section(marker: str) -> str:
    text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
    body = text[
        text.index(f"<!-- {marker}:start -->") + len(f"<!-- {marker}:start -->") : text.index(f"<!-- {marker}:end -->")
    ].strip()
    out, table = [], []

    def flush():
        if table:
            cells = [[c.strip() for c in line.strip().strip("|").split("|")] for line in table if "---" not in line]
            out.append(("table", cells))
            table.clear()

    for line in body.splitlines():
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


def part3(d):
    comp = load("reflexion_comparison.json")
    refl = [json.loads(line) for line in (RAW / "reflections.jsonl").read_text(encoding="utf-8").splitlines()]
    d.h2("Part 3. Reflexion and Bounded Self-Correction")
    d.p(
        "After each fixed task the deterministic verifier checks the tool chain and the answer against MySQL. If it "
        "fails, I write one short reflection from the verifier evidence (not from the model's reasoning) and retry "
        "with "
        "it as a separate, labelled untrusted message. At most two retries, a shared budget of 10 tool calls and 9,000 "
        "tokens, and the run always ends with success, budget_exhausted or human_review."
    )
    code(d, func_src("domain_tools/fixed_tasks.py", "verify", 34))
    code(d, func_src("domain_tools/reflexion.py", "write_reflection", 20))
    d.h3("Stored reflection (failed then retried)")
    retried = next((r for r in comp if r["loop"] == "reflexion" and r["retries"] > 0), None)
    if retried and retried["reflections"]:
        r = retried["reflections"][0]
        d.p(f"Task {r['task']}, run {r['run_id']}, user {r['user_id']}, after attempt {r['attempt']}:")
        d.bullets(
            [f"Evidence: {e}" for e in r["evidence"]]
            + [
                f"What went wrong: {r['what_went_wrong']}",
                f"Revised strategy: {r['revised_strategy']}",
                f"Outcome of this run: {retried['stop_reason']} after {retried['retries']} retry(ies)",
            ]
        )
    d.p(f"All {len(refl)} reflections are in `raw/reflections.jsonl`.")
    d.h3("Comparison on the same three tasks")
    d.add(_metrics_section("part3-table"))


def part4(d):
    d.h2("Part 4. Framework ReAct/MRKL Bike-share Agent")
    d.p(
        "I chose Bay Wheels. All four official pricing pages loaded as plain HTML, but Bay Wheels is the only one that "
        "sells a Month pass ($29/month), so the monthly-membership question fits it directly. The agent is LangGraph's "
        "`create_react_agent` with ChatOllama (llama3.2:3b) and three pure-function tools that all return "
        "`{success, data, error, source, ts}`."
    )
    code(d, json.dumps(TOOL_SCHEMAS, indent=1)[:1800])
    code(
        d,
        func_src("bikeshare/tools.py", "check_read_only", 14)
        + "\n\n"
        + func_src("bikeshare/tools.py", "calculator", 18),
    )
    code(d, func_src("bikeshare/tools.py", "policy_retriever", 26))
    for name, title in (
        ("membership_wins", "Scenario 1 - membership wins"),
        ("payperuse_wins", "Scenario 2 - pay-per-use wins"),
    ):
        r = load(f"bikeshare_{name}.json")
        snap = load(f"pricing_snapshot_{name}.json")
        summ = load(f"bikeshare_trip_summary_{name}.json")
        v = r["verified"]
        d.h3(title)
        fig(
            d,
            f"p4_ui_{name}",
            f"UI for {name}: tool-call timeline, cost comparison, decision, citations and the "
            f"metrics strip (steps, total time, stop reason).",
        )
        d.p(
            f"Data: {summ['rows']} real trips, {summ['first_ride'][:10]} to {summ['last_ride'][:10]} "
            f"({summ['selection_rule']}). Agent decision: **{r['agent_decision']}**; tool-computed: "
            f"**{v['decision']}** ({'agrees' if r['decision_matches_tools'] else 'does not agree'}). Pay-per-use "
            f"${v['pay_per_use_total']:,.2f} vs membership ${v['membership_total']:,.2f} (${v['membership_fees']:,.2f} "
            f"in Month pass fees for {v['months']} months + ${v['membership_residual_charges']:,.2f} member per-minute "
            f"charges). Break-even is {v['break_even_rides_per_month']} rides per month and the rider averaged "
            f"{v['rides_per_month']}. Stop reason `{r['stop_reason']}`, {r['steps']} steps, {r['total_time_s']} s."
        )
        d.p("Agent justification: " + " ".join((r["final_text"] or "").split())[:900])
        d.table(
            [["Week", "Rides", "Avg minutes", "Pay-per-use spend"]]
            + [
                [w["week"], str(w["rides"]), str(w["avg_minutes"]), f"${w['pay_per_use_spend']:.2f}"]
                for w in v["weekly_last_8"]
            ]
        )
        d.p(
            f"Pricing snapshot: {snap['source_url']}, accessed {snap['access_date']}, SHA-256 `{snap['sha256']}` "
            f"(text in `raw/pricing_snapshot_{name}.txt`)."
        )
    d.p(
        "Assumptions: per-minute charges are billed per started minute; the Month pass is counted for every month with "
        "a ride; the page lists no Month-pass unlock fee for classic bikes, so member unlocks are $0; the public data "
        "has no rider id, so each scenario is real trips treated as one rider, with only the dates moved."
    )


def part5(d):
    d.h2("Part 5. Prompt Injection and Tool Security")
    tm = (REPORT_DIR / "THREAT_MODEL.md").read_text(encoding="utf-8")
    d.add(r5.md_paragraphs(tm))
    d.h3("Attack fixture")
    d.p(
        "`Homework7/fixtures/hostile_pricing.html` copies the real price table and adds three injected instructions "
        "next to the prices (so the retriever returns them). I only ran it against my own agent through a file:// URL."
    )
    d.h3("Results")
    d.add(_metrics_section("part5-table"))
    res = rows("injection_results.csv")
    ex = [["Condition", "Run", "Decision", "Rows before/after", "Leaked ids", "Answer excerpt"]]
    ex += [
        [
            r["condition"],
            r["run"],
            r["agent_decision"] or "-",
            f"{r['rows_before']}/{r['rows_after']}",
            r["leaked_ride_ids"],
            r["answer_excerpt"][:160],
        ]
        for r in res
        if r["run"] == "1"
    ]
    d.table(ex, widths=["12%", "6%", "18%", "12%", "8%", "44%"])
    d.h3("Why the tool boundary is different from a prompt-only defense")
    d.p(
        "The prompt defense only asks the model to behave; the model can still decide to follow the page, and a small "
        "model often does. The read-only check in `csv_sql` runs in my code before SQLite sees the query, so a DELETE "
        "or DROP is refused no matter what the page or the model says. A prompt can lower the chance of an attack; a "
        "tool boundary removes the capability."
    )


def part6(d):
    d.h2("Part 6. File Tools and a Safety Gate")
    code(d, between("agent_tools/safety_gate.py", "SAFE_PREFIXES = (", "\n)\n") + "\n)")
    code(d, func_src("agent_tools/safety_gate.py", "destructive_reason", 34))
    code(d, func_src("agent_tools/safety_gate.py", "confirm_bash", 16))
    code(d, func_src("agent_tools/file_tools.py", "FileTools", 24))
    fig(
        d,
        "p6_run",
        "One run: glob -> search -> read finds config_loader.py (DEBUG) and prints it, then the 10-command "
        "safety-gate test (5 allowed, 5 blocked) and the v1 false allows now blocked.",
    )
    d.add(_metrics_section("part6-table"))
    v1 = load("safety_gate_v1_false_allows.json")
    d.p(
        "False allows I found in the first version: "
        + "; ".join(f"`{r['command']}`" for r in v1["results"])
        + ". The redirect rule only looked for targets starting with `/`, so `~`, `$HOME` and `../..` paths slipped "
        "through. I fixed it by also treating those targets as writes outside the sandbox."
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
        for section in (section0, part1, part2, part3, part4, part5, part6, ai_use):
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
            f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW7 - Kavan Siddesh</title>"
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
        print(f"DRAFT - MISSING screenshots shown as red boxes: {', '.join(MISSING)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
