"""
=============================================================================
 PERSONAL CONFIGURATION - EDIT THIS SECTION IF ANY VALUE BELOW IS WRONG
=============================================================================
Per DATA 260 HW3 Section 0, these six values are derived once from your SJSU
Student ID and "stay fixed for the rest of the semester." They were carried
over unchanged from the Homework 1 report (Homework1/README.md), where SID4
was first computed, so they are not being guessed here. If your SID4 was
ever recorded incorrectly, fix SID4 below and every derived value updates
with it.
"""

# ---- Manually confirmed personal values -----------------------------------
SID4 = 9486

# ---- Derived values (do not hardcode these separately elsewhere) ----------
PORT_BASE = 8000 + (SID4 % 900)
PREFIX = f"s{SID4}"
SEED = SID4
VERIFY_SEED = 260000 + SID4
DOMAIN_ID = SID4 % 8

# Domain assignment for DOMAIN_ID 6, as recorded in Homework1/README.md and
# Homework1/DOMAIN_SCHEMA.md. Kept consistent with HW1/HW2 rather than
# re-derived, since the assignment is fixed for the whole semester.
DOMAIN_NAME = "Rental housing listings"

# =============================================================================
# PART 1 - AUTH APP SETTINGS
# =============================================================================
# How long a session may sit idle (no request to a protected route) before it
# is treated as expired. Kept short on purpose so idle-timeout behavior can be
# verified by hand in under two minutes; raise it for normal use.
IDLE_TIMEOUT_SECONDS = 90

# =============================================================================
# PART 2 - RETRIEVAL (LLAMAINDEX) SETTINGS
# =============================================================================
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Where the manually downloaded domain corpus (>= 200 KB) lives.
CORPUS_DIR = "rag/corpus"

# Number of nodes to retrieve per query for every technique.
TOP_K = 5

# Token-based chunking (TokenTextSplitter).
TOKEN_CHUNK_SIZE = 256
TOKEN_CHUNK_OVERLAP = 32

# Semantic chunking (SemanticSplitterNodeParser).
SEMANTIC_BUFFER_SIZE = 1
SEMANTIC_BREAKPOINT_PERCENTILE = 95

# Sentence-window chunking (SentenceWindowNodeParser).
SENTENCE_WINDOW_SIZE = 3
