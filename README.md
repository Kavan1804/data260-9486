# DATA 260 - data260-9486 (Kavan Siddesh)

Repository: https://github.com/Kavan1804/data260-9486

| Value | Configuration |
|---|---|
| SID4 | 9486 |
| PORT_BASE | 8486 (= 8000 + 9486 mod 900) |
| PREFIX | s9486 |
| SEED | 9486 |
| VERIFY_SEED | 269486 |
| DOMAIN_ID | 6 - rental housing listings |
| Hardware | Apple Mac with M1 chip and 8 GB unified memory |
| Local model | llama3.2:3b (Ollama) |
| Database | MySQL `s9486_rel` |

Values are defined once in `config.py`.

## Layout

The application lives in shared root-level folders and is extended by each homework
(HW5 moved the HW4 `backend/` and `frontend/` here with `git mv`; tag `hw4` still has
the original `Homework4/` layout).

| Path | What |
|---|---|
| `backend/app/` | FastAPI + SQLAlchemy + MySQL: session login (HW4), `landlords` + `listings` CRUD, relationship query, N+1 endpoints (HW4) |
| `frontend/` | React (Vite) client; data layer in Redux Toolkit (`src/store`, `src/features/listings`, `src/features/landlords`) |
| `mcp_servers/meals_server.py` | MCP server `meals` (TheMealDB, 4 tools, STDIO) |
| `mcp_servers/domain_server.py` | MCP server `s9486_listings` (3 domain tools, `{ok, data, error}`) |
| `domain_tools/` | envelope, repositories, retry/backoff, fault injection, fair-housing safety rule, `execute_tool`, `run_agent` |
| `tests/run_offline_tests.py` | offline assert-based tests (no DB, LLM, or network) |
| `scripts/` | migration, experiments, MCP call recorder, self-check, report renderer |
| `reports/hw05/` | RUN_LOG.txt, raw/, METRICS.md, TOOL_CONTRACTS.md, AI_USE.md, REFLECTION.md, report, verification.json |
| `Homework1/` - `Homework4/` | earlier homework reports and HW-specific scripts |

## Data model (HW5)

- `landlords`: `id`, `full_name` (primary text), `company` (secondary text), `email` (unique,
  validated, stored lower-case), `created_at`, `updated_at`.
- `listings`: `id`, `title` (primary), `address`, `listing_code` (unique, format `LST-12345`),
  `available_units` (INT, default 1, CHECK >= 0), `landlord_id` (FK -> landlords.id,
  ON DELETE RESTRICT), `created_at`, `updated_at`.
- Deleting a landlord who still owns listings is refused (API returns 409, MySQL FK is RESTRICT).
- Passwords (table `users`, HW4) are bcrypt hashes only.

`scripts/migrate_hw05.py` adds the HW5 table/columns to an existing HW4 database without
dropping anything: it seeds 20 landlords with SEED 9486, backfills `listing_code = LST-<id>`
and a seeded `landlord_id` for the 5,000 HW4 listings, then adds the constraints. Re-running it
changes nothing.

## API (all routes except /health and /auth/login need the session cookie)

| Method | Path | Result |
|---|---|---|
| POST | /auth/login, /auth/logout; GET /auth/me | HW4 session auth |
| POST | /landlords | 201; 409 duplicate email; 422 invalid email |
| GET | /landlords?skip=0&limit=50 | `{total, skip, limit, items}` (limit 1-200) |
| GET / PUT / DELETE | /landlords/{id} | 404 if missing; PUT is partial; DELETE 409 while listings exist |
| GET | /landlords/{id}/listings | relationship query, paginated |
| POST | /listings | 201; 409 duplicate code; 422 bad code / unknown landlord_id |
| GET | /listings?skip=0&limit=50 | `{total, skip, limit, items}`, newest first |
| GET / PUT / DELETE | /listings/{id} | 404 if missing; PUT is partial |

## Setup (repo root)

```bash
make install                     # .venv + requirements.txt, frontend npm install
cp .env.example .env             # put your MySQL user/password in DATABASE_URL
make migrate                     # create/upgrade s9486_rel (safe to re-run)
make create-user                 # only if you have no login user yet
make backend                     # FastAPI on http://localhost:8486
make frontend                    # second terminal: React on http://localhost:5173
```

Use `http://localhost:5173` (not 127.0.0.1) so the session cookie reaches `localhost:8486`.

## HW5 runs

```bash
make inspect-meals               # MCP Inspector for the meals server
make inspect-domain              # MCP Inspector for the domain server
make mcp-calls                   # call every MCP tool over STDIO -> raw/mcp_*_calls.json
make contracts                   # TOOL_CONTRACTS.md from the recorded calls
make retry-demo                  # first-try success / retry success / retries exhausted
make retry-experiment            # 150 fault-injected calls (0/20/50%) -> raw/retry_*.{csv,json}, METRICS.md
make test                        # offline tests: PASS/FAIL per test + X/Y
make safety-demo                 # allowed vs blocked call through execute_tool
make agent-scenarios             # Ollama agent runs -> raw/agent_runs.jsonl, METRICS.md
make verify-hw05                 # smoke test -> reports/hw05/verification.json
make report                      # reports/hw05/report.pdf + Kumar_HW5.pdf
```

Each `make` target except the long-running servers appends its console output, with a
timestamp, to `reports/hw05/RUN_LOG.txt`.
