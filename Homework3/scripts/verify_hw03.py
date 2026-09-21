#!/usr/bin/env python3
"""Homework 3 self-check.

Runs a mix of always-checkable structural checks (required files exist, the
Python compiles, questions.yaml is well-formed) and post-experiment checks
(raw/ retrieval output and computed metrics exist). The post-experiment
checks will legitimately fail (not error) until you have run
rag/run_experiments.py and rag/compute_metrics.py yourself - that is
expected before you have real data, and the script reports it plainly
instead of pretending those results exist.

Usage:
    python3 scripts/verify_hw03.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"

REQUIRED_FILES = [
    ROOT / "config.py",
    ROOT / "main.py",
    ROOT / "routers" / "auth.py",
    ROOT / "templates" / "index.html",
    ROOT / "templates" / "login.html",
    ROOT / "templates" / "dashboard.html",
    ROOT / "rag" / "pipelines.py",
    ROOT / "rag" / "run_experiments.py",
    ROOT / "rag" / "compute_metrics.py",
    ROOT / "rag" / "corpus_prep.py",
    ROOT / "rag" / "build_manifest.py",
    REPORT_DIR / "questions.yaml",
    REPORT_DIR / "SOURCES.md",
    REPORT_DIR / "METRICS.md",
    REPORT_DIR / "RUN_LOG.txt",
    REPORT_DIR / "report_template.md",
    REPORT_DIR / "AI_USE.md",
]

REQUIRED_TECHNIQUES = ["token", "semantic", "sentence_window"]


def record(name: str, passed: bool, details: str = "") -> Dict[str, Any]:
    return {"check": name, "passed": passed, "details": details}


def check_required_files() -> tuple[bool, str]:
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        return False, f"Missing files: {missing}"
    return True, "All required files exist."


def run_py_compile() -> tuple[bool, str]:
    files = [
        "config.py",
        "main.py",
        "routers/auth.py",
        "rag/pipelines.py",
        "rag/run_experiments.py",
        "rag/compute_metrics.py",
        "rag/corpus_prep.py",
        "rag/build_manifest.py",
        "scripts/verify_hw03.py",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", *files],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True, "Python compilation succeeded."
    return False, result.stderr.strip() or result.stdout.strip()


def check_config_values() -> tuple[bool, str]:
    sys.path.insert(0, str(ROOT))
    import config  # noqa: E402

    if config.PORT_BASE != 8000 + (config.SID4 % 900):
        return False, "PORT_BASE does not match 8000 + (SID4 mod 900)."
    if config.PREFIX != f"s{config.SID4}":
        return False, "PREFIX does not match 's' + SID4."
    if config.VERIFY_SEED != 260000 + config.SID4:
        return False, "VERIFY_SEED does not match 260000 + SID4."
    if config.DOMAIN_ID != config.SID4 % 8:
        return False, "DOMAIN_ID does not match SID4 mod 8."
    return True, "Derived configuration values are internally consistent."


def check_questions_yaml() -> tuple[bool, str]:
    import yaml

    data = yaml.safe_load((REPORT_DIR / "questions.yaml").read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    if len(questions) != 5:
        return False, f"Expected 5 questions, found {len(questions)}."

    required_keys = {"id", "question", "expected_answer", "expected_source_file", "single_source"}
    for q in questions:
        if not required_keys.issubset(q.keys()):
            return False, f"Question {q.get('id')} is missing one of {required_keys}."

    single_source_count = sum(1 for q in questions if q["single_source"])
    if single_source_count < 2:
        return False, f"Expected at least 2 single-source questions, found {single_source_count}."
    return True, "questions.yaml has 5 well-formed questions, 2+ single-source."


def check_raw_results() -> tuple[bool, str]:
    missing = [t for t in REQUIRED_TECHNIQUES if not (RAW_DIR / f"{t}.jsonl").exists()]
    if missing:
        return False, f"TODO_RUN_MANUALLY: raw/ is missing results for: {missing}. Run rag/run_experiments.py."
    return True, "raw/ contains per-technique retrieval results for all three techniques."


def check_summary_metrics() -> tuple[bool, str]:
    path = RAW_DIR / "summary_metrics.json"
    if not path.exists():
        return False, "TODO_RUN_MANUALLY: raw/summary_metrics.json missing. Run rag/compute_metrics.py."
    return True, "raw/summary_metrics.json exists."


def check_corpus_manifest() -> tuple[bool, str]:
    path = REPORT_DIR / "CORPUS_MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("total_bytes") in (None, 0) or not manifest.get("files"):
        return False, "TODO_RUN_MANUALLY: CORPUS_MANIFEST.json is still a placeholder. Run rag/build_manifest.py."
    if manifest["total_bytes"] < 200_000:
        return False, f"Corpus is only {manifest['total_bytes']} bytes; the assignment requires >= 200 KB."
    return True, f"Corpus manifest lists {manifest['total_bytes']} bytes across {len(manifest['files'])} files."


def main() -> int:
    checks = [
        ("required_files", check_required_files),
        ("py_compile", run_py_compile),
        ("config_values", check_config_values),
        ("questions_yaml", check_questions_yaml),
        ("raw_results", check_raw_results),
        ("summary_metrics", check_summary_metrics),
        ("corpus_manifest", check_corpus_manifest),
    ]

    results: List[Dict[str, Any]] = []
    for name, fn in checks:
        try:
            passed, details = fn()
        except Exception as exc:  # surfaced in JSON rather than crashing the script
            passed, details = False, f"{type(exc).__name__}: {exc}"
        results.append(record(name, passed, details))

    overall = all(r["passed"] for r in results)
    payload = {
        "homework": 3,
        "commit_hash": os.getenv("COMMIT_HASH", "local-uncommitted"),
        "checks": results,
        "passed": overall,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "verification.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
