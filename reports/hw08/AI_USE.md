# AI Use - HW8

**1. What I used an AI assistant for, and what I did myself.**

I used an AI assistant (Claude Code) for most of this homework, the same way as in HW7. It read the HW8 PDF,
my HW7 code and the two demo ZIPs with me, and pointed out where the demos did not match the assignment (the
topic names, the message shape, auto-commit, port 8000, OpenAI in the multi-agent demo). It wrote most of the
HW8 code from my instructions: the Kafka worker and RPC client, the FastAPI wrapper route, the
docker-compose file and Dockerfile, the Planner/Writer/Reviewer agents and their shared loop, the failure
test scripts, the offline tests and verify_hw08.py. It also helped with the Markdown files and the report,
explained error messages, and debugged the problems below. Claude Code ran the logged runs in RUN_LOG.txt in
my terminal on my Mac, and I approved each command.

What I did myself: I chose the design choices it asked me about (show duplicate delivery on the Part 1
worker, use a fast template mode for the failure tests, run FastAPI in Docker, keep short code snippets in the
report), started Docker and Ollama, read the logs and the raw files to check that they show what the report
says, took the screenshots, and decided what to submit.

**2. One AI-produced output that was wrong or unsuitable.**

The first version of the agent loop that the AI wrote used aiokafka's default consumer settings (10 s
session timeout) and did not handle a failed offset commit. That was fine for the fast-mode tests, but in my
first real pipeline run the Writer's model call took 37 s. Kafka dropped the Writer from its consumer group
during the call, and when the Writer tried to commit after sending its draft, aiokafka raised
`CommitFailedError` and the Writer process crashed.

**3. How the problem was detected.**

The pipeline still reached s9486_final, so the summary looked fine. I only saw the problem in the Writer's log
(`raw/agent_logs/writer.log`) and in RUN_LOG.txt: "OffsetCommit failed ... UnknownMemberIdError", then a
traceback ending in `CommitFailedError`, right after the "sent to s9486_drafts" line. The first test run of
the day also showed many "Heartbeat failed" warnings, and the Mac was using about 12 GB of swap.

**4. What was changed and why it works now.**

The agents now allow 30 s without a heartbeat (`session_timeout_ms=30000`) and 10 minutes between polls, so a
slow model call does not get the Writer kicked out. If a commit still fails because the group rebalanced, the
loop logs it and keeps going instead of crashing. The output was already sent, so Kafka will deliver the
message again and the duplicate check (correlation_id already done) skips it. I also lowered the agents'
model context to 2048 tokens and gave the Kafka broker a smaller heap so the Mac swaps less. After the change
the second pipeline run committed every offset with no errors, and an offline test
(`test_commit_failure_after_rebalance_does_not_crash`) checks the new path.
