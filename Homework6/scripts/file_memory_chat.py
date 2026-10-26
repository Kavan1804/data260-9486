#!/usr/bin/env python3
"""HW6 Part 4: terminal chat that uses file-based memory (AGENT.md + MEMORY.md).

Both files are loaded into the system prompt on every turn; the model is the
local Ollama model through the HW5 adapter. Commands: /memory /compact /dream /help.

Usage (repo root):
    python Homework6/scripts/file_memory_chat.py                      # interactive
    python Homework6/scripts/file_memory_chat.py --script "I prefer Santa Clara" "/dream" "/memory"
    python Homework6/scripts/file_memory_chat.py --memory-path /tmp/MEMORY.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hw6_common import banner

import config
from backend.app import file_memory
from backend.app.memory_logic import SYSTEM_PRIMER, default_model


def run_turn(text: str, history: list[dict], model, memory_path: Path) -> str:
    if file_memory.is_command(text):
        return file_memory.handle_command(text, model, history[-16:], path=memory_path)["reply"]
    system = file_memory.build_system_prompt(
        SYSTEM_PRIMER, file_memory.load_agent_md(), file_memory.load_memory_md(memory_path)
    )
    reply = model.chat([{"role": "system", "content": system}, *history[-12:], {"role": "user", "content": text}], [])
    answer = (reply.get("content") or "").strip()
    history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
    return answer


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-path", type=Path, default=config.MEMORY_MD)
    ap.add_argument("--script", nargs="*", help="messages/commands to send in order instead of typing them")
    args = ap.parse_args()

    banner(f"Part 4 file-memory chat (model {config.OLLAMA_MODEL}, memory {args.memory_path.name})")
    text = file_memory.load_memory_md(args.memory_path)
    due, reasons = file_memory.needs_consolidation(text)
    print(
        f"AGENT.md: {file_memory.count_memory_lines(file_memory.load_agent_md())} lines | "
        f"{args.memory_path.name}: {file_memory.count_memory_lines(text)} lines | "
        f"consolidation due: {'yes - ' + '; '.join(reasons) if due else 'no'}"
    )
    print("Type /help for commands, /quit to exit.\n", flush=True)

    model = default_model()
    history: list[dict] = []
    inputs = iter(args.script) if args.script else None
    while True:
        try:
            text = next(inputs) if inputs else input("you> ")
        except (StopIteration, EOFError, KeyboardInterrupt):
            break
        text = text.strip()
        if not text:
            continue
        if text in ("/quit", "/exit"):
            break
        if inputs:
            print(f"you> {text}")
        print(f"assistant> {run_turn(text, history, model, args.memory_path)}\n", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
