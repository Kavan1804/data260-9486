# AGENT.md - durable project and agent instructions (s9486)

<!-- HW6 Part 4. Expanded from Homework1/AGENT.md (the HW1 code-review prompt, kept below
     under "Code review"). Loaded into the system prompt by backend/app/file_memory.py. -->

## Project description
1. This is the DATA 260 shared application for SID4 9486: a rental-housing listings app (DOMAIN_ID 6) that each homework extends in place; never create a separate copy of the app for one homework.
2. HW6 adds a MongoDB document view of listings (`s9486_doc.listings`) and chat memory (`messages`, `summaries`, `episodes`) next to the HW4/HW5 MySQL backend.

## Technology stack
3. Backend: Python 3 + FastAPI on port 8486 (`config.PORT_BASE`), SQLAlchemy/MySQL (`s9486_rel`), PyMongo/MongoDB (`s9486_doc`), Pydantic v2 schemas. Since HW7 the domain routes use JWT bearer auth with roles reader / writer / moderator, and Ruff + pre-commit check every commit.
4. Models: only the local Ollama model, called through the HW5 adapter `domain_tools.agent.OllamaModel`; no hosted or paid model APIs.
5. Frontend: React (Vite) + Redux Toolkit in `frontend/`.

## Coding conventions
6. New functions (HW6 onward) have type hints on all parameters and on the return value.
7. New public functions (name without a leading underscore) have a docstring.
8. Lines are at most 120 characters.
9. Read ports, URLs, database names and model names from `config.py`; never hard-code them or any credential.
10. Backend code under `backend/` does not call `print()`; return data or raise `HTTPException` instead.

## Testing approach
11. Unit tests are plain-assert scripts (`tests/run_offline_tests.py`, `Homework6/tests/run_hw6_tests.py`) that run without MySQL, MongoDB, Ollama or network, using fake models and in-memory stores.
12. Tests that need MongoDB run only with `--live` and use the throwaway database `s9486_doc_test`.

## Prohibited actions
13. Do not import OpenAI, Flask or Redis. LangChain/LangGraph is allowed only in `bikeshare/` (HW7 Part 4 asks for a framework-based ReAct agent); everywhere else the agents stay hand-written.
14. Do not commit `.env`, credentials, `.venv/`, `__pycache__/` or `.DS_Store`.
15. Do not fabricate results, metrics, screenshots, timestamps or commit hashes; report what a real run printed.
16. Do not delete or rewrite working HW1-HW5 code to make a new homework pass.

## Code review (from HW1 AGENT.md)
17. When asked to review code, act as a strict reviewer of correctness, reliability, security, readability and maintainability.
18. Review answers use bullet points only: every non-empty line starts with "- ", with no headings, numbered lists, paragraphs or code fences; if nothing is wrong, return one bullet saying no significant issues were found.
