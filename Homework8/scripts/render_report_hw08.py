#!/usr/bin/env python3
"""Render the HW8 report (reports/hw08/report.pdf and Kumar_HW8.pdf).

Same layout as the HW5-HW7 reports (reuses scripts/render_report_hw05.py): configuration table first, one
section per part, labeled screenshots, tables from reports/hw08/raw/ and METRICS.md. HW8 asks for short code
snippets, so each snippet is cut straight out of the source file (between two marker lines), and each log
excerpt comes from the last logged run of that make target in RUN_LOG.txt. A screenshot that does not exist
yet is shown as a clearly marked MISSING box. Main headings 14 pt bold, subheadings 12 pt bold, body 11 pt.

Usage (repo root):
    make report-hw08                                   # commit hash = HEAD
    COMMIT_HASH=<sha> python Homework8/scripts/render_report_hw08.py
"""

from __future__ import annotations

import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from hw8_common import RAW, REPORT_DIR, ROOT

import config

# Loaded after the hw*_common import, which puts scripts/ on sys.path (a plain import would be sorted above it).
r5 = importlib.import_module("render_report_hw05")

r5.SHOTS = REPORT_DIR / "screenshots"
OUT_PDF = REPORT_DIR / "report.pdf"
NAMED_PDF = REPORT_DIR / "Kumar_HW8.pdf"
CSS = r5.CSS.replace("Homework 5", "Homework 8") + (
    ".missing { border: 2px dashed #ef4444; color: #b91c1c; padding: 10pt; margin: 6pt 0 12pt 0; }\n"
    ".cmd { white-space: pre-wrap; font-size: 8pt; line-height: 1.3; break-inside: avoid; }\n"
    ".cmd.long { break-inside: auto; }\n"
    ".src { font-size: 8.5pt; color: #6b7280; margin: 6pt 0 0 0; }\n"
)
HARDWARE = "MacBook Air with Apple M1 chip (8 GB unified memory)"
r5.CROPS = {}
MISSING: list[str] = []


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def fig(d, name: str, caption: str, width: str = "100%") -> None:
    if (r5.SHOTS / f"{name}.png").exists():
        d.fig(name, caption, width=width)
    else:
        MISSING.append(name)
        d.add(f"<div class='missing'><b>MISSING SCREENSHOT ({html.escape(name)}.png):</b> {html.escape(caption)}</div>")


def block(d, text: str, long: bool = False) -> None:
    d.add(f"<div class='cmd{' long' if long else ''}'>{html.escape(text.rstrip())}</div>")


def code(d, path: str, start: str, end: str | None = None, note: str = "") -> None:
    """A short snippet from a real file: from the first line containing `start` to the line containing `end`."""
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    i = next(k for k, line in enumerate(lines) if start in line)
    j = next((k for k in range(i, len(lines)) if end and end in lines[k]), i)
    d.add(f"<p class='src'>{html.escape(path)}, lines {i + 1}-{j + 1}{(' - ' + html.escape(note)) if note else ''}</p>")
    block(d, "\n".join(lines[i : j + 1]))


def log_section(target: str) -> list[str]:
    """The last logged RUN_LOG.txt section for a make target (header line + its output)."""
    lines = (REPORT_DIR / "RUN_LOG.txt").read_text(encoding="utf-8").splitlines()
    starts = [
        i for i, ln in enumerate(lines) if ln.startswith("=====") and ln.endswith(f" {target} (Kavan Siddesh) =====")
    ]
    if not starts:
        return []
    i = starts[-1]
    j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("===== ")), len(lines))
    return lines[i:j]


DATE = re.compile(r"\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2}\.\d{3})")


def shorten(line: str, width: int = 150) -> str:
    """Drop the date and long JSON values so a log line fits on one or two lines of the PDF."""
    line = DATE.sub(r"\1", line.strip())
    line = re.sub(r" value=\{.*", " value={...}", line)
    line = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", lambda m: m.group(0)[:8] + "...", line
    )
    return line if len(line) <= width else line[: width - 4] + " ..."


