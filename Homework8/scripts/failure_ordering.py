#!/usr/bin/env python3
"""HW8 Part 3D: ordering with s9486_tasks (2 partitions) and two Writer instances in one consumer group.

20 related messages are made with random.Random(VERIFY_SEED): 4 listings x 5 updates each (seq 1..5), mixed
together in one send order. Each message also says how long its "work" takes (0.05-0.60 s, same seed), so the
two Writers finish at different speeds. The test runs twice with the same 20 messages:

  unkeyed  key=None          aiokafka picks a random partition for each message
  keyed    key=listing_code  every update of one listing hashes to the same partition

For each listing it checks: how many partitions its messages went to, and whether seq 1..5 finished in order.
Writers run in --mode fast (no model call) and write one JSON line per processed message (--record).

Usage (repo root, `make kafka-up` first):  python Homework8/scripts/failure_ordering.py
Writes reports/hw08/raw/ordering_messages.json, ordering_unkeyed.csv, ordering_keyed.csv, ordering_summary.json
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
import uuid
from datetime import datetime

from hw8_common import RAW, Proc, banner, footer, send_raw, skip_test_messages, utc_now, write_csv, write_json

import config
from kafka_service.common import to_bytes

N_LISTINGS, UPDATES = 4, 5
EVENTS = ["price changed", "photos added", "units updated", "tour slot added", "marked as leased"]
READY = re.compile(r"\[(writer-\d)\] ready: .* assigned partitions=\[([\d, ]*)\]")


def make_messages(seed: int) -> list[dict]:
    rng = random.Random(seed)
    listings = sorted({f"LST-{rng.randint(10000, 99999)}" for _ in range(N_LISTINGS)})
    left = {code: 1 for code in listings}  # next seq per listing
    out = []
    for index in range(N_LISTINGS * UPDATES):
        code = rng.choice([c for c in listings if left[c] <= UPDATES])
        seq = left[code]
        left[code] += 1
        out.append(
            {
                "correlation_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                "question": f"Listing {code} update {seq}/{UPDATES}: {EVENTS[seq - 1]}",
                "plan": [f"Apply update {seq} to {code}"],
                "test": {"entity": code, "seq": seq, "index": index, "work_s": round(rng.uniform(0.05, 0.6), 3)},
            }
        )
    return out


def wait_for_split(writers: list[Proc], timeout: float = 90) -> dict[str, list[int]]:
    """Wait until each Writer owns exactly one of the two partitions (after the group rebalance)."""
    end = time.time() + timeout
    while time.time() < end:
        latest = {}
        for w in writers:
            for line in w.lines:
                m = READY.search(line)
                if m:
                    latest[m.group(1)] = [int(x) for x in m.group(2).split(",") if x.strip()]
        if (
            len(latest) == 2
            and sorted(sum(latest.values(), [])) == [0, 1]
            and all(len(v) == 1 for v in latest.values())
        ):
            return latest
        time.sleep(0.2)
    raise SystemExit(f"writers did not split the partitions: {latest}")


def run(name: str, msgs: list[dict], keyed: bool) -> list[dict]:
    print(f"\n=== {name} run: key={'listing_code' if keyed else 'None'}", flush=True)
    group = f"{config.PREFIX}_writers_order_{name}_{datetime.now():%H%M%S}"
    record = RAW / f"ordering_{name}_records.jsonl"
    record.unlink(missing_ok=True)
    writers = [
        Proc(
            f"writer-{i}",
            [
                "kafka_agents/writer.py",
                "--mode",
                "fast",
                "--group",
                group,
                "--instance",
                f"writer-{i}",
                "--from",
                "latest",
                "--record",
                str(record),
            ],
            echo=False,
        )
        for i in (1, 2)
    ]
    try:
        split = wait_for_split(writers)
        print(f"  consumer group {group}: " + ", ".join(f"{w} has partition {p}" for w, p in sorted(split.items())))
        items = [((m["test"]["entity"].encode() if keyed else None), to_bytes(m)) for m in msgs]
        metas = send_raw(config.TOPIC_TASKS, items)
        print(
            f"  sent 20 messages: partition 0 got {sum(m['partition'] == 0 for m in metas)}, "
            f"partition 1 got {sum(m['partition'] == 1 for m in metas)}"
        )
        end = time.time() + 90
        while time.time() < end and (not record.exists() or len(record.read_text().splitlines()) < len(msgs)):
            time.sleep(0.2)
    finally:
        for w in writers:
            w.stop()
    rows = [json.loads(line) for line in record.read_text().splitlines()]
    rows.sort(key=lambda r: r["processed_at"])
    t0 = rows[0]["started_at"] if rows else 0
    for rank, r in enumerate(rows, 1):
        r["processed_rank"] = rank
        r["processed_ms"] = round((r["processed_at"] - t0) * 1000)
    return rows


def summarize(rows: list[dict]) -> dict:
    per = {}
    for code in sorted({r["entity"] for r in rows}):
        mine = [r for r in rows if r["entity"] == code]  # already in processing order
        seqs = [r["seq"] for r in mine]
        per[code] = {
            "partitions": sorted({r["partition"] for r in mine}),
            "writers": sorted({r["instance"] for r in mine}),
            "processed_seq_order": seqs,
            "in_order": seqs == sorted(seqs),
        }
    return {
        "processed": len(rows),
        "listings": per,
        "listings_split_across_partitions": sum(len(v["partitions"]) > 1 for v in per.values()),
        "listings_out_of_order": sum(not v["in_order"] for v in per.values()),
    }


def show(name: str, summary: dict) -> None:
    print(f"  {'listing':10} {'partitions':11} {'writers':20} processed seq order   in order")
    for code, v in summary["listings"].items():
        print(
            f"  {code:10} {str(v['partitions']):11} {', '.join(v['writers']):20} "
            f"{str(v['processed_seq_order']):21} {v['in_order']}"
        )
    print(
        f"  -> {name}: {summary['processed']}/20 processed, {summary['listings_split_across_partitions']} listing(s) "
        f"split across partitions, {summary['listings_out_of_order']} listing(s) out of order"
    )


def main() -> int:
    banner(f"Part 3D ordering (20 messages from VERIFY_SEED {config.VERIFY_SEED}, 2 partitions, 2 writers)")
    msgs = make_messages(config.VERIFY_SEED)
    write_json(RAW / "ordering_messages.json", {"seed": config.VERIFY_SEED, "messages": msgs})
    print("  send order: " + " ".join(f"{m['test']['entity'][-5:]}#{m['test']['seq']}" for m in msgs))

    results = {}
    for name, keyed in (("unkeyed", False), ("keyed", True)):
        rows = run(name, msgs, keyed)
        cols = [
            "processed_rank",
            "processed_ms",
            "send_index",
            "entity",
            "seq",
            "key",
            "partition",
            "offset",
            "instance",
        ]
        write_csv(RAW / f"ordering_{name}.csv", [{c: r.get(c) for c in cols} for r in rows])
        results[name] = summarize(rows)
        print("  processing order: " + " ".join(f"{r['entity'][-5:]}#{r['seq']}(p{r['partition']})" for r in rows))
        show(name, results[name])
    skip_test_messages()

    write_json(RAW / "ordering_summary.json", {"run_at": utc_now(), "seed": config.VERIFY_SEED, "runs": results})
    keyed = results["keyed"]
    ok = (
        keyed["processed"] == 20
        and keyed["listings_split_across_partitions"] == 0
        and keyed["listings_out_of_order"] == 0
    )
    print(f"\nkeyed run kept every listing on one partition and in order: {ok}")
    return 0 if ok and results["unkeyed"]["processed"] == 20 else 1


if __name__ == "__main__":
    code = main()
    footer("Part 3D ordering")
    sys.exit(code)
