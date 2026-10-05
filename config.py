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
RETRY_MAX_ATTEMPTS = 3          # 1 try + 2 retries
RETRY_BASE_DELAY_S = 0.05       # 50 ms, doubled each retry
RETRY_MAX_DELAY_S = 0.4
CALL_TIMEOUT_S = 2.0            # per attempt
FAILURE_RATES = [0.0, 0.2, 0.5]
CALLS_PER_RATE = 50

# HW5 Part 2A - TheMealDB
MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1/"
HTTP_TIMEOUT_S = 10.0

# HW5 Part 5 - agent
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
AGENT_MAX_STEPS = 6