def excerpt(target: str, keep, first: int | None = None, width: int = 150) -> str:
    lines = log_section(target)
    out = [lines[0]] if lines else ["(no logged run yet)"]
    out += [shorten(ln, width) for ln in lines[1:] if keep(ln)]
    return "\n".join(out[: first + 1] if first else out)


def pipeline_seconds() -> float:
    """send_question -> reviewer done, from the trace in raw/pipeline_journey.json."""
    from datetime import datetime

    trace = load("pipeline_journey.json")["final"]["trace"]
    first = datetime.fromisoformat(trace[0]["sent_at"])
    return (datetime.fromisoformat(trace[-1]["done_at"]) - first).total_seconds()


def metrics_section(marker: str) -> str:
    text = (REPORT_DIR / "METRICS.md").read_text(encoding="utf-8")
    body = text[
        text.index(f"<!-- {marker}:start -->") + len(f"<!-- {marker}:start -->") : text.index(f"<!-- {marker}:end -->")
    ]
    out, table = [], []

    def flush():
        if table:
            out.append(
                ("table", [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table if "---" not in ln])
            )
            table.clear()

    for line in body.strip().splitlines():
        if line.strip().startswith("|"):
            table.append(line)
        else:
            flush()
            if line.strip():
                out.append(("p", line.strip()))
    flush()
    doc = r5.Doc(Path(tempfile.gettempdir()))
    for kind, val in out:
        doc.table(val) if kind == "table" else doc.p(val)
    return "".join(doc.parts)


# ---------------------------------------------------------------- sections


def section0(d, commit: str):
    d.add("<h1>DATA 260 Homework 8</h1>")
    d.add("<div class='sub'>Kavan Siddesh</div>")
    d.h2("Section 0. Personal Configuration and Domain", new_page=False)
    d.table(
        [
            ["GitHub repository", config.REPO_URL],
            ["SID4", "9486"],
            ["PORT_BASE", str(config.PORT_BASE)],
            ["PREFIX", config.PREFIX],
            ["SEED", str(config.SEED)],
            ["VERIFY_SEED", str(config.VERIFY_SEED)],
            ["DOMAIN_ID", f"{config.DOMAIN_ID} - {config.DOMAIN_NAME} (primary entity: Listing)"],
            ["Hardware", HARDWARE],
            ["Local model", f"{config.OLLAMA_MODEL} (Ollama), used by the Planner, Writer and Reviewer"],
            ["Kafka", "apache/kafka:3.9.2 in Docker (KRaft, one broker), Python client aiokafka 0.15.0"],
            ["Tagged commit hash", f"{commit} (tag hw8)"],
        ],
        header=False,
        cls="kv",
    )
    d.p(
        "Both collaborators (Sbnikitha, supriyaselvanganesan) have access to the repository. HW8 extends the same "
        "root-level application as HW5-HW7. The new code is in `kafka_service/`, `kafka_agents/`, "
        "`backend/app/routers/kafka_listings.py`, `docker-compose.yml` and `Dockerfile`; the HW8 demo, scripts and "
        "tests are in `Homework8/`, and the results (`RUN_LOG.txt`, `raw/`, `METRICS.md`, `AI_USE.md`, "
        "`verification.json`) are in `reports/hw08/`."
    )


