# HW10 - evaluation, judge validation, tracing and dashboard (Kavan Siddesh, SID4 9486, PREFIX s9486)

Run from the repo root. Every `make` target except `label-drafts` and `dashboard` appends to
`reports/hw10/RUN_LOG.txt`.

| Step | Command | What it does |
|---|---|---|
| 0 | `make hw10-up` | Redis (HW9 compose) + the HW8 Kafka broker and topics. Ollama must be running (llama3.2:3b, all-minilm). |
| 1 | `make eval-cases` | Freezes 20 real Writer drafts from `s9486_drafts` into `Homework10/data/eval_cases.json` (only once) |
| 2 | `make label-drafts` | I label each draft 1-5 by hand -> `human_labels.csv`, then commit both files before step 6 |
| 3 | `make trace-demo` | Part 2 evaluated question + Part 4.2 hit / miss / failed traces |
| 4 | `make latency-run` | Part 4.3: 50 confirmed cache misses + 10 hits (`make latency-resume` keeps finished requests after an interruption) |
| 5 | `make judge-validation` | Part 3: judge vs my labels, 3 runs (refuses if the labels are not committed) |
| 6 | `make metrics-hw10` | Fills the tables in `reports/hw10/METRICS.md` from `raw/` |
| 7 | `make test-hw10`, `make verify-hw10` | Automated checks / evidence checks -> `verification.json` |
| 8 | `make dashboard` | Streamlit dashboard on http://localhost:8501 (Summary, Evaluation, Trace lookup) |
| 9 | `make report-hw10` | `reports/hw10/report.pdf` and `Kumar_HW10.pdf` |

## Where things are

| Path | What |
|---|---|
| `Homework10/hw10/judge.py` | deepeval GEval with a local Ollama judge (llama3.2:3b, temperature 0, num_ctx 2048, 1-5 rubric) |
| `Homework10/hw10/evaluator.py` | joins plan/draft/final by correlation_id from Kafka, runs the four criteria under a deadline |
| `Homework10/hw10/traced_ingress.py` | HW9 cache + HW8 pipeline with one trace_id (= correlation_id) and spans per stage |
| `kafka_agents/tracing.py` | `write_span()`; the agents call it from `kafka_agents/base.py` when `TRACE_SPANS_FILE` is set |
| `Homework10/hw10/analysis.py` | journeys, queue wait, p50/p95 stage table (used by the scripts, dashboard and report) |
| `Homework10/dashboard/app.py` | Streamlit dashboard |
| `reports/hw10/raw/spans.jsonl` | every span of every traced request |

## Changes outside Homework10/
- `kafka_agents/base.py`:
  - writes one span per message (stage, queue wait from the Kafka record timestamp, attempts, error)
  - adds a test-only `test.fail_stage` hook for the failed-trace demo
- `kafka_agents/send_question.py`: optional `correlation_id` and `test` parameters.
- `kafka_agents/tracing.py` is new.
- None of these change HW8/HW9 behavior unless tracing is turned on, and the HW8/HW9 tests still pass.
- `requirements.txt`: `deepeval`, `streamlit`, `scipy`. `Makefile`: HW10 targets. `pyproject.toml`: Ruff
  ignores the starter files. `.gitignore`: starter demo folder, PDF, screenshots.
