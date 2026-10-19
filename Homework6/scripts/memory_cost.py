#!/usr/bin/env python3
"""HW6 Part 3: summary table, compression-policy comparison and memory-cost estimate.

Reads reports/hw06/raw/turns_<setting>.csv (conversation turns only, probes excluded)
and reports/hw06/raw/probe_scores.json, then writes
    reports/hw06/raw/memory_summary.json, memory_cost.csv
and fills the tables in reports/hw06/METRICS.md.

Prompt tokens are Ollama's prompt_eval_count. If a row has no real count, the
ceil(chars/4) estimate is used for that row and the table says so.

Cost: $1 per million input tokens, $5 per million output tokens,
10,000 conversations x 30 turns. Two views:
    reply only     - the /api/chat reply call
    with upkeep    - plus the memory upkeep calls (fact extraction, summaries)

Usage (repo root):
    python Homework6/scripts/memory_cost.py
"""

from __future__ import annotations

import json
import sys

from hw6_common import RAW, SETTING_NAMES, SETTINGS, banner, fill_metrics_section, read_csv, write_csv, write_json

INPUT_PER_M = 1.0
OUTPUT_PER_M = 5.0
CONVERSATIONS = 10_000
TURNS = 30
PROBE_TOLERANCE = 0.5  # "best" = cheapest setting within 0.5 probe points of the top score


def num(value) -> float | None:
    return float(value) if value not in (None, "", "None") else None


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def cost_for(input_tokens_per_turn: float, output_tokens_per_turn: float,
             conversations: int = CONVERSATIONS, turns: int = TURNS) -> float:
    """Dollar cost of `conversations` conversations of `turns` turns."""
    per_turn = input_tokens_per_turn * INPUT_PER_M / 1e6 + output_tokens_per_turn * OUTPUT_PER_M / 1e6
    return per_turn * turns * conversations


def summarize(label: str, rows: list[dict], probe_mean: float | None) -> dict:
    conv = [r for r in rows if r["phase"] == "conversation"]
    real = [num(r["prompt_tokens"]) for r in conv]
    estimated_rows = sum(1 for v in real if v is None)
    prompt = [num(r["prompt_tokens"]) if num(r["prompt_tokens"]) is not None else num(r["prompt_tokens_est"])
              for r in conv]
    completion = [num(r["completion_tokens"]) if num(r["completion_tokens"]) is not None
                  else num(r["completion_tokens_est"]) for r in conv]
    s = {
        "setting": label,
        "name": SETTING_NAMES[label],
        "turns": len(conv),
        "rows_using_estimate": estimated_rows,
        "mean_prompt_tokens": round(mean(prompt), 1),
        "mean_prompt_tokens_est": round(mean([num(r["prompt_tokens_est"]) for r in conv]), 1),
        "mean_completion_tokens": round(mean(completion), 1),
        "mean_aux_prompt_tokens": round(mean([num(r["aux_prompt_tokens"]) or 0 for r in conv]), 1),
        "mean_aux_completion_tokens": round(mean([num(r["aux_completion_tokens"]) or 0 for r in conv]), 1),
        "mean_latency_ms": round(mean([num(r["latency_ms"]) for r in conv]), 1),
        "mean_model_latency_ms": round(mean([num(r["model_latency_ms"]) for r in conv]), 1),
        "mean_primer_tokens_est": round(mean([num(r["system_primer_tokens_est"]) for r in conv]), 1),
        "mean_summary_tokens_est": round(mean([num(r["long_term_summary_tokens_est"]) for r in conv]), 1),
        "mean_window_tokens_est": round(mean([num(r["short_term_window_tokens_est"]) for r in conv]), 1),
        "mean_episodic_tokens_est": round(mean([num(r["episodic_facts_tokens_est"]) for r in conv]), 1),
        "probe_mean": probe_mean,
    }
    s["cost_reply_only"] = round(cost_for(s["mean_prompt_tokens"], s["mean_completion_tokens"]), 2)
    s["cost_with_upkeep"] = round(cost_for(s["mean_prompt_tokens"] + s["mean_aux_prompt_tokens"],
                                           s["mean_completion_tokens"] + s["mean_aux_completion_tokens"]), 2)
    return s


def pick_best_worst(summaries: list[dict]) -> tuple[dict, dict, str]:
    scored = [s for s in summaries if s["probe_mean"] is not None]
    if scored:
        top = max(s["probe_mean"] for s in scored)
        good = [s for s in scored if s["probe_mean"] >= top - PROBE_TOLERANCE]
        best = min(good, key=lambda s: s["cost_with_upkeep"])
        rule = (f"best = cheapest setting (with upkeep) whose probe score is within {PROBE_TOLERANCE} of the top "
                f"score {top}; worst = most expensive setting (ties broken by lower probe score)")
    else:
        best = min(summaries, key=lambda s: s["cost_with_upkeep"])
        rule = "no probe scores yet: best = cheapest, worst = most expensive"
    worst = max(summaries, key=lambda s: (s["cost_with_upkeep"], -(s["probe_mean"] or 0)))
    return best, worst, rule


