"""Shared personal configuration for the root-level application (HW5 onward).

Values are fixed for the semester and match Homework4/config.py. The backend
only imports names that exist in both files, so the HW4 scripts (which put
Homework4/ first on sys.path) still work with the moved backend/.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

SID4 = 9486
PORT_BASE = 8000 + (SID4 % 900)
PREFIX = f"s{SID4}"
SEED = SID4
VERIFY_SEED = 260000 + SID4
DOMAIN_ID = SID4 % 8
DOMAIN_NAME = "Rental housing listings"

HARDWARE = "Apple Mac with M1 chip and 8 GB unified memory"
REPO_URL = "https://github.com/Kavan1804/data260-9486"

# Backend
DB_NAME = f"{PREFIX}_rel"
SESSION_TTL_MINUTES = 30
SESSION_COOKIE_NAME = "session_id"
FRONTEND_ORIGINS = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# HW5 Part 1 - landlords backfill for the existing listings
N_LANDLORDS = 20

# HW5 Part 3 - retry policy for domain storage calls
RETRY_MAX_ATTEMPTS = 3  # 1 try + 2 retries
RETRY_BASE_DELAY_S = 0.05  # 50 ms, doubled each retry
RETRY_MAX_DELAY_S = 0.4
CALL_TIMEOUT_S = 2.0  # per attempt
FAILURE_RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50

# HW5 Part 2A - TheMealDB
MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1/"
HTTP_TIMEOUT_S = 10.0

# HW5 Part 5 - agent
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
AGENT_MAX_STEPS = 6


def _env_value(name: str) -> str | None:
    """Env value, or None when unset, blank, or still a <I_MUST_PROVIDE_...> placeholder."""
    value = (os.getenv(name) or "").strip()
    return None if not value or value.startswith("<") else value


def _env_int(name: str, default: int) -> int:
    value = _env_value(name)
    return int(value) if value else default


# HW6 Part 1 - MongoDB document store (same server for Part 2 memory collections)
MONGODB_URI = _env_value("MONGODB_URI") or "mongodb://localhost:27017"
MONGODB_DB = _env_value("MONGODB_DB") or f"{PREFIX}_doc"
MONGO_TIMEOUT_MS = 2000

# HW6 Part 2 - memory. OLLAMA_MODEL falls back to the HW5 LLM_MODEL so the same local model is used.
OLLAMA_MODEL = _env_value("OLLAMA_MODEL") or LLM_MODEL
# No embedding model is configured in HW5. When this is unset, episodes use the local
# hashed bag-of-words embedding in backend/app/memory_logic.py (labelled "hash-bow-256").
OLLAMA_EMBED_MODEL = _env_value("OLLAMA_EMBED_MODEL")
OLLAMA_NUM_CTX = _env_int("OLLAMA_NUM_CTX", 8192)  # large enough that SHORT_TERM_N=30 is not truncated
SHORT_TERM_N = _env_int("SHORT_TERM_N", 12)
SUMMARIZE_EVERY_USER_MSGS = _env_int("SUMMARIZE_EVERY_USER_MSGS", 5)
LIFETIME_EVERY_SESSION_SUMMARIES = 2  # condense into the lifetime summary after every 2nd session summary
EPISODIC_TOP_K = _env_int("EPISODIC_TOP_K", 3)
MAX_FACTS_PER_MESSAGE = 3

# HW6 Part 3 - one memory-saving policy ("compress"): the newest messages stay verbatim,
# older messages inside the window are clipped.
COMPRESS_KEEP_RECENT = 4
COMPRESS_MAX_CHARS = 120
HW6_REPORT_DIR = ROOT / "reports" / "hw06"
CHAT_USAGE_LOG = Path(_env_value("CHAT_USAGE_LOG") or HW6_REPORT_DIR / "raw" / "chat_usage.jsonl")

# HW6 Part 4 - file-based memory
AGENT_MD = ROOT / "AGENT.md"
MEMORY_MD = Path(_env_value("MEMORY_MD") or ROOT / "MEMORY.md")
MEMORY_MAX_LINES = 40
MEMORY_MAX_AGE_HOURS = 24

# HW7 Part 1 - JWT bearer auth (replaces the HW4 session cookie on the domain routes).
# The secret lives only in .env (never committed); there is no default on purpose.
JWT_SECRET_KEY = _env_value("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
ROLES = ("reader", "writer", "moderator")
HW7_REPORT_DIR = ROOT / "reports" / "hw07"
