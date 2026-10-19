#!/usr/bin/env python3
"""HW6 Part 3: score the probe answers with the 1-5 rubric in Homework6/memory_probes.yaml.

Scoring is keyword based and deterministic, so anyone can re-run it and get the
same numbers (rules are in the YAML header). It reads every
reports/hw06/raw/probe_answers_<setting>.json and writes
reports/hw06/raw/probe_scores.csv and probe_scores.json.

Usage (repo root):
    python Homework6/scripts/score_probes.py
"""

from __future__ import annotations

import json
import sys

import yaml

from hw6_common import PROBES_YAML, RAW, SETTING_NAMES, SETTINGS, banner, write_csv, write_json


def normalize(text: str) -> str:
    return " ".join((text or "").lower().replace(",", "").split())


def score_answer(answer: str, probe: dict) -> tuple[int, str]:
    """Return (score 1-5, reason) for one answer."""
    text = normalize(answer)
    criteria = probe["criteria"]
    met = [any(normalize(str(k)) in text for k in group) for group in criteria]
    frac = sum(met) / len(criteria)
    if frac == 1:
        score = 5
    elif frac >= 2 / 3:
        score = 4
    elif frac >= 1 / 3:
        score = 3
    else:
        score = 1
    reason = f"{sum(met)}/{len(criteria)} criteria met"
    stale = [s for s in probe.get("stale", []) if normalize(str(s)) in text]
    if stale and not all(met):  # rubric 2: only an outdated value was recalled
        score = 2
        reason += f"; outdated value {stale} recalled"
    return score, reason


def main() -> int:
    banner("Part 3 probe scoring (memory_probes.yaml rubric)")
    probes = {p["id"]: p for p in yaml.safe_load(PROBES_YAML.read_text(encoding="utf-8"))["probes"]}
    rows = []
    for label in SETTINGS:
        path = RAW / f"probe_answers_{label}.json"
        if not path.exists():
            print(f"(skip {label}: {path.name} not found - run run_memory_experiments.py first)")
            continue
        for a in json.loads(path.read_text(encoding="utf-8")):
            score, reason = score_answer(a["answer"], probes[a["probe_id"]])
            rows.append({"setting": label, "run_id": a["run_id"], "probe_id": a["probe_id"], "score": score,
                         "reason": reason, "expected": a["expected"], "answer": a["answer"]})
    if not rows:
        print("No probe answers found.")
        return 1

    write_csv(RAW / "probe_scores.csv", rows)
    summary = {}
    print(f"\n{'setting':<62} {'probe scores':<18} mean")
    for label in SETTINGS:
        scores = [r["score"] for r in rows if r["setting"] == label]
        if scores:
            summary[label] = {"scores": scores, "mean": round(sum(scores) / len(scores), 2)}
            print(f"{SETTING_NAMES[label]:<62} {str(scores):<18} {summary[label]['mean']}")
    write_json(RAW / "probe_scores.json", {"per_answer": rows, "per_setting": summary})
    print(f"\nWrote {RAW / 'probe_scores.csv'} and {RAW / 'probe_scores.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
