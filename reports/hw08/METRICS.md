# HW8 Metrics - SID4 9486 (Kavan Siddesh)

Configuration: PORT_BASE 8486, PREFIX s9486, SEED 9486, VERIFY_SEED 269486, DOMAIN_ID 6 (rental housing
listings), MacBook Air with Apple M1 chip (8 GB), local model llama3.2:3b via Ollama, Kafka apache/kafka:3.9.2
(KRaft, one broker in Docker).

The tables between the markers are written by `Homework8/scripts/build_metrics.py` from the files in `raw/`;
I did not edit them by hand.

## Part 1 - Listing request/response over Kafka (raw/part1_*.json)

<!-- part1-table:start -->
| Run | correlation_id | listing_id | CREATE request (topic/partition/offset) | Same id | GET matches |
|---|---|---|---|---|---|
| homework_demo.py --via kafka | `9cf1f8b7-7818-49b3-98b4-c7188cf2fe0b` | `7c32b4af-b23e-4d04-8c39-1702ab931d6c` | s9486_entity_requests/0/53 | True | True |
| homework_demo.py --via api | `34bce634-4e17-43cf-ad46-8dcae4916006` | `6759ef73-b695-47de-921f-30fa51d32cba` | s9486_entity_requests/0/55 | True | True |

| Error case (through FastAPI 8486) | HTTP | success | error | correlation_id echoed |
|---|---|---|---|---|
| valid CREATE_LISTING | 201 | True | - | True |
| missing title | 400 | False | Invalid listing data: title: Field required | True |
| empty address | 400 | False | Invalid listing data: address: String should have at least 1 character | True |
| bad listing_code | 400 | False | Invalid listing data: listing_code: String should match pattern '^LST-\d{5}$' | True |
| negative available_units | 400 | False | Invalid listing data: available_units: Input should be greater than or equal to 0 | True |
| data is not an object | 400 | False | data must be a JSON object | True |
| unknown listing_id | 404 | False | Listing not found | True |
| unknown operation | 400 | False | Unknown operation | True |

8/8 cases gave the expected result and echoed the same correlation_id.
<!-- part1-table:end -->

## Part 2 - Three-agent pipeline (raw/pipeline_journey.json)

<!-- part2-table:start -->
| Stage | Reads | Writes | Time (s) |
|---|---|---|---|
| planner (read s9486_inbox/0/1) | s9486_inbox | s9486_tasks | 27.5 |
| writer (read s9486_tasks/1/0) | s9486_tasks | s9486_drafts | 32.7 |
| reviewer (read s9486_drafts/0/1) | s9486_drafts | s9486_final | 13.4 |
| total (send_question -> final) | | | 73.6 |

correlation_id `d17566c4-8863-45fa-a8b6-be4f3a9fc8df` kept through all stages: True. Final status `approved`, answer 161 words, model llama3.2:3b for all three agents. Reviewer notes: "The draft covers the plan and provides a clear step-by-step guide for students moving to San Jose. It emphasizes the importance of researching the location, verifying lease terms, inspecting the apartment, and reviewing the lease agreement carefully."
<!-- part2-table:end -->

## Part 3 - Failure table (raw/duplicate_replay.json, consumer_death.json, poison_message.json, ordering_summary.json)

<!-- part3-table:start -->
| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery (same message sent twice) | worker: 2 different listing_ids, 2 listings for one request; writer: 2 drafts | worker: same listing_id both times, 1 listing (saved response re-sent); writer: 1 draft, duplicate skipped |
| Consumer killed mid-work (SIGKILL 2 s into a 6 s task) | auto-commit: offset already committed at the kill (partition=0 committed=15 log_end=15 lag=0; partition=1 committed=54 log_end=54 lag=0); restarted writer never saw task B, 0 drafts -> lost | commit after processing: partition=1 committed=55 log_end=56 lag=1 at the kill; restarted writer got task B again and finished it (1 draft, partition=1 committed=56 log_end=56 lag=0) |
| Poison message (not JSON / no plan) | writer crashed on the same offset twice (exit codes [1, 1]), 0/2 good tasks after it ran, partition=1 committed=57 log_end=60 lag=3 | 3 tries each, 2 messages moved to s9486_dead_letter, 2/2 good tasks ran, partition=1 committed=65 log_end=65 lag=0 |
| Two partitions / two consumers (20 VERIFY_SEED messages) | no key: 4/4 listings split across partitions, 4/4 finished out of order | key = listing_code: 0/4 split, 0/4 out of order |
<!-- part3-table:end -->

