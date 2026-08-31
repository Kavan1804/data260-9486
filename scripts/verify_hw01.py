#!/usr/bin/env python3
"""Homework 1 self-check."""

from __future__ import annotations

import csv
import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw01"
RAW_DIR = REPORT_DIR / "raw"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"

REQUIRED_FILES = [
    ROOT / "AGENT.md",
    ROOT / "hw1_client.py",
    ROOT / "agents_demo.py",
    ROOT / "DOMAIN_SCHEMA.md",
    ROOT / "Dockerfile",
    ROOT / "src" / "model_client.py",
    ROOT / "scripts" / "run_nondeterminism.py",
    ROOT / "scripts" / "verify_hw01.py",
    REPORT_DIR / "report.md",
    REPORT_DIR / "report.css",
    REPORT_DIR / "AI_USE.md",
    REPORT_DIR / "METRICS.md",
]

REQUIRED_SCREENSHOTS = [
    "part1_localhost_app.png",
    "part1_invalid_description_alert.png",
    "part1_missing_terms_alert.png",
    "part1_docker_localhost.png",
    "part1_docker_container.png",
    "part1_ecs_public_ip.png",
    "part2_planner_reviewer.png",
    "part2_finalized_output.png",
    "part3_metrics.png",
    "part4_stats_turn3.png",
    "part4_stats_turn5.png",
]

EXPECTED_CASE = {
    "title": "Two-Bedroom Apartment Near SJSU",
    "content": (
        "A furnished two-bedroom apartment with in-unit laundry, secure parking, "
        "and convenient access to public transit is available near the San Jose "
        "State University campus."
    ),
    "email": "kavan.siddeshkumar@sjsu.edu",
}

EXPECTED_METRICS = {
    "0.0": {
        "runs": 20,
        "distinct_tag_sets": 1,
        "tags_in_all_runs": [
            "furnished two-bedroom",
            "secure parking",
            "two-bedroom apartment near sjsu",
        ],
        "tags_in_exactly_one_run": [],
        "latency_ms": {
            "p50": 74523.73,
            "p95": 103968.01,
            "p99": 120482.96,
        },
    },
    "0.7": {
        "runs": 20,
        "distinct_tag_sets": 3,
        "tags_in_all_runs": ["furnished two-bedroom"],
        "tags_in_exactly_one_run": ["convenient access"],
        "latency_ms": {
            "p50": 80115.68,
            "p95": 91286.90,
            "p99": 96006.23,
        },
    },
}


def record(name: str, passed: bool, details: str = "") -> Dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def parse_publish_package(text: str) -> Dict[str, Any]:
    marker = " Publish Package "
    position = text.rfind(marker)
    if position == -1:
        raise ValueError("Publish Package block not found")
    payload = text[position + len(marker):].strip()
    return json.loads(payload)


def run_py_compile() -> tuple[bool, str]:
    files = [
        "agents_demo.py",
        "hw1_client.py",
        "src/model_client.py",
        "scripts/run_nondeterminism.py",
    ]
    command = [sys.executable, "-m", "py_compile", *files]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True, "Python compilation succeeded."
    return False, result.stderr.strip() or result.stdout.strip()


def check_required_files() -> tuple[bool, str]:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.exists()]
    if missing:
        return False, f"Missing files: {missing}"
    return True, "All required files exist."


def check_agent_prompt() -> tuple[bool, str]:
    text = (ROOT / "AGENT.md").read_text(encoding="utf-8")
    required_phrases = [
        "Respond using bullet points only.",
        "Begin every non-empty line with \"- \".",
        "Do not use headings.",
        "If no problems are found, return one bullet stating that no significant issues were found.",
    ]
    if not text.strip():
        return False, "AGENT.md is empty."
    if not all(phrase in text for phrase in required_phrases):
        return False, "AGENT.md is missing the strict bullet-only review requirements."
    return True, "AGENT.md requires bullet-only review responses."


