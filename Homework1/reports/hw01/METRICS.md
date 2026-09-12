# Part 3 Metrics

The nondeterminism experiment reused the same fixed rental-housing input for all 40 runs: 20 at temperature `0.0` and 20 at temperature `0.7`.

## Tag Metrics

| Metric | Temperature 0.0 | Temperature 0.7 |
|---|---|---|
| Distinct tag sets | 1 | 3 |
| Tags in all runs | `furnished two-bedroom`, `secure parking`, `two-bedroom apartment near sjsu` | `furnished two-bedroom` |
| Tags in exactly one run | None | `convenient access` |

## Latency Metrics

| Metric | Temperature 0.0 | Temperature 0.7 |
|---|---:|---:|
| p50 latency | 74523.73 ms | 80115.68 ms |
| p95 latency | 103968.01 ms | 91286.90 ms |
| p99 latency | 120482.96 ms | 96006.23 ms |

## Interpretation

At temperature `0.0`, identical input produced the same tag set in every run, which is the expected stable behavior for a deterministic setting.

At temperature `0.7`, the same input produced three distinct tag sets, which is acceptable for optional search tags because multiple relevant phrasing choices can be useful. That same amount of variation would be unacceptable for lease decisions, compliance checks, or any other high-stakes output that must remain identical for the same input.

## Acceptable Variation Example

For a rental listing, small differences in search tags or summary wording are acceptable when they still describe the same property features, such as `furnished two-bedroom` versus `furnished two-bedroom apartment`.

## Unacceptable Variation Example

It would be unacceptable if the same input sometimes produced a different property category, a different lease price, or a contradictory eligibility decision.
