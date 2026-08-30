# DATA 260 Coursework

Student repository for DATA 260 homework assignments.

## Homework 1 Configuration

| Value | Configuration |
|---|---|
| SID4 | 9486 |
| PORT_BASE | 8486 |
| PREFIX | s9486 |
| SEED | 9486 |
| VERIFY_SEED | 269486 |
| DOMAIN_ID | 6 |
| Assigned Domain | Rental housing listings |
| Hardware | Apple Mac with M1 chip and 8 GB unified memory |
| Local Model | qwen3:4b |

The recommended qwen3:8b model was replaced with qwen3:4b because the computer has 8 GB of unified memory. The smaller model is more practical for repeated local experiments while retaining the required agent capabilities.

## Repository Structure

- `reports/hw01/` — Homework 1 report, metrics, logs, and experiment results
- `reports/hw01/raw/` — Machine-readable experimental results
- `reports/hw01/cases/` — Fixed experiment inputs
- `src/` — Reusable source modules
- `DOMAIN_SCHEMA.md` — Rental housing listing schema

## Reproducible Run Instructions

Instructions will be added as each component is implemented.