def part1(d):
    d.h2("Part 1. Backend Service Request/Response over Kafka")
    d.p(
        "My primary entity is **Listing** (rental housing listings), so the two operations are `CREATE_LISTING` and "
        "`GET_LISTING` and the id is `listing_id`. The client never calls the worker. It writes a request to "
        "`s9486_entity_requests` and waits for the answer with the same correlation_id on `s9486_entity_responses`. "
        "The worker keeps listings in a plain Python dict and makes each `listing_id` with `uuid4()`. It checks the "
        "fields with the same `ListingCreate` model my REST API has used since HW4, so a missing, empty or "
        "badly formatted field gets a clean error."
    )
    d.h3("I-II. Topics and message schemas")
    d.table(
        [
            ["Topic", "Partitions", "Written by", "Read by"],
            ["s9486_entity_requests", "1", "client (homework_demo.py) or the FastAPI wrapper", "worker"],
            ["s9486_entity_responses", "1", "worker (the topic named in reply_to)", "client or FastAPI wrapper"],
        ],
        widths=["30%", "12%", "32%", "26%"],
    )
    demo = load("part1_demo_kafka.json")
    req = demo["create"]["request"]
    block(
        d,
        "Request (CREATE_LISTING):\n"
        + json.dumps(req, indent=2)
        + "\n\nResponses:\n"
        + json.dumps(demo["create"]["response"])
        + "\n"
        + json.dumps({**demo["get"]["response"], "listing": {"listing_id": "...", "title": "...", "...": "..."}})
        + '\n{"correlation_id": "...", "success": false, "error": "Listing not found"}',
    )
    code(
        d,
        "kafka_service/worker.py",
        "    def handle(self, operation, data)",
        'return {"success": False, "error": "Unknown operation"}',
    )
    code(d, "kafka_service/messages.py", "def build_request(", "    }", "the correlation_id is created once")
    code(
        d,
        "kafka_service/rpc.py",
        "    async def _listen(self)",
        "fut.set_result(",
        "the client matches each response to its waiting request by correlation_id",
    )
    d.h3("III. Docker: Kafka, worker and FastAPI")
    d.p(
        "`make kafka-up` starts everything from my root `docker-compose.yml`: the Kafka broker, a one-time "
        "`kafka-init` container that creates the topics (auto-create is turned off), the worker "
        "(`python -m kafka_service.worker`) and my existing FastAPI app on 127.0.0.1:8486. The FastAPI app gets one "
        "new route file, `/api/kafka/listings`, which uses the same Kafka client and passes the caller's "
        "correlation_id through unchanged."
    )
    fig(d, "p1_docker_ps", "`make kafka-ps`: docker ps with s9486_kafka, s9486_worker and s9486_api running.")
    fig(
        d,
        "p1_service_logs",
        '`make kafka-logs`: the worker prints "Consumer is ready and listening..." and FastAPI prints '
        '"FastAPI started at http://127.0.0.1:8486".',
    )
    d.h3("IV-V. homework_demo.py: CREATE_LISTING then GET_LISTING")
    fig(
        d,
        "p1_demo_create",
        "`make homework-demo`, steps 1-7: one correlation_id, the CREATE request sent to s9486_entity_requests, the "
        "worker receiving, processing and replying, and the client getting the listing_id.",
    )
    fig(
        d,
        "p1_demo_get",
        "Steps 8-14: GET_LISTING with that listing_id, the full send/receive/process/reply/response sequence, the "
        "retrieved listing and the correlation_id check.",
    )
    fig(
        d,
        "p1_demo_api",
        "`make homework-demo-api`: the same flow through the FastAPI wrapper, with the API container's lines "
        "(HTTP request -> sent to Kafka -> received response -> HTTP 201/200 to the caller).",
    )
    d.p("Full sequence from RUN_LOG.txt (`make homework-demo`, ids shortened):")
    block(
        d,
        excerpt(
            "homework-demo",
            lambda ln: ("client |" in ln or "worker |" in ln) or "correlation_id unchanged" in ln,
        ),
        long=True,
    )
    api = load("part1_demo_api.json")
    a_lines = [ln for ln in log_section("homework-demo-api") if "api    |" in ln]
    d.p("correlation_id flow for the FastAPI run (from `raw/part1_demo_api.json` and the API container log):")
    d.table(
        [
            ["Hop", "correlation_id"],
            ["homework_demo.py creates it and sends it in the HTTP body", api["create"]["request"]["correlation_id"]],
            [
                "FastAPI puts it in the Kafka request (API log)",
                "same" if any(api["correlation_id"] in x for x in a_lines) else "-",
            ],
            ["worker response on s9486_entity_responses", api["create"]["response"]["correlation_id"]],
            [
                "HTTP response returned to the caller (CREATE / GET)",
                f"{api['create']['response']['correlation_id']} / {api['get']['response']['correlation_id']}",
            ],
        ],
        widths=["55%", "45%"],
    )
    d.h3("Results: demo runs and error cases")
    d.add(metrics_section("part1-table"))
    fig(
        d,
        "p1_errors",
        "`make api-calls`: invalid fields, unknown listing_id and unknown operation all return "
        "success false with a clean error and the same correlation_id.",
    )


