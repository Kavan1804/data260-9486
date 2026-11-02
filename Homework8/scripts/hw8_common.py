"""Small helpers shared by the HW8 scripts (same pattern as hw6_common.py / hw7_common.py)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from hw5_common import STUDENT  # noqa: E402,F401 - same name in every terminal screenshot
from hw5_common import banner as _hw5_banner  # noqa: E402

import config  # noqa: E402

HW8_DIR = ROOT / "Homework8"
REPORT_DIR = config.HW8_REPORT_DIR  # reports/hw08
RAW = REPORT_DIR / "raw"
BASE_URL = f"http://127.0.0.1:{config.PORT_BASE}"


def banner(title: str) -> None:
    _hw5_banner(f"HW8 | {title}")


def footer(title: str) -> None:
    """Last line of every HW8 script, so the name is visible even when the banner has scrolled off."""
    print(f"===== {STUDENT} | SID4 {config.SID4} | {config.PREFIX} | HW8 | {title} - done =====", flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def docker_logs(container: str, since_utc: str, must_contain: str | None = None) -> list[str]:
    """Lines a container printed since `since_utc` (optionally only lines containing a string)."""
    try:
        out = subprocess.run(
            ["docker", "logs", "--since", since_utc, container], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = (out.stdout + out.stderr).splitlines()
    return [ln for ln in lines if must_contain is None or must_contain in ln]


def fill_metrics_section(marker: str, content: str) -> None:
    """Replace the text between <!-- {marker}:start --> and <!-- {marker}:end --> in reports/hw08/METRICS.md."""
    path = REPORT_DIR / "METRICS.md"
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    path.write_text(text[:i] + "\n" + content.strip() + "\n" + text[j:], encoding="utf-8")


# ---------- running agents as child processes (pipeline demo, failure tests, verify) ----------
# aiokafka prints these warnings while a group rebalances or the Mac is busy; they stay in the log files
# but are not echoed to the terminal.
NOISE = ("Heartbeat failed", "Marking the coordinator dead", "Group Coordinator Request failed", "Heartbeat session")


class Proc:
    """A child process whose output is echoed with a name prefix and kept in self.lines."""

    def __init__(self, name: str, args: list[str], log_file: Path | None = None, echo: bool = True):
        import threading

        self.name = name
        self.lines: list[str] = []
        self.log_file = log_file
        self.echo = echo
        cmd = [sys.executable, "-u", *args]
        if echo:
            print(f"  $ {' '.join(args)}   [{name}]", flush=True)
        self.p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self) -> None:
        log = self.log_file.open("a", encoding="utf-8") if self.log_file else None
        for line in self.p.stdout:
            line = line.rstrip("\n")
            self.lines.append(line)
            if log:
                log.write(line + "\n")
                log.flush()
            if self.echo and not line.startswith(NOISE):
                print(f"  {self.name:>9} | {line}", flush=True)
        if log:
            log.close()

    def wait_for(self, text: str, timeout: float = 60, after: int = 0) -> bool:
        """True once a line (from index `after` on) contains `text`."""
        import time

        end = time.time() + timeout
        while time.time() < end:
            if any(text in ln for ln in self.lines[after:]):
                return True
            if self.p.poll() is not None:
                time.sleep(0.3)  # let the reader thread finish
                return any(text in ln for ln in self.lines[after:])
            time.sleep(0.1)
        return False

    def count(self, text: str) -> int:
        return sum(text in ln for ln in self.lines)

    def kill(self) -> None:
        """SIGKILL: the process gets no chance to clean up or commit (a crash)."""
        import signal

        if self.p.poll() is None:
            self.p.send_signal(signal.SIGKILL)
        self.p.wait(timeout=10)
        self._t.join(timeout=5)

    def stop(self) -> None:
        """SIGTERM: the agent leaves its consumer group cleanly."""
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(timeout=10)
        self._t.join(timeout=5)


def kafka_cli(*args: str) -> str:
    """Run a Kafka CLI tool inside the broker container, e.g. kafka_cli("kafka-consumer-groups.sh", ...)."""
    tool, *rest = args
    out = subprocess.run(
        ["docker", "exec", "s9486_kafka", f"/opt/kafka/bin/{tool}", "--bootstrap-server", "kafka:29092", *rest],
        capture_output=True,
        text=True,
        timeout=90,
    )
    return (out.stdout + out.stderr).strip()


def group_offsets(group: str) -> list[str]:
    """`kafka-consumer-groups --describe` rows (TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG)."""
    rows = []
    for line in kafka_cli("kafka-consumer-groups.sh", "--describe", "--group", group).splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0] == group:
            rows.append(f"topic={parts[1]} partition={parts[2]} committed={parts[3]} log_end={parts[4]} lag={parts[5]}")
    return rows


def skip_test_messages() -> None:
    """Move the normal Part 2 groups past the test messages, so `make planner`/`writer`/`reviewer` later do not
    process the test questions, tasks and drafts with the real model."""
    for group, topic in (
        (f"{config.PREFIX}_planners", config.TOPIC_INBOX),
        (f"{config.PREFIX}_writers", config.TOPIC_TASKS),
        (f"{config.PREFIX}_reviewers", config.TOPIC_DRAFTS),
    ):
        out = kafka_cli(
            "kafka-consumer-groups.sh",
            "--reset-offsets",
            "--to-latest",
            "--execute",
            "--group",
            group,
            "--topic",
            topic,
        )
        status = "moved to the end" if "NEW-OFFSET" in out else out.splitlines()[-1] if out else "no output"
        print(f"  cleanup: group {group} on {topic}: {status}", flush=True)


# ---------- small Kafka helpers (each opens its own short-lived client) ----------


async def _partitions(topic: str) -> list[int]:
    from aiokafka import AIOKafkaProducer

    from kafka_service.common import bootstrap

    prod = AIOKafkaProducer(bootstrap_servers=bootstrap())
    await prod.start()
    try:
        return sorted(await prod.partitions_for(topic))
    finally:
        await prod.stop()


async def _end_offsets(topic: str) -> dict[int, int]:
    from aiokafka import AIOKafkaConsumer, TopicPartition

    from kafka_service.common import bootstrap

    tps = [TopicPartition(topic, p) for p in await _partitions(topic)]
    c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None)
    await c.start()
    try:
        return {tp.partition: off for tp, off in (await c.end_offsets(tps)).items()}
    finally:
        await c.stop()


async def _read_since(topic: str, start: dict[int, int]) -> list[dict]:
    from aiokafka import AIOKafkaConsumer, TopicPartition

    from kafka_service.common import bootstrap

    tps = [TopicPartition(topic, p) for p in sorted(start)]
    c = AIOKafkaConsumer(bootstrap_servers=bootstrap(), group_id=None, enable_auto_commit=False)
    await c.start()
    out: list[dict] = []
    try:
        c.assign(tps)
        for tp in tps:
            c.seek(tp, start[tp.partition])
        ends = await c.end_offsets(tps)
        while [tp for tp in tps if await c.position(tp) < ends[tp]]:
            batch = await c.getmany(timeout_ms=1000)
            for tp, records in batch.items():
                for r in records:
                    try:
                        value = json.loads(r.value)
                    except (ValueError, TypeError):
                        value = (r.value or b"").decode("utf-8", "replace")
                    out.append(
                        {"partition": r.partition, "offset": r.offset, "key": r.key and r.key.decode(), "value": value}
                    )
    finally:
        await c.stop()
    return out


async def _send_raw(topic: str, items: list[tuple[bytes | None, bytes]]) -> list[dict]:
    from aiokafka import AIOKafkaProducer

    from kafka_service.common import bootstrap

    prod = AIOKafkaProducer(bootstrap_servers=bootstrap())
    await prod.start()
    try:
        metas = []
        for key, value in items:
            r = await prod.send_and_wait(topic, value, key=key)
            metas.append({"topic": r.topic, "partition": r.partition, "offset": r.offset})
        return metas
    finally:
        await prod.stop()


def topic_end(topic: str) -> dict[int, int]:
    """Current end offset of every partition (read this before a test, then read_since after it)."""
    import asyncio

    return asyncio.run(_end_offsets(topic))


def read_since(topic: str, start: dict[int, int]) -> list[dict]:
    import asyncio

    return asyncio.run(_read_since(topic, start))


def send_raw(topic: str, items: list[tuple[bytes | None, bytes]]) -> list[dict]:
    """Send exact bytes (used to replay a message unchanged and to send a poison message)."""
    import asyncio

    return asyncio.run(_send_raw(topic, items))


def task_message(cid: str, question: str, **extra) -> dict:
    """A Writer task like the Planner makes, for the failure tests."""
    return {"correlation_id": cid, "question": question, "plan": ["Short answer", "One example"], **extra}
