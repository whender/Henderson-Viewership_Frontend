# AP movement v4: preserve sparse histogram features

The previous quantile construction could produce only `[0]` for a rare positive flag. Right-sided binning put both zero and one in bin 1, preventing any tree split on that feature. The repair moves thresholds equal to the observed minimum or maximum between adjacent distinct training values. Interior quantiles and inference conventions are unchanged; constant columns have no thresholds. No new features, model hyperparameters, outcome weights, or team-specific corrections were added.

Chronological comparison uses the same 2019–2024 expanding-year folds and previously inspected 2025 follow-up. All model training uses prior seasons. The production artifact trains through 2025 (158 polls). `binning_repair_validation.json` retains both models' metrics, including newcomer tradeoffs; the dashboard's validation metrics now describe v4.

| Metric | Original | Fixed |
|---|---:|---:|
| 2019–2024 rank MAE | 1.12826 | 1.05749 |
| 2019–2024 Top25 overlap | 94.5836% | 94.5376% |
| 2019–2024 newcomer recall | 55.31% | 53.54% |
| 2025 rank MAE | 1.13067 | 1.01867 |
| 2025 Top25 overlap | 94.6667% | 94.6667% |
| 2025 newcomer recall | 60.0% | 57.5% |
| 2025 newcomer precision | 82.76% | 79.31% |

The September 13 next-release outlook still places Texas third. Fixing feature visibility does not establish that the learned model sufficiently rewards a win over No. 1. The current opponent buckets still group ranks 1–5 together. Earlier null results for sparse-feature experiments should not be treated as conclusive without rerunning with repaired bins.

Verification covers rare positive/negative flags, constant and sparse continuous columns, learning a rare flag, serialization, target-rank immunity, and exact Python/browser scenario parity. Browser inference accepts both v3 and v4 payloads during rollout.
