# AI Use - HW4

**1. What I used an AI assistant for, and what I did myself.**
I used Claude Code for a real share of the code, not only the write-up. It
adapted the professor's DATA236_demo4 starter to my rental-listing domain
(React pages, API helper, FastAPI routes), replaced the starter's
user_id-only login with email/password login backed by bcrypt hashes and a
server-side `sessions` table, and drafted the N+1 seed/measurement scripts,
the EXPLAIN script, `rag.py`, and the smoke test. It also helped me improve
error handling, check my work against the assignment requirements, structure
the N+1 experiment, and organize and refine the RAG analysis and the reports.
What I did myself: set up MySQL and the `s9486_rel` database, created my
login user, ran every script in my own terminal (seeding, EXPLAIN, the 180
measured requests, the RAG runs with llama3.2:3b), tested the React app and
every endpoint in Postman, captured all screenshots, chose and checked the
corpus documents, and reviewed the numbers and model answers before putting
them in METRICS.md and the report.

**2. One AI-produced output that was wrong/unsuitable.**
The first version of `rag.py` called Ollama with `"think": false` and
`num_predict: 300`, assuming that flag would turn off qwen3:4b's reasoning
mode. It did not. In the first full RAG run every answer began with text like
"Okay, the user is asking about California Civil Code 1950.5..." and was cut
off at the 300-token limit before the actual answer. That made all three
configurations useless for evaluation. A second, smaller issue: the
AI-written keyword check marked Q3 retrieval as wrong even though the
retrieved chunk contained the "30 days' written notice" answer.

**3. How I detected the problem.**
I read the answers in `RUN_LOG.txt` instead of just checking that the run
finished. Then I tested the model directly with a trivial prompt ("What is
2+2? Answer in one sentence.") through the Ollama API. With `think: false`,
the `/no_think` switch, an empty `<think></think>` prefill, and a raw qwen3
chat template, the reply was always several sentences of reasoning. Only
`think: true` separated the reasoning from the answer, and that took about
55 seconds even for 2+2, which is too slow for 27 calls on an 8 GB M1. For
the Q3 check, I compared the flagged chunk text in `retrieved_chunks.txt`
with the expected answer by hand.

**4. What I changed, and why it works now.**
I removed qwen3:4b and switched Part 4 to `llama3.2:3b`, a smaller
non-thinking Llama model (this also matches the "smaller Llama model"
requirement). I also removed the `think` flag from `rag.py`. A single test
query then returned a short, cited answer in about 13 seconds, and the full
run finished in a few minutes with clean answers. For the keyword check, I
kept the automatic results unchanged in `raw/` and recorded the manual
corrections separately in METRICS.md, so the raw output still matches what
the script actually produced.
