#!/usr/bin/env python3
"""HW7 Part 4: run the LangGraph ReAct agent on both scenario CSVs with the saved pricing snapshot.

For each scenario it saves, in reports/hw07/raw/:
  bikeshare_<scenario>.json             full result (decision, justification, costs, timeline, citations, metrics)
  pricing_snapshot_<scenario>.txt       the exact pricing-page text used for the run
  pricing_snapshot_<scenario>.json      source URL, access date/time, SHA-256 (checked against the text)

Usage (repo root, Ollama running):  python Homework7/scripts/run_bikeshare_scenarios.py
"""

from __future__ import annotations

import hashlib
import sys

from hw7_common import FIXTURES, RAW, banner, fill_metrics_section, write_json

from bikeshare.agent import run_bikeshare
from bikeshare.tools import load_page

URL = "https://www.lyft.com/bikes/bay-wheels/pricing"
SCENARIOS = ("membership_wins", "payperuse_wins")


def main() -> int:
    banner("Part 4 bike-share ReAct agent (LangGraph + llama3.2:3b) on both scenarios")
    page = load_page(URL, mode="snapshot")
    if hashlib.sha256(page["text"].encode("utf-8")).hexdigest() != page["sha256"]:
        print("snapshot hash does not match its text - stopping")
        return 1
    print(f"pricing source: {URL}\n  {page['origin']}, captured {page['captured_at']}, SHA-256 {page['sha256']}\n")
    table = [
        "| Scenario | Rows | Agent decision | Tool-computed decision | Pay-per-use | Membership (fees + residual) | "
        "Break-even rides/month vs actual | Steps | Time (s) | Stop reason |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name in SCENARIOS:
        csv_path = FIXTURES / "bikeshare" / f"scenario_{name}.csv"
        print(f"=== scenario {name} ({csv_path.name})")
        r = run_bikeshare(csv_path.read_text(encoding="utf-8"), URL, csv_name=csv_path.name, page_mode="snapshot")
        for t in r["timeline"]:
            if t["by"] == "agent":
                print(
                    f"  [{t['step']}] {t['tool']}({str(t['input'])[:120]}) -> "
                    f"{'ok' if t['success'] else 'error: ' + str(t['error'])} {t['observation'][:110]}"
                )
        v = r["verified"]
        print(
            f"  agent decision: {r['agent_decision']} | tool-computed: {v['decision']} | agrees: "
            f"{r['decision_matches_tools']}"
        )
        print(
            f"  pay-per-use ${v['pay_per_use_total']:,.2f} vs membership ${v['membership_total']:,.2f} "
            f"(fees ${v['membership_fees']:,.2f} + residual ${v['membership_residual_charges']:,.2f}); "
            f"break-even {v['break_even_rides_per_month']} rides/month vs actual {v['rides_per_month']}"
        )
        print(f"  steps {r['steps']}, total time {r['total_time_s']} s, stop reason {r['stop_reason']}")
        print("  final answer:\n    " + r["final_text"].replace("\n", "\n    ") + "\n")
        write_json(RAW / f"bikeshare_{name}.json", r)
        (RAW / f"pricing_snapshot_{name}.txt").write_text(page["text"], encoding="utf-8")
        write_json(
            RAW / f"pricing_snapshot_{name}.json",
            {
                "scenario": name,
                "source_url": URL,
                "access_date": page["captured_at"],
                "sha256": page["sha256"],
                "chars": len(page["text"]),
                "origin": page["origin"],
            },
        )
        table.append(
            f"| {name} | {v['rides']} | {r['agent_decision']} | {v['decision']} | ${v['pay_per_use_total']:,.2f} "
            f"| ${v['membership_total']:,.2f} (${v['membership_fees']:,.2f} + "
            f"${v['membership_residual_charges']:,.2f}) "
            f"| {v['break_even_rides_per_month']} vs {v['rides_per_month']} | {r['steps']} | {r['total_time_s']} "
            f"| {r['stop_reason']} |"
        )
    table += ["", f"Pricing snapshot: {URL}, captured {page['captured_at']}, SHA-256 `{page['sha256']}`."]
    fill_metrics_section("part4-table", "\n".join(table))
    print("\n".join(table))
    return 0


if __name__ == "__main__":
    sys.exit(main())
