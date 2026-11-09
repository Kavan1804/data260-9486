# HW9 Metrics - Kavan Siddesh (SID4 9486, PREFIX s9486)

All tables between the `<!-- ...:start -->` / `<!-- ...:end -->` markers are written by
`make metrics-hw09` from `reports/hw09/raw/`. Every number comes from a logged run in `RUN_LOG.txt`.

Setup:
- Mac with M1 chip and 8 GB of memory.
- MySQL 9.4 (`s9486_rel`) and Redis 8.2.2 in Docker (container `s9486_redis`, vector index via FT.CREATE).
- HW8 Kafka pipeline: planner, writer and reviewer running llama3.2:3b.
- all-minilm embeddings (384 dimensions, cosine).

## Part 1 - view counter

<!-- part1-table:start -->
| Listing | Redis key | Accesses | Synced at | Redis after | MySQL view_count after |
|---|---|---|---|---|---|
| LST-00042 (id 42) | `s9486:views:listing:42` | 25 | 10, 20 | 25 | 20 |
<!-- part1-table:end -->

## Part 2 - semantic cache (threshold 0.85)

<!-- part2-table:start -->
| # | Category | Query | is_cached | Similarity | Latency (ms) |
|---|---|---|---|---|---|
| 1 | new | How many units are available at listing LST-00117? | False | 0.0000 | 45,666.3 |
| 2 | exact | How many units are available at listing LST-00117? | True | 1.0000 | 774.3 |
| 3 | new | What should I check before signing a lease for an apartment in San Jose? | False | 0.0846 | 41,694.1 |
| 4 | paraphrase | Before I sign an apartment lease in San Jose, what things should I check? | True | 0.9667 | 225.6 |
| 5 | new | Who is the landlord for listing LST-00230? | False | 0.5420 | 34,623.7 |
| 6 | paraphrase | Which landlord manages listing LST-00230? | True | 0.9697 | 233.1 |
| 7 | new | How can I get my full security deposit back when I move out? | False | 0.3055 | 104,025.7 |
| 8 | exact | What should I check before signing a lease for an apartment in San Jose? | True | 1.0000 | 151.9 |
| 9 | new | What is a fair way to split rent and utilities with roommates? | False | 0.3393 | 35,990.0 |
| 10 | paraphrase | When I move out, how do I make sure my security deposit is returned? | True | 0.8541 | 154.8 |
| 11 | paraphrase | How many open units does listing LST-00117 have right now? | True | 0.9062 | 146.9 |
| 12 | exact | What is a fair way to split rent and utilities with roommates? | True | 1.0000 | 59.1 |

| Measure | Value |
|---|---|
| Queries (new / exact / paraphrase) | 12 (5 / 3 / 4) |
| Cache hit rate | 7/12 = 58.3% |
| Served from cache: new / exact / paraphrase | 0/5 / 3/3 / 4/4 |
| Average latency, cached | 249.4 ms |
| Average latency, not cached (HW8 pipeline) | 52,400.0 ms |
| HW8 pipeline calls | 5 |
<!-- part2-table:end -->

## Part 3 - threshold sweep (40 cases from cache_cases.yaml)

<!-- sweep-table:start -->
| Threshold | Hit rate | False-hit rate | Mean latency (ms) | Total cost |
|---|---|---|---|---|
| 0.75 | 28/40 = 70.0% | 9/28 = 32.1% | 11,736.1 | $22.62 |
| 0.80 | 26/40 = 65.0% | 7/26 = 26.9% | 14,148.8 | $17.64 |
| 0.85 | 24/40 = 60.0% | 6/24 = 25.0% | 15,998.5 | $15.16 |
| 0.90 | 19/40 = 47.5% | 4/19 = 21.1% | 20,165.9 | $10.21 |
| 0.95 | 19/40 = 47.5% | 4/19 = 21.1% | 20,147.4 | $10.21 |

Total cost = misses x $0.01 + false hits x $2.50. Misses and false hits per threshold:

| Threshold | Misses | False hits | Should-hit cases missed |
|---|---|---|---|
| 0.75 | 12 | 9 | 1 |
| 0.80 | 14 | 7 | 1 |
| 0.85 | 16 | 6 | 2 |
| 0.90 | 21 | 4 | 5 |
| 0.95 | 21 | 4 | 5 |
<!-- sweep-table:end -->

### One false hit

