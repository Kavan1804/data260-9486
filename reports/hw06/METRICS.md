# HW6 Metrics - SID4 9486 (Kavan Siddesh)

Configuration: PORT_BASE 8486, PREFIX s9486, SEED 9486, VERIFY_SEED 269486, DOMAIN_ID 6 (rental
housing listings), MacBook Air with Apple M1 chip (8 GB), local model llama3.2:3b via Ollama
(temperature 0, seed 9486, num_ctx 8192). No embedding model was installed, so episodes use my
local hashed bag-of-words embedding (`hash-bow-256`). Experiments ran on 2026-10-19.

The tables between the markers are written by `make memory-cost` from the files in `raw/`; I did not
edit them by hand. "Mean prompt tokens/turn" is Ollama's own `prompt_eval_count` for the reply call
(conversation turns only, the 5 probes are left out). The split into primer / summary / window /
episodic facts is an estimate (characters / 4), because Ollama only gives me the total. The real
count came out at about 94% of my estimate in every setting.

## Part 3.3 - short-term memory size (30-message conversation + 5 probes, fresh session each)

<!-- memory-table:start -->
| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |
|---|---|---|---|
| SHORT_TERM_N=4 | 624.5 | 47276.6 | 4.2 |
| SHORT_TERM_N=12 | 1135.5 | 42067.9 | 4.6 |
| SHORT_TERM_N=30 | 1906.4 | 103772.5 | 4.4 |
| Compression policy (N=12, last 4 verbatim, older clipped to 120 chars) | 768.5 | 43939.1 | 4.0 |
<!-- memory-table:end -->

### Estimated prompt composition per turn (tokens, estimate)

<!-- token-breakdown:start -->
| Setting | Primer | Long-term summary | Short-term window | Episodic facts | Upkeep prompt tokens/turn | Rows using estimate |
|---|---|---|---|---|---|---|
| SHORT_TERM_N=4 | 64.0 | 208.7 | 332.6 | 29.6 | 384.6 | 0/30 |
| SHORT_TERM_N=12 | 64.0 | 242.3 | 842.6 | 29.6 | 377.4 | 0/30 |
| SHORT_TERM_N=30 | 64.0 | 235.5 | 1685.5 | 29.6 | 374.1 | 0/30 |
| Compression policy (N=12, last 4 verbatim, older clipped to 120 chars) | 64.0 | 284.0 | 372.4 | 29.6 | 355.0 | 0/30 |
<!-- token-breakdown:end -->

## Part 3.4 - memory-saving policy (compression) vs. the N=12 baseline

<!-- policy-table:start -->
| Baseline | Policy | Prompt tokens/turn saved | Saving | Probe quality change |
|---|---|---|---|---|
| SHORT_TERM_N=12 (1135.5) | Compression policy (N=12, last 4 verbatim, older clipped to 120 chars) (768.5) | 367.0 | 32.3% | -0.6 |

Against SHORT_TERM_N=30 the policy saves 59.7% of prompt tokens per turn.
<!-- policy-table:end -->

## Part 3.5 - memory cost, 10,000 conversations x 30 turns ($1/M input, $5/M output)

<!-- cost-table:start -->
| Case | Setting | Input tokens/turn | Output tokens/turn | Cost, reply only | Cost, with upkeep |
|---|---|---|---|---|---|
| Best | SHORT_TERM_N=4 | 624.5 (+384.6 upkeep) | 134.1 (+79.8 upkeep) | $388.50 | $623.58 |
| Worst | SHORT_TERM_N=30 | 1906.4 (+374.1 upkeep) | 126.0 (+78.9 upkeep) | $760.92 | $991.50 |

Selection rule: best = cheapest setting (with upkeep) whose probe score is within 0.5 of the top score 4.6; worst = most expensive setting (ties broken by lower probe score). Price: $1.0/M input, $5.0/M output; 10,000 conversations x 30 turns.
<!-- cost-table:end -->

## Probe scores per question (raw/probe_scores.csv)

| Probe | N=4 | N=12 | N=30 | Compression |
|---|---|---|---|---|
| p1 name + city | 3 | 3 | 3 | 3 |
| p2 budget (updated at turn 14) | 5 | 5 | 5 | 2 |
| p3 pet name + type | 5 | 5 | 5 | 5 |
| p4 move-in date | 5 | 5 | 4 | 5 |
| p5 flooring + reason | 3 | 5 | 5 | 5 |
| Mean | 4.2 | 4.6 | 4.4 | 4.0 |

## Notes

- **Best and worst.** I picked "best" as the cheapest setting whose probe score is within 0.5 of the top
  score (4.6 for N=12), and "worst" as the most expensive setting. N=4 scored 4.2, which is close enough,
  and it is the cheapest, so it is the best. N=30 is the most expensive and did not score higher than
  N=12, so it is the worst. The compression run (4.0) was more than 0.5 below the top, so I did not count it.
- **Upkeep cost.** Fact extraction and summaries add about 355-385 input tokens and 80 output tokens per
  turn. That is roughly 40% of the cost for N=4, so the memory system itself is not free.
- **Which probes failed.** No setting remembered the name "Priya" (p1 = 3 everywhere). The extractor never
  saved the name as a fact and the summaries dropped it, so once turn 1 left the window it was gone. With
  N=4 the model still knew I wanted hardwood or vinyl floors but gave a made-up reason instead of the allergy.
  N=30 said "mid-January" instead of January 15.
- **Compression and probe quality.** The compression run lost 0.6 points, all from the budget probe. Both
  budget facts ($2,600 and the newer $2,900) were retrieved, and the model chose the old one. Episodes have
  no "newer value wins" rule, so this is more a retrieval problem than a compression problem. With one run
  per setting and only 5 probes, a difference of 0.2-0.6 is a single question.
- **Latency.** Latency includes the extra extraction and summary calls and was noisy on my 8 GB laptop
  (N=4 ran first and had some very slow turns). N=30 was clearly slower (median 92 s vs 28-38 s).
