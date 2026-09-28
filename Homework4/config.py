"""Personal configuration for HW4.

Carried over unchanged from Homework1/README.md and Homework3/config.py, since
the assignment says these values stay fixed for the whole semester.
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

# Part 2
DB_NAME = f"{PREFIX}_rel"
SESSION_TTL_MINUTES = 30
SESSION_COOKIE_NAME = "session_id"
FRONTEND_ORIGINS = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

# Part 3
N_LISTINGS = 5000
N_INQUIRIES = 200
PAGE_SIZES = [10, 50, 200]
REQUESTS_PER_SIZE = 30
WARMUP_REQUESTS = 3

# Part 4
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CORPUS_DIR = ROOT / "corpus"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3
K_SWEEP = [1, 3, 5]
# Cosine-similarity floor used by context-engineered RAG to drop irrelevant chunks.
RELEVANCE_THRESHOLD = 0.35
REFUSAL_TEXT = "I cannot answer this question from the provided documents"
