#!/usr/bin/env python3
"""Render the HW5 report (reports/hw05/report.pdf and Kumar_HW5.pdf).

Same layout idea as the HW4 report: configuration table first, one section per
part, labeled screenshots with captions, result tables built from the raw files.
Only what the HW5 handout asks for; no source code (it is in the GitHub repository).

Screenshots come from reports/hw05/screenshots/. Only the rendered copies are
cropped (browser/app chrome removed) - the files in screenshots/ are untouched.
The page is HTML printed to PDF by headless Google Chrome, so heading and body
sizes are exact points: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt.

Usage (repo root):
    python scripts/render_report_hw05.py                 # commit hash = HEAD
    COMMIT_HASH=<sha> python scripts/render_report_hw05.py
"""

from __future__ import annotations

import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

from hw5_common import RAW, REPORT_DIR, ROOT

import config

SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW5.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Crop boxes as fractions (left, top, right, bottom) of the original screenshot.
CROPS = {
    "p1_db_": (0.205, 0.115, 0.935, 0.66),         # Workbench: query + result rows only
    "p2_meals_ingredient": (0.02, 0.098, 0.705, 0.66),   # long results: first ~20 lines
    "p2_meals_random": (0.02, 0.098, 0.705, 0.66),
    "p2_meals_details": (0.02, 0.098, 0.705, 0.66),
    # Terminals: drop empty right margin and the VS Code panel tabs / status bar
    "p3_retry_demo": (0.0, 0.09, 0.80, 1.0),
    "p3_retry_experiment": (0.0, 0.0, 0.71, 0.91),
    "p4_offline_tests": (0.0, 0.075, 0.46, 0.945),
    "p5_safety": (0.0, 0.0, 0.965, 0.915),
    "p5_agent_runs": (0.0, 0.0, 0.965, 0.96),
    "p1_landlord_": (0.178, 0.125, 0.822, 0.975),  # Postman: drop sidebar, AI panel, browser bar
    "p1_listing_": (0.178, 0.125, 0.822, 0.975),
    "p1_relationship": (0.178, 0.125, 0.822, 0.975),
    "p1_err_": (0.178, 0.125, 0.822, 0.975),
    "p2_": (0.02, 0.098, 0.705, 0.935),            # Inspector: keep tool list + result, drop message log
}


# ---------------------------------------------------------------- helpers

def esc(s) -> str:
    return html.escape(str(s))