def part2(d):
    d.h2("Part 2. Three-Agent Kafka Pipeline")
    d.p(
        "Planner, Writer and Reviewer are three separate Python processes. They share one small loop "
        "(`kafka_agents/base.py`): read a message, do the agent's step, send the result to the next topic, then "
        "commit the offset. No agent imports or calls another agent; the only connection between them is Kafka. All "
        "three use llama3.2:3b. The Planner returns 2-4 steps as JSON, the Writer answers the question by following "
        "the steps, and the Reviewer returns approved true/false with a short note."
    )
    d.table(
        [
            ["Sender", "Reads topic", "Sends to", "Message adds"],
            ["send_question.py", "-", "s9486_inbox (1 partition)", "correlation_id, question"],
            ["planner.py", "s9486_inbox", "s9486_tasks (2 partitions)", "plan"],
            ["writer.py", "s9486_tasks", "s9486_drafts (1 partition)", "draft"],
            ["reviewer.py", "s9486_drafts", "s9486_final (1 partition)", "status, answer, review"],
        ],
        widths=["20%", "22%", "30%", "28%"],
    )
    d.h3("Topic creation")
    code(d, "scripts/kafka_create_topics.sh", "create() {", "create s9486_dead_letter 1")
    fig(
        d,
        "p2_topics",
        "`make kafka-topics`: the s9486_ topics created with kafka-topics.sh, s9486_tasks with 2 partitions.",
    )
    d.h3("Agent code")
    code(
        d,
        "kafka_agents/base.py",
        "    async def one_record(self, record, consumer, producer)",
        "msg = from_bytes(record.value)",
        "start of the shared loop",
    )
    code(
        d,
        "kafka_agents/planner.py",
        "    def handle(self, msg: dict) -> dict:",
        "steps = [s.strip() for s in steps[:4]]",
    )
    code(
        d,
        "kafka_agents/reviewer.py",
        "            reply, seconds = ask(",
        '"status": "approved" if approved else "needs_revision",',
    )
    d.h3("Running the agents (one terminal each)")
    block(
        d,
        "make planner        # python kafka_agents/planner.py\n"
        "make writer         # python kafka_agents/writer.py\n"
        "make reviewer       # python kafka_agents/reviewer.py\n"
        "make send-question  # python kafka_agents/send_question.py",
    )
    d.figs2([("p2_planner", "Terminal 1: Planner."), ("p2_writer", "Terminal 2: Writer.")])
    d.figs2([("p2_reviewer", "Terminal 3: Reviewer."), ("p2_send", "Terminal 4: send_question.py and the final JSON.")])
    for n in ("p2_planner", "p2_writer", "p2_reviewer", "p2_send"):
        if not (r5.SHOTS / f"{n}.png").exists():
            MISSING.append(n)
            d.add(f"<div class='missing'><b>MISSING SCREENSHOT ({n}.png)</b></div>")
    d.h3("IV. One complete message journey (inbox -> final)")
    j = load("pipeline_journey.json")
    d.p(
        f"From `make pipeline-demo` (all four processes started by the script, log lines with correlation_id "
        f"`{j['correlation_id']}` in time order):"
    )
    block(d, "\n".join(shorten(ln, 150) for ln in j["journey"]), long=True)
    d.add(metrics_section("part2-table"))
    d.p("Final message read from `s9486_final` (`raw/final_message.json`):")
    block(d, json.dumps(j["final"], indent=2, ensure_ascii=False), long=True)
    writer_s = j["final"]["writer"]["seconds"]
    d.h3("How Kafka helped the agents coordinate")
    d.p(
        "Each agent only knows its input topic and its output topic, so I could start, stop and restart them in any "
        f"order. When the Writer was slow (about {writer_s:.0f} s per answer on my Mac), the next question would "
        "wait in `s9486_tasks` instead of blocking the Planner. Because every message keeps the correlation_id and "
        "a small `trace` list, I could follow one question through all four topics from the logs and the final JSON. "
        "Kafka also remembers each agent's committed offset, which is what Part 3 builds on."
    )
    d.p(
        "One problem I hit: in my first logged run the Writer's 37 s model call was longer than the 10 s consumer "
        "session timeout, so Kafka dropped the Writer from its group. The draft was sent, but the commit after it "
        "failed and the Writer crashed. I raised the session timeout to 30 s and made a failed commit log a message "
        "instead of crashing (details in AI Use). The journey above is the second run, which had no errors."
    )


