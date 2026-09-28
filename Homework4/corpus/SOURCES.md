# RAG Corpus Sources

Five public rental-housing documents saved as HTML. `rag.py` strips the HTML
at load time and only reads `.txt` / `.html` files, so this file is not indexed.

| File | Document | Source URL | Access date |
|---|---|---|---|
| ca_civil_code_1941_1_habitability.txt | California Civil Code 1941.1 (untenantable dwellings) | https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1941.1 (confirm) | PENDING |
| ca_civil_code_1950_5_security_deposit.txt | California Civil Code 1950.5 (security deposits) | https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1950.5 (confirm) | PENDING |
| ca_tenant_notice_requirements.txt | California Civil Code 1946 (notice to end a periodic tenancy) | https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1946 (confirm) | PENDING |
| ca_tenant_protection_act_ab1482.txt | California Civil Code 1946.2 (Tenant Protection Act, just cause) | https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1946.2 (confirm) | PENDING |
| fair_housing_act.txt | U.S. DOJ - The Fair Housing Act | https://www.justice.gov/crt/fair-housing-act-1 | PENDING |

The first four files came from the HW3 corpus (`Homework3/rag/corpus/`); the
empty `hud_fair_market_rents.txt` from HW3 was not reused.
