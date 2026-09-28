# HW4 Metrics

Configuration: SID4 9486, PORT_BASE 8486, SEED 9486, VERIFY_SEED 269486,
database `s9486_rel`, hardware Apple M1 / 8 GB, local model `llama3.2:3b`.

## Part 3 - N+1 measurement

Setup: 5,000 `listings` and 200 `listing_inquiries` seeded with SEED 9486
(`scripts/seed_n1.py`). Every request asks for page 1. SQL statements are
counted in the backend with a SQLAlchemy `before_cursor_execute` listener
(session lookup excluded). Latency is the client-side round trip measured by
`scripts/measure_n1.py`. Raw data for all 180 requests is in `raw/n1_requests.csv`
and `raw/n1_requests.json`.

- naive: `SELECT` the page, then one `SELECT ... WHERE listing_id = ?` per listing -> expected 1 + N statements
- fixed: `selectinload(Listing.inquiries)` -> page query + one `WHERE listing_id IN (...)` -> expected 2 statements

`measure_n1.py` replaces the block below with the measured tables.

<!-- N1_RESULTS_START -->
_Measured 2026-09-28T12:15:53; client-side latency over localhost; page=1; 30 recorded requests per row after 3 warm-ups._

| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 11 | 7.9 | 8.83 | 8.95 |
| 10 | fixed | 2 | 4.02 | 4.46 | 4.6 |
| 50 | naive | 51 | 25.73 | 27.04 | 28.16 |
| 50 | fixed | 2 | 5.43 | 5.94 | 6.08 |
| 200 | naive | 201 | 92.9 | 96.75 | 117.97 |
| 200 | fixed | 2 | 9.75 | 10.41 | 10.56 |

| Page size | Speedup at p50 (naive / fixed) | Speedup at p95 | SQL stmts saved/req |
|---|---|---|---|
| 10 | 1.97x | 1.98x | 9 |
| 50 | 4.74x | 4.55x | 49 |
| 200 | 9.53x | 9.29x | 199 |
<!-- N1_RESULTS_END -->

### Why the speedup changes with page size

The naive version's statement count grows with the page (11, 51, 201) while the
fixed version always runs 2 statements. Each extra naive statement is another
round trip to MySQL plus parse/execute and ORM overhead, so naive latency grows
almost linearly: from page size 10 to 200 its p50 went from 7.90 ms to 92.90 ms,
roughly 0.45 ms per extra listing. The fixed version only pays for more rows in
the same two queries and for serializing them, about 0.03 ms per extra listing
(4.02 ms to 9.75 ms).

At page size 10 both versions share a fixed per-request cost (HTTP handling,
session lookup, JSON encoding) of a few milliseconds, and only 9 extra queries
separate them, so the speedup is just 1.97x. As the page grows, the extra
queries dominate the naive time while the fixed cost stays nearly flat, so the
speedup rises to 4.74x at 50 and 9.53x at 200. It keeps widening with page size
because the naive cost is O(N) round trips and the fixed cost is O(1) round trips.
The naive p99 at 200 (117.97 ms vs p95 96.75 ms) also shows that more round
trips give more chances for an occasional slow one.

## Part 3 - Index and EXPLAIN

Index (declared in `backend/app/models.py`, created by `scripts/explain_index.py`):

```sql
CREATE INDEX ix_listing_inquiries_listing_id ON listing_inquiries (listing_id);
```

EXPLAIN before/after output: `raw/explain_before_after.txt` (run 2026-09-28T12:15:36).

| Query | Before: type / key / rows | After: type / key / rows |
|---|---|---|
| naive per-listing lookup (`listing_id = 7`) | index / PRIMARY / 200 (filtered 10%, Using where) | ref / ix_listing_inquiries_listing_id / 1 (filtered 100%) |
| fixed selectin lookup (`listing_id IN (1..10)`) | index / PRIMARY / 200 (filtered 50%, Using where) | range / ix_listing_inquiries_listing_id / 11 (Using index condition; Using filesort) |

What changed: without an index on `listing_id`, MySQL had no usable key
(`possible_keys` = NULL) and walked the whole clustered primary key (`type=index`,
200 rows) and filtered every row with `Using where`, only choosing PRIMARY to get
the `ORDER BY id` order for free. After adding the index, the per-listing lookup
became `type=ref` with `ref=const`, reading about 1 row, and the IN query became
a `range` scan over 11 index entries. The optimizer now adds a small filesort to
order those 11 rows by id, which is much cheaper than scanning all 200 rows. With
only 200 related rows the latency effect is small, but the rows examined per
query drop from the whole table to just the matches, and that gap grows with the
table size.

## Part 4 - RAG evaluation

Run 2026-09-28T12:44:14, `llama3.2:3b`, all-MiniLM-L6-v2 + FAISS, 5 documents ->
165 chunks (500/50 characters), top_k = 3. Full per-question table:
`raw/evaluation_table.md` / `raw/evaluation.csv`.

Automatic keyword-based summary (from `rag.py evaluate`):

| Config | Accuracy (correct answers) | Faithfulness (grounded) | Format compliance | Robustness (refusal behaviour) |
|---|---|---|---|---|
| no_rag | 1/6 | n/a | n/a | 4/6 |
| basic_rag | 2/6 | 2/6 | n/a | 4/6 |
| context_rag | 4/6 | 5/6 | 6/6 | 5/6 |

Manual review of the automatic checks (automatic files left unchanged):

| Q | Config | Automatic | Manual | Reason |
|---|---|---|---|---|
| Q3 | basic_rag, context_rag | correct retrieval = no | yes | chunk `ca_tenant_notice_requirements#002` contains "at least 30 days' written notice"; the "month to month" keyword sits in the preceding chunk, so the keyword check was too strict |
| Q4 | basic_rag, context_rag | grounded = no | yes (grounded), no (correct) | "two months' rent" is stated in the retrieved chunk, but it is the small-landlord exception in 1950.5(c)(5); neither config flagged the ambiguity or gave the general one-month rule |
| Q2 | context_rag | refused when needed = no | refusal was faithful but incomplete | at k = 3 the relocation-amount chunk (#031) was not retrieved, so refusing was consistent with the evidence given; at k = 5 it answered both parts correctly |

k-sweep (context_rag, `raw/k_sweep.md`):

| Q | k = 1 | k = 3 | k = 5 | Best k |
|---|---|---|---|---|
| Q1 | correct | correct | correct | 1 (same answer, shortest context) |
| Q2 | refused (evidence missing) | refused (evidence missing) | correct, cites [4] and [3] | 5 |
| Q3 | correct | correct, hedged | refused (extra just-cause chunks confused it) | 1 |