def part3(d):
    d.h2("Part 3. Failure Behavior")
    d.p(
        "Each fix has a switch, so the same code can run with and without it. The tests use the real Kafka topics, "
        "consumer groups and commits, but the Writer runs in `--mode fast` (fixed template answer, no model call) so "
        "20+ messages finish quickly. Each test starts its own Writer processes in a new consumer group."
    )
    d.h3("Failure table")
    d.add(metrics_section("part3-table"))

    d.h3("I. Duplicate delivery")
    d.p(
        "`make dup-test` sends the exact same bytes twice (same correlation_id) to the Part 1 worker and to the "
        "Writer. Without the fix the worker made a second listing and the Writer a second draft. With the fix both "
        "remember which correlation_ids they already finished. The worker sends the saved response again (same "
        "listing_id), and the Writer skips the message and only commits it."
    )
    code(
        d,
        "kafka_service/worker.py",
        "        key = f\"{cid}:{request['operation']}\"",
        "return reply_to, self.answered[key]",
    )
    code(
        d, "kafka_agents/base.py", "        if not a.no_idempotency and cid and cid in self.done:", "            return"
    )
    block(
        d,
        excerpt(
            "dup-test",
            lambda ln: (
                ln.startswith("=== ") or "listings_in_store" in ln or "duplicate correlation_id" in ln or "->" in ln
            ),
        ),
    )
    fig(
        d,
        "p3_duplicate",
        "`make dup-test`: the replay before the fix (2 listings / 2 drafts) and after the fix "
        "(same listing_id / duplicate skipped).",
    )

    d.h3("II. Consumer death")
    d.p(
        "`make death-test` sends task A (finishes normally) and task B (6 s of work). Two seconds into task B the "
        "Writer is killed with SIGKILL, and a new Writer starts in the same group. With auto-commit, aiokafka had "
        "already committed B's offset in the background, so B was never done (lost). With the commit after "
        "processing, B's offset was still uncommitted (lag 1), so Kafka gave B to the restarted Writer and it "
        "finished it."
    )
    code(d, "kafka_agents/base.py", "            enable_auto_commit=a.commit", "max_poll_interval_ms=600000,")
    code(
        d,
        "kafka_agents/base.py",
        "    async def commit(self, consumer, record)",
        "await consumer.commit({TopicPartition",
    )
    block(
        d,
        excerpt(
            "death-test",
            lambda ln: (
                ln.startswith("=== ")
                or "committed offsets " in ln
                or "killed" in ln
                or "committed=" in ln
                or "->" in ln
                or ("writer*" in ln and ("received" in ln or "committed offset" in ln))
            ),
        ),
    )
    fig(
        d,
        "p3_death",
        "`make death-test`: kill during task B, committed offsets right after the kill and after the "
        "restart, for auto-commit and for commit after processing.",
    )

    d.h3("III. Poison message")
    d.p(
        "`make poison-test` puts a bad message (not JSON, and in the second run also a task with no plan) in front "
        "of two good tasks on the same partition. Before the fix the Writer crashed on it, and every restart read the "
        "same offset and crashed again, so the good tasks were stuck behind it. After the fix each bad message is "
        f"tried {config.WRITER_MAX_RETRIES} times, then written to `s9486_dead_letter` with the error and its source "
        "offset, and committed, so the next tasks run."
    )
    code(
        d,
        "kafka_agents/base.py",
        "            except Exception as exc:",
        "await asyncio.sleep(0.5 * attempt)",
        "inside: for attempt in range(1, a.max_retries + 1)",
    )
    code(d, "kafka_agents/base.py", "        if out is None:", "await self.commit(consumer, record)")
    block(
        d,
        excerpt(
            "poison-test",
            lambda ln: (
                ln.startswith("=== ")
                or "FAILED" in ln
                or "attempt " in ln
                or "gave up" in ln
                or "s9486_dead_letter offset=" in ln
                or "->" in ln
                or "exited with code" in ln
            ),
        ),
    )
    fig(
        d,
        "p3_poison",
        "`make poison-test`: crash loop before the fix; 3 attempts, s9486_dead_letter and the good "
        "tasks processed after the fix.",
    )

    d.h3("IV. Ordering (VERIFY_SEED, 2 partitions, 2 Writers in one group)")
    d.p(
        "`make ordering-test` makes 20 related messages with `random.Random(269486)`: 4 listings with 5 updates "
        "each (seq 1-5), mixed into one send order. Two Writers join one consumer group, so each owns one partition "
        "of `s9486_tasks`. The same 20 messages are sent twice: once with no key, and once with the listing_code as "
        "the key. Each Writer logs every message it finished (`raw/ordering_*.csv`)."
    )
    code(
        d,
        "Homework8/scripts/failure_ordering.py",
        '        items = [((m["test"]["entity"].encode() if keyed',
        "metas = send_raw(config.TOPIC_TASKS, items)",
        "the partition key",
    )
    d.add(metrics_section("ordering-table"))
    block(
        d,
        excerpt(
            "ordering-test",
            lambda ln: "send order" in ln or "processing order" in ln or "-> " in ln or "has partition" in ln,
            width=400,
        ),
    )
    runs = load("ordering_summary.json")["runs"]
    un = runs["unkeyed"]
    keyed_parts = ", ".join(sorted({str(p) for v in runs["keyed"]["listings"].values() for p in v["partitions"]}))
    d.p(
        "Without a key, aiokafka picks a random partition for each message, so "
        f"{un['listings_split_across_partitions']} of 4 listings had their updates split across both Writers and "
        f"{un['listings_out_of_order']} of 4 finished out of order (a later seq done before an earlier one). With "
        "the key, every update of a listing went to the "
        f"same partition and was handled by one Writer in order. All 4 keys hashed to partition {keyed_parts}, so one "
        "Writer did all the work and the other sat idle. A key keeps the order, but with only a few keys the load can "
        "be uneven."
    )
    fig(d, "p3_ordering", "`make ordering-test`: both runs, partition per listing and processed order.")

    d.h3("V. Comparison with my HW2 in-process graph")
    d.p(
        "In HW2 my LangGraph workflow (supervisor -> planner -> reviewer) ran as function calls in one Python process. "
        "Each node got the previous node's state as a return value. Here the same kind of hand-off goes through "
        "Kafka topics between separate processes."
    )
    d.table(
        [
            ["", "What changed"],
            [
                "Benefit 1: failures stay separate",
                "When the Writer crashed or was killed, the Planner and Reviewer kept "
                "running and the work waited in s9486_tasks. In HW2 one exception ended the whole graph run.",
            ],
            [
                "Benefit 2: independent scaling",
                "I could run two Writers in one consumer group and Kafka split the 2 partitions between "
                "them, without changing the Planner or Reviewer. In HW2 every step ran one after another in the "
                "same process.",
            ],
            [
                "Responsibility 1: duplicates and offsets",
                "Kafka can deliver a message again (a replay, or a crash before "
                "the commit), so I had to add the idempotency check and decide when to commit. A function call in HW2 "
                "ran exactly once.",
            ],
            [
                "Responsibility 2: ordering and bad messages",
                "Order is only kept inside one partition, so I had to choose a key. A bad message can "
                "block a partition forever, so I had to add retries and a dead-letter topic. In HW2 the order was "
                "just the order of the code.",
            ],
        ],
        widths=["30%", "70%"],
    )


