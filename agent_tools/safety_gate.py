"""HW7 Part 6: safety gate for the bash tool (pure Python, testable without a model).

Contract:
  is_destructive(command) -> bool          independent deny-list check
  destructive_reason(command) -> str | None which rule matched (for the gate's reason text)
  confirm_bash(command, auto_approve=False) -> {"allowed": bool, "reason": str}

Order of checks in confirm_bash:
  1. destructive?  -> blocked unless auto_approve=True (explicit confirmation), EVEN IF the command
                      starts with a SAFE_PREFIXES entry (e.g. "echo x > /etc/hosts", "find . -delete")
  2. every part of the command starts with a SAFE_PREFIXES entry -> allowed
  3. anything else -> blocked unless auto_approve=True
A command is split on ;, &&, ||, |, newlines and $( ) / backticks first, so "ls && rm -rf x" is judged
by its worst part.
"""

from __future__ import annotations

import re
import shlex

# Read-only or sandbox-local commands that may run without asking.
SAFE_PREFIXES = (
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "echo",
    "python3 -m py_compile",
    "git status",
    "git diff",
    "git log",
)

# Absolute paths a redirect must never write to (anything under / except these harmless ones).
_HARMLESS_ABSOLUTE = ("/dev/null", "/dev/stdout", "/dev/stderr", "/tmp/", "/private/tmp/", "/var/folders/")
_SPLIT = re.compile(r"\|\||&&|;|\||\n|`|\$\(|\)")


def _parts(command: str) -> list[str]:
    return [p.strip() for p in _SPLIT.split(command or "") if p.strip()]


def _words(part: str) -> list[str]:
    try:
        words = shlex.split(part, posix=True)
    except ValueError:  # unbalanced quotes: fall back to plain splitting
        words = part.split()
    # "\rm", "/bin/rm", "command rm", "env X=1 rm" all run rm
    words = [w.lstrip("\\") for w in words]
    while words and (words[0] in ("command", "builtin", "exec", "nohup", "time", "env") or "=" in words[0]):
        words = words[1:]
    if words:
        words[0] = words[0].rsplit("/", 1)[-1]
    return words


def _redirect_targets(part: str) -> list[str]:
    targets = re.findall(r"(?:\d?>>?|&>)\s*([^\s;&|]+)", part)
    words = _words(part)
    if words and words[0] == "tee":
        targets += [w for w in words[1:] if not w.startswith("-")]
    return [t.strip("'\"") for t in targets]


def destructive_reason(command: str) -> str | None:
    for part in _parts(command):
        words = _words(part)
        if not words:
            continue
        cmd, args = words[0].lower(), words[1:]
        flags = "".join(a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--"))
        long_flags = {a for a in args if a.startswith("--")}

        if cmd in ("sudo", "su", "doas", "pkexec"):
            return f"privilege escalation ({cmd})"
        if cmd == "rm" and ("r" in flags.lower() or "--recursive" in long_flags):
            return "recursive deletion (rm -r)"
        if cmd == "find" and ("-delete" in args or ("-exec" in args and "rm" in args)):
            return "recursive deletion (find -delete / -exec rm)"
        if cmd in ("chmod", "setfacl") or (cmd == "chflags"):
            return f"permission change ({cmd})"
        if cmd in ("chown", "chgrp"):
            return f"ownership change ({cmd})"
        if cmd.startswith(("mkfs", "newfs")) or cmd in ("fdisk", "parted", "diskutil", "wipefs"):
            return f"filesystem creation / disk formatting ({cmd})"
        if cmd == "dd" and any(a.startswith("of=/dev/") for a in args):
            return "raw-device write (dd of=/dev/...)"
        for target in _redirect_targets(part):
            if target.startswith("/dev/") and not target.startswith(_HARMLESS_ABSOLUTE):
                return f"raw-device write (redirect to {target})"
            if target.startswith("/") and not target.startswith(_HARMLESS_ABSOLUTE):
                return f"redirection to a root path ({target})"
            # Fix for the v1 false allows: ~ and $VAR expand to absolute paths, and .. climbs out of
            # the sandbox, so "cat a > ~/.bashrc" or "echo x > ../../etc/hosts" are root-path writes too.
            if target.startswith(("~", "$")) or ".." in target.replace("\\", "/").split("/"):
                return f"redirection outside the sandbox ({target})"
    return None


def is_destructive(command: str) -> bool:
    return destructive_reason(command) is not None


def _is_safe_prefix(part: str) -> bool:
    normalized = " ".join(_words(part))
    return any(normalized == p or normalized.startswith(p + " ") for p in SAFE_PREFIXES)


def confirm_bash(command: str, auto_approve: bool = False) -> dict:
    reason = destructive_reason(command)
    if reason:
        if auto_approve:
            return {"allowed": True, "reason": f"destructive ({reason}) but explicitly confirmed"}
        return {"allowed": False, "reason": f"blocked: destructive ({reason}); needs explicit confirmation"}
    parts = _parts(command)
    if parts and all(_is_safe_prefix(p) for p in parts):
        return {"allowed": True, "reason": "allowed: every part starts with a SAFE_PREFIXES entry"}
    if auto_approve:
        return {"allowed": True, "reason": "not on the allow-list, but explicitly confirmed"}
    return {"allowed": False, "reason": "blocked: not on the SAFE_PREFIXES allow-list; needs confirmation"}
