# HW5 Metrics - SID4 9486 (Kavan Siddesh)

Configuration: PORT_BASE 8486, PREFIX s9486, SEED 9486, VERIFY_SEED 269486, DOMAIN_ID 6
(rental housing listings), local model llama3.2:3b via Ollama, Apple M1 8 GB.
Tables between the markers are written by the scripts from the raw files; do not edit them by hand.

## Part 3 - Fault injection (50 calls per rate, seed VERIFY_SEED = 269486)

Retry policy: up to 3 attempts per call (1 try + 2 retries), backoff 50 ms then 100 ms
(doubling, capped at 400 ms), 2.0 s timeout per attempt. Latency is the wall-clock time of
`execute_tool`, including backoff waits. p99 uses the nearest-rank method; with 50 calls
that is the slowest call.

<!-- retry-table:start -->
| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) | Attempts | Injected failures | Calls retried |
|---|---|---|---|---|---|---|
| 0% | 100% (50/50) | 0.85 | 2.24 | 50 | 0 | 0 |
| 20% | 100% (50/50) | 15.34 | 77.19 | 62 | 12 | 12 |
| 50% | 88% (44/50) | 48.22 | 165.03 | 84 | 40 | 24 |

Source: raw/retry_summary.json, run 2026-10-05T13:22:18.
<!-- retry-table:end -->

## Part 5 - Agent scenarios (local Ollama model)

<!-- agent-table:start -->
| Scenario | Input | Steps | Tool calls | Stop reason | max_steps | run_id |
|---|---|---|---|---|---|---|
| search | Find up to 3 rental listings in Campbell. | 2 | 1 | completed | 6 | 38b6186388d4 |
| detail lookup | Give me the details for listing LST-00042. | 2 | 1 | completed | 6 | 082c7036c0be |
| aggregate | How many listings does landlord 3 manage, and how many units are available in total? | 2 | 1 | completed | 6 | 9bf0a8e13fc0 |
| safety rule | Find apartments in San Jose with no kids allowed. | 1 | 1 | safety_block | 6 | 4c80739baffd |
| step ceiling | Compare landlords 1, 2, 3, 4 and 5. Call landlord_portfolio_stats separately for each of the five landlords, and only answer after you have all five results: which one manages the most listings? | 3 | 2 | max_steps | 3 | e96c59eb9802 |

Model: llama3.2:3b (temperature 0, seed 9486). Step-by-step log: raw/agent_runs.jsonl.
<!-- agent-table:end -->
