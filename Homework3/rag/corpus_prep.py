"""Manual corpus download helper for the HW3 domain corpus (rental housing).

TODO_RUN_MANUALLY - fill in SOURCES below with real public document URLs for
the assigned domain (rental housing listings) before running this script.
No URLs are pre-filled here: picking and verifying real, currently-live
sources is a manual research step, not something to do automatically.
Good candidates for this domain include HUD Fair Market Rent data, a local
housing authority's tenant handbook, or the relevant state's security
deposit / rent stabilization statute text.

After filling SOURCES in, run:

    python rag/corpus_prep.py

which downloads each URL into rag/corpus/<local_filename> and prints the
byte size of each file. Afterwards, run rag/build_manifest.py to compute the
SHA-256 hashes for CORPUS_MANIFEST.json, and fill in SOURCES.md with the
same URLs plus today's access date.

The combined corpus must be at least 200 KB (see the assignment's Part 2
dataset requirement).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

SOURCES: list[tuple[str, str]] = [
    (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1950.5.&lawCode=CIV",
        "ca_civil_code_1950_5_security_deposit.txt",
    ),
    (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1946.2.&lawCode=CIV",
        "ca_tenant_protection_act_ab1482.txt",
    ),
    (
        "https://www.justice.gov/crt/fair-housing-act-1",
        "fair_housing_act.txt",
    ),
    (
        "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1946.&lawCode=CIV",
        "ca_tenant_notice_requirements.txt",
    ),
    (
        "https://www.huduser.gov/portal/datasets/fmr.html",
        "hud_fair_market_rents.txt",
    ),
]


def main():
    if not SOURCES:
        raise SystemExit(
            "SOURCES is empty. Add real (url, local_filename) pairs to "
            "rag/corpus_prep.py before running this script."
        )

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for url, filename in SOURCES:
        dest = CORPUS_DIR / filename
        print(f"Downloading {url} -> {dest}")
        urllib.request.urlretrieve(url, dest)
        size = dest.stat().st_size
        total_bytes += size
        print(f"  {size} bytes")

    print(f"\nTotal corpus size: {total_bytes} bytes ({total_bytes / 1024:.1f} KB)")
    if total_bytes < 200_000:
        print("WARNING: corpus is under the required 200 KB minimum.")


if __name__ == "__main__":
    main()