def verification(d):
    d.h2("Verification and Conclusions")
    v = json.loads((REPORT_DIR / "verification.json").read_text(encoding="utf-8"))
    d.p(
        f"`make verify-hw08` writes `reports/hw08/verification.json`. Last run: {v['passed']}/{v['total']} checks "
        f"passed (commit `{v['commit_hash'][:12]}`, model {v['model']['name']}, SEED {v['seed']}, VERIFY_SEED "
        f"{v['verify_seed']}). It checks behavior, not wording."
    )
    d.table(
        [["Check", "Result"]] + [[c["name"], "PASS" if c["passed"] else "FAIL"] for c in v["checks"]],
        widths=["70%", "30%"],
    )
    d.h3("Conclusions")
    d.bullets(
        [
            "Splitting the Listing service into a client and a worker worked as long as the correlation_id is "
            "created once and copied unchanged; both demo runs and all error cases kept it.",
            f"The three agents only talk through Kafka. One question took about {pipeline_seconds():.0f} s end to end, "
            "almost all of it "
            "the local model.",
            "Each failure was easy to cause once the parts were separate processes: a replay made a second listing, "
            "auto-commit lost a task when the Writer died, and one bad message blocked a partition. Idempotency, "
            "committing after processing, and retries + a dead-letter topic fixed them in my tests.",
            "Keys keep related messages in order, but they decide the load too: my 4 keys all landed on one partition.",
            "The JMeter instructions are a separate DATA 236 demo (`/users-direct` on port 8000) and are not part of "
            "the HW8 PDF, so I did not run a load test.",
        ]
    )


