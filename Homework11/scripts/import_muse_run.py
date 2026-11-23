#!/usr/bin/env python3
"""HW11 Parts 5-6: rebuild the Muse run from its snapshot and save the watch.py outputs the report uses.

The snapshot is restored into a temporary folder (the real ledger is never touched), then the unchanged commands
`watch.py trace`, `watch.py metrics` and a run-latency query are run on it.

Usage (repo root):  python Homework11/scripts/import_muse_run.py SNAPSHOT [--tokens N]
Writes reports/hw11/raw/{snapshot,metrics,trace_alert,runs,decisions}.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "Homework11" / "stock-watch"
RAW = ROOT / "reports" / "hw11" / "raw"
ALERT_KEY = "sec:0009999913-26-000051"  # D1: the filing that also arrives through a news story


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", type=Path)
    ap.add_argument("--tokens", type=float, help="tokens for the runs, from Muse Settings > Usage")
    args = ap.parse_args()
    print("===== Kavan Siddesh | SID4 9486 | s9486 | HW11 | Muse run import =====")
    RAW.mkdir(parents=True, exist_ok=True)
    if args.snapshot.resolve() != (RAW / "snapshot.json").resolve():
        shutil.copy(args.snapshot, RAW / "snapshot.json")
    with tempfile.TemporaryDirectory() as home:
        shutil.copy(KIT / "sources.json", home)

        def watch(*cmd: str):
            out = subprocess.run(
                [sys.executable, str(KIT / "watch.py"), "--home", home, *cmd], capture_output=True, text=True
            )
            if out.returncode:
                raise SystemExit(out.stdout + out.stderr)
            return json.loads(out.stdout)

        watch("restore", "--file", str(RAW / "snapshot.json"))
        usage = ["--usage-tokens", str(args.tokens)] if args.tokens is not None else []
        metrics = watch("metrics", "--gold", str(KIT / "golden" / "gold_hw11.json"), *usage)
        effect = hashlib.sha256(ALERT_KEY.encode()).hexdigest()[:12]
        trace = watch("trace", "--effect-id", effect)
        con = sqlite3.connect(Path(home) / "state" / "watch.db")
        con.row_factory = sqlite3.Row
        runs = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY started")]
        decisions = [
            dict(r)
            for r in con.execute(
                "SELECT i.title, l.* FROM ledger l JOIN items i ON i.effect_id = l.effect_id ORDER BY l.decided"
            )
        ]
        con.close()
    for r in runs:
        r["latency_s"] = None
        if r["finished"]:
            r["latency_s"] = (
                datetime.fromisoformat(r["finished"]) - datetime.fromisoformat(r["started"])
            ).total_seconds()
    for name, data in (("metrics", metrics), ("trace_alert", trace), ("runs", runs), ("decisions", decisions)):
        (RAW / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    for r in runs:
        print(f"run {r['run_id']} mode={r['mode']} status={r['status']} latency={r['latency_s']} s")
    print(f"trace for effect {effect}: {' -> '.join(t['step'] for t in trace)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
