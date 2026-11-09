# AI Use - HW9

**How I used AI on this homework.**

I used an AI assistant (Claude Code) to help with documentation and Markdown where it was needed, help write and
organize the report, debug errors, and write and improve the code. I connected the required services (MySQL,
Docker with Redis and Kafka, Ollama), reviewed the outputs, and made the final decisions about the project.

To be specific about what the assistant did, since it was more than small fixes:

- It read the HW9 PDF, the two starter files (demo.py, caching_agents.py) and my HW8 code with me, and
  pointed out what the starters did not cover: the in-memory caches, the OpenAI calls, the unprefixed
  `user:...` keys and the `flushdb()` call in demo.py.
- It wrote most of the new HW9 code from my instructions:
  - the listing database/cache class with `increment_listing_views`
  - the Redis vector cache and the ingress in front of my HW8 Kafka pipeline
  - the data-version check
  - the sweep and stale-answer scripts
  - the Answering/Evaluator agents, lessons and validation gate
  - the dataset builder, the tests and the Makefile targets
- It wrote the 40 cases in cache_cases.yaml and checked in MySQL that the "similar but different" pairs really
  have different answers. I reviewed the file and committed it myself before the sweep was run.
- It picked the setup details and explained them to me:
  - Ollama's all-minilm (MiniLM) for embeddings, so torch did not have to be installed on my 8 GB Mac
  - Redis 8 in its own Docker compose file
  - the cost values ($0.01 per miss, $2.50 per false hit)
  - which threshold to ship (0.90)
  I read the reasons in METRICS.md and agree with them.
- It ran the logged commands in RUN_LOG.txt in my terminal on my Mac, and I approved each one. I took the
  screenshots myself.
- It helped write METRICS.md and the report text. I checked the numbers against the raw files.

What I decided myself:
- to commit cache_cases.yaml before the sweep, as the PDF asks
- to allow the small fix to my HW8 pipeline (below)
- for Part 4, to give the Answering Agent the realistic listing record (landlord_id plus a get_landlord tool)
  instead of the full record, after the full-record version passed every training question
- what to submit

_(Space for anything I changed by hand:)_

**One AI-produced output that was wrong or unsuitable, and how it was fixed.**

The first two Part 2 runs failed (both are kept in RUN_LOG.txt):

- In run 1, an exact-duplicate cache hit took 34.5 s. Then on question 7 ("How can I get my full security
  deposit back when I move out?") the HW8 Planner's model call timed out twice (180 s each), and the run stopped
  with a TimeoutError.
- In run 2, the Planner picked up that same leftover question again and timed out again.

The assistant's first explanation was wrong. It blamed memory: `ollama ps` showed only one model loaded and the
Mac had about 8 GB of swap in use. So it kept the embedding model loaded (`keep_alive`), added an untimed
warm-up call, and stopped the two HW8 containers HW9 does not use. That did fix the slow 34.5 s embedding call,
but the Planner still hung on the second run while both models were loaded, so memory was not the cause of the
timeouts.

The real cause showed up when we sent the Planner's exact request straight to Ollama with an output limit:

- With `format=json` and seed 9486, llama3.2:3b answered the deposit question with endless escaped Cyrillic
  text and never stopped. My HW8 code had no output limit, so each try ran until the 180 s timeout.
- The same thing happened for one of my Part 3 seed questions, so the sweep would have hung too.
- With seed 9487 the same question gave normal JSON in 14 s.

I approved a small change to the HW8 pipeline:
- The agents' replies are capped at 512 tokens (`AGENT_NUM_PREDICT`).
- If a JSON reply is unusable, the call is retried once with seed 9487, and the retry is logged.
- The new `num_predict` option in the shared OllamaModel defaults to off, so HW5-HW7 behave as before.

The HW5-HW8 test suites still pass. In the third Part 2 run the Planner log shows "unusable JSON with seed 9486
... trying once with seed 9487" and the question finished.
