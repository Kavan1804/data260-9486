# HW10 Metrics - Kavan Siddesh (SID4 9486, PREFIX s9486)

The tables between the `<!-- ...:start -->` / `<!-- ...:end -->` markers are written by `make metrics-hw10` from
`reports/hw10/raw/`. Every number comes from a logged run in `RUN_LOG.txt`.

Setup:
- Mac with M1 chip and 8 GB of memory.
- HW8 Kafka pipeline (planner, writer, reviewer) with llama3.2:3b.
- HW9 Redis semantic cache (namespace `s9486:hw10`, threshold 0.85).
- Judge: deepeval GEval with llama3.2:3b in Ollama, temperature 0, 1-5 rubric.

## Summary (dashboard page 1)

<!-- summary:start -->
All logged HW10 requests (2026-11-16T05:38:30 to 2026-11-16T11:57:10 UTC, source raw/spans.jsonl): 65 requests, 11 hits / 54 misses (hit rate 16.9%), 2 errors (error rate 3.1%); successful miss end-to-end p50 56.0 s, p95 104.9 s; hit p50 42 ms.
<!-- summary:end -->

## Part 2 - evaluation of one end-to-end question

<!-- part2:start -->
Question: Who is the landlord for listing LST-00117, and how many units are open there?  
trace_id: `a791b5a3-399f-4f43-bfb8-48b97b212288` - judge `llama3.2:3b` (temperature 0.0, num_ctx 2048), evaluation took 34.28 s, 3 judge calls. Final answer identical to the draft: True.

| Criterion | Score (1-5) | Saved with it |
|---|---|---|
| Plan Quality | 3 | reason: The response partially covers the question, but the steps are vague and repetitive, and the order is not sensible. The steps do not follow a logical flow and would make the writer guess facts, such as the available_units field. The response lacks specificity and clarity. |
| Writer Helpfulness | 4 | trace_id `a791b5a3-399f-4f43-bfb8-48b97b212288` |
| Final Answer Helpfulness | 4 | final answer: Here's the step-by-step answer: 1. Search the s9486_rel listings database for the landlord of LST-00117. The landlord of LST-00117 is found to be Oscar Tran. 2. Extract the landlord's name and contact information from the database. The extracted information is: Landlord Name: Oscar Tran. 3. Check th |
| Final-vs-Draft Improvement | draft 4, final 4, difference +0 | The Reviewer approved the draft and passed it on unchanged (final answer = draft text), so the final answer cannot be better than the draft; the judge gave both the same score. |
<!-- part2:end -->

### Scores by stage over the 50 evaluated requests (Part 4.3 run)

<!-- stage-scores:start -->
| Stage / criterion | Mean | Median | Min | Max | Scores 1/2/3/4/5 |
|---|---|---|---|---|---|
| Planner - Plan Quality | 3.04 | 3 | 1 | 4 | 3/5/29/13/0 |
| Writer - Writer Helpfulness | 3.04 | 3 | 1 | 5 | 6/6/25/6/7 |
| Reviewer output - Final Answer Helpfulness | 3.04 | 3 | 1 | 5 | 6/6/25/6/7 |

Evaluated requests: 50 of 50. Final - draft: 0 better, 50 same, 0 worse (mean +0.00).
<!-- stage-scores:end -->

## Part 3 - judge vs human labels

<!-- judge:start -->
| Judge scores vs human labels | Spearman | p-value | Mean abs. difference | Exact matches |
|---|---|---|---|---|
| run1 | 0.171 | 0.4722 | 1.65 | 1/20 |
| run2 | 0.171 | 0.4722 | 1.65 | 1/20 |
| run3 | 0.171 | 0.4722 | 1.65 | 1/20 |
| median_of_3 | 0.171 | 0.4722 | 1.65 | 1/20 |

| Repeatability (3 runs) | Value |
|---|---|
| Cases whose score changed | 0/20 |
| Run pairs with a change | 0/60 |
| Mean absolute change | 0 |
| Max absolute change | 0 |

