# HW9 - Redis caching in front of the HW8 system (Kavan Siddesh, SID4 9486, PREFIX s9486)

Run everything from the repo root, in this order. Every `make` target appends to `reports/hw09/RUN_LOG.txt`
with a `(Kavan Siddesh)` header line.

## 0. Services (once per session)

| What | How |
|---|---|
| Python env | `.venv` from HW5-HW8 (`source .venv/bin/activate`, or just use `make`) |
| Packages added in HW9 | `redis==6.4.0`, `numpy==2.3.3` (in `requirements.txt`) |
| MySQL `s9486_rel` | the same local MySQL server as HW4-HW8 (`DATABASE_URL` in `.env`) |
| Docker Desktop | must be running |
| Redis 8.2.2 + Kafka | `make hw9-up` (Redis from `Homework9/docker-compose.yml`, Kafka + topics from the HW8 `docker-compose.yml`) |
| Ollama | the Ollama app running; models `llama3.2:3b` (HW5-HW8) and `all-minilm` (`ollama pull all-minilm`, 45 MB) |

`make hw9-ps` shows the containers, the Redis version, the vector indexes, and `ollama list`.

## 1. Run order

| Step | Command | Part | Model? |
|---|---|---|---|
| 1 | `make migrate-hw09` | adds `listings.view_count` (safe to rerun) | no |
| 2 | `make counter-demo` | Part 1: 25 accesses, sync at 10 and 20 | no |
| 3 | `make cache-demo` | Part 2: 12 queries through the semantic cache (~5 min) | yes |
| 4 | `make sweep` | Part 3.2-3.4: 10 seeds + 40 cases x 5 thresholds (~30 min) | yes |
| 5 | `make stale-demo` | Part 3.5: stale hit, then version-marker invalidation (~3 min) | yes |
| 6 | `make part4-data` | builds reference + input datasets (already done once; do not rerun after the test runs) | no |
| 7 | `make revision-demo` | Part 4.1: controlled bad first answer -> feedback -> revision | yes |
| 8 | `make part4-train` | Part 4.2-4.3: lessons from training, validation gate | yes |
| 9 | `make variants` | Part 4.4: four variants on the unchanged `test_data.json` | yes |
| 10 | `make metrics-hw09` | fills the tables in `reports/hw09/METRICS.md` | no |
| 11 | `make test-hw9` / `make verify-hw09` | automated checks / evidence check -> `verification.json` | no |
| 12 | `make report-hw09` | `reports/hw09/report.pdf` and `Kumar_HW9.pdf` | no |

`make cache-reset` empties only the HW9 cache namespaces (`s9486:semcache:*`, `s9486:sweep:*`,
`s9486:stale:*`, `s9486:test:*`) and their indexes. Nothing in HW9 calls FLUSHALL/FLUSHDB.

## 2. Where things are

| Path | What |
|---|---|
| `Homework9/hw9/listing_store.py` | MySQL + Redis class for listings; Part 1 method `increment_listing_views()` |
| `Homework9/hw9/semantic_cache.py` | Redis HASH entries + `FT.CREATE` vector index (FLAT, COSINE, 384 dims) |
| `Homework9/hw9/embeddings.py` | all-minilm embeddings through Ollama |
| `Homework9/hw9/ingress.py` | cache in front of the HW8 pipeline, data-version check |
| `Homework9/hw9/pipeline.py` | the HW8 Kafka pipeline (`send_and_wait`) and starting the three HW8 agents |
| `Homework9/hw9/agents.py` | Answering Agent, Evaluator Agent, lessons, validation rule, the four variants |
| `Homework9/data/` | `cache_cases.yaml`, `reference_data.json`, `training/validation/test_data.json`, `lessons.json` |
| `Homework9/scripts/` | one script per part (the `make` targets above) |
| `Homework9/tests/run_hw9_tests.py` | automated checks (no model calls) |
| `reports/hw09/` | `RUN_LOG.txt`, `raw/`, `METRICS.md`, `AI_USE.md`, `verification.json`, report PDFs |

## 3. Redis keys (all start with s9486:)

| Key | Type | Used by |
|---|---|---|
| `s9486:views:listing:<id>` | string counter (INCR) | Part 1 |
| `s9486:semcache:entry:<id>` | HASH (query, answer, embedding, data_version, depends_on) | Part 2 |
| `s9486:sweep:entry:<id>` | HASH, same fields | Part 3 sweep |
| `s9486:stale:entry:<id>` | HASH, same fields | Part 3.5 |
| `s9486:idx:semcache`, `s9486:idx:sweep`, `s9486:idx:stale` | FT vector indexes | Parts 2-3 |

## 4. Changes outside Homework9/

- `config.py`: `AGENT_NUM_PREDICT = 512`.
- `domain_tools/agent.py`: optional `num_predict` and per-call `seed` in `OllamaModel.chat`. The defaults keep
  the HW5-HW8 behavior.
- `kafka_agents/llm.py`: caps the agent replies, and retries an unusable JSON reply once with seed+1. llama3.2
  sometimes never stopped in JSON mode; see `reports/hw09/AI_USE.md`.
- `Makefile`: HW9 targets. `requirements.txt`: `redis`, `numpy`.
- `pyproject.toml`: Ruff ignores the two starter files and knows the `hw9` package.
- MySQL: a new column `listings.view_count INT NOT NULL DEFAULT 0`.
- `Homework9/demo.py` (starter): its Redis keys now start with `s9486:`, and `flushdb()` was replaced by a
  prefix-only delete. `caching_agents.py` is unchanged.
