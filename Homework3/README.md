# DATA 260 - Homework 3

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

These match `Homework1/README.md` since the assignment specifies they stay
fixed for the semester. See `config.py` for the single place they are
defined and derived - edit `SID4` there if it needs correcting.

## Repository layout

- `config.py` - personal configuration values and Part 1/Part 2 settings (edit here first)
- `main.py` - FastAPI app entry point, session middleware setup
- `routers/auth.py` - Part 1 authentication router (`/`, `/login`, `/dashboard`, `/logout`)
- `templates/` - Jinja2 + Bootstrap templates for the auth app
- `rag/pipelines.py` - Part 2 chunking/indexing/retrieval-only implementation
- `rag/corpus_prep.py` - manual corpus download helper (edit `SOURCES` first)
- `rag/build_manifest.py` - computes `reports/hw03/CORPUS_MANIFEST.json` from the downloaded corpus
- `rag/run_experiments.py` - runs all three techniques against `reports/hw03/questions.yaml`, writes `reports/hw03/raw/`
- `rag/compute_metrics.py` - recomputes the summary metrics table from `reports/hw03/raw/`
- `scripts/verify_hw03.py` - homework self-check, writes `reports/hw03/verification.json`
- `reports/hw03/` - written report, logs, raw results, and corpus documentation

## Part 1: Run the auth app

```bash
cd Homework3
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Open `http://localhost:8486/`. Log in with `admin` / `password` (see
`routers/auth.py`). The session cookie is `Secure`, `HttpOnly`, and
`SameSite=lax` (see `main.py`); Chrome/Edge send `Secure` cookies over
`http://localhost`, but Safari/Firefox require real HTTPS to verify that
attribute - use `--ssl-keyfile`/`--ssl-certfile` with uvicorn there instead.

## Part 2: Run the retrieval comparison

```bash
# 1. Add real source URLs to rag/corpus_prep.py, then:
python rag/corpus_prep.py
python rag/build_manifest.py

# 2. Confirm reports/hw03/questions.yaml is final, then:
python -m rag.run_experiments
python -m rag.compute_metrics
```

## Self-check

```bash
COMMIT_HASH=$(git rev-parse HEAD) python3 scripts/verify_hw03.py
```

Writes `reports/hw03/verification.json`.
