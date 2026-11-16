# Reliability work - API 0.5

This release adds historical evaluation, an optional delivery calibration candidate, and conservative recommendation safeguards. It does not establish calibrated full-match win probabilities or a proven benefit from selecting a particular XI.

Version 0.5 adds a [full two-innings evaluation](full-match-backtesting.md). Anonymous population forecasts use only prior deliveries and known post-toss venue/order; player-based diagnostics additionally condition on post-match recorded participant pools and are NOT verified pre-match-XI forecasts. Their results must remain separate from the older outcome/score benchmarks below.

The [completed full-match results](full-match-results.md) show no established winner-prediction advantage over neutral. Raw player-model first-innings 90% score intervals covered only about 65% of observed evaluation scores. A frozen development-fitted correction improves uncertainty diagnostics but requires wider intervals and is not enabled in serving.

## What was measured

The delivery correction was fitted only on 16,299 date-blocked 2024 legal-delivery observations. Performance records are restricted to dates before the prediction date, with the existing four-year lookback. Its coefficients are frozen before evaluating 2025 and 2026. Those later seasons had already been inspected for earlier model diagnostics: this is a retrospective evaluation, not a newly untouched or prospective trial.

| Metric | 2025 raw | 2025 correction | 2026 raw | 2026 correction |
| --- | --- | --- | --- | --- |
| Boundary calibration error, percentage points | 1.90 | 0.80 | 2.03 | 0.86 |
| Zero-batter-run calibration error, percentage points | 1.41 | 0.27 | 1.10 | 1.11 |
| Striker-dismissal calibration error, percentage points | 0.13 | 0.14 | 0.05 | 0.19 |
| Joint log loss, lower is better | 1.510126 | 1.509028 | 1.521060 | 1.520119 |

Calibration errors are weighted errors over ten probability bins, not error bounds for every forecast or percentages of deliveries predicted correctly. Boundary calibration improved in both evaluation years. Dot/dismissal results are mixed. The joint log-loss improvements have paired 95% match-cluster intervals crossing zero: 2025 -0.000464 to 0.002655; 2026 -0.000889 to 0.002696. A robust overall improvement is not demonstrated. Therefore the correction is a challenger, not the default simulation model.

Full details, event Brier scores, sparse-context segments and uncertainty limitations are in `outputs/delivery-calibration-backtest.json`. The original raw delivery report remains `outputs/bayesian-backtest.json`.

## How the optional correction works

The 20-category joint probabilities are multiplied by `exp(boundary_offset * boundary + dot_offset * zero_batter_runs + dismissal_offset * striker_dismissed)` and normalized together. This preserves a valid joint distribution; events are not adjusted independently into an inconsistent set of probabilities. Fitting uses joint log loss, three coefficients bounded to [-0.75, 0.75] and a fixed L2 penalty of 10. Coefficients are approximately [0.156149, -0.031697, 0.105984].

Pair-prediction responses now include a separate `calibrated_forecast` only for the evaluated phase-plus-venue scope, with the default raw configuration and an `as_of` on/after 2025-01-01. Earlier cutoffs, bowling-type mode and missing phase/venue do not receive this correction. Original posterior probabilities, parameter intervals and density curves remain unchanged. Corrected forecasts do not inherit the raw credible intervals: their `intervals` field is null.

Simulation/optimization requests may set `use_delivery_calibration: true`; the default is false. Simulation transforms each sampled posterior probability vector, or the posterior mean when posterior sampling is disabled, using the frozen coefficients. Coefficient uncertainty is not propagated. This is not a fitted match-state model, extras correction or match-win calibrator. The XI surrogate continues to use raw delivery-posterior utility; simulation can optionally use the challenger. Training metadata records the choice, and reliability flags identify the experimental correction.

## Genuine pre-match benchmarks

`GET /api/v1/predictions/match-benchmark` requires `team_a_id`, `team_b_id`, `venue_id` and exclusive `as_of`. It reads only earlier match outcomes and first-innings totals. No current roster, batting order inferred from the target match, future player performance, toss, weather or injury information enters these benchmarks.

The archive screen requires scheduled twenty-over/six-ball matches, no D/L flag, and a first innings completing 120 legal balls or finishing all out within that limit. There are 1,202 eligible first-innings records in the saved pack. Wins are evaluated only when a winner is known; a complete first innings from a no-result game can still enter score evaluation. This screen is not proof of fully reconstructed historical playing conditions. Win probabilities condition on a decisive outcome: ties and no-results are not modeled.

