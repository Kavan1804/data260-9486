#!/usr/bin/env python3
"""HW6 Part 4.4: check AGENT.md itself, then check that a function follows it.

1. AGENT.md has >= 5 numbered instructions in >= 3 of the required categories.
2. A function is checked against the machine-checkable AGENT.md rules:
     R6 type hints on every parameter and the return value
     R7 docstring on a public function
     R8 lines <= 120 characters
     R9 no hard-coded host/port/URL/credential strings
     R10 no print() calls
     R13 no LangChain / OpenAI / Flask / Redis imports in the module
   Default target: backend/app/file_memory.py::count_memory_lines (implemented for HW6
   following AGENT.md).
   --generate asks the local Ollama model (AGENT.md in the system prompt) to write
   days_until_available(); the code is saved, checked against the same rules, and - only
   if it imports nothing but datetime and calls no file/OS/eval functions - run on 4 cases.

Usage (repo root):
    python Homework6/scripts/agent_md_check.py
    python Homework6/scripts/agent_md_check.py --generate
Writes reports/hw06/raw/agent_md_check.json (and generated_function.py with --generate).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from datetime import date, datetime

from hw6_common import RAW, ROOT, banner, write_json

import config

CATEGORIES = ["Project description", "Technology stack", "Coding conventions", "Testing approach",
              "Prohibited actions"]
BANNED_MODULES = ("langchain", "openai", "flask", "redis")
HARDCODED = re.compile(r"localhost|127\.0\.0\.1|https?://|mongodb://|\b8486\b|\b27017\b|password|api[_-]?key", re.I)
UNSAFE_CALLS = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "getattr", "setattr"}

GENERATE_TASK = (
    "Write one Python function `days_until_available(available_from, today)` for this project. "
    "available_from is a datetime (the move-in date of a listing document) and today is a date. "
    "Return how many whole days remain until available_from's date, or 0 if it is today or already past. "
    "Use only the datetime module. Reply with a single ```python code block and nothing else."
)
GENERATE_CASES = [
    ((datetime(2026, 11, 1, 9, 0), date(2026, 10, 18)), 14),
    ((datetime(2026, 10, 18, 23, 0), date(2026, 10, 18)), 0),
    ((datetime(2026, 9, 1), date(2026, 10, 18)), 0),
    ((datetime(2027, 1, 15), date(2026, 12, 31)), 15),
]


def agent_md_summary(text: str) -> dict:
    """Count numbered instructions under each '## heading' of AGENT.md."""
    counts: dict[str, int] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            counts.setdefault(current, 0)
        elif current and re.match(r"^\d+\.\s", line):
            counts[current] += 1
    covered = [c for c in CATEGORIES if counts.get(c, 0) > 0]
    total = sum(counts.values())
    return {"instructions_per_section": counts, "total_instructions": total, "required_categories_covered": covered,
            "passed": total >= 5 and len(covered) >= 3}


def check_function(source: str, name: str) -> list[dict]:
    """Check one function in `source` against the AGENT.md rules R6-R10 and R13."""
    tree = ast.parse(source)
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)
    if fn is None:
        return [{"rule": "exists", "passed": False, "details": f"function {name} not found"}]
    fn_src = ast.get_source_segment(source, fn) or ""
    args = [a for a in fn.args.args + fn.args.kwonlyargs if a.arg not in ("self", "cls")]
    unannotated = [a.arg for a in args if a.annotation is None]
    long_lines = [i + 1 for i, line in enumerate(fn_src.splitlines()) if len(line) > 120]
    strings = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    hardcoded = [s for s in strings if HARDCODED.search(s) and s != ast.get_docstring(fn)]
    prints = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print"]
    imported = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    imported += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    banned = [m for m in imported if m.split(".")[0].lower() in BANNED_MODULES]
    checks = [
        ("R6_type_hints", not unannotated and fn.returns is not None,
         f"unannotated params: {unannotated}; return annotated: {fn.returns is not None}"),
        ("R7_docstring", name.startswith("_") or bool(ast.get_docstring(fn)), f"docstring: {ast.get_docstring(fn)!r}"),
        ("R8_line_length", not long_lines, f"lines > 120 chars: {long_lines}"),
        ("R9_no_hardcoded_config", not hardcoded, f"suspicious strings: {hardcoded}"),
        ("R10_no_print", not prints, f"print() at lines: {prints}"),
        ("R13_no_banned_imports", not banned, f"banned imports: {banned}"),
    ]
    return [{"rule": r, "passed": bool(p), "details": d} for r, p, d in checks]


def safe_to_run(source: str) -> tuple[bool, str]:
    """Only run generated code that imports datetime alone and calls no file/OS/eval builtins."""
    tree = ast.parse(source)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name != "datetime" for a in n.names):
            return False, f"imports {[a.name for a in n.names]}"
        if isinstance(n, ast.ImportFrom) and n.module != "datetime":
            return False, f"imports from {n.module}"
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) in UNSAFE_CALLS:
            return False, f"calls {n.func.id}()"
        if isinstance(n, ast.Attribute) and n.attr.startswith("__"):
            return False, f"uses {n.attr}"
    return True, "datetime only"


def extract_code(reply: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", reply, re.S)
    return (m.group(1) if m else reply).strip() + "\n"


def generate(model) -> dict:
    from backend.app import file_memory

    system = file_memory.build_system_prompt("You write Python code for this project and follow its instructions.",
                                             file_memory.load_agent_md(), "")
    reply = model.chat([{"role": "system", "content": system}, {"role": "user", "content": GENERATE_TASK}], [])
    code = extract_code(reply.get("content") or "")
    out = RAW / "generated_function.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"# Generated by {getattr(model, 'name', 'model')} with AGENT.md in the system prompt "
                   f"(Homework6/scripts/agent_md_check.py --generate). Not imported by the app.\n{code}",
                   encoding="utf-8")
    result = {"model": getattr(model, "name", None), "file": str(out), "code": code}
    try:
        result["rules"] = check_function(code, "days_until_available")
    except SyntaxError as exc:
        result["rules"] = [{"rule": "parses", "passed": False, "details": str(exc)}]
        return result
    ok, why = safe_to_run(code)
    result["safe_to_run"] = {"passed": ok, "details": why}
    if ok:
        namespace: dict = {}
        exec(compile(code, str(out), "exec"), namespace)  # noqa: S102 - checked by safe_to_run above
        fn = namespace.get("days_until_available")
        cases = []
        for args, expected in GENERATE_CASES:
            try:
                got = fn(*args)
            except Exception as exc:  # noqa: BLE001
                got = f"{type(exc).__name__}: {exc}"
            cases.append({"args": [str(a) for a in args], "expected": expected, "got": got, "passed": got == expected})
        result["behavior"] = cases
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="also ask the local model to generate a function")
    args = ap.parse_args()
    banner("Part 4 AGENT.md instructions + function compliance check")

    summary = agent_md_summary(config.AGENT_MD.read_text(encoding="utf-8"))
    print(f"AGENT.md: {summary['total_instructions']} numbered instructions; per section: "
          f"{summary['instructions_per_section']}")
    print(f"[{'PASS' if summary['passed'] else 'FAIL'}] >= 5 instructions in >= 3 required categories "
          f"(covered: {summary['required_categories_covered']})\n")

    target = ROOT / "backend" / "app" / "file_memory.py"
    implemented = check_function(target.read_text(encoding="utf-8"), "count_memory_lines")
    print(f"Implemented function: {target.relative_to(ROOT)}::count_memory_lines")
    for c in implemented:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['rule']}: {c['details']}")
    result = {"agent_md": summary, "implemented_function": {"target": f"{target.relative_to(ROOT)}::count_memory_lines",
                                                            "rules": implemented}}
    ok = summary["passed"] and all(c["passed"] for c in implemented)

    if args.generate:
        from backend.app.memory_logic import default_model

        gen = generate(default_model())
        print(f"\nGenerated function ({gen['model']}) saved to {gen['file']}:\n{gen['code']}")
        for c in gen["rules"]:
            print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['rule']}: {c['details']}")
        if "safe_to_run" in gen:
            print(f"  safe to run: {gen['safe_to_run']}")
        for case in gen.get("behavior", []):
            print(f"  [{'PASS' if case['passed'] else 'FAIL'}] days_until_available{tuple(case['args'])} -> "
                  f"{case['got']} (expected {case['expected']})")
        result["generated_function"] = gen

    write_json(RAW / "agent_md_check.json", result)
    print(f"\nWrote {RAW / 'agent_md_check.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
