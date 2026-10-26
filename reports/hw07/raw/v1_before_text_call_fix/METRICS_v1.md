# HW7 first run (v1), before the text-tool-call fix

These are the real Part 2 and Part 3 tables from the first run on 2026-10-26, kept as evidence. The harness then got a fix (see METRICS.md notes) and both experiments were run again.

## Part 2 (v1)

21 attempts (7 per task), model llama3.2:3b, temperature 0.7, max_steps 8, max failed repairs 2, seed = VERIFY_SEED + attempt.

| Measure | Result |
|---|---|
| Tool-call attempts (slots) | 21 |
| Well-formed before repair (first try) | 66.7% (14/21) |
| Well-formed after repair path | 100.0% (21/21) |
| Repairs that worked / failed | 7 / 2 |
| Task success (verifier) | 0.0% (0/21) |
| Total tool calls executed | 21 (mean 1.00 per attempt) |

| Task | Attempts | Verifier pass | Mean tool calls | Stop reasons |
|---|---|---|---|---|
| A | 7 | 0 | 1.00 | {'completed': 7} |
| B | 7 | 0 | 1.00 | {'completed': 7} |
| C | 7 | 0 | 1.00 | {'completed': 7} |

| Failure type | Attempts with this failure |
|---|---|
| malformed arguments | 7 |
| unknown tool | 0 |
| text instead of tool | 0 |
| lost chain | 21 |

Raw rejected-call kinds (every rejection, not per attempt): {'schema_validation': 9}.
Error recovery (LST-99999): handled without crashing = True, tool error = 'No listing found with listing_code LST-99999', stop_reason = completed.

## Part 3 (v1)

5 runs per task x 3 tasks per loop, same seeds for both loops. Means are per run; Reflexion numbers include all attempts of a run.

| Metric | Original loop | Reflexion loop |
|---|---|---|
| Task success | 0/15 (0%) | 0/15 (0%) |
| Unsupported claims | 8 claims in 5 runs | 8 claims in 5 runs |
| Retry rate | 0/15 runs (0 retries) | 15/15 runs (30 retries) |
| Tool calls (mean per run) | 1.00 | 3.00 |
| Tokens (mean per run) | 1266 | 4979 |
| Latency (ms, mean per run) | 14290 | 49078 |
| Verifier false rejections (strict FAIL, answer correct) | 10 | 10 |
| Stop reasons | completed: 15 | budget_exhausted: 1, human_review: 14 |
