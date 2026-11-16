# Full-match backtesting - API 0.5

This evaluator runs the same two-innings engine and delivery sampler as the API, rather than scoring only next-ball probabilities or independent team-strength benchmarks. It is a retrospective diagnostic, not proof of production accuracy or a better XI.

Read the [completed results](full-match-results.md) before using predictions. The player-based winner model failed to establish an advantage over neutral; raw score intervals substantially under-covered. The saved correction experiments do not change the live defaults.

## Two different information scopes

1. **Anonymous population forecasts.** Fixed anonymous XIs and a fixed legal bowling schedule; legal-delivery probabilities and extras distributions use only earlier records, venue and phase. Neither player identities nor the target match's batting/bowling usage enter this model. Venue and batting-first team are treated as known post-toss inputs. These are genuine post-toss, prior-information population forecasts, but they do not distinguish player strength.
2. **Observed-participant-pool diagnostics.** Cricsheet's players field lists officially involved players, not a timestamped pre-match announcement. Most recent IPL lists contain twelve players including an Impact Player. Using those lists conditions on information reconstructed after the game. This diagnostic must NOT be described as verified pre-match lineup accuracy.

For the participant model, historical positions and phase-specific bowling usage come exclusively from preceding dates within the four-year window. Openers are inferred from prior batter/non-striker appearances, not the order of the target's player list. Recent median batting positions determine the hypothetical batting XI/order; historical bowling frequency determines the hypothetical fielding XI and five bowlers. The fixed twenty-over schedule respects four overs per bowler and no consecutive overs.

When batting and fielding XIs differ, a hypothetical interval swap is selected from the observed pool. The evaluator does not read the target's actual replacement timing/pair to choose it, and it does not claim that the hypothetical swap or historical overseas/registration constraints were legal. Thirteen-player or overlapping pools are excluded from participant diagnostics but remain eligible for anonymous forecasts when match-format checks pass. The public API's current-season roster and domestic-interval-Impact safeguards are not relaxed.

Cricsheet source semantics: [official JSON format](https://cricsheet.org/format/json/#players). The archive and processed database are the existing attributable local snapshots; this run does not replace them or imply a new live collection.

## Date and format safeguards

The window includes `as_of - 1461 days <= match_date < as_of`. Every match on the forecast date is excluded, even double-headers. The offline adapter maintains rolling sufficient statistics and timestamp-filtered supplemental-event distributions. At the first evaluated case in each season it is checked against a fresh live `SimulationEvidence` instance: matchup posteriors/counts, delivery-type CDFs, supplemental prototype multisets, run tails, wicket-mode shares and training traces must match.

The case screen requires two completed ordinary innings, six balls per over, twenty scheduled overs, a consistent unadjusted target and a decisive score-consistent ordinary result. It excludes D/L/revised targets, incomplete chases, observed ties/Super Overs/no-results, unsupported innings penalties and invalid lengths. Every omitted requested-season match gets a reason. These checks cannot establish unrecorded weather/pitch or eligibility conditions.

Actual runs/wickets/winner are used only for eligibility checks and scoring. They are not supplied as prediction targets to the simulator. The simulator generates its own first-innings score, then chases that simulated target. Simulated ties are reported; win metrics condition on decisive simulated trials. A half-count probability estimator prevents infinite estimated log loss from zero observed Monte Carlo wins. It does not correct structural bias.

## Development, evaluation and challengers

2024 is development data: raw delivery hyperparameters were already selected on it. The optional delivery correction was fitted on 2024 and can only enter 2025-and-later scenarios. It is not applied retroactively in 2024. Raw and optionally corrected participant simulations are compared on identical eligible match IDs in 2025/2026.

The evaluator fits two additional **diagnostics only** on 2024 raw predictions: a bounded, regularized intercept/logit-scale win correction, and a bounded mean-shift/interval-scale first-innings correction. Coefficients are frozen before evaluating 2025/2026. Corrected first-innings distributions are post-processing diagnostics, not physical reruns and not changes to win probabilities. There is no automatic promotion into serving. The location/scale procedure has no temporal conformal-coverage guarantee; fitting and model-selection uncertainty is not propagated.

The 2025/2026 archive had previously been inspected for other model diagnostics. These results are retrospective evaluations, not newly untouched or prospective tests. Improving delivery calibration does not necessarily improve full-match predictions. A challenger that fails at match level remains disabled by default.

## Metrics and artifacts

The main artifact is `outputs/full-match-backtest.json`; it includes source-code/data hashes, all match-level forecasts and cutoffs, saved hypothetical plans, exclusions, bridge checks and separate season results. `outputs/full-match-backtest.progress.json` is only a resumable checkpoint, never a final accuracy report. Limited runs are explicitly marked smoke tests.

Win metrics: Brier score, log loss, ten-bin calibration error, classification accuracy with half credit at exactly 50%, date-cluster paired comparison intervals, and Monte Carlo precision. Baselines include neutral 50/50 and a rolling Beta(5,5)-smoothed batting-first win rate using only earlier eligible matches. The participant/population comparison uses matched IDs; it must not compare different cohorts as if paired.

First-innings metrics: run MAE/RMSE/bias, wicket bias, empirical coverage and width of nominal 80%/90% score intervals, and Monte Carlo standard error of the simulated mean. Second-innings totals are scored separately as unconditional joint predictions. They are NOT conditional on the actual observed first-innings target. Coverage estimates and ten-bin win calibration are noisy with roughly one season of matches; date-cluster intervals do not capture all team/season dependence.

Reproduce from the project root:

```powershell
.\.venv\Scripts\python.exe scripts/backtest_matches.py --simulations 400
# Resume only when the exact code/data/configuration signature still matches:
.\.venv\Scripts\python.exe scripts/backtest_matches.py --simulations 400 --resume
.\.venv\Scripts\python.exe scripts/check_match_backtest.py
.\.venv\Scripts\python.exe scripts/report_match_backtest.py
# Explicit smoke-test artifact, not a substitute for the complete evaluation:
.\.venv\Scripts\python.exe scripts/backtest_matches.py --simulations 50 --limit 2 --output outputs/full-match-smoke.json
```

Per-game seeds derive from the declared seed plus a SHA-256-derived match ID value. Runs are sequential and date-blocked; snapshots are consumed before advancing the rolling index. Files are checkpointed atomically only after a complete match's variants finish. The SQLite database is opened read-only, and its digest must remain unchanged. No new packages are required.

## Still not established

Verified announced-XI accuracy; registered/date-valid eligibility; optimal XI counterfactual benefit; live player availability; learned score-pressure/toss/weather/pitch effects; production calibration; prospective performance on genuinely new matches. Those require new inputs or new evaluations, not a relabeling of this report.