def ai_use(d):
    d.h2("AI Use")
    d.add(r5.md_paragraphs((REPORT_DIR / "AI_USE.md").read_text(encoding="utf-8")))


def main() -> int:
    commit = (
        os.getenv("COMMIT_HASH")
        or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        d = r5.Doc(tmp)
        for section in (section0, part1, part2, part3, verification, ai_use):
            section(d, commit) if section is section0 else section(d)
        font_dir = r5.find_font()
        font_css = ""
        if font_dir:
            for fam, f, w in [
                ("DejaVu Sans", "DejaVuSans.ttf", "normal"),
                ("DejaVu Sans", "DejaVuSans-Bold.ttf", "bold"),
                ("DejaVu Sans Mono", "DejaVuSansMono.ttf", "normal"),
            ]:
                if (Path(font_dir) / f).exists():
                    shutil.copy(Path(font_dir) / f, tmp / f)
                    font_css += f"@font-face {{ font-family: '{fam}'; src: url('{f}'); font-weight: {w}; }}\n"
        page = (
            f"<!doctype html><html><head><meta charset='utf-8'><title>DATA 260 HW8 - Kavan Siddesh</title>"
            f"<style>{font_css}{CSS}</style></head><body>{''.join(d.parts)}</body></html>"
        )
        (tmp / "report.html").write_text(page, encoding="utf-8")
        subprocess.run(
            [
                r5.CHROME,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}",
                (tmp / "report.html").as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        if os.getenv("KEEP_HTML"):
            shutil.copytree(tmp, os.environ["KEEP_HTML"], dirs_exist_ok=True)
    shutil.copy(OUT_PDF, NAMED_PDF)
    print(
        f"wrote {OUT_PDF.relative_to(ROOT)} and {NAMED_PDF.relative_to(ROOT)} "
        f"(commit {commit[:12]}, {d.fig_no} figures)"
    )
    if MISSING:
        print(f"DRAFT - MISSING screenshots shown as red boxes: {', '.join(dict.fromkeys(MISSING))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
