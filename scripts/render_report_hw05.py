#!/usr/bin/env python3
"""Render the HW5 report (reports/hw05/report.pdf and Kumar_HW5.pdf).

Same layout idea as the HW4 report: configuration table first, one section per
part, labeled screenshots with captions, result tables built from the raw files.
No source code is included (the code is in the GitHub repository).

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
    d.add("<div class='sub'>Kavan Siddesh &nbsp;|&nbsp; Rental housing listings (DOMAIN_ID 6)</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table([
        ["GitHub repository", config.REPO_URL],
        ["SID4", "9486"],
        ["PORT_BASE", f"{config.PORT_BASE}  (8000 + 9486 mod 900)"],
        ["PREFIX", config.PREFIX],
        ["SEED", str(config.SEED)],
        ["VERIFY_SEED", f"{config.VERIFY_SEED}  (260000 + 9486)"],
        ["DOMAIN_ID", f"{config.DOMAIN_ID} (9486 mod 8) - {config.DOMAIN_NAME}"],
        ["Hardware", config.HARDWARE],
        ["Local model", f"{config.LLM_MODEL} (Ollama 0.34.4)"],
        ["Database", f"MySQL 9.4.0, database {config.DB_NAME}"],
        ["Tagged commit hash", commit],
        ["Submission tag", "hw5"],
    ], header=False, cls="kv")
    d.p("The hw5 tag points to the commit that adds this PDF and verification.json on top of the commit "
        "above; that commit has all of the code and evidence, and it is the one the self-check tested. "
        "Both collaborators (Sbnikitha, supriyaselvanganesan) have access to the repository.")
    d.h3("How HW5 extends HW4")
    d.p("HW5 continues the HW4 FastAPI + MySQL rental-listing app instead of starting a new one. I moved the HW4 "
        "backend and frontend to shared root-level folders with git mv (history kept; tag hw4 still has the old "
        "layout) and extended them there. The professor's DATA236_Demo5 starter was used as a reference for the "
        "related-entity pattern and the Redux Toolkit slice, not copied as a separate app.")
    d.table([
        ["Folder", "What is in it"],
        ["backend/", "FastAPI + SQLAlchemy: session login (HW4), landlords + listings CRUD, relationship query"],
        ["frontend/", "React (Vite) client, data layer in Redux Toolkit"],
        ["mcp_servers/", "meals (TheMealDB) and s9486_listings (domain) MCP servers over STDIO"],
        ["domain_tools/", "envelope, retry/backoff, fault injection, safety rule, execute_tool, run_agent"],
        ["tests/", "offline test runner (no database, model or network)"],
        ["reports/hw05/", "RUN_LOG.txt, raw/, METRICS.md, TOOL_CONTRACTS.md, AI_USE.md, REFLECTION.md, verification.json"],
    ], widths=["22%", "78%"])



def part1(d: Doc):
    d.h2("Part 1. Extending the FastAPI + MySQL Application")
    d.h3("I. Database")
    d.p("The related entity is the landlord who owns a listing. One landlord has many listings, and every listing "
        "belongs to exactly one landlord.")
    d.table([
        ["Table", "Columns and constraints"],
        ["landlords (new)", "id INT PK auto increment; full_name VARCHAR(120) NOT NULL (primary text); company "
                            "VARCHAR(160) NOT NULL (secondary text); email VARCHAR(255) NOT NULL UNIQUE (validated, "
                            "stored lower-case); created_at / updated_at DATETIME (updated_at has ON UPDATE)"],
        ["listings (extended)", "id INT PK; title VARCHAR(200) (primary field); address; listing_code VARCHAR(9) NOT "
                                "NULL UNIQUE, format LST-12345; available_units INT NOT NULL DEFAULT 1 with CHECK >= 0; "
                                "landlord_id INT NOT NULL FOREIGN KEY to landlords.id ON DELETE RESTRICT; created_at / updated_at"],
    ], widths=["22%", "78%"])
    d.p("My database already had 5,000 HW4 listings, so I did not drop anything. The migration created the "
        "landlords table, seeded 20 landlords with SEED 9486, gave each existing listing the code LST-<id> and a "
        "seeded landlord, and only then added NOT NULL, UNIQUE, the foreign key and the CHECK. Running it again "
        "changes nothing. Deleting a landlord who still owns listings is refused twice: the API returns 409 first, "
        "and MySQL's RESTRICT foreign key blocks it as a backstop. Passwords are still only bcrypt hashes in the "
        "HW4 users table.")
    d.fig("p1_db_landlords", "DESCRIBE landlords: unique email (UNI) and timestamps.", width="88%")
    d.fig("p1_db_listings", "DESCRIBE listings: unique listing_code, available_units default 1, "
          "landlord_id foreign key (MUL), timestamps.", width="88%")

    d.h3("II. API")
    d.p("All routes use Pydantic request and response schemas and still need the HW4 session cookie, so I logged "
        "in once in Postman before these requests. List endpoints are paginated with skip and limit (1-200) and "
        "return total, skip, limit and items. PUT is a partial update, and an empty body or a null field is a 422.")
    d.table([
        ["Endpoint", "Success", "Errors handled"],
        ["POST /landlords", "201", "409 duplicate email; 422 invalid email or missing field"],
        ["GET /landlords?skip&limit", "200 page", "422 bad skip/limit"],
        ["GET / PUT / DELETE /landlords/{id}", "200", "404 not found; 409 duplicate email (PUT); 409 still has listings (DELETE)"],
        ["GET /landlords/{id}/listings", "200 page", "404 landlord not found (relationship query)"],
        ["POST /listings", "201", "409 duplicate listing_code; 422 bad code format, negative units, unknown landlord_id"],
        ["GET /listings?skip&limit", "200 page", "422 bad skip/limit"],
        ["GET / PUT / DELETE /listings/{id}", "200", "404 not found; 409 / 422 as for POST (PUT)"],
    ], widths=["36%", "13%", "51%"])
    d.label("Landlord (related entity) CRUD")
    d.fig("p1_landlord_create", "POST /landlords creates landlord 24 (201 Created).")
    d.fig("p1_landlord_list", "GET /landlords?skip=0&limit=5: paginated list (total 21 at the time).")
    d.fig("p1_landlord_get", "GET /landlords/1 returns one landlord (200).")
    d.fig("p1_landlord_update", "PUT /landlords/1 with only the company field: partial update, updated_at changes.")
    d.label("Listing (primary entity) CRUD")
    d.fig("p1_listing_create", "POST /listings with landlord_id 1 creates LST-90001 (201).")
    d.fig("p1_listing_list", "GET /listings?skip=0&limit=5: newest first, total 5001.")
    d.fig("p1_listing_get", "GET /listings/5002 (200).")
    d.fig("p1_listing_update", "PUT /listings/5002 with available_units 3 (partial update, 200).")
    d.fig("p1_listing_delete", "DELETE /listings/5002 returns the deleted listing (200).")
    d.label("Relationship query and error handling")
    d.fig("p1_relationship", "GET /landlords/1/listings: all listings of landlord 1 (total 269), paginated.")
    d.fig("p1_err_duplicate_409", "Unique-constraint error: the same landlord email again returns 409 Conflict.")
    d.fig("p1_err_format_422", "Unique-field format validation: listing_code \"ABC\" fails the LST-12345 pattern (422).")
    d.fig("p1_err_restrict_409", "Relationship error: landlord 1 still owns 269 listings, so DELETE is refused (409).")
    d.fig("p1_err_notfound_404", "Not found: GET /listings/999999 returns 404.")

    d.h3("III. Redux Client")
    d.p("I moved the React data layer from useState in App to Redux Toolkit. The store has a listings slice and a "
        "small landlords slice (for the landlord dropdown and names). The listings slice has four Axios async "
        "thunks: fetch (GET /listings), create (POST), update (PUT /listings/{id}) and delete (DELETE "
        "/listings/{id}). Each thunk rejects with the FastAPI error message, and the slice stores loading/error "
        "state plus a success notice. Home reads only from the store, so the list updates by itself after create, "
        "update and delete. Each screenshot shows the thunk and reducer code in VS Code next to the result in the "
        "browser.")
    d.fig("p1_redux_home", "Home: fetchListings thunk and its pending/fulfilled/rejected cases (left); Home "
          "rendering the store (\"showing 1-25 of 5000\") (right).")
    d.fig("p1_redux_create", "Create: createListing thunk and createListing.fulfilled, which puts the new row "
          "first; Home shows \"Created listing LST-12345 (ID 5010)\".")
    d.fig("p1_redux_update", "Update (listing selected by ID 1): updateListing thunk; Home shows \"Updated "
          "listing LST-00001\" with 5 units.")
    d.fig("p1_redux_delete", "Delete button on the row: deleteListing thunk and the reducer that filters the row "
          "out; Home shows \"Deleted listing ID 1\" and the total drops to 5000.")


def part2(d: Doc):
    meals = json.loads((RAW / "mcp_meals_calls.json").read_text())
    calls = {(c["tool"], json.dumps(c["arguments"], sort_keys=True)): c for c in meals["calls"]}
    details = calls[("meal_details", json.dumps({"id": "52771"}))]["result"]
    nomatch = calls[("search_meals_by_name", json.dumps({"limit": 5, "query": "zzzxqq"}, sort_keys=True))]["result"]
    bad = calls[("meal_details", json.dumps({"id": "abc"}))]["result"]

    d.h2("Part 2. MCP Tool Servers")
    d.h3("A. TheMealDB server (meals)")
    d.p("meals is a Python FastMCP server over STDIO that calls https://www.themealdb.com/api/json/v1/1/ with the "
        "public test key 1. Every request has a 10 s timeout. Logs go to stderr only, because stdout carries the "
        "MCP JSON-RPC messages. I ran it with mcp dev (MCP Inspector).")
    d.table([
        ["Tool", "Endpoint", "Returns"],
        ["search_meals_by_name(query, limit=5)", "search.php?s=", "up to limit (1-25) meals: id, name, area, category, thumb"],
        ["meals_by_ingredient(ingredient, limit=12)", "filter.php?i=", "up to limit cards: id, name, thumb"],
        ["random_meal()", "random.php", "same shape as meal_details"],
        ["meal_details(id)", "lookup.php?i=", "id, name, category, area, instructions, image, source, youtube, ingredients [{name, measure}]"],
    ], widths=["32%", "17%", "51%"])
    d.p(f"When TheMealDB answers \"meals\": null, the tool returns an empty result with a short message instead of "
        f"failing. For example, the query zzzxqq returned count {nomatch['count']} and \"{nomatch['message']}\". Bad "
        f"input, timeouts, network errors and invalid JSON are raised as a clean tool error that the Inspector "
        f"shows. For example, meal_details(\"abc\") returned \"{bad}\". Both of these calls are recorded in "
        f"raw/mcp_meals_calls.json.")
    d.fig("p2_meals_search", "search_meals_by_name (query \"Arrabiata\", limit 5): one result, Spicy Arrabiata Penne.")
    d.fig("p2_meals_ingredient", "meals_by_ingredient (ingredient \"chicken\", limit 12): 12 small cards (first results shown).")
    d.fig("p2_meals_random", "random_meal: a full recipe (Traditional Croatian Goulash) in the meal_details shape (top of the result).")
    d.fig("p2_meals_details", f"meal_details (id 52771): {details['name']}, {len(details['ingredients'])} "
          f"ingredients with name and measure.")

    d.h3("B. Domain server (s9486_listings)")
    d.p("The second FastMCP server works on my own s9486_rel data and has exactly three tools. All three return "
        "the same envelope {ok, data, error}: error is null on success, and on failure ok is false and data is "
        "null. This envelope is defined once (domain_tools/envelope.py) and reused by execute_tool in Part 4. The "
        "tools validate their inputs themselves, so a bad call comes back as an error envelope and the server "
        "never crashes. Logs go to stderr.")
    d.table([
        ["Tool", "Kind", "What it returns"],
        ["search_listings(query, limit, min_units)", "search", "listings whose title or address contains the query, with landlord name"],
        ["get_listing(listing_code)", "detail lookup", "one listing by its unique code, with landlord name and company"],
        ["landlord_portfolio_stats(landlord_id)", "aggregate", "listing count, total / average / min / max available units for one landlord"],
    ], widths=["38%", "16%", "46%"])
    d.fig("p2_domain_search_ok", "search_listings, valid (query \"Campbell\", limit 3): ok true, 3 listings.")
    d.fig("p2_domain_search_invalid", "search_listings, intentionally invalid (query \"a\", limit 50): ok false, data null.")
    d.fig("p2_domain_detail_ok", "get_listing, valid (listing_code \"LST-00042\").")
    d.fig("p2_domain_detail_invalid", "get_listing, intentionally invalid (listing_code \"42\").")
    d.fig("p2_domain_stats_ok", "landlord_portfolio_stats, valid (landlord_id 2): 279 listings.")
    d.fig("p2_domain_stats_invalid", "landlord_portfolio_stats, intentionally invalid (landlord_id -5).")
    d.p("The Inspector cuts off long error strings. The full returned errors are listed in Part 3 and in "
        "TOOL_CONTRACTS.md.")


def part3(d: Doc):
    rec = json.loads((RAW / "mcp_domain_calls.json").read_text())
    from domain_tools.contracts import REJECTED
    from domain_tools.execute import TOOL_SPECS

    by_call = {(c["tool"], json.dumps(c["arguments"], sort_keys=True)): c for c in rec["calls"]}
    d.h2("Part 3. Tool Contracts Under Stress")
    d.h3("Contracts and rejected calls")
    d.p("These are the same rejected calls as in Part 2B. The returned errors come from the recorded MCP calls "
        "(raw/mcp_domain_calls.json).")
    rows = [["Tool", "Expected input schema", "Rejected input", "Returned output", "Why rejected"]]
    for name, spec in TOOL_SPECS.items():
        props = spec["schema"]["properties"]
        parts = []
        for k, v in props.items():
            rng = []
            if "minLength" in v:
                rng.append(f"{v['minLength']}-{v['maxLength']} chars")
            if "minimum" in v:
                rng.append(f"min {v['minimum']}" + (f", max {v['maximum']}" if "maximum" in v else ""))
            if "pattern" in v:
                rng.append("pattern LST- + 5 digits")
            if "default" in v:
                rng.append(f"default {v['default']}")
            req = " (required)" if k in spec["schema"]["required"] else ""
            parts.append(f"{k}: {v['type']}{req}" + (f", {', '.join(rng)}" if rng else ""))
        bad, _, why = REJECTED[name]
        out = by_call[(name, json.dumps(bad, sort_keys=True))]["result"]
        rows.append([name, "; ".join(parts) + "; no extra fields", json.dumps(bad),
                     f"ok false, data null, error: \"{out['error']}\"", why])
    d.table(rows, widths=["15%", "25%", "14%", "28%", "18%"])

    d.h3("Retry policy")
    d.p("Storage calls (the MySQL queries behind the three tools) run through call_with_retry. Each attempt has "
        "a 2.0 s timeout. Only temporary failures are retried (timeouts, dropped connections and the injected "
        "faults), with at most 3 attempts. The backoff waits 50 ms before the 2nd attempt and 100 ms before the "
        "3rd (doubling, capped at 400 ms). Bad input is never retried. When all attempts fail, the tool returns "
        "a clean {ok: false} envelope instead of raising.")
    d.fig("p3_retry_demo", "make retry-demo: (1) success on the first attempt, (2) first attempt fails and the "
          "retry succeeds after 50 ms, (3) all 3 attempts fail and a clean error envelope is returned.")

    s = json.loads((RAW / "retry_summary.json").read_text())
    rows_csv = list(csv.DictReader((RAW / "retry_calls.csv").open()))
    d.h3("Fault injection at 0%, 20% and 50% (VERIFY_SEED 269486)")
    d.p("A fault injector sits in front of the real MySQL repository. For every storage attempt it draws a number "
        "from random.Random(269486), and the attempt fails when the draw is below the rate. Each rate starts from "
        "the same seed, so the same calls fail on every run. The self-check replays the seed and gets exactly the "
        "recorded failure pattern. Each rate ran 50 calls (a fixed mix of the three tools), so 150 calls in "
        f"total ({len(rows_csv)} rows in raw/retry_calls.csv). Each row has the call number, rate, random draws, "
        "injected failures, retries, success, latency and the error or result.")
    t = [["Injected failure rate", "Success rate", "Mean latency (ms)", "p99 latency (ms)", "Attempts", "Calls retried"]]
    for r in s["rates"]:
        t.append([f"{r['failure_rate']:.0%}", f"{r['success_rate']:.0%} ({r['successes']}/{r['calls']})",
                  f"{r['mean_latency_ms']:.2f}", f"{r['p99_latency_ms']:.2f}", str(r["total_attempts"]),
                  str(r["calls_with_retry"])])
    d.table(t)
    d.p("Latency is the wall-clock time of execute_tool, including the backoff waits. p99 uses the nearest-rank "
        "method, which with 50 calls is the slowest call.")
    d.fig("p3_retry_experiment", "make retry-experiment: the three 50-call runs.")
    r20, r50 = s["rates"][1], s["rates"][2]
    d.h3("Is this retry policy right for an interactive assistant?")
    d.p(f"Mostly yes. At 20% injected failures every call still succeeded, and the average cost was only "
        f"{r20['mean_latency_ms']:.0f} ms (p99 {r20['p99_latency_ms']:.0f} ms), which a user would never notice "
        f"next to a model reply that takes seconds. At 50% the success rate fell to {r50['success_rate']:.0%}, "
        f"close to the expected 1 - 0.5^3 = 87.5%, and p99 was still only {r50['p99_latency_ms']:.0f} ms. Those "
        f"failures came back quickly as clean errors that the agent can explain. Retries add at most 150 ms of "
        f"waiting, which is short enough for chat. The weak spot is the timeout: a hung database could cost "
        f"3 x 2 s = 6 s before the error. For an interactive assistant I would add one overall deadline of about "
        f"2-3 s per tool call.")
    d.h3("Changes for batch processing")
    d.p("In a batch job, finishing every record matters more than speed, so I would use more attempts (5-8; at a "
        "50% fault rate 6 attempts succeed 1 - 0.5^6 = 98.4% of the time). The backoff would be longer and "
        "randomized (start at 0.5-1 s, cap around 30-60 s, with jitter so workers do not retry in lockstep) and "
        "per-attempt timeouts would be longer (10-30 s). I would also save progress so that records that still "
        "fail are logged and retried later, instead of stopping the whole job.")


def part4(d: Doc):
    d.h2("Part 4. One Safe Tool Entry Point and Offline Tests")
    d.h3("execute_tool(name, inputs)")
    d.p("execute_tool is the only way the Part 5 agent can reach a domain tool. It looks up the tool by name "
        "(unknown names are an error), accepts the inputs as a dict or a JSON string, applies the Part 5 safety "
        "rule, runs the tool with the retry policy, and always returns the {ok, data, error} envelope as a JSON "
        "string. Any unexpected exception is turned into an error envelope, so the caller never crashes. The "
        "storage layer is injected, which lets the tests swap MySQL for an in-memory fixture.")
    d.h3("Offline test runner")
    d.p("tests/run_offline_tests.py is a plain Python runner with assert statements (no pytest). It uses a small "
        "temporary in-memory fixture instead of MySQL and MockModel instead of Ollama. It also disables network "
        "sockets for the whole run, so any test that tried to reach a database, model or API would fail. It "
        "covers a valid and the Part 3 rejected input for every tool, plus not-found cases, bad tool names, the "
        "retry cases, and the two Part 5 tests.")
    d.table([
        ["Tests", "What they check"],
        ["1-6", "valid input and the Part 3 rejected input for search_listings, get_listing, landlord_portfolio_stats"],
        ["7-8", "not-found results and bad names / non-JSON / extra fields come back as error envelopes"],
        ["9-13", "retry: first-try success, fail then success, all retries fail, backoff 0/50/100/200/400 ms, seeded faults repeat exactly"],
        ["14-15", "Part 5: safety rule blocks a call (storage never touched); run_agent with MockModel stops at max_steps"],
        ["16", "agent does not accept a fabricated tool result as an answer (see AI use)"],
    ], widths=["12%", "88%"])
    d.fig("p4_offline_tests", "make test: PASS for each of the 16 tests and the final 16/16 summary.", width="68%")


def part5(d: Doc):
    rows = [json.loads(l) for l in (RAW / "agent_runs.jsonl").read_text().splitlines()]
    stops = [r for r in rows if r["event"] == "stop"]
    d.h2("Part 5. Agent Loop, Safety Rule, and Reflection")
    d.h3("I. Safety rule (fair housing)")
    d.p("My domain is rental housing, so the rule comes from the Fair Housing Act and California law (both were "
        "in my HW3/HW4 corpus). A listing search may not filter on a protected characteristic: familial status, "
        "race, color or national origin, religion, disability, sex, or source of income (for example \"no kids\", "
        "\"christians only\", \"no section 8\"). execute_tool checks the search query before anything runs. If "
        "the rule is broken it returns {ok: false, data: null, error: ...} without raising, and the database is "
        "never queried. The patterns target exclusionary phrasing, so a normal search like \"family room\" still "
        "works.")
    d.fig("p5_safety", "make safety-demo: the allowed search (\"San Jose\") returns 3 listings; the blocked "
          "search (\"San Jose no kids\") returns the error envelope.")
    d.h3("II. Agent loop")
    d.p(f"run_agent(user_input) sends the conversation and the three tool definitions to the local "
        f"{config.LLM_MODEL} model through Ollama (temperature 0, seed 9486). A turn counter goes up each step, "
        f"and the loop stops at max_steps ({config.AGENT_MAX_STEPS} by default). Each step runs at most one tool "
        f"call through execute_tool; extra calls the model packs into the same reply are logged and skipped. "
        f"The JSON result goes back to the model. The run stops on a normal answer (completed), a safety-rule "
        f"block (safety_block), or the step ceiling (max_steps). Every run start, step, tool call (name, inputs, "
        f"result) and the final stop reason is written to raw/agent_runs.jsonl.")
    d.h3("III. Additional offline tests")
    test_fig = d.fig_of.get("p4_offline_tests", "in Part 4")
    d.p(f"Two tests were added to the Part 4 runner and pass offline without an API key, model, external API or "
        f"database (Figure {test_fig}). Test 14 checks that execute_tool blocks a \"no kids\" search with "
        "{ok: false, data: null} and never touches storage. Test 15 runs run_agent with MockModel, which always "
        "asks for another tool call, and checks that it stops at max_steps = 3 with 3 steps, 3 tool calls and "
        "stop reason max_steps in the log.")
    d.h3("IV. Metrics (local Ollama model)")
    t = [["Scenario", "Input", "Steps", "Tool calls", "Stop reason"]]
    for s in stops:
        t.append([s["scenario"], s["user_input"], f"{s['steps']} (max {s['max_steps']})", str(s["tool_calls"]), s["stop_reason"]])
    d.table(t, widths=["13%", "53%", "11%", "9%", "14%"])
    d.p("The first three scenarios each needed one tool call and then a normal answer, and the answers matched "
        "the database. The safety scenario stopped right after the blocked search. In the step-ceiling scenario "
        "the model tried to batch five calls and invented a result once, so it ran out of steps (see Reflection).")
    d.fig("p5_agent_runs", "make agent-scenarios: five runs with llama3.2:3b, with steps, tool calls and stop reason for each.")
    d.h3("V. Reflection")
    d.add(md_paragraphs((REPORT_DIR / "REFLECTION.md").read_text()))


def ai_use(d: Doc):
    d.h2("AI Use")
    d.add(md_paragraphs((REPORT_DIR / "AI_USE.md").read_text()))


def verification(d: Doc):
    v = json.loads((REPORT_DIR / "verification.json").read_text())
    d.h2("Self-check (verification.json)")
    d.p(f"make verify-hw05 starts what it needs, tests behavior and writes reports/hw05/verification.json "
        f"(homework {v['homework']}, SID4 {v['sid4']}, commit {v['commit_hash'][:12]}, model "
        f"{v['configuration']['llm_model']}, SEED {v['seed']}, VERIFY_SEED {v['verify_seed']}). Result: "
        f"{v['passed']} passed, {v['failed']} failed.")
    t = [["Check", "Result", "Details"]]
    for c in v["checks"]:
        t.append([c["check"], "PASS" if c["passed"] else "FAIL", c["details"]])
    d.table(t, widths=["30%", "9%", "61%"])
    d.h3("Reproducible commands (repo root)")
    d.add("<div class='cmd'>make install            # .venv + npm install\n"
          "cp .env.example .env    # MySQL DATABASE_URL\n"
          "make migrate            # landlords table + backfill (safe to re-run)\n"
          "make backend            # FastAPI on http://localhost:8486\n"
          "make frontend           # React on http://localhost:5173\n"
          "make inspect-meals      # MCP Inspector (also: make inspect-domain)\n"
          "make mcp-calls contracts retry-demo retry-experiment test safety-demo agent-scenarios\n"
          "make verify-hw05        # writes reports/hw05/verification.json</div>")


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
        ai_use(d)
        if (REPORT_DIR / "verification.json").exists():
            verification(d)
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
