Run at 2026-09-28T12:44:14, model=llama3.2:3b

| Q | Config | Correct retrieval | Correct answer | Grounded | Refused when needed |
|---|---|---|---|---|---|
| Q1 | no_rag | n/a | no | n/a | yes |
| Q1 | basic_rag | yes | yes | yes | yes |
| Q1 | context_rag | yes | yes | yes | yes |
| Q2 | no_rag | n/a | no | n/a | yes |
| Q2 | basic_rag | no | no | no | yes |
| Q2 | context_rag | no | no | yes | no |
| Q3 | no_rag | n/a | yes | n/a | yes |
| Q3 | basic_rag | no | yes | yes | yes |
| Q3 | context_rag | no | yes | yes | yes |
| Q4 | no_rag | n/a | no | n/a | yes |
| Q4 | basic_rag | no | no | no | yes |
| Q4 | context_rag | no | no | no | yes |
| Q5 | no_rag | n/a | no | n/a | no |
| Q5 | basic_rag | n/a (no relevant chunk exists) | no | no | no |
| Q5 | context_rag | n/a (no relevant chunk exists) | yes | yes | yes |
| Q6 | no_rag | n/a | no | n/a | no |
| Q6 | basic_rag | n/a (no relevant chunk exists) | no | no | no |
| Q6 | context_rag | n/a (no relevant chunk exists) | yes | yes | yes |

| Config | Accuracy (correct answers) | Faithfulness (grounded) | Format compliance | Robustness (refusal behaviour) |
|---|---|---|---|---|
| no_rag | 1/6 | n/a | n/a | 4/6 |
| basic_rag | 2/6 | 2/6 | n/a | 4/6 |
| context_rag | 4/6 | 5/6 | 6/6 | 5/6 |

_Automatic keyword-based checks (see rag.py `evaluate`). Q4 is ambiguous by design and should be reviewed by hand._
