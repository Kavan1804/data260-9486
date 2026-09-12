# HW2 Metrics

Generated with `python scripts/run_graph_experiments.py` using the frozen case in `cases/schema_input.json` and deterministic fake-model fixtures for pipeline verification. Replace with the same experiment using the local `qwen3:8b` run log before submission.

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---:|---:|
| Valid first attempt | 30 | 3.2 |
| Valid after 1 retry | 0 | - |
| Valid after 2+ retries | 0 | - |
| Hit turn ceiling | 0 | - |

Ceiling 2: 20/20 completed, mean pipeline latency 3.2 ms. Ceiling 10: 20/20 completed, mean pipeline latency 3.3 ms. The smaller ceiling is selected for deployment in this deterministic fixture because it completed all runs with slightly lower mean latency.

The ceiling comparison and adversarial results are stored in `raw/ceiling_comparison.json` and `raw/adversarial_runs.json`.