def inline_md(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<span class='id'>\1</span>", s)
    return s


def md_paragraphs(md: str, skip_title: bool = True) -> str:
    lines = md.strip().splitlines()
    if skip_title and lines and lines[0].startswith("# "):
        lines = lines[1:]
    out, para, items = [], [], []

    def flush():
        if para:
            out.append(f"<p>{inline_md(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline_md(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for ln in lines:
        if not ln.strip():
            flush()
        elif ln.startswith("- "):
            if para:
                out.append(f"<p>{inline_md(' '.join(para))}</p>")
                para.clear()
            items.append(ln[2:].strip())
        elif ln.startswith("**") and ln.rstrip().endswith("**"):
            flush()
            out.append(f"<p class='q'>{inline_md(ln.strip())}</p>")
        else:
            if items:
                flush()
            para.append(ln.strip())
    flush()
    return "\n".join(out)


def trim_bottom(img: Image.Image, margin: int = 24) -> Image.Image:
    """Cut empty rows at the bottom (same color as the bottom-left pixel)."""
    bg = Image.new(img.mode, img.size, img.getpixel((5, img.height - 5)))
    diff = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 40 else 0)
    # ignore a thin strip at the right edge (scrollbars)
    box = diff.crop((0, 0, int(img.width * 0.97), img.height)).getbbox()
    if not box:
        return img
    return img.crop((0, 0, img.width, min(img.height, box[3] + margin)))


def prepare(name: str, tmp: Path) -> str | None:
    src = SHOTS / f"{name}.png"
    if not src.exists():
        return None
    img = Image.open(src).convert("RGB")
    for prefix, (l, t, r, b) in CROPS.items():
        if name.startswith(prefix):
            w, h = img.size
            img = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
            if not name.startswith(("p3_", "p4_", "p5_")):
                img = trim_bottom(img)
            break
    if img.width > 2600:
        img = img.resize((2600, round(img.height * 2600 / img.width)), Image.LANCZOS)
    out = tmp / f"{name}.jpg"
    img.save(out, "JPEG", quality=90, optimize=True)
    return out.name


class Doc:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.parts: list[str] = []
        self.fig_no = 0
        self.fig_of: dict[str, int] = {}
        self.missing: list[str] = []
        self.pending_label = ""

    def label(self, text: str):
        """Bold run-in label that stays on the same page as the next figure."""
        self.pending_label = f"<p class='lbl'><b>{esc(text)}</b></p>"

    def add(self, s: str):
        self.parts.append(s)

    def h2(self, text: str, new_page: bool = True):
        self.add(f"<h2 class='{'np' if new_page else ''}'>{esc(text)}</h2>")

    def h3(self, text: str):
        self.add(f"<h3>{esc(text)}</h3>")

    def p(self, text: str):
        self.add(f"<p>{inline_md(text)}</p>")

    def bullets(self, items: list[str]):
        self.add("<ul>" + "".join(f"<li>{inline_md(i)}</li>" for i in items) + "</ul>")

    def table(self, rows: list[list], header: bool = True, widths: list[str] | None = None, cls: str = ""):
        if len(rows) > 12:
            cls += " long"
        cols = "".join(f"<col style='width:{w}'>" for w in widths) if widths else ""
        body = []
        for i, row in enumerate(rows):
            tag = "th" if header and i == 0 else "td"
            body.append("<tr>" + "".join(f"<{tag}>{inline_md(c)}</{tag}>" for c in row) + "</tr>")
        self.add(f"<table class='{cls}'><colgroup>{cols}</colgroup>{''.join(body)}</table>")

    def fig(self, name: str, caption: str, width: str = "100%", max_h: str | None = None):
        src = prepare(name, self.tmp)
        if src is None:
            self.missing.append(name)
            return
        self.fig_no += 1
        self.fig_of[name] = self.fig_no
        style = f"width:{width};" + (f"max-height:{max_h};object-fit:contain;" if max_h else "")
        label, self.pending_label = self.pending_label, ""
        self.add(f"<figure>{label}<img src='{src}' style='{style}'><figcaption><b>Figure {self.fig_no}.</b> "
                 f"{inline_md(caption)} <span class='fn'>({esc(name)}.png)</span></figcaption></figure>")

    def figs2(self, items: list[tuple[str, str]]):
        cells = []
        for name, caption in items:
            src = prepare(name, self.tmp)
            if src is None:
                self.missing.append(name)
                continue
            self.fig_no += 1
            cells.append(f"<figure><img src='{src}'><figcaption><b>Figure {self.fig_no}.</b> {inline_md(caption)} "
                         f"<span class='fn'>({esc(name)}.png)</span></figcaption></figure>")
        self.add("<div class='two'>" + "".join(cells) + "</div>")


def find_font() -> str | None:
    candidates = list(Path("/").glob("Users/*/Library/Fonts/DejaVuSans.ttf")) + list(Path("/Library/Fonts").glob("DejaVuSans.ttf"))
    # matplotlib ships DejaVu Sans (the font the HW4 report used); check the system Pythons too
    candidates += list(Path("/Library/Frameworks/Python.framework/Versions").glob(
        "*/lib/python3*/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf"))
    for venv in (ROOT / ".venv", ROOT / "Homework4" / ".venv", ROOT / "Homework1" / ".venv"):
        candidates += list(venv.glob("lib/python3*/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf"))
    return str(candidates[0].parent) if candidates else None


CSS = """
@page { size: Letter; margin: 0.6in 0.65in 0.75in 0.65in;
  @bottom-left { content: "DATA 260 - Homework 5  |  Kavan Siddesh (SID4 9486)"; font: 8.5pt var(--f); color: #6b7280; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8.5pt var(--f); color: #6b7280; } }
:root { --f: 'DejaVu Sans', 'Helvetica Neue', Arial, sans-serif; }
body { font-family: var(--f); font-size: 11pt; line-height: 1.38; color: #111827; margin: 0; }
h1 { font-size: 14pt; font-weight: bold; margin: 0 0 2pt 0; }
.sub { font-size: 11pt; color: #374151; margin: 0 0 10pt 0; }
h2 { font-size: 14pt; font-weight: bold; margin: 14pt 0 8pt 0; padding-bottom: 4pt; border-bottom: 1.5px solid #9ca3af; }
h2.np { break-before: page; margin-top: 0; }
h3 { font-size: 12pt; font-weight: bold; margin: 12pt 0 5pt 0; break-after: avoid; }
p { margin: 0 0 7pt 0; text-align: left; }
p.q { margin-top: 9pt; }
ul { margin: 0 0 7pt 0; padding-left: 18pt; } li { margin: 1.5pt 0; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 10pt 0; font-size: 10pt; break-inside: avoid; table-layout: fixed; }
table.long { break-inside: auto; } tr { break-inside: avoid; }
p.lbl { text-align: left; margin: 2pt 0 4pt 0; }
th, td { border: 1px solid #d1d5db; padding: 3.5pt 5pt; vertical-align: top; text-align: left; overflow-wrap: anywhere; }
th { background: #eef2f7; font-weight: bold; }
tr:nth-child(even) td { background: #f9fafb; }
table.kv td:first-child { background: #f3f4f6; width: 34%; }
.id { font-family: 'DejaVu Sans Mono', Menlo, monospace; font-size: 9.5pt; }
figure { margin: 6pt 0 12pt 0; break-inside: avoid; text-align: center; }
figure img { border: 1px solid #cbd5e1; display: block; margin: 0 auto; }
figcaption { font-size: 9.5pt; color: #374151; margin-top: 3pt; text-align: left; }
.fn { color: #9ca3af; }
.two { display: flex; gap: 12pt; align-items: flex-start; break-inside: avoid; }
.two figure { flex: 1; margin-top: 4pt; } .two img { width: 100%; }
.note { border-left: 3px solid #9ca3af; padding: 4pt 8pt; background: #f9fafb; margin: 6pt 0 10pt 0; }
.cmd { font-family: 'DejaVu Sans Mono', Menlo, monospace; font-size: 9pt; background: #f3f4f6; border: 1px solid #e5e7eb; padding: 6pt 8pt; white-space: pre; margin: 4pt 0 10pt 0; }
"""


# ---------------------------------------------------------------- sections

def section0(d: Doc, commit: str):
    d.add("<h1>DATA 260 Homework 5</h1>")
    d.add("<div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table([
        ["GitHub repository", config.REPO_URL],
        ["SID4", "9486"],
        ["PORT_BASE", str(config.PORT_BASE)],
        ["PREFIX", config.PREFIX],
        ["SEED", str(config.SEED)],
        ["VERIFY_SEED", str(config.VERIFY_SEED)],
        ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME}"],
        ["Hardware", config.HARDWARE],
        ["Local model", f"{config.LLM_MODEL} (Ollama)"],
        ["Tagged commit hash", f"{commit} (tag hw5)"],
    ], header=False, cls="kv")
    d.p("Both collaborators (Sbnikitha, supriyaselvanganesan) have access to the repository.")


