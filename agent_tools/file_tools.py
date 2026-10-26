"""HW7 Part 6: six file tools for an agent, all bound to one sandbox directory.

FileTools(root) gives read_file, write_file, edit_file, glob_files, search_in_files and bash.
Every path is resolved inside `root`; a path that would escape it (../../etc/passwd, an absolute
path elsewhere, a symlink out) is refused. bash only runs after safety_gate.confirm_bash allows it,
with cwd=root and a timeout. Every tool returns the same shape as the Part 4 tools:
{"success": bool, "data": ..., "error": str | None, "source": str, "ts": str}.
"""

from __future__ import annotations

import difflib
import fnmatch
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .safety_gate import confirm_bash


def _result(success: bool, data=None, error: str | None = None, source: str = "") -> dict:
    return {
        "success": success,
        "data": data,
        "error": error,
        "source": source,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class FileTools:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"sandbox root {self.root} is not a directory")

    def _path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError(f"path {rel!r} is outside the sandbox")
        return p

    def _rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def read_file(self, path: str, max_lines: int | None = None) -> dict:
        """Read a text file; max_lines keeps only the first N lines."""
        try:
            p = self._path(path)
            lines = p.read_text(encoding="utf-8").splitlines()
            shown = lines if max_lines is None else lines[: max(0, int(max_lines))]
            return _result(
                True,
                {
                    "path": self._rel(p),
                    "content": "\n".join(shown),
                    "lines_returned": len(shown),
                    "total_lines": len(lines),
                    "truncated": len(shown) < len(lines),
                },
                source=self._rel(p),
            )
        except (OSError, PermissionError, ValueError) as exc:
            return _result(False, error=f"read_file failed: {exc}", source=path)

    def write_file(self, path: str, content: str) -> dict:
        """Create or overwrite a text file inside the sandbox."""
        try:
            p = self._path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return _result(True, {"path": self._rel(p), "bytes": len(content.encode("utf-8"))}, source=self._rel(p))
        except (OSError, PermissionError) as exc:
            return _result(False, error=f"write_file failed: {exc}", source=path)

    def edit_file(self, path: str, old: str, new: str) -> dict:
        """Replace exactly one occurrence of `old` with `new` and return a short unified diff."""
        try:
            p = self._path(path)
            before = p.read_text(encoding="utf-8")
            count = before.count(old)
            if count != 1:
                return _result(
                    False,
                    error=f"edit_file: expected exactly 1 match of the old text, found {count}",
                    source=self._rel(p),
                )
            after = before.replace(old, new, 1)
            p.write_text(after, encoding="utf-8")
            diff = "".join(
                difflib.unified_diff(
                    before.splitlines(True), after.splitlines(True), f"a/{self._rel(p)}", f"b/{self._rel(p)}", n=1
                )
            )
            return _result(True, {"path": self._rel(p), "diff": diff}, source=self._rel(p))
        except (OSError, PermissionError) as exc:
            return _result(False, error=f"edit_file failed: {exc}", source=path)

    def glob_files(self, pattern: str) -> dict:
        """List files matching a glob pattern (relative to the sandbox), sorted."""
        if pattern.startswith("/") or ".." in Path(pattern).parts:
            return _result(False, error="glob_files: pattern must stay inside the sandbox", source=pattern)
        files = sorted(self._rel(p) for p in self.root.glob(pattern) if p.is_file())
        return _result(True, {"pattern": pattern, "files": files, "count": len(files)}, source=str(self.root))

    def search_in_files(self, query: str, file_pattern: str = "*") -> dict:
        """Find lines containing `query` in files whose name matches file_pattern (e.g. '*.py')."""
        hits = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and fnmatch.fnmatch(p.name, file_pattern):
                try:
                    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                        if query in line:
                            hits.append({"path": self._rel(p), "line": n, "text": line.strip()})
                except (OSError, UnicodeDecodeError):
                    continue
        return _result(
            True,
            {"query": query, "file_pattern": file_pattern, "matches": hits, "count": len(hits)},
            source=str(self.root),
        )

    def bash(self, command: str, auto_approve: bool = False, timeout_s: float = 10.0) -> dict:
        """Run a shell command in the sandbox only if the safety gate allows it."""
        gate = confirm_bash(command, auto_approve=auto_approve)
        if not gate["allowed"]:
            return _result(False, {"gate": gate}, error=f"blocked by safety gate: {gate['reason']}", source=command)
        try:
            p = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return _result(False, {"gate": gate}, error=f"timed out after {timeout_s} s", source=command)
        return _result(
            p.returncode == 0,
            {"gate": gate, "returncode": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]},
            error=None if p.returncode == 0 else f"exit code {p.returncode}",
            source=command,
        )
