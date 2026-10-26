#!/usr/bin/env python3
"""HW7 Part 6: file tools integration test + 10-command safety-gate test (pure Python, no model).

(a) In a new temporary sandbox directory, write three small Python files, then follow the instruction
    "Find the Python file that contains DEBUG and show me its contents" with glob -> search -> read.
    edit_file and bash are also exercised once inside the same sandbox.
(b) Run the 10 fixed safety-gate commands (5 should pass, 5 should be blocked) through confirm_bash.
    One of the blocked ones is the false allow found in the first version of the gate
    (raw/safety_gate_v1_false_allows.json), so the run shows it is fixed now.
(c) Run a longer list of tricky variants as extra evidence.

The sandbox is deleted at the end. Writes reports/hw07/raw/file_tools_integration.json,
raw/safety_gate_results.csv/.json and the Part 6 table in METRICS.md.

Usage (repo root):  python Homework7/scripts/run_file_tools_demo.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile

from hw7_common import RAW, banner, fill_metrics_section, write_csv, write_json

from agent_tools.file_tools import FileTools
from agent_tools.safety_gate import SAFE_PREFIXES, confirm_bash, is_destructive

FILES = {
    "app.py": 'def greet(name):\n    return f"Hello, {name}"\n\n\nprint(greet("SJSU"))\n',
    "utils.py": "def add(a, b):\n    return a + b\n\n\ndef mean(xs):\n    return sum(xs) / len(xs)\n",
    "config_loader.py": (
        'DEBUG = True\nLOG_LEVEL = "info"\n\n\ndef load():\n    return {"debug": DEBUG, "level": LOG_LEVEL}\n'
    ),
}

GATE_TESTS = [
    # (command, expected_allowed, why it is in the test)
    ("ls -la", True, "read-only listing"),
    ("grep -n DEBUG *.py", True, "read-only search"),
    ("cat config_loader.py", True, "read a file in the sandbox"),
    ("python3 -m py_compile app.py utils.py", True, "syntax check, writes only __pycache__"),
    ("echo done > notes.txt", True, "redirect to a relative file inside the sandbox"),
    ("rm -rf build", False, "recursive deletion"),
    ("sudo ls /root", False, "privilege escalation"),
    ("chmod 777 app.py", False, "permission change"),
    ("echo pwned > /etc/hosts", False, "redirect to a root path (echo IS on SAFE_PREFIXES)"),
    ("cat app.py > ~/.bashrc", False, "write outside the sandbox (was a false allow in v1, now fixed)"),
]

EXTRA_BLOCK = [
    "rm -r -f build",
    r"\rm -fr x",
    "/bin/rm -Rf x",
    "rm --recursive x",
    "ls && rm -rf x",
    "find . -name '*.py' -delete",
    "chown root app.py",
    "dd if=/dev/zero of=/dev/disk2",
    "mkfs.ext4 /dev/sdb1",
    "cat x > /dev/disk2",
    "echo $(rm -rf ~)",
    "echo x > ../../etc/hosts",
    "echo x > $HOME/.zshrc",
    "git status; chmod -R 777 .",
]


def show(step: str, call: str, res: dict) -> None:
    print(f"[{step}] {call}")
    print(f"    success={res['success']} error={res['error']}")


def main() -> int:
    banner("Part 6 file tools (glob -> search -> read) + safety gate")
    sandbox = tempfile.mkdtemp(prefix="hw7_sandbox_s9486_")
    print(f"temporary sandbox: {sandbox}\nSAFE_PREFIXES = {SAFE_PREFIXES}\n")
    tools = FileTools(sandbox)
    integration = {"sandbox": sandbox, "steps": []}
    try:
        for name, body in FILES.items():
            r = tools.write_file(name, body)
            show("write_file", f"write_file({name!r})", r)
            integration["steps"].append({"tool": "write_file", "path": name, "result": r})

        print('\nInstruction: "Find the Python file that contains DEBUG and show me its contents."')
        g = tools.glob_files("*.py")
        show("1 glob", "glob_files('*.py')", g)
        print(f"    files: {g['data']['files']}")
        s = tools.search_in_files("DEBUG", file_pattern="*.py")
        show("2 search", "search_in_files('DEBUG', file_pattern='*.py')", s)
        for m in s["data"]["matches"]:
            print(f"    {m['path']}:{m['line']}: {m['text']}")
        target = s["data"]["matches"][0]["path"]
        rd = tools.read_file(target, max_lines=20)
        show("3 read", f"read_file({target!r}, max_lines=20)", rd)
        print("    ----- " + target + " -----")
        print("\n".join("    " + line for line in rd["data"]["content"].splitlines()))
        found_ok = target == "config_loader.py" and "DEBUG = True" in rd["data"]["content"]
        print(f"    -> found the DEBUG file: {found_ok}\n")
        integration["steps"] += [
            {"tool": "glob_files", "result": g},
            {"tool": "search_in_files", "result": s},
            {"tool": "read_file", "result": rd},
        ]

        e = tools.edit_file("config_loader.py", "DEBUG = True", "DEBUG = False")
        show("edit", "edit_file('config_loader.py', 'DEBUG = True', 'DEBUG = False')", e)
        print("    diff:\n" + "\n".join("      " + line for line in e["data"]["diff"].splitlines()))
        b = tools.bash("grep -n DEBUG config_loader.py")
        show("bash", "bash('grep -n DEBUG config_loader.py')", b)
        print(f"    stdout: {b['data']['stdout'].strip()}")
        esc = tools.read_file("../../etc/hosts")
        show("escape", "read_file('../../etc/hosts')", esc)
        integration["steps"] += [
            {"tool": "edit_file", "result": e},
            {"tool": "bash", "result": b},
            {"tool": "read_file (escape attempt)", "result": esc},
        ]
        integration["found_debug_file"] = found_ok
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        print(f"\n(sandbox {sandbox} removed)")

    print("\n10-command safety-gate test (confirm_bash, auto_approve=False):")
    rows = []
    for cmd, expect, why in GATE_TESTS:
        r = confirm_bash(cmd)
        ok = r["allowed"] == expect
        rows.append(
            {
                "set": "required",
                "command": cmd,
                "expected": "allow" if expect else "block",
                "result": "allow" if r["allowed"] else "block",
                "is_destructive": is_destructive(cmd),
                "passed": ok,
                "reason": r["reason"],
                "why": why,
            }
        )
        print(
            f"  [{'PASS' if ok else 'FAIL'}] expected {'allow' if expect else 'block':<5} got "
            f"{'allow' if r['allowed'] else 'block':<5} | {cmd:<40} | {r['reason']}"
        )
    confirmed = confirm_bash("rm -rf build", auto_approve=True)
    print(f"\n  with explicit confirmation: confirm_bash('rm -rf build', auto_approve=True) -> {confirmed}")
    v1 = json.loads((RAW / "safety_gate_v1_false_allows.json").read_text(encoding="utf-8"))
    print("\n  False allows found in v1 of the gate (raw/safety_gate_v1_false_allows.json) and their result now:")
    for item in v1["results"]:
        now = confirm_bash(item["command"])
        print(
            f"    {item['command']:<28} v1: {'allow' if item['allowed'] else 'block'} -> now: "
            f"{'allow' if now['allowed'] else 'block'} ({now['reason']})"
        )
        rows.append(
            {
                "set": "v1_false_allow",
                "command": item["command"],
                "expected": "block",
                "result": "allow" if now["allowed"] else "block",
                "is_destructive": is_destructive(item["command"]),
                "passed": not now["allowed"],
                "reason": now["reason"],
                "why": "false allow in v1, fixed",
            }
        )
    print("\n  Extra tricky variants (all should be blocked):")
    for cmd in EXTRA_BLOCK:
        r = confirm_bash(cmd)
        rows.append(
            {
                "set": "extra",
                "command": cmd,
                "expected": "block",
                "result": "allow" if r["allowed"] else "block",
                "is_destructive": is_destructive(cmd),
                "passed": not r["allowed"],
                "reason": r["reason"],
                "why": "",
            }
        )
        print(f"    [{'PASS' if not r['allowed'] else 'FAIL'}] {cmd:<32} {r['reason']}")

    req = [r for r in rows if r["set"] == "required"]
    allow_ok = sum(r["passed"] for r in req if r["expected"] == "allow")
    block_ok = sum(r["passed"] for r in req if r["expected"] == "block")
    extra = [r for r in rows if r["set"] != "required"]
    print(
        f"\nRequired tests: {sum(r['passed'] for r in req)}/10 passed ({allow_ok}/5 allowed, {block_ok}/5 blocked); "
        f"extra + v1 cases blocked: {sum(r['passed'] for r in extra)}/{len(extra)}; "
        f"integration found the DEBUG file: {integration['found_debug_file']}"
    )

    write_json(RAW / "file_tools_integration.json", integration)
    write_csv(RAW / "safety_gate_results.csv", rows)
    write_json(RAW / "safety_gate_results.json", {"confirmed_destructive_example": confirmed, "rows": rows})
    table = ["| Command | Expected | Result | Reason |", "|---|---|---|---|"]
    table += [f"| `{r['command']}` | {r['expected']} | {r['result']} | {r['reason']} |" for r in req]
    table += [
        "",
        f"Required: {sum(r['passed'] for r in req)}/10 correct. Extra tricky variants and the three v1 false "
        f"allows: {sum(r['passed'] for r in extra)}/{len(extra)} blocked. Integration test (glob -> search -> read) "
        f"found config_loader.py: {integration['found_debug_file']}.",
    ]
    fill_metrics_section("part6-table", "\n".join(table))
    return 0 if all(r["passed"] for r in rows) and integration["found_debug_file"] else 1


if __name__ == "__main__":
    sys.exit(main())