def part1(d: Doc):
    d.h2("Part 1. FastAPI + MySQL Extension")
    d.h3("I. Database")
    d.fig("p1_db_landlords", "landlords table (related entity).", width="88%")
    d.fig("p1_db_listings", "listings table (primary entity) with landlord_id foreign key.", width="88%")
    d.h3("II. API (Postman)")
    d.label("Landlords")
    d.fig("p1_landlord_create", "Create landlord - 201.")
    d.fig("p1_landlord_list", "Get all landlords with pagination - 200.")
    d.fig("p1_landlord_get", "Get one landlord - 200.")
    d.fig("p1_landlord_update", "Update landlord - 200.")
    d.label("Listings")
    d.fig("p1_listing_create", "Create listing - 201.")
    d.fig("p1_listing_list", "Get all listings with pagination - 200.")
    d.fig("p1_listing_get", "Get one listing - 200.")
    d.fig("p1_listing_update", "Update listing - 200.")
    d.fig("p1_listing_delete", "Delete listing - 200.")
    d.label("Relationship query and errors")
    d.fig("p1_relationship", "All listings of landlord 1 - 200.")
    d.fig("p1_err_duplicate_409", "Duplicate email (unique constraint) - 409.")
    d.fig("p1_err_format_422", "Invalid listing_code format (validation) - 422.")
    d.fig("p1_err_restrict_409", "Delete landlord that still has listings - 409.")
    d.fig("p1_err_notfound_404", "Listing not found - 404.")
    d.h3("III. Redux Client")
    d.fig("p1_redux_home", "Home - fetchListings thunk/slice and the list read from Redux state.")
    d.fig("p1_redux_create", "Create - createListing thunk and the new listing on Home.")
    d.fig("p1_redux_update", "Update - updateListing thunk and the updated listing on Home.")
    d.fig("p1_redux_delete", "Delete - deleteListing thunk and the listing removed from Home.")


