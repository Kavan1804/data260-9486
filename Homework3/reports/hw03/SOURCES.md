# HW3 Corpus Sources

TODO_RUN_MANUALLY: this table is a template. Fill in one row per document
after you actually download it with `rag/corpus_prep.py`, then re-run
`rag/build_manifest.py` to fill in `CORPUS_MANIFEST.json` with the real byte
sizes and SHA-256 hashes.

Domain: Rental housing listings (DOMAIN_ID 6). Suggested categories of
public source documents for this domain: HUD Fair Market Rent data, a state
or local tenant-rights statute (e.g. security deposit limits, rent increase
caps, notice-to-vacate requirements), and federal fair housing law text.
The combined corpus must total at least 200 KB.

| Local filename | Source URL | Access date |
|---|---|---|
| ca_civil_code_1950_5_security_deposit.txt | TODO_RUN_MANUALLY | TODO_RUN_MANUALLY |
| ca_tenant_protection_act_ab1482.txt | TODO_RUN_MANUALLY | TODO_RUN_MANUALLY |
| fair_housing_act.txt | TODO_RUN_MANUALLY | TODO_RUN_MANUALLY |
| hud_fair_market_rents.txt | TODO_RUN_MANUALLY | TODO_RUN_MANUALLY |
| ca_tenant_notice_requirements.txt | TODO_RUN_MANUALLY | TODO_RUN_MANUALLY |

Add or remove rows if your final corpus differs from `questions.yaml`'s
`expected_source_file` values - just keep the two in sync.