<!-- false-hit:start -->
- Threshold: 0.95
- Cached query (A01): Who is the landlord for listing LST-00305?
- Incoming query (S01, labeled similar): Who is the landlord for listing LST-00350?
- Similarity: 0.9700
- Cached answer returned (key sentence): The available_units field contains the landlord's information: Carmen Chowdhury (Rose Garden Realty).
- Correct answer, fresh pipeline run (key sentence): Looking for the landlord's information in the s9486_rel listings database, I find that the landlord's name is Oscar Tran and the property is managed by Santa Clara Homes.
- Full answers: reports/hw09/raw/false_hit.json
<!-- false-hit:end -->

### Stale answer and invalidation

<!-- stale-table:start -->
| Step | is_cached | Latency (ms) | data_version | Key sentence of the answer |
|---|---|---|---|---|
| first ask | False | 25,528.9 | `@4dd97538` | The available units information for LST-00888 is: available_units=1. |
| repeat before update | True | 205.4 | `@4dd97538` | The available units information for LST-00888 is: available_units=1. |
| stale hit (check off) | True | 50.2 | `@4dd97538` | The available units information for LST-00888 is: available_units=1. |
| version check on | False | 20,282.8 | `@599f8956` | The available_units value is 0. |
| repeat after refresh | True | 262.6 | `@599f8956` | The available_units value is 0. |
<!-- stale-table:end -->

## Part 4 - lessons and validation

<!-- lessons-table:start -->
| Lesson | Failure pattern | From | Validation (failing before -> after) | Decision | use_count |
|---|---|---|---|---|---|
| lesson_001 | The answer omits the number of available units. | tr03 | 0 -> 0 | kept | 8 |
<!-- lessons-table:end -->

## Part 4 - four variants on test_data.json

<!-- variants-table:start -->
| Variant | Correct answers | Incorrect answers | Average attempts | Average latency |
|---|---|---|---|---|
| Baseline | 10 | 2 | 1.00 | 6.46 s |
| Evaluator Repair | 12 | 0 | 1.17 | 7.23 s |
| Lesson Memory | 12 | 0 | 1.17 | 7.38 s |
| Validated Improvement | 12 | 0 | 1.17 | 7.12 s |

Same test_data.json for all four runs: True
<!-- variants-table:end -->

## Notes

### Part 1
The counter only touches MySQL on every 10th view, so 25 views cost 2 database writes instead of 25. The other
side of that is that MySQL can be up to 9 views behind Redis (here it shows 20 while Redis has 25). If Redis
were lost, those views would be lost too.

### Part 2
Every new question was a miss and every exact repeat and paraphrase was a hit. Cached answers came back in
about 0.25 s on average, compared with about 52 s for the HW8 pipeline. Two things to know:

- Q2's 774 ms was the first lookup after a pipeline run, so it is slower than the other hits.
- Q7 (104 s) is the security-deposit question where the Planner's first JSON reply was unusable and was
  retried with seed 9487 (see AI_USE.md).

The paraphrase in Q10 only just passed (0.8541 vs 0.85).

### Part 3.2 - what the sweep shows
- Exact duplicates hit at every threshold (similarity 1.0).
- Paraphrases ranged from 0.68 (P07) to 0.99 (P06). From 0.90 up, five paraphrases miss (P04, P05, P07, P08,
  P09). P07 ("How far in advance must I tell my landlord that I'm moving out?") never hits, even at 0.75.
- The four "same question, different listing" cases (S01-S04: landlord, city, address and home type of another
  listing) scored 0.959-0.970. That is higher than 7 of the 10 paraphrases, so they are false hits at every
  threshold, even 0.95. MiniLM sees `LST-00305` and `LST-00350` as almost the same token string.
- The other "similar" cases (S05-S10) and all 10 unrelated cases drop out as the threshold goes up. Unrelated
  questions never got above 0.56.
- Mean latency goes up with the threshold because every extra miss costs a full pipeline run (~35-50 s). A hit
  costs about 74 ms on average (embedding + Redis KNN + version check).
- Latency note: a case's pipeline time was measured the first time it missed and reused at the other thresholds
  (the run printed "pipeline time reused"). The hit/miss decisions and lookup times were measured fresh at
  every threshold.

