# Homework 8 - Kafka request/response, three-agent pipeline, failure behavior

For HW8 I kept extending the same root-level app. This folder only has `homework_demo.py`, the HW8 scripts and
the tests; the results (RUN_LOG, raw data, METRICS, AI_USE, verification.json, report) are in `reports/hw08/`.
The professor's DATA236_DEMO8 and multi-agent-demo folders and the PDFs stay local and are gitignored.

## What I added and where

| Part | Files |
|---|---|
| Docker | `docker-compose.yml` (Kafka KRaft + topic setup + worker + FastAPI), `Dockerfile`, `scripts/kafka_create_topics.sh` |
| 1 Request/response | `kafka_service/messages.py` (schema, reuses `ListingCreate`), `kafka_service/worker.py`, `kafka_service/rpc.py`, `backend/app/routers/kafka_listings.py`, `Homework8/homework_demo.py` |
| 2 Agents | `kafka_agents/planner.py`, `writer.py`, `reviewer.py`, `send_question.py`, `base.py` (shared loop), `llm.py` |
| 3 Failures | `kafka_agents/base.py` (idempotency, commit after processing, retries + dead-letter), `Homework8/scripts/failure_*.py` |
| Checks | `Homework8/tests/run_hw8_tests.py` (offline), `Homework8/scripts/verify_hw08.py` |

Entity: **Listing**, so the operations are `CREATE_LISTING` / `GET_LISTING` and the id is `listing_id`.

| Topic | Partitions | Used by |
|---|---|---|
| s9486_entity_requests / s9486_entity_responses | 1 / 1 | Part 1 client or API -> worker -> client or API |
| s9486_inbox / s9486_tasks / s9486_drafts / s9486_final | 1 / 2 / 1 / 1 | send_question -> planner -> writer -> reviewer -> send_question |
| s9486_dead_letter | 1 | messages that failed 3 times |

Auto-create is off in the broker, so every topic above is created on purpose by `scripts/kafka_create_topics.sh`.

## Settings

Nothing new goes in `.env`. `KAFKA_BOOTSTRAP` defaults to `localhost:9092` on the Mac; docker-compose sets
`kafka:29092` for the containers. The containers read the existing `.env` at run time (it is never copied into
the image). `WORKER_IDEMPOTENCY=off` is only for the Part 3A "before" run. Model: `llama3.2:3b` through Ollama.

## How I ran it (repo root)

```bash
make kafka-up              # build + start Kafka, topic setup, worker, FastAPI on 127.0.0.1:8486
make kafka-ps kafka-logs   # docker ps, "Consumer is ready and listening...", "FastAPI started at ..."
make kafka-topics          # create (if missing) + list the s9486_ topics
make homework-demo         # Part 1 through Kafka directly
make homework-demo-api     # Part 1 through the FastAPI wrapper
make api-calls             # Part 1 error cases
make pipeline-demo         # Part 2 with all agents started for me (or the 4 terminals below)
make dup-test death-test poison-test ordering-test   # Part 3 (or: make failure-tests)
make metrics-hw08 test-hw8 verify-hw08
make report-hw08
```

Part 2 in four terminals (start the agents first; a new consumer group starts at the end of its topic):

```bash
make planner      # terminal 1  (python kafka_agents/planner.py)
make writer       # terminal 2  (python kafka_agents/writer.py)
make reviewer     # terminal 3  (python kafka_agents/reviewer.py)
make send-question   # terminal 4  (python kafka_agents/send_question.py)
```

The failure tests start their own Writer processes in their own consumer groups, and at the end they move the
normal Part 2 groups past the test messages (`make reset-groups` does the same by hand), so the real agents do
not process them later. Stop the four-terminal agents before running the failure tests.

## Notes

- The `/api/kafka/*` routes do not need a JWT: they only use the worker's in-memory dict, not MySQL.
- JMeter is not part of the HW8 PDF, so I did not run it.
- `make kafka-down` removes the containers, and the topics and messages go with them (no volume).