def main() -> int:
    banner("Part 3 memory cost (input $1/M, output $5/M, 10,000 x 30-turn conversations)")
    probe_path = RAW / "probe_scores.json"
    probe = json.loads(probe_path.read_text(encoding="utf-8"))["per_setting"] if probe_path.exists() else {}

    summaries = []
    for label in SETTINGS:
        path = RAW / f"turns_{label}.csv"
        if path.exists():
            summaries.append(summarize(label, read_csv(path), probe.get(label, {}).get("mean")))
        else:
            print(f"(skip {label}: {path.name} not found)")
    if not summaries:
        print("No experiment data found. Run run_memory_experiments.py first.")
        return 1

    def fmt(v):
        return "n/a" if v is None else v

    table = ["| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |", "|---|---|---|---|"]
    table += [f"| {s['name']} | {s['mean_prompt_tokens']} | {s['mean_latency_ms']} | {fmt(s['probe_mean'])} |"
              for s in summaries]
    breakdown = ["| Setting | Primer | Long-term summary | Short-term window | Episodic facts | "
                 "Upkeep prompt tokens/turn | Rows using estimate |", "|---|---|---|---|---|---|---|"]
    breakdown += [f"| {s['name']} | {s['mean_primer_tokens_est']} | {s['mean_summary_tokens_est']} | "
                  f"{s['mean_window_tokens_est']} | {s['mean_episodic_tokens_est']} | {s['mean_aux_prompt_tokens']} | "
                  f"{s['rows_using_estimate']}/{s['turns']} |" for s in summaries]

    by = {s["setting"]: s for s in summaries}
    policy_lines = []
    if "n12" in by and "compress" in by:
        base, comp = by["n12"], by["compress"]
        saved = base["mean_prompt_tokens"] - comp["mean_prompt_tokens"]
        pct = 100 * saved / base["mean_prompt_tokens"] if base["mean_prompt_tokens"] else 0
        dq = (None if base["probe_mean"] is None or comp["probe_mean"] is None
              else round(comp["probe_mean"] - base["probe_mean"], 2))
        policy_lines = ["| Baseline | Policy | Prompt tokens/turn saved | Saving | Probe quality change |",
                        "|---|---|---|---|---|",
                        f"| {base['name']} ({base['mean_prompt_tokens']}) | {comp['name']} "
                        f"({comp['mean_prompt_tokens']}) | {round(saved, 1)} | {pct:.1f}% | {fmt(dq)} |"]
        if "n30" in by:
            s30 = by["n30"]["mean_prompt_tokens"]
            pct30 = 100 * (s30 - comp["mean_prompt_tokens"]) / s30 if s30 else 0
            policy_lines.append(f"\nAgainst SHORT_TERM_N=30 the policy saves {pct30:.1f}% of prompt tokens per turn.")

    best, worst, rule = pick_best_worst(summaries)
    cost_rows = []
    cost_md = ["| Case | Setting | Input tokens/turn | Output tokens/turn | Cost, reply only | Cost, with upkeep |",
               "|---|---|---|---|---|---|"]
    for case, s in (("Best", best), ("Worst", worst)):
        tin = round(s["mean_prompt_tokens"] + s["mean_aux_prompt_tokens"], 1)
        tout = round(s["mean_completion_tokens"] + s["mean_aux_completion_tokens"], 1)
        cost_md.append(f"| {case} | {s['name']} | {s['mean_prompt_tokens']} (+{s['mean_aux_prompt_tokens']} upkeep) | "
                       f"{s['mean_completion_tokens']} (+{s['mean_aux_completion_tokens']} upkeep) | "
                       f"${s['cost_reply_only']:,.2f} | ${s['cost_with_upkeep']:,.2f} |")
        cost_rows.append({"case": case, **s, "input_tokens_per_turn_with_upkeep": tin,
                          "output_tokens_per_turn_with_upkeep": tout})
    cost_md.append(f"\nSelection rule: {rule}. Price: ${INPUT_PER_M}/M input, ${OUTPUT_PER_M}/M output; "
                   f"{CONVERSATIONS:,} conversations x {TURNS} turns.")

    print("\n".join(table), "\n")
    print("\n".join(breakdown), "\n")
    print("\n".join(policy_lines), "\n")
    print("\n".join(cost_md))

    write_json(RAW / "memory_summary.json", {"settings": summaries, "best": best["setting"], "worst": worst["setting"],
                                             "rule": rule})
    write_csv(RAW / "memory_cost.csv", cost_rows)
    fill_metrics_section("memory-table", "\n".join(table))
    fill_metrics_section("token-breakdown", "\n".join(breakdown))
    fill_metrics_section("policy-table", "\n".join(policy_lines) or "_compress and n12 runs needed_")
    fill_metrics_section("cost-table", "\n".join(cost_md))
    print(f"\nWrote {RAW / 'memory_summary.json'}, {RAW / 'memory_cost.csv'} and updated METRICS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
