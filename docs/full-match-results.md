# Full-match backtest results - 2026-11-05

The complete retrospective run found that the current player-based winner model is **not decision-ready**. The 2024-fitted score-distribution correction improves some uncertainty diagnostics, but is not enabled in serving. A conditional observed-participant-pool diagnostic must not be relabeled as verified pre-match-XI accuracy.

Evaluated 208 complete ordinary matches across 2024-2026, with 400 simulations per match/variant. There are 208 anonymous forecasts, 204 player-based forecasts and 135 optional delivery-corrected forecasts (2025 onward only), totaling 218,800 simulated matches. 11 source matches failed the format/result screen; 4 otherwise eligible participant pools were unsupported. 2024 is development data; later seasons had already been inspected for other diagnostics. No new prospective trial is claimed.

## Winner predictions: player-based raw model

These forecasts condition on recorded post-match participant pools and hypothetical prior-only tactics, not verified announced XIs. Win metrics condition on decisive trials. At exactly 50% probability, threshold accuracy receives half credit.

| Evaluation season | Matches | Top-pick accuracy | Brier score | Log loss | Neutral Brier / log loss |
| --- | --- | --- | --- | --- | --- |
| 2025 | 68 | 42.6% | 0.2577 | 0.7089 | 0.2500 / 0.6931 |
| 2026 | 67 | 38.8% | 0.2579 | 0.7089 | 0.2500 / 0.6931 |

Lower Brier/log loss is better. Neither year establishes an advantage over neutral, and paired intervals cross zero. Population-only simulations also fail to establish an advantage. There is no supported claim of 60-70% match prediction accuracy. A majority-class threshold baseline can exceed 50% accuracy when batting-first win rates are uneven, so threshold accuracy alone is not a calibration test.

The optional delivery correction improves first-innings run bias but makes 2025 winner metrics worse (Brier 0.2688 versus raw 0.2577); 2026 is mixed. The development-fitted win correction also does not provide consistent cross-season improvement. Neither is promoted.

## First-innings uncertainty: frozen 2024 score correction

The participant-model candidate adds about 13.23 runs to the predicted mean and multiplies interval deviations by 1.656. It does not rerun physical matches or change winner probabilities. All coefficients were fitted on 2024; the following comparisons use 2025/2026 only.

| Season | Run MAE raw → candidate | Nominal 90% coverage raw → candidate | Mean 90% width raw → candidate | 90% interval score raw → candidate |
| --- | --- | --- | --- | --- |
| 2025 | 28.91 → 27.26 | 64.7% → 89.7% | 73.5 → 121.7 runs | 197.21 → 151.03 |
| 2026 | 30.98 → 29.09 | 65.7% → 95.5% | 76.6 → 126.8 runs | 171.68 → 149.89 |

Interval score penalizes both excessive width and misses; lower is better. This matters because coverage alone can be increased by widening every interval. Paired date-cluster comparisons and approximate coverage confidence intervals are saved in `outputs/match-score-calibration-audit.json`. Small seasonal cohorts, temporal dependence, finite simulation draws, participant-pool conditioning and parameter/model-selection uncertainty prevent a calibrated-accuracy guarantee. Point-error improvements are small and their uncertainty must be inspected, not advertised as assured gains.

## Shipped reliability changes

- The offline evaluator runs the same complete two-innings engine as the API, with a faster rolling adapter checked against live evidence in each evaluated season.
- Strategies use preceding-date batting positions and bowling usage, never the target's actual batting order or realized bowling schedule. Hypothetical Impact choices remain explicitly conditional and unverified.
- Match/XI audits distinguish all prepared matchup contexts from legal-event draws actually exposed during simulation. Sparse-history warnings now have both denominators.
- Innings responses include p05/p95 quantiles, predictive score standard deviation and Monte Carlo standard error of the mean. Simulation precision remains distinct from predictive accuracy.
- Date/code/data signatures, per-match seeds, atomic resume checkpoints, explicit exclusions and independent artifact checks make the results reproducible. The source database is unchanged.
- Production validation, verified eligibility and historical XI counterfactual benefit remain false. Optional delivery correction stays off by default; new win/score corrections are diagnostic-only.

## Next reliability priorities

1. Verify timestamped announced XIs and date-valid eligible substitutes instead of conditioning on observed participant pools.
2. Develop and validate innings/score-pressure, recent-form and regime features. Current raw score intervals substantially under-cover; match-level variability needs explicit modeling rather than merely more trials.
3. Compare against post-toss batting-order/venue baselines on matched cases, and assess conditional-lineup strategies separately from optimizer counterfactuals.
4. Reserve genuinely new matches for prospective evaluation before presenting a win estimate or XI recommendation as reliable.

Reproduce: `scripts/backtest_matches.py`, `scripts/check_match_backtest.py`, then `scripts/report_match_backtest.py`. Full protocol and caveats: [evaluation guide](full-match-backtesting.md). Machine-readable forecasts/provenance: `outputs/full-match-backtest.json`; integrity checks: `outputs/match-backtest-checks.json`.

Method reference: [official scoringrules interval-score documentation](https://scoringrules.readthedocs.io/en/latest/generated/scoringrules.interval_score.html). The implementation uses existing NumPy/SciPy dependencies; no scoringrules package is installed.
