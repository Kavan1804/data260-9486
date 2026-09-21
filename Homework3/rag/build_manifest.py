"""Compute reports/hw03/CORPUS_MANIFEST.json from the files in rag/corpus/.

TODO_RUN_MANUALLY - run this only after rag/corpus_prep.py (or an equivalent
manual download) has populated rag/corpus/ with the real domain corpus.
Every byte size and SHA-256 hash below is computed from the files on disk at
run time; nothing here is invented.

Usage:
    python rag/build_manifest.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "reports" / "hw03" / "CORPUS_MANIFEST.json"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    files = sorted(CORPUS_DIR.glob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt files found in {CORPUS_DIR}. Populate the corpus first.")

    entries = []
    total_bytes = 0
    for path in files:
        size = path.stat().st_size
        total_bytes += size
        entries.append({"filename": path.name, "byte_size": size, "sha256": sha256_of(path)})

    manifest = {"total_bytes": total_bytes, "files": entries}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"\nWrote {MANIFEST_PATH}")
    if total_bytes < 200_000:
        print("WARNING: corpus is under the required 200 KB minimum.")


if __name__ == "__main__":
    main()
