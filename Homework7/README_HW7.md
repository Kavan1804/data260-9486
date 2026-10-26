# Homework 7 - JWT roles, agent loop, Reflexion, bike-share ReAct agent, prompt injection, file tools

For HW7 I kept extending the same root-level app. This folder only has the HW7 scripts, tests and fixtures;
the results (RUN_LOG, raw data, METRICS, AI_USE, threat model, verification.json, report) are in `reports/hw07/`.
The professor's Demo 7 project and the DOCX stay local and are gitignored (the demo has its own `.git` and `.env`).

## What I added and where

| Part | Files |
|---|---|
| 1 JWT + roles | `backend/app/security.py` (JWT, `get_current_user`, `require_roles`), `backend/app/main.py` (routes), `backend/app/models.py` (`users.username`, `users.role`), `scripts/migrate_hw07.py`, `frontend/src/api/listingsApi.js` (bearer token) |
| 1 Linting | `pyproject.toml` (Ruff E/F/I, line length 120), `.pre-commit-config.yaml` (ruff-check --fix, ruff-format) |
| 2 Agent loop | `domain_tools/agent.py` (`run_agent` repair path, counters, budgets), `domain_tools/validation.py`, `Homework7/fixtures/agent_tasks.json` |
| 3 Reflexion | `domain_tools/fixed_tasks.py` (verifier), `domain_tools/reflexion.py` |
| 4 Bike share | `bikeshare/tools.py` (csv_sql, policy_retriever, calculator), `bikeshare/pricing.py`, `bikeshare/agent.py` (LangGraph), `backend/app/routers/bikeshare.py`, `frontend/src/pages/BikeShare.jsx`, `Homework7/fixtures/bikeshare/` |
| 5 Injection | `Homework7/fixtures/hostile_pricing.html`, `reports/hw07/THREAT_MODEL.md`, `Homework7/scripts/run_injection_tests.py` |
| 6 File tools | `agent_tools/file_tools.py`, `agent_tools/safety_gate.py` |
| Checks | `Homework7/tests/run_hw7_tests.py` (22 offline + 1 live), `Homework7/scripts/verify_hw07.py` |

Roles on my existing routes: `GET /listings`, `/listings/{id}`, `/landlords`, ... any logged-in role;
`POST`/`PUT` writer or moderator; `DELETE` moderator only. `POST /auth/login` takes a username and password
and returns a JWT; `GET /auth/me` returns the user and role. The HW6 `/api/*` routes are unchanged.

## Settings

All in `.env` (not committed; placeholders in `.env.example`): `DATABASE_URL` (MySQL `s9486_rel`),
`JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` (30), and `HW7_READER_PASSWORD` / `HW7_WRITER_PASSWORD` /
`HW7_MODERATOR_PASSWORD` for the three test users `s9486_reader`, `s9486_writer`, `s9486_moderator`.
Model: `llama3.2:3b` through Ollama for everything.

## How I ran it (repo root)

```bash
make migrate-hw07          # users table: username + role, seed 3 test users (bcrypt only)
make backend               # FastAPI on 8486 (separate terminal)
make auth-demo             # Part 1: all the 200/201/401/403 cases
make test-all              # HW5 + HW6 + HW7 offline tests
make test-hw7-live         # + the JWT/role flow against MySQL
make lint format-check     # Ruff
make agent-reliability     # Part 2: 21 attempts + nonexistent ID
make reflexion-compare     # Part 3: original vs Reflexion
make bikeshare-scenarios   # Part 4: build the two scenario CSVs from the real Bay Wheels data
make bikeshare-run         # Part 4: agent on both scenarios with the saved pricing snapshot
make injection-tests       # Part 5: 3 attacks x 3 defense levels
make file-tools-demo       # Part 6: glob -> search -> read + 10-command safety gate
make verify-hw07           # reports/hw07/verification.json
```

The bike-share page is at `http://localhost:5173/bikeshare` after `make frontend`.

## Things I want to point out

- **Why Bay Wheels.** All four pricing pages loaded as plain HTML, but Bay Wheels is the only one that sells
  a Month pass ($29/month), so "monthly membership vs pay-per-use" fits it without converting an annual price.
- **Scenarios.** The public trip data has no rider id, so each scenario is real trips (real bike type, stations
  and duration) treated as one rider. Only the dates were moved, with a fixed seed, to spread the rides over
  26 weeks (membership wins) or 48 months (pay-per-use wins). `build_bikeshare_scenarios.py` shows the exact rule.
- **Numbers come from tools.** The cost table is computed with `csv_sql` and `calculator`. The agent runs
  twice: a draft turn on its own (kept and shown as "draft decision"), then a final turn that gets the
  tool-computed totals, the cheaper option and the pricing snippets. I did this because in testing
  llama3.2:3b called the calculator with made-up numbers before reading any data, and even with the right
  totals it once said $1,392 was less than $1,124.84. The page shows whether the final decision agrees with
  the tool-computed numbers.
- **The small model.** llama3.2:3b usually answers after one tool call, so most "lost chain" failures in
  Part 2 are real model behaviour. I checked that it was not my message format by trying Ollama's
  `tool_name` field; it made no difference.