def part2(d: Doc):
    d.h2("Part 2. MCP Tool Servers")
    d.h3("A. TheMealDB Server (meals)")
    d.fig("p2_meals_search", "search_meals_by_name - query \"Arrabiata\", limit 5.")
    d.fig("p2_meals_ingredient", "meals_by_ingredient - ingredient \"chicken\", limit 12.")
    d.fig("p2_meals_random", "random_meal.")
    d.fig("p2_meals_details", "meal_details - id 52771.")
    d.h3("B. Domain Server (s9486_listings)")
    d.fig("p2_domain_search_ok", "search_listings - valid call.")
    d.fig("p2_domain_search_invalid", "search_listings - invalid call.")
    d.fig("p2_domain_detail_ok", "get_listing - valid call.")
    d.fig("p2_domain_detail_invalid", "get_listing - invalid call.")
    d.fig("p2_domain_stats_ok", "landlord_portfolio_stats - valid call.")
    d.fig("p2_domain_stats_invalid", "landlord_portfolio_stats - invalid call.")


def part3(d: Doc):
    rec = json.loads((RAW / "mcp_domain_calls.json").read_text())
    from domain_tools.contracts import REJECTED
    from domain_tools.execute import TOOL_SPECS

    by_call = {(c["tool"], json.dumps(c["arguments"], sort_keys=True)): c for c in rec["calls"]}
    d.h2("Part 3. Tool Contracts Under Stress")
    d.h3("1. Tool contracts (rejected calls from Part 2B)")
    rows = [["Tool", "Expected input schema", "Rejected input", "Returned error", "Why rejected"]]
    for name, spec in TOOL_SPECS.items():
        parts = []
        for k, v in spec["schema"]["properties"].items():
            rng = []
            if "minLength" in v:
                rng.append(f"{v['minLength']}-{v['maxLength']} chars")
            if "minimum" in v:
                rng.append(f"min {v['minimum']}" + (f", max {v['maximum']}" if "maximum" in v else ""))
            if "pattern" in v:
                rng.append("LST- + 5 digits")
            req = " (required)" if k in spec["schema"]["required"] else ""
            parts.append(f"{k}: {v['type']}{req}" + (f", {', '.join(rng)}" if rng else ""))
        bad, _, why = REJECTED[name]
        out = by_call[(name, json.dumps(bad, sort_keys=True))]["result"]
        rows.append([name, "; ".join(parts), json.dumps(bad),
                     f"{{\"ok\": false, \"data\": null, \"error\": \"{out['error']}\"}}", why])
    d.table(rows, widths=["15%", "25%", "14%", "28%", "18%"])

    d.h3("2. Timeouts and retry with exponential backoff")
    d.fig("p3_retry_demo", "Success on first attempt, failure then retry success, and failure after all retries.")

    s = json.loads((RAW / "retry_summary.json").read_text())
    d.h3("3. Failure simulation with VERIFY_SEED (50 calls per rate)")
    t = [["Injected failure rate", "Success rate", "Mean latency (ms)", "p99 latency (ms)"]]
    for r in s["rates"]:
        t.append([f"{r['failure_rate']:.0%}", f"{r['success_rate']:.0%}", f"{r['mean_latency_ms']:.2f}",
                  f"{r['p99_latency_ms']:.2f}"])
    d.table(t)
    d.fig("p3_retry_experiment", "150 calls at 0%, 20% and 50% (raw data in reports/hw05/raw/).")

    r20, r50 = s["rates"][1], s["rates"][2]
    d.h3("4. Evaluation")
    d.p(f"**Interactive assistant:** the policy is suitable. At 20% failures every call still succeeded with only "
        f"{r20['mean_latency_ms']:.0f} ms mean and {r20['p99_latency_ms']:.0f} ms p99 latency. At 50% the success "
        f"rate was {r50['success_rate']:.0%} and p99 stayed at {r50['p99_latency_ms']:.0f} ms, so failures come back "
        f"quickly as clean errors. The backoff waits at most 150 ms in total. The only risk is the 2 s timeout per "
        f"attempt (up to about 6 s if the database hangs), so for chat I would add an overall limit of about 2-3 s.")
    d.p("**Batch processing:** speed matters less than finishing every record, so I would use more retries "
        "(5-8), longer backoff with jitter (starting around 0.5-1 s, capped at 30-60 s) and longer timeouts "
        "(10-30 s), and log records that still fail so they can be retried later.")


