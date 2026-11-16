# AI Use - HW10

**How I used AI on this homework.**

I used an AI assistant (Claude Code) to help with documentation and Markdown, to write and organize the report,
to debug errors, and to write most of the HW10 code. I connected and restarted the services (Docker with Redis
and Kafka, MySQL, Ollama), reviewed the outputs, and made the final decisions.

What the assistant did:
- It read the HW10 PDF and the starter files (ge-eval2.py uses OpenAI; the DATA236 demo is an Iris Streamlit
  app) and planned how to apply them to my HW8/HW9 system with a local judge instead of OpenAI.
- It wrote most of the new code from my instructions:
  - the deepeval GEval judge wrapper for Ollama
  - the evaluator that joins plan, draft and final by correlation_id
  - the span tracing, plus the small tracing hooks in my HW8 agents
  - the traced cache ingress
  - the trace demo, the 50-request experiment and the judge-validation script
  - the Streamlit dashboard, the tests, the metrics builder and the report renderer
- It picked the 20 Writer drafts for eval_cases.json from my HW8/HW9 runs, with a fixed seed, and wrote the
  labeling helper. It did not write or suggest any labels.
- It ran the logged commands in RUN_LOG.txt in my terminal on my Mac, and I approved each one. It also set up
  `caffeinate` so the Mac would not sleep during the long overnight run. I took the screenshots myself.
- It helped write METRICS.md and the report text. I checked the numbers against the raw files.

What I did and decided myself:
- I hand-labeled all 20 drafts (1-5 helpfulness) in human_labels.csv. I committed eval_cases.json and
  human_labels.csv before the judge scored anything, and I did not change the labels afterwards.
- I agreed to stop my Lab 1 containers, which were using port 9092, while HW10 ran.
- I chose to resume the 50-request run instead of starting over after Docker stopped responding.
- I decided what to submit.

_(Space for anything I changed by hand:)_

**One AI-produced output that was wrong or unsuitable, and how it was fixed.**

The assistant's first judge setup used a 4096-token context for the judge, while my HW8 agents use 2048. Ollama
treats a different context size as a separate model instance. During the 50-request run it kept unloading and
reloading llama3.2:3b every time the pipeline switched between an agent call and a judge call. The first request
took 220 s, the Mac was using about 8.7 GB of swap, and `ollama ps` showed the model being reloaded.

The fix:
- The judge now uses the same context size as the agents (2048 tokens is enough for the rubric, the question and
  a draft).
- The partial run and the first trace demo were moved to `reports/hw10/raw/archive/` (kept, not deleted) and
  run again with the final settings.
- After the fix, requests took about 45-150 s.
- Part 3 had not started yet, so all judge-validation scores use the final settings.
