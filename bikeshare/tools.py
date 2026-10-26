"""HW7 Part 4: the three MRKL tools as pure functions with JSON schemas.

Every tool returns the common shape {"success", "data", "error", "source", "ts"} and never raises.

csv_sql(sql)                   read-only SELECT over the uploaded trips (table `trips`)
policy_retriever(url, query, k) short quotable passages from the pricing page (saved snapshot first)
calculator(expression, units)  safe arithmetic, whitelist ^[0-9+\\-*/().\\s]+$, AST walk, no eval

The read-only contract of csv_sql is enforced in code at three levels, so it holds no matter what the
model (or a prompt injection) asks for: (1) one statement only, starting with SELECT or WITH,
(2) no write/DDL/PRAGMA/ATTACH keywords, (3) SQLite itself: PRAGMA query_only=ON plus an authorizer
that denies everything except reading. `read_only=False` exists only so Part 5 can measure what
happens WITHOUT the tool-boundary defense.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import operator
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import config

SNAPSHOT_DIR = Path(config.ROOT) / "reports" / "hw07" / "raw" / "pricing_snapshots"
FIXTURE_DIR = Path(config.ROOT) / "Homework7" / "fixtures"
MAX_ROWS = 200

TOOL_SCHEMAS = {
    "csv_sql": {
        "type": "object",
        "description": "Run ONE read-only SELECT query over the uploaded trips table `trips`. Columns: ride_id, "
        "rideable_type ('classic_bike' or 'electric_bike'), started_at, ended_at, duration_min (REAL), "
        "start_station_name, end_station_name, member_casual, ride_date (YYYY-MM-DD), ride_month (YYYY-MM), "
        "ride_week (YYYY-WW).",
        "properties": {"sql": {"type": "string", "description": "A single SELECT statement"}},
        "required": ["sql"],
        "additionalProperties": False,
    },
    "policy_retriever": {
        "type": "object",
        "description": "Fetch the bike-share pricing page and return short quotable passages that match the query "
        "(membership price, included minutes, per-minute charges, unlock fees, overage rules).",
        "properties": {
            "url": {"type": "string", "description": "Pricing page URL"},
            "query": {"type": "string", "description": "What to look for, e.g. 'month pass price'"},
            "k": {"type": "integer", "minimum": 1, "maximum": 8, "default": 4},
        },
        "required": ["url", "query"],
        "additionalProperties": False,
    },
    "calculator": {
        "type": "object",
        "description": "Safe arithmetic on numbers only: digits, + - * / ( ) and spaces.",
        "properties": {
            "expression": {"type": "string", "pattern": r"^[0-9+\-*/().\s]+$"},
            "units": {"type": "string"},
        },
        "required": ["expression"],
        "additionalProperties": False,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def result(success: bool, data=None, error: str | None = None, source: str | None = None) -> dict:
    return {"success": success, "data": data, "error": error, "source": source, "ts": now_iso()}


# ---------------------------------------------------------------- csv_sql

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|pragma|attach|detach|vacuum|reindex|analyze|truncate|grant|"
    r"revoke|begin|commit|rollback|savepoint|release|load_extension)\b",
    re.I,
)
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorizer(action, *_args):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


class TripStore:
    """The uploaded CSV loaded into an in-memory SQLite table `trips` (plus a few derived columns)."""

    def __init__(self, csv_text: str, source: str = "uploaded.csv"):
        self.source = source
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        # LangGraph can run two tool calls in parallel threads; the read-only switches (authorizer,
        # query_only) are per connection, so every query holds this lock.
        self.lock = threading.Lock()
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        if not rows:
            raise ValueError("the CSV has no data rows")
        cols = list(rows[0].keys())
        self.columns = cols
        quoted = ", ".join(f'"{c}" TEXT' for c in cols)
        self.conn.execute(f"CREATE TABLE trips ({quoted})")
        self.conn.executemany(
            f"INSERT INTO trips VALUES ({', '.join('?' for _ in cols)})", [tuple(r.get(c) for c in cols) for r in rows]
        )
        self.conn.execute("ALTER TABLE trips ADD COLUMN duration_min REAL")
        self.conn.execute("ALTER TABLE trips ADD COLUMN ride_date TEXT")
        self.conn.execute("ALTER TABLE trips ADD COLUMN ride_month TEXT")
        self.conn.execute("ALTER TABLE trips ADD COLUMN ride_week TEXT")
        self.conn.execute(
            "UPDATE trips SET duration_min = ROUND((julianday(ended_at) - julianday(started_at)) * 1440.0, 3), "
            "ride_date = substr(started_at, 1, 10), ride_month = substr(started_at, 1, 7), "
            "ride_week = strftime('%Y-%W', started_at)"
        )
        self.conn.commit()
        self.row_count = len(rows)

    @classmethod
    def from_path(cls, path: str | Path) -> "TripStore":
        return cls(Path(path).read_text(encoding="utf-8"), source=Path(path).name)


def check_read_only(sql: str) -> str | None:
    """Return why `sql` is not allowed, or None if it is a single read-only SELECT/WITH."""
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        return "empty SQL"
    if ";" in text:
        return "only one statement is allowed (found ';')"
    if not re.match(r"^(select|with)\b", text, re.I):
        return "only SELECT (or WITH ... SELECT) queries are allowed"
    m = FORBIDDEN.search(text)
    if m:
        return f"keyword {m.group(0).upper()} is not allowed in a read-only query"
    return None


def csv_sql(store: TripStore, sql: str, read_only: bool = True) -> dict:
    if read_only:
        why = check_read_only(sql)
        if why:
            return result(False, error=f"csv_sql refused: {why}", source=store.source)
    with store.lock:
        return _run_sql(store, sql, read_only)


def _run_sql(store: TripStore, sql: str, read_only: bool) -> dict:
    cur = store.conn.cursor()
    try:
        if read_only:
            store.conn.execute("PRAGMA query_only = ON")
            store.conn.set_authorizer(_authorizer)
        if not read_only and ";" in sql.strip().rstrip(";"):
            cur.executescript(sql)  # defense OFF (Part 5 baseline only): "DROP TABLE trips; SELECT 1" would run
        else:
            cur.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1) if cur.description else []
        names = [d[0] for d in cur.description] if cur.description else []
        data = [dict(zip(names, r)) for r in rows[:MAX_ROWS]]
        if not read_only:
            store.conn.commit()
        return result(
            True,
            {"rows": data, "row_count": len(data), "truncated": len(rows) > MAX_ROWS, "source": store.source},
            source=store.source,
        )
    except sqlite3.Error as exc:
        return result(False, error=f"csv_sql error: {exc}", source=store.source)
    finally:
        if read_only:
            store.conn.set_authorizer(None)
            store.conn.execute("PRAGMA query_only = OFF")


# ---------------------------------------------------------------- policy_retriever


def html_to_lines(html_text: str) -> list[str]:
    import html as html_lib

    t = re.sub(r"(?s)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_text)
    t = re.sub(r"<(br|p|div|li|h[1-6]|tr|td|th|section|span)[^>]*>", "\n", t)
    t = html_lib.unescape(re.sub(r"<[^>]+>", " ", t))
    lines = [" ".join(line.split()) for line in t.splitlines()]
    return [line for line in lines if line]


def _snapshot_paths(url: str) -> tuple[Path, Path]:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    return SNAPSHOT_DIR / f"{key}.txt", SNAPSHOT_DIR / f"{key}.json"


def load_page(url: str, mode: str = "snapshot") -> dict:
    """Return {"text", "url", "captured_at", "sha256", "origin"}.

    mode="snapshot": use the saved snapshot for this URL if there is one, otherwise fetch live and save it.
    mode="live": always fetch live (and save a new snapshot).
    Local fixtures (Part 5) are read from Homework7/fixtures via file:// or http://localhost URLs.
    """
    txt_path, meta_path = _snapshot_paths(url)
    if mode == "snapshot" and txt_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        text = txt_path.read_text(encoding="utf-8")
        return {**meta, "text": text, "origin": "saved snapshot"}
    parsed = urlparse(url)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path)).resolve()  # file URIs percent-encode spaces
        if FIXTURE_DIR.resolve() not in path.parents:
            raise PermissionError("file:// URLs are only allowed for Homework7/fixtures")
        raw = path.read_text(encoding="utf-8")
    elif parsed.scheme in ("http", "https"):
        import httpx

        resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (s9486 HW7)"})
        resp.raise_for_status()
        raw = resp.text
    else:
        raise ValueError(f"unsupported URL scheme {parsed.scheme!r}")
    text = "\n".join(html_to_lines(raw))
    meta = {
        "url": url,
        "captured_at": now_iso(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text),
    }
    if parsed.scheme in ("http", "https") and "localhost" not in (parsed.hostname or ""):
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(text, encoding="utf-8")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return {**meta, "text": text, "origin": "live fetch"}


TERMS = {
    "month": 3,
    "pass": 2,
    "membership": 3,
    "member": 2,
    "price": 2,
    "$": 2,
    "unlock": 3,
    "min": 2,
    "minute": 2,
    "free": 2,
    "included": 2,
    "overage": 2,
    "ebike": 1,
    "classic": 1,
    "single": 2,
    "ride": 1,
}


def policy_retriever(url: str, query: str, k: int = 4, mode: str = "snapshot") -> dict:
    try:
        page = load_page(url, mode=mode)
    except Exception as exc:  # noqa: BLE001 - tool must not raise
        return result(False, error=f"policy_retriever could not load {url}: {type(exc).__name__}: {exc}", source=url)
    lines = page["text"].splitlines()
    q_words = {w for w in re.findall(r"[a-z$]+", (query or "").lower()) if len(w) > 2 or w == "$"}
    passages = []
    for i in range(0, max(len(lines) - 1, 1), 2):  # windows of 6 lines, step 2
        chunk = " | ".join(lines[i : i + 6])
        low = chunk.lower()
        score = sum(2 for w in q_words if w in low) + sum(v for t, v in TERMS.items() if t in low) * 0.25
        if "$" in chunk:
            score += 1
        passages.append({"text": chunk[:400], "source": url, "score": round(score, 2), "line": i + 1})
    seen, top = set(), []
    for p in sorted(passages, key=lambda p: (-p["score"], p["line"])):
        if p["text"] not in seen:
            seen.add(p["text"])
            top.append(p)
        if len(top) >= max(1, min(int(k or 4), 8)):
            break
    return result(
        True,
        {"passages": top, "captured_at": page["captured_at"], "sha256": page["sha256"], "page_origin": page["origin"]},
        source=url,
    )


# ---------------------------------------------------------------- calculator

CALC_RE = re.compile(r"^[0-9+\-*/().\s]+$")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    raise ValueError(f"unsupported syntax: {type(node).__name__}")


def calculator(expression: str, units: str | None = None) -> dict:
    expr = (expression or "").strip()
    if not expr or not CALC_RE.fullmatch(expr):
        return result(False, error="calculator: only digits, + - * / ( ) . and spaces are allowed", source="calculator")
    if len(expr) > 300:
        return result(False, error="calculator: expression too long", source="calculator")
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return result(False, error="calculator: division by zero", source="calculator")
    except (SyntaxError, ValueError) as exc:
        return result(False, error=f"calculator: {exc}", source="calculator")
    data = {"value": round(float(value), 6)}
    if units:
        data["units"] = units
    return result(True, data, source="calculator")