def part4(d: Doc):
    d.h2("Part 4. One Safe Tool Entry Point and Offline Tests")
    d.fig("p4_offline_tests", "Offline test runner: PASS/FAIL for each test and the final summary.", width="68%")


def part5(d: Doc):
    rows = [json.loads(l) for l in (RAW / "agent_runs.jsonl").read_text().splitlines()]
    stops = [r for r in rows if r["event"] == "stop"]
    d.h2("Part 5. Agent Loop, Safety Rule, and Reflection")
    d.h3("I. Safety rule")
    d.fig("p5_safety", "Fair-housing rule in execute_tool: one allowed call and one blocked call.")
    d.h3("II. Agent loop")
    d.fig("p5_agent_runs", f"run_agent with {config.LLM_MODEL}: steps, tool calls and stop reason per scenario.")
    d.h3("III. Additional tests")
    test_fig = d.fig_of.get("p4_offline_tests", "in Part 4")
    d.p(f"Tests 14 (safety rule blocks a call) and 15 (run_agent with MockModel stops at max_steps) are shown "
        f"passing in Figure {test_fig}.")
    d.h3("IV. Metrics")
    t = [["Scenario", "Input", "Steps", "Tool calls", "Stop reason"]]
    for s in stops:
        t.append([s["scenario"], s["user_input"], str(s["steps"]), str(s["tool_calls"]), s["stop_reason"]])
    d.table(t, widths=["13%", "55%", "9%", "9%", "14%"])
    d.h3("V. Reflection")
    d.add(md_paragraphs((REPORT_DIR / "REFLECTION.md").read_text()))


def main() -> int:
    commit = os.getenv("COMMIT_HASH") or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        d = Doc(tmp)
        section0(d, commit)
        part1(d)
        part2(d)
        part3(d)
        part4(d)
        part5(d)
        font_dir = find_font()
        font_css = ""
        if font_dir:
            for fam, f, w in [("DejaVu Sans", "DejaVuSans.ttf", "normal"), ("DejaVu Sans", "DejaVuSans-Bold.ttf", "bold"),
                              ("DejaVu Sans Mono", "DejaVuSansMono.ttf", "normal")]:
                if (Path(font_dir) / f).exists():
                    shutil.copy(Path(font_dir) / f, tmp / f)
                    font_css += f"@font-face {{ font-family: '{fam}'; src: url('{f}'); font-weight: {w}; }}\n"
        page = (f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW5 - Kavan Siddesh</title>"
                f"<style>{font_css}{CSS}</style></head><body>{''.join(d.parts)}</body></html>")
        (tmp / "report.html").write_text(page, encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT_PDF}", (tmp / "report.html").as_uri()],
                       check=True, capture_output=True)
        if os.getenv("KEEP_HTML"):
            shutil.copytree(tmp, os.environ["KEEP_HTML"], dirs_exist_ok=True)
    shutil.copy(OUT_PDF, NAMED_PDF)
    print(f"wrote {OUT_PDF.relative_to(ROOT)} and {NAMED_PDF.relative_to(ROOT)} (commit {commit[:12]}, {d.fig_no} figures)")
    if d.missing:
        print(f"MISSING screenshots (left out): {', '.join(d.missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
