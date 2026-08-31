# DATA 260 Coursework

Student repository for DATA 260 homework assignments.

## Homework 1 Configuration

| Value | Configuration |
|---|---|
| SID4 | 9486 |
| PORT_BASE | 8486 |
| PREFIX | s9486 |
| SEED | 9486 |
| VERIFY_SEED | 269486 |
| DOMAIN_ID | 6 |
| Assigned Domain | Rental housing listings |
| Hardware | Apple Mac with M1 chip and 8 GB unified memory |
| Local Model | qwen3:4b |

The recommended `qwen3:8b` model was replaced with `qwen3:4b` because the available Mac hardware has only 8 GB of unified memory, so the smaller model is more practical for repeated local runs.

## Repository Layout

- `app/` - Part 1 rental listing HTML, CSS, and JavaScript
- `agents_demo.py` - Part 2 multi-agent rental-domain demo
- `hw1_client.py` - Part 4 strict code-review client
- `src/model_client.py` - Shared Ollama adapter used by every model call
- `scripts/run_nondeterminism.py` - Part 3 experiment runner
- `scripts/verify_hw01.py` - Homework self-check
- `reports/hw01/` - Written report, logs, raw results, and screenshots

## Reproducible Commands

Run all commands from `data260-9486/` unless noted otherwise.

### Part 1: Local HTML app

Start the static site:

```bash
python3 -m http.server 8486 --directory app
```

Open `http://localhost:8486/` in a browser.

### Part 1: Docker build, run, and stop

Build the image:

```bash
docker build -t data260-hw1:s9486 .
```

Run the container:

```bash
docker run --name data260-hw1-s9486 -p 8486:80 data260-hw1:s9486
```

Stop and remove the container:

```bash
docker stop data260-hw1-s9486
docker rm data260-hw1-s9486
```

### Ollama model setup

Start Ollama if it is not already running:

```bash
ollama serve
```

Pull the local model used for this homework:

```bash
ollama pull qwen3:4b
```

Optional check:

```bash
ollama list
```

### Part 2: Agent demo

```bash
python3 agents_demo.py \
  --title "Two-Bedroom Apartment Near SJSU" \
  --content "A furnished two-bedroom apartment with in-unit laundry, secure parking, and convenient access to public transit is available near the San Jose State University campus." \
  --email "kavan.siddeshkumar@sjsu.edu" \
  --model qwen3:4b \
  --strict \
  | tee reports/hw01/raw/agent_demo_part2.txt
```

### Part 3: Non-determinism experiment

```bash
python3 scripts/run_nondeterminism.py --runs-per-temperature 20 --model qwen3:4b
```

This reuses the fixed input in `reports/hw01/cases/nondeterminism_input.json` and writes the raw results into `reports/hw01/raw/`.

### Part 4: Code-review client

```bash
python3 hw1_client.py --model qwen3:4b
```

Useful commands inside the client:

- `/stats` - print turn count, cumulative token totals, and serialized conversation-history length
- `/exit` or `/quit` - close the session

### Homework verification

```bash
python3 scripts/verify_hw01.py
```

Or, if available:

```bash
make verify-hw01
```

## Part 4 Conceptual Answers

- Prior history is resent because the Ollama chat API is stateless between requests.
- A system prompt sets global behavior and rules, while a user message supplies the current request.
- Input tokens grow because earlier conversation messages are sent again on each turn.
- Growth is eventually limited by the model context window and practical latency and memory constraints.

## Submission Notes

- The final report is `reports/hw01/report.pdf`.
- The submission tag is `hw1`.
- The content-complete source commit hash is recorded in the report for reproducibility, and the final tagged submission commit is explained in the handoff because a commit cannot contain its own final hash.