### Part 3.3 - why the false hit happens
The cached query "Who is the landlord for listing LST-00305?" and the incoming "Who is the landlord for listing
LST-00350?" share every word except the listing code. The two codes even use the same digits, just in a
different order. A sentence embedding mostly encodes what the question is about ("who is the landlord of a
listing"), and the code is only a small part of the vector, so the similarity is 0.97. The cache returned
Carmen Chowdhury (LST-00305's landlord), but the right answer for LST-00350 is Oscar Tran. The data-version
check does not catch this either: it compares the cached entry's own listing (LST-00305), which did not change.

### Part 3.4 - cost model and the threshold I would ship
- **Cache miss = $0.01.** A miss runs the HW8 pipeline: 3 llama3.2 calls, about 35-50 s of the Mac's GPU, and
  the student waits that long. On a hosted small model the same three calls would be well under a cent, so
  $0.01 also covers some of the waiting.
- **False hit = $2.50.** A false hit gives the student facts about a different listing (the wrong landlord,
  address or city). They may contact the wrong person or go to the wrong place, and then someone has to sort
  it out. I counted about 5 minutes of a support person's time at about $30/hour.

So one false hit costs as much as 250 misses. With these numbers the total cost falls from $22.62 at 0.75 to
$10.21 at 0.90 and 0.95, which are tied: the same 19 hits, the same 4 false hits (S01-S04) and the same 21
misses.

**I would ship 0.90.** It costs the same as 0.95 on my 40 cases, and a paraphrase that scores between 0.90 and
0.95 would still be a hit, while 0.95 would send it to the pipeline. The trade-off is that 0.90 already loses 5
of the 10 paraphrases (the hit rate drops from 60% at 0.85 to 47.5%), and it still does not stop the 4
listing-code false hits. No threshold can stop them, because they score higher than most real paraphrases.

What would actually fix them (not built in this homework): only accept a hit when the LST codes in the new
question are the same as the cached entry's `depends_on` codes.

### Part 3.5 - invalidation trade-off
Each cache entry stores a data-version marker, `LST-xxxxx@<hash of the listing row>`, for every listing the
question mentions. On a hit, the ingress re-reads those rows from MySQL and compares the hashes.

- **Good:** any change to the row is caught, even an UPDATE made outside my code (the demo used a plain
  UPDATE), and only the affected entries are thrown away.
- **Cost:** every hit on a listing question now does a MySQL read. In the Part 2 run that took 61-93 ms per
  hit, which was a large share of the cached latency. The cache still saves the ~35-50 s pipeline run, but no
  longer saves database reads.
- **Limit:** general questions (marker "none") are never invalidated this way, and a question that depends on
  many rows would need many reads per hit.

A TTL would be cheaper, but it would still serve stale answers until the entry expires.

### Labeling notes (Part 3.1)
I did not find a labeling mistake after the sweep, and `cache_cases.yaml` is unchanged since commit `5267b81`.
Two cases are worth mentioning:
- S07 ("How much notice does my landlord need to give before entering my apartment?") scored 0.855 against A07
  (notice before *moving out*). The words overlap, but the answers really are different, so should_miss is
  right.
- P07 is a true paraphrase but only scored 0.68.

### Part 4
**Setup.**
- The Answering Agent gets the listing record the way my HW4 API returns it (with `landlord_id`, no name) and
  has a `get_landlord` tool.
- With the full record in the prompt, llama3.2:3b passed every training question, so there was nothing to learn
  from. That run is kept in RUN_LOG.
- The Evaluator checks answers with rules against `reference_data.json`.
- I fixed one Evaluator bug during training: "not explicitly stated" was marked REVISE, but it is a correct
  "not in the data" answer.

**Lessons.**
- In training, only tr03 failed on its first answer: it said a unit was available but did not give the number.
- With my first rule (a lesson only after the same failure happens twice), no lesson was ever created in two
  logged runs. I switched to one failure, following the PDF's "a lesson created after one failed answer".
- `lesson_001` was then loaded by tr05, tr08 and tr12. tr08 is the same kind of question as tr03, and it passed
  on the first try.
- Validation was 10/10 before and after the lesson, so it was kept (unchanged is allowed).

**Test set.**
- Baseline was 10/12. te04 made up a rent of $2,200, and te12 said "not a valid listing code".
- Evaluator Repair, Lesson Memory and Validated Improvement were all 12/12 with 1.17 attempts on average: two
  questions needed a second attempt, and the lesson did not change any test result.

**Limitations.**
1. The Evaluator's phrase rules can be wrong in both directions:
   - te12's baseline answer ("not a valid listing code") was actually correct but marked REVISE, so the true
     baseline score was 11/12.
   - te10's "a studio, and it has 1 bedroom" passed.
   I did not change the Evaluator after seeing test results.
2. Lessons are matched by question topic, and lesson_001 was tagged with tr03's topics (units *and* landlord),
   so it also loads for landlord-only questions such as va01.
3. 12 test questions are too few to show a difference between the three repair variants.