| Case | Human | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| c01 | 5 | 3 | 3 | 3 |
| c02 | 5 | 3 | 3 | 3 |
| c03 | 4 | 1 | 1 | 1 |
| c04 | 4 | 2 | 2 | 2 |
| c05 | 4 | 3 | 3 | 3 |
| c06 | 3 | 3 | 3 | 3 |
| c07 | 4 | 3 | 3 | 3 |
| c08 | 5 | 3 | 3 | 3 |
| c09 | 5 | 3 | 3 | 3 |
| c10 | 5 | 3 | 3 | 3 |
| c11 | 5 | 2 | 2 | 2 |
| c12 | 4 | 3 | 3 | 3 |
| c13 | 4 | 1 | 1 | 1 |
| c14 | 5 | 4 | 4 | 4 |
| c15 | 5 | 3 | 3 | 3 |
| c16 | 3 | 4 | 4 | 4 |
| c17 | 4 | 3 | 3 | 3 |
| c18 | 5 | 3 | 3 | 3 |
| c19 | 4 | 3 | 3 | 3 |
| c20 | 3 | 2 | 2 | 2 |
<!-- judge:end -->

## Part 4.2 - trace examples

<!-- traces:start -->
| Example | trace_id | Stages (duration ms, status) |
|---|---|---|
| miss | `a791b5a3-399f-4f43-bfb8-48b97b212288` | cache_lookup 62 ok, pipeline 52,157 ok, planner 16,741 ok, writer 23,208 ok, reviewer 11,681 ok, cache_store 173 ok, evaluation 34,276 ok, request 87,353 ok |
| hit | `ce1af7c1-6c4b-448e-b761-f3482d74c9e9` | cache_lookup 707 ok, request 709 ok |
| failed | `7df2fa3a-214e-4d0e-b1be-faa1ce3172d8` | cache_lookup 53 ok, pipeline 90,043 error, planner 1,506 error, request 90,604 error |

Failed trace: failing stage **planner** (3 attempts, sent to the dead-letter topic), error: `RuntimeError: injected failure in planner (HW10 failed-trace demo)`.
<!-- traces:end -->

## Part 4.3 - stage latency (50 cache misses)

<!-- latency:start -->
| Stage | p50 (ms) | p95 (ms) | % of cache-miss end-to-end |
|---|---|---|---|
| Cache lookup | 183.2 | 1,006.8 | 0.5% |
| Planner | 9,019.2 | 18,945.5 | 15.7% |
| Writer | 18,484.2 | 28,982.0 | 29.7% |
| Reviewer | 6,862.0 | 22,858.2 | 14.3% |
| Queue wait (total) | 96.2 | 3,084.0 | 1.4% |
| Evaluation | 19,967.1 | 33,474.7 | 37.0% |
| (other: Kafka client setup, offset reads, cache store) | | | 1.4% |

Requests: 50 confirmed cache misses (served from cache: 0); end-to-end p50 55.7 s, p95 105.6 s. Sessions: earlier (resumed): 20, this run: 30.
Cache hits (separate metric): 10/10 served from cache, p50 42 ms, max 248 ms.
<!-- latency:end -->

## Notes

### Coordination
- **Planner.** Plans scored a median of 3. 29 of the 50 got exactly 3 and none got 5. The judge's reasons are
  mostly "vague or repetitive steps". That matches what I see: the Planner often adds steps like "check the
  available_units field" even when the question is about the landlord.