def check_adapter_interface() -> tuple[bool, str]:
    model_text = (ROOT / "src" / "model_client.py").read_text(encoding="utf-8")
    tree = ast.parse(model_text)
    model_class = next(
        (
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ModelClient"
        ),
        None,
    )
    if model_class is None:
        return False, "ModelClient class was not found in src/model_client.py."

    complete_method = next(
        (
            node for node in model_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "complete"
        ),
        None,
    )
    if complete_method is None:
        return False, "ModelClient.complete was not found."

    args = complete_method.args
    arg_names = [arg.arg for arg in args.args]
    if arg_names[:3] != ["self", "messages", "tools"]:
        return False, "ModelClient.complete should accept self, messages, and tools."
    if not args.defaults or not isinstance(args.defaults[-1], ast.Constant) or args.defaults[-1].value is not None:
        return False, "ModelClient.complete should default tools=None."

    hw1_client_text = (ROOT / "hw1_client.py").read_text(encoding="utf-8")
    if "from src.model_client import ModelClient" not in hw1_client_text:
        return False, "hw1_client.py does not import the shared adapter."
    return True, "Adapter interface and client import look correct."


def check_fixed_input() -> tuple[bool, str]:
    case = json.loads((REPORT_DIR / "cases" / "nondeterminism_input.json").read_text(encoding="utf-8"))
    if case != EXPECTED_CASE:
        return False, "The fixed nondeterminism input does not match the expected rental case."
    return True, "Fixed nondeterminism input matches the expected case."


def check_raw_runs() -> tuple[bool, str]:
    runs = json.loads((RAW_DIR / "nondeterminism_runs.json").read_text(encoding="utf-8"))
    if len(runs) != 40:
        return False, f"Expected 40 runs, found {len(runs)}."

    counts = Counter(str(run["temperature"]) for run in runs)
    if counts.get("0.0", 0) != 20 or counts.get("0.7", 0) != 20:
        return False, f"Expected 20 runs per temperature, found {dict(counts)}."

    with (RAW_DIR / "nondeterminism_runs.csv").open(encoding="utf-8") as file:
        csv_rows = list(csv.DictReader(file))
    if len(csv_rows) != 40:
        return False, f"Expected 40 CSV rows, found {len(csv_rows)}."
    return True, "Raw nondeterminism results contain 40 records split 20/20."


def check_metrics() -> tuple[bool, str]:
    metrics = json.loads((RAW_DIR / "nondeterminism_metrics.json").read_text(encoding="utf-8"))
    if metrics != EXPECTED_METRICS:
        return False, "Nondeterminism metrics do not match the preserved expected values."
    return True, "Nondeterminism metrics match the expected values."


def check_part2_evidence() -> tuple[bool, str]:
    for name in ("agent_demo_part2.txt", "agent_demo_final.txt"):
        package = parse_publish_package((RAW_DIR / name).read_text(encoding="utf-8"))
        final = package["agents"]["final"]
        tags = final.get("tags", [])
        summary = final.get("summary", "")
        if len(tags) != 3:
            return False, f"{name} does not contain exactly three final tags."
        if len(summary.split()) > 25:
            return False, f"{name} final summary exceeds 25 words."
    return True, "Part 2 evidence contains three tags and a <=25 word summary."


def check_screenshots() -> tuple[bool, str]:
    missing = [
        name for name in REQUIRED_SCREENSHOTS
        if not (SCREENSHOT_DIR / name).exists()
    ]
    if missing:
        return False, f"Missing screenshots: {missing}"

    leftover = sorted(
        path.name for path in SCREENSHOT_DIR.glob("Screenshot *.png")
    )
    if leftover:
        return False, f"Renamed screenshot cleanup incomplete: {leftover}"
    return True, "Required screenshots are present and renamed."


def check_report_artifacts() -> tuple[bool, str]:
    pdf = REPORT_DIR / "report.pdf"
    md = REPORT_DIR / "report.md"
    if not md.exists():
        return False, "report.md is missing."
    if not pdf.exists():
        return False, "report.pdf is missing."
    return True, "Report source and PDF both exist."


def main() -> int:
    checks = [
        ("required_files", check_required_files),
        ("agent_prompt", check_agent_prompt),
        ("adapter_interface", check_adapter_interface),
        ("fixed_input", check_fixed_input),
        ("raw_runs", check_raw_runs),
        ("metrics", check_metrics),
        ("part2_evidence", check_part2_evidence),
        ("screenshots", check_screenshots),
        ("py_compile", run_py_compile),
        ("report_artifacts", check_report_artifacts),
    ]

    results: List[Dict[str, Any]] = []
    for name, fn in checks:
        try:
            passed, details = fn()
        except Exception as exc:  # pragma: no cover - surfaced in JSON
            passed, details = False, f"{type(exc).__name__}: {exc}"
        results.append(record(name, passed, details))

    overall = all(result["passed"] for result in results)
    output = {
        "overall_pass": overall,
        "checks": results,
    }
    (REPORT_DIR / "verification.json").write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
