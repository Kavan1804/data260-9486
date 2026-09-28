#!/usr/bin/env python3
"""Render the Homework 4 report to PDF using Pillow, in the same visual style as HW1/HW2.

Code is not included (it is submitted through GitHub). Tables and console output
come from reports/hw04/raw/ and RUN_LOG.txt, and screenshots from
reports/hw04/screenshots/. A missing screenshot is drawn as a visible
PENDING box instead of being left out silently.

Usage (from Homework4/):
    python3 scripts/render_report.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402

REPORT_DIR = ROOT / "reports" / "hw04"
RAW = REPORT_DIR / "raw"
SHOTS = REPORT_DIR / "screenshots"
OUTPUT_PDF = REPORT_DIR / "final report.pdf"

# The code is submitted through the GitHub link, so the report shows only
# outputs (console logs, tables, screenshots), never source excerpts.
SOURCE_PREFIXES = ("frontend/", "backend/", "scripts/", "rag.py")
REPO_URL = "https://github.com/Kavan1804/data260-9486"

W, H = 1600, 2070
MARGIN = 70
BODY_W = W - 2 * MARGIN
BOTTOM = H - 90


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_manager.findfont(name, fallback_to_default=True), size=size)


TITLE = font("DejaVu Sans", 34)
H1 = font("DejaVu Sans", 24)
H2 = font("DejaVu Sans", 18)
BODY = font("DejaVu Sans", 15)
SMALL = font("DejaVu Sans", 13)
MONO = font("DejaVu Sans Mono", 13)
MONO_S = font("DejaVu Sans Mono", 11)


def lh(fnt, extra=6):
    b = fnt.getbbox("Ag")
    return b[3] - b[1] + extra


# ---------------------------------------------------------------- source helpers

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def py_def(rel: str, *names: str) -> str:
    src = read(rel)
    lines = src.splitlines()
    parts = []
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            start = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1
            parts.append("\n".join(lines[start:node.end_lineno]))
    return "\n\n".join(parts)


def between(rel: str, start: str, end: str) -> str:
    """Lines from the first containing `start` to the next containing `end`.
    An `end` ending in a newline must match the whole (right-stripped) line."""
    lines = read(rel).splitlines()
    i = next(n for n, ln in enumerate(lines) if start in ln)
    if end.endswith("\n"):
        j = next(n for n in range(i + 1, len(lines)) if lines[n].rstrip() == end.rstrip("\n"))
    else:
        j = next(n for n in range(i, len(lines)) if end in lines[n])
    return "\n".join(lines[i:j + 1])


def run_log_section(target: str, which: int = -1, max_lines: int | None = None) -> tuple[str, str]:
    """Return (timestamp, text) of a `make <target>` section in RUN_LOG.txt."""
    text = (REPORT_DIR / "RUN_LOG.txt").read_text(encoding="utf-8")
    heads = list(re.finditer(r"^===== (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ([\w-]+) =====$", text, re.M))
    hits = [h for h in heads if h.group(2) == target]
    h = hits[which]
    nxt = next((x.start() for x in heads if x.start() > h.start()), len(text))
    body = text[h.end():nxt].strip("\n")
    lines = [ln for ln in body.splitlines() if "Loading weights" not in ln and "Warning" not in ln]
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines in RUN_LOG.txt)"]
    return h.group(1), "\n".join(lines)


def md_rows(md: str) -> list[list[str]]:
    rows = [ln.strip() for ln in md.splitlines() if ln.strip().startswith("|")]
    return [[c.strip() for c in r.strip("|").split("|")] for r in rows if not re.fullmatch(r"\|[\s\-|:]+\|", r)]


# ---------------------------------------------------------------- screenshot cropping

def focus(name: str, img: Image.Image) -> Image.Image:
    """Crop away window chrome so the relevant part stays readable at report size.
    Only the rendered copy is cropped; files in screenshots/ are untouched."""
    w, h = img.size
    if name.startswith("postman_"):
        # request/response pane only (drops the Postman sidebar and AI chat panel)
        return img.crop((int(w * 0.18), int(h * 0.055), int(w * 0.745), h))
    if name.startswith("mysql_"):
        # stack the query editor, the result grid and the action log; drop the schema tree and empty space
        x0, x1 = int(w * 0.15), int(w * 0.62)
        bands = [(0.12, 0.215), (0.445, 0.72), (0.925, 0.985)]
        parts = [img.crop((x0, int(h * a), x1, int(h * b))) for a, b in bands]
        out = Image.new("RGB", (x1 - x0, sum(p.height for p in parts) + 8 * (len(parts) - 1)), "#cbd5e1")
        y = 0
        for p in parts:
            out.paste(p, (0, y))
            y += p.height + 8
        return out
    return img


# ---------------------------------------------------------------- layout engine

class Report:
    def __init__(self):
        self.pages: list[Image.Image] = []
        self.new_page()

    def new_page(self):
        self.page = Image.new("RGB", (W, H), "white")
        self.draw = ImageDraw.Draw(self.page)
        self.pages.append(self.page)
        self.y = MARGIN

    def ensure(self, h: int):
        if self.y + h > BOTTOM:
            self.new_page()

    def title(self, text):
        self.draw.text((MARGIN, self.y), text, font=TITLE, fill="black")
        self.y += 60

    def heading(self, text, new_page=True):
        if new_page and self.y > MARGIN:
            self.new_page()
        self.ensure(60)
        self.draw.text((MARGIN, self.y), text, font=H1, fill="black")
        self.y += lh(H1) + 8
        self.draw.line([MARGIN, self.y, W - MARGIN, self.y], fill="#94a3b8", width=2)
        self.y += 16

    def sub(self, text):
        self.ensure(80)
        self.draw.text((MARGIN, self.y), text, font=H2, fill="black")
        self.y += lh(H2) + 8

    def _wrap_words(self, text, fnt, width):
        text = text.replace("`", "")
        out = []
        for para in text.split("\n"):
            if not para.strip():
                out.append("")
                continue
            cur = ""
            for w in para.split():
                cand = w if not cur else f"{cur} {w}"
                if self.draw.textlength(cand, font=fnt) <= width:
                    cur = cand
                else:
                    if cur:
                        out.append(cur)
                    cur = w
            if cur:
                out.append(cur)
        return out

    def text(self, text, fnt=BODY, gap=10):
        for line in self._wrap_words(text, fnt, BODY_W):
            self.ensure(lh(fnt))
            self.draw.text((MARGIN, self.y), line, font=fnt, fill="black")
            self.y += lh(fnt)
        self.y += gap

    def bullets(self, items, fnt=BODY):
        for item in items:
            lines = self._wrap_words(item, fnt, BODY_W - 26)
            for i, line in enumerate(lines):
                self.ensure(lh(fnt))
                if i == 0:
                    self.draw.text((MARGIN, self.y), "-", font=fnt, fill="black")
                self.draw.text((MARGIN + 26, self.y), line, font=fnt, fill="black")
                self.y += lh(fnt)
        self.y += 8

    def code(self, text, label=None, fnt=MONO):
        """Monospace block on a light grey panel; wraps long lines by character."""
        if label and label.startswith(SOURCE_PREFIXES):
            return
        if label:
            self.ensure(lh(SMALL) + 3 * lh(fnt))
            self.draw.text((MARGIN, self.y), label, font=SMALL, fill="#334155")
            self.y += lh(SMALL) + 2
        cw = self.draw.textlength("M", font=fnt)
        per_line = int((BODY_W - 24) // cw)
        lines = []
        for raw in text.rstrip().splitlines():
            raw = raw.replace("\t", "    ")
            while len(raw) > per_line:
                lines.append(raw[:per_line])
                raw = "  " + raw[per_line:]
            lines.append(raw)
        step = lh(fnt, 4)
        i = 0
        while i < len(lines):
            self.ensure(step * 2 + 16)
            room = max(1, (BOTTOM - self.y - 16) // step)
            chunk = lines[i:i + room]
            box_h = len(chunk) * step + 14
            self.draw.rectangle([MARGIN, self.y, W - MARGIN, self.y + box_h], fill="#f5f5f5", outline="#d4d4d4")
            yy = self.y + 7
            for ln in chunk:
                self.draw.text((MARGIN + 12, yy), ln, font=fnt, fill="#111111")
                yy += step
            self.y += box_h + 10
            i += len(chunk)

    def table(self, rows, col_widths, fnt=SMALL, header=True):
        pad = 8
        for r_i, row in enumerate(rows):
            cells = [self._wrap_words(str(c), fnt, w - 2 * pad) or [""] for c, w in zip(row, col_widths)]
            row_h = max(len(c) for c in cells) * lh(fnt, 4) + 2 * pad
            self.ensure(row_h)
            x = MARGIN
            for c_i, (lines, w) in enumerate(zip(cells, col_widths)):
                fill = "#e2e8f0" if header and r_i == 0 else ("#f8fafc" if c_i == 0 and not header else "white")
                self.draw.rectangle([x, self.y, x + w, self.y + row_h], fill=fill, outline="#94a3b8")
                yy = self.y + pad
                for ln in lines:
                    self.draw.text((x + pad, yy), ln, font=fnt, fill="black")
                    yy += lh(fnt, 4)
                x += w
            self.y += row_h
        self.y += 14

    def images(self, items: list[tuple[str, str]], box_h: int = 760):
        """Screenshots side by side (portrait) with captions under each."""
        n = len(items)
        gap = 24
        box_w = (BODY_W - gap * (n - 1)) // n
        cap_lines = max(len(self._wrap_words(c, SMALL, box_w)) for _, c in items)
        self.ensure(box_h + cap_lines * lh(SMALL) + 20)
        for i, (name, cap) in enumerate(items):
            left = MARGIN + i * (box_w + gap)
            self._paste(name, (left, self.y, left + box_w, self.y + box_h))
            yy = self.y + box_h + 6
            for ln in self._wrap_words(cap, SMALL, box_w):
                self.draw.text((left, yy), ln, font=SMALL, fill="#334155")
                yy += lh(SMALL)
        self.y += box_h + cap_lines * lh(SMALL) + 22

    def wide_image(self, name: str, cap: str, box_h: int = 560):
        self.ensure(box_h + lh(SMALL) + 20)
        self._paste(name, (MARGIN, self.y, W - MARGIN, self.y + box_h))
        self.draw.text((MARGIN, self.y + box_h + 6), cap, font=SMALL, fill="#334155")
        self.y += box_h + lh(SMALL) + 22

    def _paste(self, name, box):
        path = SHOTS / name
        x0, y0, x1, y1 = box
        if not path.exists():
            self.draw.rectangle(box, fill="#fff7ed", outline="#b45309", width=3)
            msg = self._wrap_words(f"PENDING screenshot: screenshots/{name}", BODY, x1 - x0 - 30)
            yy = y0 + (y1 - y0) // 2 - len(msg) * lh(BODY) // 2
            for ln in msg:
                self.draw.text((x0 + 15, yy), ln, font=BODY, fill="#92400e")
                yy += lh(BODY)
            return
        img = Image.open(path).convert("RGB")
        img = focus(name, img)
        scale = min((x1 - x0) / img.width, (y1 - y0) / img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        px = x0 + ((x1 - x0) - img.width) // 2
        self.page.paste(img, (px, y0))
        self.draw.rectangle([px - 1, y0 - 1, px + img.width, y0 + img.height], outline="#cbd5e1")

    def finish(self) -> list[Image.Image]:
        total = len(self.pages)
        for idx, page in enumerate(self.pages, start=1):
            d = ImageDraw.Draw(page)
            d.line([MARGIN, H - 50, W - MARGIN, H - 50], fill="#cbd5e1", width=1)
            d.text((MARGIN, H - 40), "DATA 260 - Homework 4", font=SMALL, fill="#64748b")
            d.text((W - MARGIN - 110, H - 40), f"Page {idx} of {total}", font=SMALL, fill="#64748b")
        return self.pages


# ---------------------------------------------------------------- sections

def section0(r: Report, verification: dict):
    r.title("DATA 260 Homework 4")
    r.heading("Section 0. Personal Configuration and Domain", new_page=False)
    r.table([
        ["SID4", str(config.SID4)],
        ["PORT_BASE", str(config.PORT_BASE)],
        ["PREFIX", config.PREFIX],
        ["SEED", str(config.SEED)],
        ["VERIFY_SEED", str(config.VERIFY_SEED)],
        ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME}"],
        ["Hardware", config.HARDWARE],
        ["Local model", f"{config.LLM_MODEL} (via Ollama)"],
        ["Embedding model", config.EMBEDDING_MODEL_NAME],
        ["Database", f"MySQL 9.4.0, database {config.DB_NAME}"],
        ["GitHub repository", REPO_URL],
        ["Content-complete source commit", verification.get("commit_hash", "PENDING")],
        ["Final submission tag", "hw4"],
    ], [430, 1030], header=False)
    r.text(
        "HW1-HW3 used qwen3:4b. For HW4 the installed qwen3:4b build kept writing its reasoning into the answer text even "
        "with think=false, so answers were cut off before the actual answer (see AI_USE.md). Part 4 therefore uses the "
        "smaller non-thinking llama3.2:3b, which fits the 8 GB M1. The SQLAlchemy session factory is named SessionLocal "
        "after the TA confirmed that the name in the handout (db_session_basede26) was a typo."
    )
    r.sub("Reproducible commands (run from Homework4/)")
    r.code("\n".join([
        "python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
        "cp .env.example .env            # DATABASE_URL=mysql+pymysql://USER:PASSWORD@localhost:3306/s9486_rel",
        "make init-db && make create-user",
        "make backend                    # FastAPI on http://localhost:8486",
        "cd frontend && npm install && npm run dev   # React on http://localhost:5173",
        "make seed && make explain && HW4_EMAIL=<email> make measure",
        "ollama pull llama3.2:3b && make rag",
        "make verify-hw04 && make report",
    ]))
    r.text("Repository access: both collaborators (Sbnikitha, supriyaselvanganesan) are given access to " + REPO_URL + ".")


def layout_section(r: Report):
    r.heading("Project Folder Structure")
    r.text(
        "HW4 continues the per-homework layout used for HW1-HW3 inside the same data260-9486 repository. The professor's "
        "DATA236_demo4 starter was integrated rather than copied: its backend file layout (database.py, models.py, crud.py, "
        "session_crud.py, schema.py, main.py) became backend/app/, and its React client (Vite, react-router-dom, axios, "
        "Navbar, login bar, styles.css) became frontend/. The starter folder itself is gitignored because it contains its "
        "own .venv, node_modules and .env files."
    )
    skip = {".venv", "node_modules", "__pycache__", "DATA236_demo4", ".DS_Store", "dist"}
    lines = ["Homework4/"]

    def walk(d: Path, prefix: str, depth: int):
        entries = sorted([p for p in d.iterdir() if p.name not in skip and (not p.name.startswith(".") or p.name in {".env.example", ".gitignore"})],
                         key=lambda p: (p.is_file(), p.name))
        if d.name in {"raw", "screenshots"}:
            entries = [p for p in entries if p.name != ".gitkeep"]
            if len(entries) > 4:
                entries = entries[:4] + [Path(f"... {len(entries) - 4} more files")]
        for i, p in enumerate(entries):
            last = i == len(entries) - 1
            is_dir = p.exists() and p.is_dir()
            lines.append(f"{prefix}{'`-- ' if last else '|-- '}{p.name}{'/' if is_dir else ''}")
            if is_dir and depth < 3:
                walk(p, prefix + ("    " if last else "|   "), depth + 1)

    walk(ROOT, "", 0)
    r.code("\n".join(lines), label="Folder tree generated from the repository", fnt=MONO_S)


def part1(r: Report):
    r.heading("Part 1. React Client - Login (Login.jsx) and Home Page (Home.jsx, route /)")
    r.text(
        "App checks the HTTP-only session cookie on load by calling GET /auth/me (the cookie itself cannot be read by "
        "JavaScript). Login.jsx posts email + password; the backend sets the cookie. While logged out, Home shows "
        "\"Login required\", the Add Listing link is disabled, and /create, /update/:id and /delete/:id render a "
        "Login required card through RequireAuth."
    )
    r.code(between("frontend/src/pages/Login.jsx", "async function handleLogin", "  }\n"), label="frontend/src/pages/Login.jsx")
    r.code(between("frontend/src/app.jsx", "// On first load", "}, []);") + "\n\n" +
           between("frontend/src/app.jsx", "<Routes>", "</Routes>"), label="frontend/src/app.jsx - session check and routes")
    r.images([("react_logged_out.png", "Logged out: 'Login required' and a disabled Add Listing link"),
              ("react_login_home.png", "After login with email + password: Home (/) lists all 5,000 listings from MySQL")], box_h=720)


def part1_crud(r: Report):
    r.heading("Part 1. React Client - II. Add a New Record (CreateRecord.jsx, route /create)")
    r.text("CreateRecord receives onAdd as a prop, keeps the two inputs in useState, and App redirects to / after the API returns the new auto-incremented ID.")
    r.code(between("frontend/src/app.jsx", "async function onAdd", "  }\n"), label="frontend/src/app.jsx - onAdd passed as a prop")
    r.code(between("frontend/src/pages/CreateRecord.jsx", "export default function CreateRecord", "  }\n"), label="frontend/src/pages/CreateRecord.jsx")
    r.images([("react_create_form.png", "Add Listing form (title = primary field, address = secondary field)"),
              ("react_create_result.png", "Redirected to / - new listing ID 5002 at the top")], box_h=700)

    r.heading("Part 1. React Client - III. Update Record (UpdateRecord.jsx, route /update/:id)")
    r.text("UpdateRecord reads the id with useParams, loads the listing in useEffect, and calls the onUpdate prop; the PUT is persisted in MySQL before redirecting to /.")
    r.code(between("frontend/src/pages/UpdateRecord.jsx", "export default function UpdateRecord", "  }, [listingId]);") + "\n\n" +
           between("frontend/src/pages/UpdateRecord.jsx", "async function handleSubmit", "  }\n"), label="frontend/src/pages/UpdateRecord.jsx")
    r.images([("react_update_form.png", "Update Listing form for ID 5002"),
              ("react_update_result.png", "Redirected to / - ID 5002 now shows 'My Home'")], box_h=700)

    r.heading("Part 1. React Client - IV. Delete Record (DeleteRecord.jsx, route /delete/:id)")
    r.text("DeleteRecord shows the listing and a Delete Listing button; the onDelete prop sends DELETE /listings/{id}, removes the row from state and redirects to /.")
    r.code(between("frontend/src/app.jsx", "async function onDelete", "  }\n") + "\n\n" +
           between("frontend/src/pages/DeleteRecord.jsx", "async function handleDelete", "  }\n"), label="frontend/src/app.jsx and DeleteRecord.jsx")
    r.images([("react_delete_confirm.png", "Delete confirmation for listing 5000"),
              ("react_delete_result.png", "Redirected to / - listing 5000 is gone, count back to 5,000")], box_h=700)


def part2(r: Report):
    r.heading("Part 2. MySQL Persistence - Database, Tables and Connection")
    r.text(
        "The connection URL comes from .env (never committed). database.py refuses to start unless the URL points at "
        "s9486_rel. scripts/init_db.py runs CREATE DATABASE IF NOT EXISTS and Base.metadata.create_all, which only creates "
        "missing tables and never drops data."
    )
    r.code(between("backend/app/database.py", "DATABASE_URL = os.getenv", "db.close()"), label="backend/app/database.py")
    r.code(between("backend/app/models.py", "class Listing(Base):", "address = Column") + "\n\n" +
           between("backend/app/models.py", "class User(Base):", "expires_at = Column"), label="backend/app/models.py (excerpt)")

    r.heading("Part 2. MySQL Persistence - Tables in s9486_rel", new_page=False)
    r.wide_image("mysql_show_tables.png", "SHOW TABLES - listing_inquiries, listings, sessions, users", box_h=820)
    r.wide_image("mysql_describe_listings.png", "DESCRIBE listings - auto-increment id, title (primary field), address (secondary field)", box_h=820)
    r.wide_image("mysql_describe_users.png", "DESCRIBE users - id, name, email (UNI), password_hash", box_h=820)
    r.wide_image("mysql_describe_sessions.png", "DESCRIBE sessions - id (session token), user_id, created_at, expires_at", box_h=820)
    r.wide_image("mysql_describe_listing_inquiries.png", "DESCRIBE listing_inquiries - related table for Part 3 (listing_id indexed, MUL)", box_h=820)
    r.wide_image("mysql_listings_latest.png", "Latest listings - 5002 'My Home' from the React test; 5004 was deleted in Postman", box_h=820)

    r.heading("Part 2. Server-Side Sessions - Login and HTTP-Only Cookie")
    r.text(
        "Login checks the bcrypt hash, inserts a row into sessions with a 256-bit random token (secrets.token_hex(32)), "
        "and sends only that opaque token in an HttpOnly, SameSite=Lax cookie. No name or email is stored in the cookie. "
        "Every protected route looks the token up in MySQL and returns 401 when it is missing, unknown or expired."
    )
    r.code(py_def("backend/app/session_crud.py", "create_session", "get_session"), label="backend/app/session_crud.py")
    r.code(py_def("backend/app/main.py", "require_session", "login"), label="backend/app/main.py")
    r.images([("postman_login.png", "POST /auth/login - 200, user returned; session cookie set"),
              ("postman_unauthorized.png", "POST /listings without a session - 401 Login required")], box_h=900)
    r.wide_image("mysql_sessions_rows.png", "sessions table: opaque 64-character tokens linked to user_id 3, expiring 30 minutes after creation", box_h=760)


def part2_crud(r: Report):
    r.heading("Part 2. CRUD API - Create (POST) and Read (GET all, GET by ID)")
    r.code(py_def("backend/app/main.py", "add_listing", "list_listings", "get_listing"), label="backend/app/main.py - all routes depend on require_session")
    r.images([("postman_create.png", "POST /listings - 201 Created, id 5004"),
              ("postman_get_all.png", "GET /listings?limit=10 - 200"),
              ("postman_get_by_id.png", "GET /listings/5004 - 200")], box_h=900)

    r.heading("Part 2. CRUD API - Update (PUT) and Delete (DELETE)")
    r.code(py_def("backend/app/main.py", "edit_listing", "remove_listing"), label="backend/app/main.py")
    r.images([("postman_update.png", "PUT /listings/5004 - 200, updated title and address"),
              ("postman_delete.png", "DELETE /listings/5004 - 200, deleted row returned"),
              ("postman_get_all_after_delete.png", "GET /listings after delete - 5004 no longer listed")], box_h=900)

    r.heading("Part 2. Logout - Server-Side Session Removed")
    r.code(py_def("backend/app/main.py", "logout") + "\n\n" + py_def("backend/app/session_crud.py", "delete_session"), label="backend/app/main.py and session_crud.py")
    r.images([("postman_logout.png", "POST /auth/logout - 200 logged out"),
              ("postman_me_after_logout.png", "GET /auth/me after logout - 401 Login required")], box_h=900)


def part3(r: Report, summary: dict | None):
    r.heading("Part 3. N+1 - Seeding 5,000 Listings and 200 Related Rows (SEED 9486)")
    r.text(
        "seed_n1.py uses random.Random(9486), so every run produces the same rows. The 200 listing_inquiries rows are "
        "attached to the first 200 listing ids, so each measured page (page 1 at sizes 10, 50 and 200) has related data. "
        "The schema comes from backend/app/models.py via scripts/init_db.py."
    )
    r.code(between("scripts/seed_n1.py", "    listings = [", "        db.execute(insert(ListingInquiry), inquiries)"), label="scripts/seed_n1.py (excerpt)")
    ts, out = run_log_section("seed")
    r.code(out, label=f"Console output - make seed ({ts}, from RUN_LOG.txt)")
    r.wide_image("mysql_count_listings.png", "MySQL: SELECT COUNT(*) FROM listings - 5000 (the inquiry count of 200 is in the console output above)", box_h=700)

    r.heading("Part 3. N+1 - Naive and Fixed List Endpoints", new_page=False)
    r.text(
        "The naive loader runs one query for the page and then one SELECT per listing for its inquiries (1 + N statements). "
        "The fixed loader uses selectinload, which fetches the inquiries for the whole page in a single WHERE listing_id IN "
        "(...) query (2 statements). A SQLAlchemy before_cursor_execute listener counts the statements of each request and "
        "returns the count in the X-SQL-Count header."
    )
    r.code(py_def("backend/app/crud.py", "list_listings_naive", "list_listings_fixed"), label="backend/app/crud.py")
    r.code(between("backend/app/query_counter.py", "@event.listens_for", "_counter.reset(token)"), label="backend/app/query_counter.py")

    for size, items in [
        (10, [("postman_naive_10_headers.png", "naive, page_size=10 - X-SQL-Count 11"),
              ("postman_fixed_10_headers.png", "fixed, page_size=10 - X-SQL-Count 2"),
              ("postman_naive_10_body.png", "naive, page_size=10 - body with inquiries")]),
        (50, [("postman_naive_50_headers.png", "naive, page_size=50 - X-SQL-Count 51"),
              ("postman_fixed_50_headers.png", "fixed, page_size=50 - X-SQL-Count 2"),
              ("postman_fixed_50_body.png", "fixed, page_size=50 - body (count 50)")]),
        (200, [("postman_naive_200_headers.png", "naive, page_size=200 - X-SQL-Count 201"),
               ("postman_fixed_200_headers.png", "fixed, page_size=200 - X-SQL-Count 2"),
               ("postman_naive_200_body.png", "naive, page_size=200 - body (count 200)")]),
    ]:
        r.heading(f"Part 3. N+1 - Postman, Both Versions at Page Size {size}")
        r.images(items, box_h=900)
        if size == 10:
            r.images([("postman_fixed_10_body.png", "fixed, page_size=10 - same items and inquiries as naive")], box_h=900)

    r.heading("Part 3. N+1 - Measurement: 3 Page Sizes x 2 Versions x 30 Requests = 180")
    r.text(
        "measure_n1.py logs in, sends 3 unrecorded warm-up requests per configuration, then 30 recorded requests. Latency "
        "is the client-side round trip (perf_counter); percentiles use the nearest-rank method, so with 30 samples p99 is "
        "the slowest request. All 180 rows are saved in raw/n1_requests.csv and raw/n1_requests.json."
    )
    r.code(py_def("scripts/measure_n1.py", "percentile", "one_request"), label="scripts/measure_n1.py (excerpt)")
    ts, out = run_log_section("measure", max_lines=7)
    r.code(out, label=f"Console output - make measure ({ts}, from RUN_LOG.txt)", fnt=MONO_S)
    if summary:
        rows = [["Page size", "Version", "SQL stmts/req", "p50 (ms)", "p95 (ms)", "p99 (ms)"]]
        for s in summary["summary"]:
            rows.append([str(s["page_size"]), s["version"], str(s["sql_statements_per_request"]),
                         f"{s['p50_ms']:.2f}", f"{s['p95_ms']:.2f}", f"{s['p99_ms']:.2f}"])
        r.table(rows, [200, 200, 260, 266, 266, 268])

    r.heading("Part 3. N+1 - How Much Faster, and Why the Speedup Grows", new_page=False)
    if summary:
        sm = summary["summary"]
        rows = [["Page size", "Speedup at p50 (naive / fixed)", "Speedup at p95", "SQL statements saved per request"]]
        for size in config.PAGE_SIZES:
            n = next(s for s in sm if s["page_size"] == size and s["version"] == "naive")
            f = next(s for s in sm if s["page_size"] == size and s["version"] == "fixed")
            rows.append([str(size), f"{n['p50_ms'] / f['p50_ms']:.2f}x", f"{n['p95_ms'] / f['p95_ms']:.2f}x",
                         str(n["sql_statements_per_request"] - f["sql_statements_per_request"])])
        r.table(rows, [220, 440, 340, 460])
    metrics = read("reports/hw04/METRICS.md")
    why = metrics.split("### Why the speedup changes with page size")[1].split("## Part 3 - Index")[0].strip()
    for para in why.split("\n\n"):
        r.text(" ".join(para.split()))

    r.heading("Part 3. Index and EXPLAIN Before / After")
    r.text("Index added on the column used by both inquiry lookups:")
    r.code("CREATE INDEX ix_listing_inquiries_listing_id ON listing_inquiries (listing_id);")
    r.code(py_def("scripts/explain_index.py", "explain_all") + "\n\nQUERIES = " + json.dumps(
        {"naive_per_listing": "... WHERE listing_id = 7 ORDER BY id", "fixed_selectin_page10": "... WHERE listing_id IN (1..10) ORDER BY id"}, indent=2),
        label="scripts/explain_index.py (excerpt)")
    explain = (RAW / "explain_before_after.txt").read_text(encoding="utf-8")
    explain = explain.split("===== SHOW CREATE TABLE")[0].strip()
    r.code(explain, label="Console output - make explain (raw/explain_before_after.txt)", fnt=MONO_S)
    block = metrics.split("EXPLAIN before/after output:")[1].split("## Part 4")[0]
    r.table(md_rows(block), [420, 520, 520])
    changed = block.split("What changed:")[1].strip()
    r.text("What changed: " + " ".join(changed.split()))


def part4(r: Report):
    meta = json.loads((RAW / "rag_run_meta.json").read_text())
    questions = json.loads(read("rag_questions.json"))["questions"]

    r.heading("Part 4. RAG - Corpus, Chunking and Index")
    r.text(
        f"Five public rental-housing documents (California Civil Code 1941.1, 1946, 1946.2, 1950.5 and the DOJ Fair Housing "
        f"Act page) are cleaned from HTML, split into {meta['n_chunks']} chunks of {meta['chunk_size_chars']} characters with "
        f"{meta['chunk_overlap_chars']} characters of overlap, embedded with all-MiniLM-L6-v2 and loaded into a FAISS "
        "IndexFlatIP (cosine similarity on normalized vectors). Characters were used instead of tokens because MiniLM "
        "truncates input at 256 tokens. Every chunk stores its text, source file name and chunk_id."
    )
    r.code(py_def("rag.py", "chunk_text", "build_chunks"), label="rag.py - chunking with source + chunk_id")
    r.code(py_def("rag.py", "VectorStore"), label="rag.py - embeddings + FAISS")
    ts, out = run_log_section("rag", max_lines=7)
    r.code(out, label=f"Console output - make rag ({ts}, from RUN_LOG.txt)", fnt=MONO_S)

    r.heading("Part 4. RAG - Retrieval Printed Before the LLM Call (top_k = 3)", new_page=False)
    r.code(py_def("rag.py", "format_retrieval"), label="rag.py")
    retrieved = (RAW / "retrieved_chunks.txt").read_text(encoding="utf-8")
    blocks = [b for b in retrieved.split("\n=== ") if b.strip()]
    first_q = [b for b in blocks if "(top_k=3)" in b][:2]
    r.code("\n".join("=== " + b.strip() if not b.startswith("Retrieved") else b for b in first_q),
           label="raw/retrieved_chunks.txt - Q1 and Q2 (full file has every question and k)", fnt=MONO_S)

    r.heading("Part 4. RAG - Three Configurations", new_page=False)
    r.text(
        "(A) No RAG sends only the question. (B) Basic RAG pastes the top-3 raw chunks. (C) Context-engineered RAG drops "
        f"chunks under a cosine score of {meta['relevance_threshold']} and near-duplicates (word Jaccard >= 0.8), groups the "
        "survivors by source and labels them [1], [2], ..., and adds grounding rules with source-number citations and the "
        "exact refusal sentence. If no chunk survives, it refuses without calling the model."
    )
    r.code("GROUNDED_SYSTEM_PROMPT = \"\"\"" + between("rag.py", "You answer questions about rental housing", "5. Keep the answer") + "\"\"\"",
           label="rag.py - grounding rules")
    r.code(py_def("rag.py", "engineer_context", "run_config"), label="rag.py - context engineering and the three configurations", fnt=MONO_S)

    r.heading("Part 4. RAG - Six-Question Test Set and Results (llama3.2:3b, top_k = 3)")
    r.table([["ID", "Type", "Question", "Expected answer"]] +
            [[q["id"], q["type"], q["question"], q["expected_answer"]] for q in questions], [70, 250, 560, 580])
    six = md_rows((RAW / "six_question_results.md").read_text(encoding="utf-8"))
    r.table([six[0][:1] + six[0][2:]] + [row[:1] + row[2:] for row in six[1:]], [70, 460, 465, 465])

    r.heading("Part 4. RAG - Refusals on Q5 and Q6")
    refusals = json.loads((RAW / "refusals.json").read_text())
    r.table([["Q", "Config", "Answer", "Exact refusal", "Refused by"]] +
            [[x["qid"], x["config"], x["answer"], "yes" if x["exact_refusal"] else "no", x["refusal_source"] or "-"] for x in refusals],
            [60, 170, 870, 150, 210])
    r.text(
        "Only Context RAG returned the exact sentence for both questions. Q6 was refused by the retrieval gate (best score "
        "0.10), and Q5 passed the gate (scores about 0.49) but the model refused under the grounding rule. No RAG invented a "
        "late-fee rule for Q5 and answered Q6 from general knowledge; Basic RAG declined in its own words, which does not "
        "meet the required format."
    )

    r.heading("Part 4. RAG - Context-Size Sweep (k = 1, 3, 5)")
    sweep = md_rows((RAW / "k_sweep.md").read_text(encoding="utf-8"))
    r.table([[row[0], row[1], row[2], row[4], row[6], row[7]] for row in sweep], [50, 40, 470, 170, 110, 620], fnt=font("DejaVu Sans", 12))
    metrics = read("reports/hw04/METRICS.md")
    ksum = metrics.split("k-sweep (context_rag, `raw/k_sweep.md`):")[1]
    r.table(md_rows(ksum), [120, 300, 340, 340, 360])

    r.heading("Part 4. RAG - Evaluation Table")
    r.code(py_def("rag.py", "evaluate"), label="rag.py - automatic evaluation rules", fnt=MONO_S)
    ev = md_rows((RAW / "evaluation_table.md").read_text(encoding="utf-8").split("| Config | Accuracy")[0])
    r.table(ev, [80, 200, 330, 290, 270, 290])
    summ = md_rows("| Config | Accuracy" + (RAW / "evaluation_table.md").read_text(encoding="utf-8").split("| Config | Accuracy")[1])
    r.table(summ, [230, 330, 300, 280, 320])
    manual = metrics.split("Manual review of the automatic checks (automatic files left unchanged):")[1].split("k-sweep")[0]
    r.sub("Manual review of the automatic checks")
    r.table(md_rows(manual), [60, 200, 240, 260, 700])

    r.heading("Part 4. RAG - Analysis")
    analysis = read("reports/hw04/RAG_ANALYSIS.md").split("\n", 1)[1]
    for para in analysis.strip().split("\n\n"):
        r.text(para.replace("**", ""))


def ai_use(r: Report):
    r.heading("AI_USE.md")
    text = read("reports/hw04/AI_USE.md").split("\n", 1)[1]
    for para in text.strip().split("\n\n"):
        r.text(" ".join(para.replace("**", "").split()))


def closing(r: Report, verification: dict):
    r.heading("Closing Notes")
    r.text(f"Self-check: make verify-hw04 (scripts/verify_hw04.py) writes verification.json. Last run: {verification.get('run_at', '-')}.")
    rows = [["Check", "Passed", "Details"]] + [[c["check"], "yes" if c["passed"] else "no", c["details"]] for c in verification.get("checks", [])]
    r.table(rows, [470, 110, 880])
    r.bullets([
        "AI use disclosure: reports/hw04/AI_USE.md",
        "Run log with timestamps: reports/hw04/RUN_LOG.txt",
        "N+1 raw data (180 requests): reports/hw04/raw/n1_requests.csv, n1_requests.json, n1_summary.json",
        "EXPLAIN output: reports/hw04/raw/explain_before_after.txt / .json",
        "RAG outputs: reports/hw04/raw/retrieved_chunks.txt, no_rag.jsonl, basic_rag.jsonl, context_rag.jsonl, "
        "six_question_results.md, refusals.json, k_sweep.jsonl / .md, evaluation_table.md, evaluation.csv",
        "Filled-in tables: reports/hw04/METRICS.md",
        f"GitHub repository: {REPO_URL} (tag hw4)",
    ])


def main() -> int:
    verification = json.loads((ROOT / "verification.json").read_text())
    summary_path = RAW / "n1_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None

    r = Report()
    section0(r, verification)
    layout_section(r)
    part1(r)
    part1_crud(r)
    part2(r)
    part2_crud(r)
    part3(r, summary)
    part4(r)
    ai_use(r)
    closing(r, verification)
    pages = r.finish()

    pages[0].save(OUTPUT_PDF, save_all=True, append_images=pages[1:], resolution=150)
    print(f"Wrote {len(pages)} pages to {OUTPUT_PDF}")
    missing = sorted({m for m in re.findall(r"screenshots/([\w.]+\.png)", Path(__file__).read_text()) if not (SHOTS / m).exists()})
    if missing:
        print("PENDING screenshots:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