## Part 3D - Ordering per listing (raw/ordering_unkeyed.csv, raw/ordering_keyed.csv)

<!-- ordering-table:start -->
| Run | Listing | Partitions | Writers | Processed seq order | In order |
|---|---|---|---|---|---|
| unkeyed | LST-54549 | [0, 1] | writer-1, writer-2 | [1, 2, 4, 3, 5] | False |
| unkeyed | LST-62000 | [0, 1] | writer-1, writer-2 | [1, 4, 2, 3, 5] | False |
| unkeyed | LST-90996 | [0, 1] | writer-1, writer-2 | [1, 3, 2, 4, 5] | False |
| unkeyed | LST-98538 | [0, 1] | writer-1, writer-2 | [1, 3, 2, 4, 5] | False |
| keyed | LST-54549 | [1] | writer-1 | [1, 2, 3, 4, 5] | True |
| keyed | LST-62000 | [1] | writer-1 | [1, 2, 3, 4, 5] | True |
| keyed | LST-90996 | [1] | writer-1 | [1, 2, 3, 4, 5] | True |
| keyed | LST-98538 | [1] | writer-1 | [1, 2, 3, 4, 5] | True |
<!-- ordering-table:end -->

## Notes

- **Which mode each run used.** Part 2 (`make pipeline-demo`) used llama3.2:3b for all three agents. The Part 3
  tests run the Writer in `--mode fast` (fixed template answer, no model call) so 20+ messages finish in seconds
  and the timing is the same each run. Kafka, the consumer groups, commits, retries and the dead-letter topic
  are the real ones in both modes.
- **Part 1.** Both demo runs (straight to Kafka and through FastAPI on 8486) kept the same correlation_id in the
  request, the worker, the response and the final result, and GET returned exactly the fields that were created.
  The worker's duplicate check uses correlation_id + operation, because `homework_demo.py` uses one
  correlation_id for both its CREATE and its GET like the assignment steps say.
- **Part 2 timing.** One question took a bit over a minute from inbox to final (table above). Almost all of that is the model on my 8 GB
  Mac (it was using a lot of swap); each Kafka hop took between 2 ms and about 250 ms in the journey log.
- **First pipeline run crashed the Writer.** In my first logged run the Writer's model call took 37 s and Kafka
  dropped it from the consumer group (10 s session timeout). The draft was already sent, but the offset commit
  then failed with `CommitFailedError` and the Writer crashed. That run is still in RUN_LOG.txt. I raised the
  session timeout to 30 s and made a failed commit log a message instead of crashing (the message gets
  redelivered and the duplicate check skips it). The second run, the one in the table, had no errors.
- **Duplicate delivery.** Without the fix the replay made a second listing in the worker's dict and a second
  draft from the Writer. With the fix the worker sends back the saved response (same listing_id) and the Writer
  skips the message. The duplicate memory is in the process only, so it is lost if the process restarts.
- **Consumer death.** With auto-commit, aiokafka committed task B's offset within its 1 s auto-commit interval, while the
  Writer was still "working", so after the kill the group's lag was already 0 and task B was never done. With the
  commit after processing, the lag stayed at 1 and the restarted Writer got task B again and finished it. The
  restart took a few seconds longer because Kafka waits for the killed member's session to time out.
- **Poison message.** Before the fix one bad message stopped the Writer for good: it crashed, and every restart
  read the same offset and crashed again, so the lag stayed at 3. After the fix each bad message was tried 3
  times (waits of 0.5 s and 1 s), written to s9486_dead_letter with the error, the source offset and the raw
  value, and then committed, so the next tasks ran.
- **Ordering.** Without a key aiokafka picks a random partition for every message, so this run's numbers would
  change if I ran it again. With the listing_code
  as the key, all updates of one listing went to one partition and finished in order. One thing I did not
  expect: all 4 listing codes hashed to partition 1, so the Writer that owned partition 1 did all 20 messages
  and the other one sat idle. A key
  keeps order but it can make the load uneven when there are only a few keys.
- **JMeter.** The HW8 PDF does not ask for a load test (the JMeter instructions are a separate DATA 236 demo
  against `/users-direct` on port 8000), so I did not run JMeter and there are no load numbers here.
