#!/usr/bin/env python3
"""Fills the tables in reports/hw08/METRICS.md from the raw files (same marker idea as HW6/HW7).

Usage (repo root, after the Part 1-3 runs):  make metrics-hw08
"""

from __future__ import annotations

import json
from datetime import datetime

from hw8_common import RAW, banner, fill_metrics_section


def load(name: str):
    return json.loads((RAW / name).read_text(encoding="utf-8"))


def part1() -> str:
    lines = [
        "| Run | correlation_id | listing_id | CREATE request (topic/partition/offset) | Same id | GET matches |",
        "|---|---|---|---|---|---|",
    ]
    for via in ("kafka", "api"):
        d = load(f"part1_demo_{via}.json")
        req = d["create"]["kafka"]["request"]
        lines.append(
            f"| homework_demo.py --via {via} | `{d['correlation_id']}` | `{d['listing_id']}` | "
            f"{req['topic']}/{req['partition']}/{req['offset']} | {d['correlation_id_preserved']} | "
            f"{d['get_matches_create']} |"
        )
    lines += [
        "",
        "| Error case (through FastAPI 8486) | HTTP | success | error | correlation_id echoed |",
        "|---|---|---|---|---|",
    ]
    cases = load("part1_error_cases.json")["cases"]
    for c in cases:
        r = c["response"]
        lines.append(
            f"| {c['case']} | {c['http_status']} | {r['success']} | {r.get('error', '-')} | "
            f"{r['correlation_id'] == c['sent_correlation_id']} |"
        )
    ok = sum(c["ok"] for c in cases)
    lines.append(f"\n{ok}/{len(cases)} cases gave the expected result and echoed the same correlation_id.")
    return "\n".join(lines)


def part2() -> str:
    d = load("pipeline_journey.json")
    f, trace = d["final"], d["final"]["trace"]
    t = [datetime.fromisoformat(x.get("sent_at") or x["done_at"]) for x in trace]
    rows = ["| Stage | Reads | Writes | Time (s) |", "|---|---|---|---|"]
    hops = [
        ("planner", "s9486_inbox", "s9486_tasks"),
        ("writer", "s9486_tasks", "s9486_drafts"),
        ("reviewer", "s9486_drafts", "s9486_final"),
    ]
    for i, (name, src, dst) in enumerate(hops, 1):
        rows.append(f"| {name} (read {trace[i]['read']}) | {src} | {dst} | {(t[i] - t[i - 1]).total_seconds():.1f} |")
    rows.append(f"| total (send_question -> final) | | | {(t[-1] - t[0]).total_seconds():.1f} |")
    words = len(f["answer"].split())
    rows += [
        "",
        f"correlation_id `{d['correlation_id']}` kept through all stages: {d['correlation_id_preserved']}. "
        f"Final status `{f['status']}`, answer {words} words, model {d['model']} for all three agents. "
        f'Reviewer notes: "{f["review"]["notes"]}"',
    ]
    return "\n".join(rows)


def part3() -> str:
    dup = {(r["consumer"], r["run"]): r for r in load("duplicate_replay.json")["runs"]}
    death = {r["run"]: r for r in load("consumer_death.json")["runs"]}
    poison = {r["run"]: r for r in load("poison_message.json")["runs"]}
    order = load("ordering_summary.json")["runs"]

    def lag(rows):
        return "; ".join(r.replace("topic=s9486_tasks ", "") for r in rows if "lag=-" not in r)

    wb, wa = dup[("Part 1 worker", "before fix")], dup[("Part 1 worker", "after fix")]
    rb, ra = dup[("Writer agent", "before fix")], dup[("Writer agent", "after fix")]
    db, da = death["before fix"], death["after fix"]
    pb, pa = poison["before fix"], poison["after fix"]
    un, ke = order["unkeyed"], order["keyed"]
    rows = [
        "| Failure scenario | Before fix | After fix |",
        "|---|---|---|",
        f"| Duplicate delivery (same message sent twice) | worker: {wb['distinct_listing_ids']} different listing_ids, "
        f"{wb['listings_created']} listings for one request; writer: {rb['drafts_written']} drafts | worker: same "
        f"listing_id both times, {wa['listings_created']} listing (saved response re-sent); writer: "
        f"{ra['drafts_written']} draft, duplicate skipped |",
        f"| Consumer killed mid-work (SIGKILL 2 s into a 6 s task) | auto-commit: offset already committed at the kill "
        f"({lag(db['offsets_after_kill'])}); restarted writer never saw task B, {db['drafts_task_b']} drafts -> lost | "
        f"commit after processing: {lag(da['offsets_after_kill'])} at the kill; restarted writer got task B again and "
        f"finished it ({da['drafts_task_b']} draft, {lag(da['offsets_after_restart'])}) |",
        f"| Poison message (not JSON / no plan) | writer crashed on the same offset twice (exit codes "
        f"{pb['writer_exit_codes']}), {pb['good_tasks_processed']}/2 good tasks after it ran, "
        f"{lag(pb['offsets_end'])} | {pa['max_retries']} tries each, {len(pa['dead_letter'])} messages moved to "
        f"s9486_dead_letter, {pa['good_tasks_processed']}/2 good tasks ran, {lag(pa['offsets_end'])} |",
        f"| Two partitions / two consumers (20 VERIFY_SEED messages) | no key: "
        f"{un['listings_split_across_partitions']}/4 listings split across partitions, "
        f"{un['listings_out_of_order']}/4 finished out of order | key = listing_code: "
        f"{ke['listings_split_across_partitions']}/4 split, {ke['listings_out_of_order']}/4 out of order |",
    ]
    return "\n".join(rows)


def ordering() -> str:
    order = load("ordering_summary.json")["runs"]
    rows = ["| Run | Listing | Partitions | Writers | Processed seq order | In order |", "|---|---|---|---|---|---|"]
    for run in ("unkeyed", "keyed"):
        for code, v in order[run]["listings"].items():
            rows.append(
                f"| {run} | {code} | {v['partitions']} | {', '.join(v['writers'])} | "
                f"{v['processed_seq_order']} | {v['in_order']} |"
            )
    return "\n".join(rows)


def main() -> None:
    banner("fill METRICS.md from raw/")
    for marker, fn in (
        ("part1-table", part1),
        ("part2-table", part2),
        ("part3-table", part3),
        ("ordering-table", ordering),
    ):
        fill_metrics_section(marker, fn())
        print(f"  filled {marker}")


if __name__ == "__main__":
    main()