- **Writer.** Drafts also averaged 3.04, with the widest spread (seven 1s and seven 5s). The Writer usually
  follows the plan literally. Some drafts then restate the plan ("I will follow the plan step by step: 1. Search
  the database ...") instead of simply answering, and the judge marks those down.
- **Reviewer.** The final answer never scored higher than the draft: 0 better, 50 same, 0 worse. This is how my
  HW8 Reviewer is built. It only approves or flags a draft and always passes the Writer's draft on unchanged as
  the answer. In these 50 requests it approved 49 and flagged 1 as needs_revision, and even that one went out
  unchanged because nothing sends it back to the Writer.
- **So the coordination is one-way.** Plan quality limits draft quality, and the Reviewer adds a label but no
  improvement. To make the Reviewer useful, a flagged draft would go back to the Writer with the reviewer notes
  (one bounded retry), like the Part 4 repair loop in HW9.
- The improvement result is not forced: the honest answer is "no improvement".

### Judge trust
- **Agreement is weak.** Spearman 0.171 (p = 0.47, not significant), mean absolute difference 1.65, and only 1
  of 20 exact matches.
- **The judge is much harsher than me.** It scored lower on 18 of 20 drafts (mean 2.75 vs my 4.3) and put 13 of
  20 at "3", so it barely separates good drafts from weak ones.
- **Some of its reasons are wrong, not just strict.** The 3B judge seems to read only the start of long drafts
  and over-penalizes the plan recap.
- c13 got a 1 for giving steps to "How do I report a noisy neighbor?", though steps are the right answer.
- c11 got a 2 for listing documents "not requested", though those documents are exactly what the question asks
  for.
- c03 got a 1 for "not giving the landlord's name", although the draft says "The landlord's name is Neha
  Nakamura", which matches the database.
- **Repeatability is perfect:** 0 of 20 cases changed across the 3 runs, and mean and max change are 0. That is
  expected at temperature 0 with the same inputs. It only shows the judge is consistent, not that it is
  right: it repeats the same mistakes every time.
- **I would not let this judge gate a deployment.** Before trusting it I would want:
  1. a larger labeled set (100+ drafts, with more weak drafts so the labels are not mostly 4-5), with a second
     human labeler to measure human-human agreement first
  2. a stronger judge model, or an ensemble, reaching Spearman of about 0.6 or more with p < 0.05 on that set
  3. repeatability checked with sampling on (temperature > 0), since temperature 0 hides how unstable the scores
     might be
  4. a calibration step that maps the judge's scale onto the human scale
  Until then it is only useful for spotting obvious failures (1s), and even that needs a person to review them.
- **My own limitation:** my labels are from one person, and I mainly rated factual correctness and usefulness.
  The judge's rubric also penalizes padding, which accounts for part of the gap (for example c01).

### Latency
- **Evaluation is the largest contributor** (37.0% of cache-miss end-to-end time, p50 20.0 s): three more 3B
  model calls after the answer is already done. Next is the **Writer** (29.7%, p50 18.5 s), the longest
  generation. Planner and Reviewer are 15.7% and 14.3%.
- **Kafka itself is cheap.** Total queue wait across the four hops has a p50 of 96 ms (1.4%). The p95 of 3.1 s
  comes from a few requests in session 1 (21:43-22:05 local), just before Docker stopped responding. The
  requests were sent one at a time, so no message was waiting behind another one; the agents and the Kafka
  broker were slow to respond while the Mac was using about 13 GB of swap (the worst Reviewer hop waited 9.3 s). The cache lookup is 0.5%.
- **What I would optimize first:** take evaluation off the request path. Run it asynchronously on the
  s9486_final topic, and only on a sample of requests. That removes about 37% of the latency the user waits for,
  without touching answer quality. After that I would make the Writer shorter: a tighter max length, and no
  plan recap in the prompt.
- **Cache hits are a separate metric:** 10 of 10 served from the cache, p50 42 ms, compared with p50 55.7 s for
  a miss.

### Run notes
- **The first 50-request run was stopped and archived.** The judge first used a 4096-token context while the
  agents used 2048. Ollama kept reloading llama3.2:3b, and the first request took 220 s. Those spans are in
  `raw/archive/` and are not used. The judge was changed to 2048 before any Part 3 score existed.
- **The second run stopped at request 21 of 50** when Docker stopped responding: the Mac had about 13 GB of swap
  in use. Request 21's evaluator could not reach Kafka; it recorded an `evaluation` error and moved on instead
  of hanging, which is one of the two errors counted on the Summary page.
- **The run was resumed:** 20 completed requests were kept from the spans log (session 1) and the other 30 were
  run in session 2, with the same seeded questions in the same order. Redis had restarted empty, so the one
  trace-demo cache entry was added back (one extra miss, not one of the 50) before the 10 cache-hit requests.
- **My Lab 1 Docker containers (port 9092) were stopped** while HW10 ran.
