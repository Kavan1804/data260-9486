# DATA 260 - Homework 4

> **Note (HW5):** `backend/` and `frontend/` were moved to the repository root with `git mv` so later
> homework extends one shared application. Tag `hw4` keeps the original `Homework4/` layout; the HW4
> scripts and `make backend` here now add the repo root to the Python path.

## Configuration

| Value | Configuration |
|---|---|
| SID4 | 9486 |
| PORT_BASE | 8486 |
| PREFIX | s9486 |
| SEED | 9486 |
| VERIFY_SEED | 269486 |
| DOMAIN_ID | 6 |
| Assigned Domain | Rental housing listings |
| Hardware | Apple Mac with M1 chip and 8 GB unified memory |
| Local Model | llama3.2:3b (HW1-HW3 used qwen3:4b; see note below) |
| Database | MySQL `s9486_rel` |

Values are defined once in `config.py`, carried over from HW1/HW3.

Model change: the installed `qwen3:4b` build always writes its reasoning into the
answer text, even with `think: false`, so answers were cut off before the actual
answer. HW4 therefore uses the smaller non-thinking `llama3.2:3b`.

## Layout

- `backend/app/` - FastAPI + SQLAlchemy + MySQL backend, built from the
  DATA236_demo4 starter's `database.py` / `models.py` / `crud.py` /
  `session_crud.py` / `schema.py` / `main.py` layout
  - `database.py` - `DATABASE_URL` from `.env`, session factory `SessionLocal`
  - `models.py` - `listings`, `listing_inquiries`, `users`, `sessions`
  - `main.py` - auth routes, protected listing CRUD, `/listings/naive` and `/listings/fixed`
  - `query_counter.py` - per-request SQL statement counter (X-SQL-Count header)
- `frontend/` - React client adapted from the DATA236_demo4 starter (Vite, react-router-dom, axios)
- `scripts/` - `init_db.py`, `seed_n1.py`, `explain_index.py`, `measure_n1.py`, `verify_hw04.py`, `render_report.py`
- `rag.py`, `rag_questions.json`, `corpus/` - Part 4 grounded RAG
- `reports/hw04/` - RUN_LOG.txt, METRICS.md, AI_USE.md, raw/, screenshots/, report
- `verification.json` - written by `make verify-hw04`

`DATA236_demo4/` is the professor's starter, kept locally for reference and
gitignored (it has its own `.venv`, `node_modules`, and `.env` files).

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | /auth/login | - | email + password, sets HTTP-only `session_id` cookie |
| POST | /auth/logout | - | deletes the server-side session, clears the cookie |
| GET | /auth/me | cookie | current user |
| POST | /listings | cookie | create listing (201) |
| GET | /listings | cookie | all listings (optional `skip`, `limit`) |
| GET | /listings/{id} | cookie | one listing |
| PUT | /listings/{id} | cookie | update listing |
| DELETE | /listings/{id} | cookie | delete listing |
| GET | /listings/naive?page_size=N | cookie | N+1 version |
| GET | /listings/fixed?page_size=N | cookie | selectinload version |

## Setup (run from `Homework4/`)

```bash
cd "Homework4"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your MySQL user/password in DATABASE_URL
```

MySQL must be running locally. Then:

```bash
make init-db                # CREATE DATABASE IF NOT EXISTS s9486_rel + create_all (never drops)
make create-user            # prompts for name, email, password (stored as a bcrypt hash)
make backend                # FastAPI on http://localhost:8486
```

Frontend (second terminal):

```bash
cd Homework4/frontend
npm install
npm run dev                 # http://localhost:5173
```

Open `http://localhost:5173` (use `localhost`, not `127.0.0.1`, so the
cookie is sent to the API on `localhost:8486`).

## Part 3 (backend running in another terminal)

```bash
make seed                   # 5,000 listings + 200 inquiries, SEED 9486 (--reset empties those two tables first)
make explain                # EXPLAIN before/after ix_listing_inquiries_listing_id
HW4_EMAIL=you@example.com make measure   # prompts for password; 180 requests -> raw/, fills METRICS.md
```

## Part 4

```bash
ollama serve                # if not already running
ollama pull llama3.2:3b
make rag                    # retrieval printouts + A/B/C configs + k-sweep -> reports/hw04/raw/
python rag.py --retrieve-only                      # retrieval only, no LLM
python rag.py --ask "your question" --mode context --k 3
```

Chunking is 500 characters with 50 characters of overlap. Characters rather than
tokens because all-MiniLM-L6-v2 truncates input at 256 tokens, so 500-token
chunks would be partly ignored by the embedder.

## Self-check

```bash
make verify-hw04            # starts the backend if needed, writes verification.json
```

After tagging (`git tag hw4`), re-run it so `commit_hash` is filled in.

## Report

```bash
make report                 # reports/hw04/report.pdf + Kumar_HW4.pdf (needs Google Chrome)
```