Twelve Elo variants (update rate, seasonal carry and probability temperature), a smoothed-form baseline and neutral 50/50 were compared on 2024. Date blocks prevent one same-day result from informing another match's prediction. Ratings use the same trailing four-year window as serving. The validation log-loss winner was **neutral**, so no team-strength favorite is promoted. This lack of demonstrated team-strength signal does not prove the lineup simulator is right or wrong.

The score benchmark uses a conditional empirical normal-inverse-gamma/Student-t predictive distribution. Venue counts are separate from the background used to estimate its prior. The score-strength candidates 5/10/20 were compared on 2024, selecting five. Before the selection cutoff, serving uses a predeclared neutral/strength-ten benchmark instead of later-fitted settings. Fewer than ten background innings prevents a venue forecast; weak team/venue history and stale archives are flagged. The distribution is continuous and not physically truncated, and plug-in prior uncertainty is not fully propagated.

The frozen benchmark was evaluated on 138 decisive games and 142 first innings across 2025/2026. The venue score benchmark's mean absolute errors were 28.65 and 31.83 runs. Its nominal 90% intervals covered 88.7% and 87.3% of observed scores; nominal 80% coverage was only 73.2% and 74.6%. Predictions are still biased low by about 9.3/8.5 runs. The venue model improved over the global score baseline in 2025, not in 2026. These results reveal remaining model problems, not a validated simulator. `outputs/reliability-backtest.json` contains all predictions, baselines, bins, date-cluster comparisons and cutoff traces.

In this archive the first listed team is the first batting team; win evaluation uses that side as its reference. The benchmark deliberately does not model batting-first/chasing effects. Its neutral 2026 calibration error is 14.3 percentage points for this ordering, so neutral is a comparison baseline, not a calibrated match forecast. Future post-toss models should explicitly use only the toss/order information known before play and be evaluated on fresh data.

## Recommendation safeguards

Match responses include `reliability` with `match_level_calibrated: false` and `decision_ready: false`. The audit flags assumed availability, unverified registration, a majority of prepared pair/phase contexts lacking direct observations, an archive more than sixty days old and a Monte Carlo interval half-width above five percentage points. These thresholds are declared safety heuristics, not learned guarantees. Prepared-context support is not a count of actual simulated ball exposures.

The additional `simulated_legal_delivery_exposures` field counts legal-event draws actually sampled, including any Super Overs, and their fractions with no or fewer than thirty direct historical pair/phase/venue observations. These draws are not independent new evidence. Anonymous population scenarios necessarily have no player-pair history; that is a baseline design, not missing source records. Prepared-context and exposure-weighted support are both retained.

The benchmark appears separately, not blended into the simulator. Probabilities are compared conditional on a decisive simulated outcome. A gap of fifteen percentage points is flagged for review, but disagreement between different models is not evidence that either forecast is wrong and is not a calibration test. In particular a neutral benchmark does not contain player-strength information.

For XI selection, if the leading simulation estimate's 95% sampling interval overlaps other candidates, selection uses the strongest surrogate utility among those overlapping candidates. It does not chase a small noisy simulation difference. Alternatives remain visible. Nonoverlapping intervals are only a conservative screening result, not a significance test or proof of higher true win probability; trials can share random seeds and model errors. An independent seeded confirmation still follows selection. Global win optimality, historical XI benefit and match eligibility remain unverified.

## Reproduce the evaluation

```powershell
.\.venv\Scripts\python.exe scripts/backtest_delivery_calibration.py
.\.venv\Scripts\python.exe scripts/backtest_reliability.py
.\.venv\Scripts\python.exe scripts/check_backend.py
.\.venv\Scripts\python.exe scripts/check_simulation.py
```

These scripts read the database without modifying it and save attributable evaluation artifacts. No new runtime dependencies are required. The API still bounds planning requests and allows one active planning job per process. The new benchmark GET reads a small match/innings archive, not the full ball-by-ball dataset.

Remaining work that could establish stronger reliability: collect/verify actual pre-match XIs and date-valid eligibility, replace the observed participant pools with those verified inputs, fit match-state/form/regime features on development data, and reserve genuinely new matches for prospective evaluation. The offline evaluator now generates strategies solely from earlier records and runs complete simulations without the target game's actual batting order or bowling usage. Additional simulations alone reduce numerical noise, not model bias.

Method reference: [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html) explains separate calibration data, reliability curves, and why Brier/log loss alone do not establish calibration. The implementation uses existing NumPy/SciPy dependencies, not scikit-learn.
