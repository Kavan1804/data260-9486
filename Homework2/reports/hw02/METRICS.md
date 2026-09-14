# HW2 Metrics

Generated with `python scripts/run_graph_experiments.py` using the frozen case in
`cases/schema_input.json` and the real local `qwen3:4b` model via `src/model_client.py`
(Ollama on localhost:11434). Full per-run records are in `raw/schema_runs.json`,
`raw/ceiling_comparison.json`, and `raw/adversarial_runs.json`; the full console
transcript is in `raw/graph_experiments_console.log` and `RUN_LOG.txt`.

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---:|---:|
| Valid first attempt | 30 | 4600.8 |
| Valid after 1 retry | 0 | - |
| Valid after 2+ retries | 0 | - |
| Hit turn ceiling | 0 | - |

Turn-ceiling comparison (20 runs each, same frozen input and model settings):

| Turn ceiling | Runs | Completed | Completion rate | Mean latency (ms) |
|---|---:|---:|---:|---:|
| 2 | 20 | 20 | 100% | 4564.4 |
| 10 | 20 | 20 | 100% | 4419.8 (1 run needed a retry: turn_count 3, latency 12555.4 ms) |

Deployment choice: turn_ceiling=2. Both ceilings reached the same 100% completion
rate on this frozen input, and ceiling 2 bounds the worst-case retry latency far
more tightly (a single retry under ceiling 10 cost ~12.6s) while giving up nothing
in observed completion rate.

Adversarial input (5 runs, turn_ceiling=2): the model was told to ignore the
tag-count/length rules and return one tag plus a 60+ word summary. It hit the
turn ceiling in 5/5 real runs (mean latency 16897.3 ms), i.e. it never produced a
schema-valid proposal under the 2-attempt budget. See `raw/adversarial_runs.json`
for per-run detail and the report for the failure explanation and proposed fix.
