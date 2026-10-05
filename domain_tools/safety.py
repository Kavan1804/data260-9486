"""Part 5 domain safety rule: fair housing.

The Fair Housing Act and California FEHA (in the HW3/HW4 corpus) forbid
filtering rentals by protected characteristics. execute_tool refuses any
search_listings query that tries to, e.g. "no kids" or "christians only".
"""

from __future__ import annotations

import re

SAFETY_ERROR_PREFIX = "Blocked by fair-housing safety rule"

# (protected class, pattern). Patterns target exclusionary phrasing, not ordinary
# words, so "family room" or "near church st" still search normally.
_RULES: list[tuple[str, re.Pattern]] = [
    ("familial status", re.compile(r"\b(no|without|exclude|excluding)\s+(kids|children|child|families|family|minors|babies)\b|\badults?[\s-]+only\b", re.I)),
    ("race / color / national origin", re.compile(r"\b(white|black|asian|hispanic|latino|mexican|indian|chinese|arab|immigrants?|foreigners?)s?[\s-]+(only|tenants only|renters only)\b|\bno\s+(immigrants?|foreigners?|blacks|asians|hispanics|mexicans|indians|arabs)\b|\bby\s+(race|ethnicity|nationality)\b", re.I)),
    ("religion", re.compile(r"\b(christians?|muslims?|jews?|jewish|hindus?|sikhs?|catholics?|buddhists?)[\s-]+only\b|\bno\s+(christians?|muslims?|jews|hindus?|sikhs?|catholics?)\b|\bby\s+religion\b", re.I)),
    ("disability", re.compile(r"\bno\s+(disabled|disabilities|handicapped|wheelchairs?|service animals?)\b|\b(able[\s-]+bodied)[\s-]+only\b", re.I)),
    ("sex / gender", re.compile(r"\b(men|women|males?|females?)[\s-]+only\b|\bno\s+(men|women|males|females)\b", re.I)),
    ("source of income", re.compile(r"\bno\s+(section\s*8|vouchers?|housing\s+vouchers?)\b", re.I)),
]

# Tool inputs that are free text and therefore checked.
CHECKED_FIELDS = {"search_listings": ["query"]}


def check_safety(name: str, inputs: dict) -> str | None:
    """Return an error message if the call violates the rule, else None."""
    for field in CHECKED_FIELDS.get(name, []):
        value = inputs.get(field)
        if not isinstance(value, str):
            continue
        for protected_class, pattern in _RULES:
            match = pattern.search(value)
            if match:
                return (f"{SAFETY_ERROR_PREFIX}: listing searches cannot filter on a protected "
                        f"characteristic ({protected_class}: '{match.group(0)}'). Search by location, "
                        f"title words, or available units instead.")
    return None
