# Direct match-winner research - 70% target not met

The new direct winner layer predicted **39 of 70 eligible 2026 matches correctly (55.7%)**. The declared minimum was 70%; that target failed. Choosing the chasing side on every eligible match achieved 45/70 (64.3%) in the same season. The challenger is therefore **not promoted into live match simulation or XI optimization**, despite improving on the earlier simulator's headline accuracy. It is not a recommendation system.

## What was built and tested

The source archive contains 1,243 matches. The fixed completed/uninterrupted/decisive ordinary-match screen yields 1,176 match observations across all saved seasons. The final 2026 cohort contains seventy matches; every one received a forecast. There is no confidence filtering, selective match removal, random train/test split, reversal of losing predictions or use of a live score to redefine the target.

The date-blocked feature builder computes sixty-seven features. These include team Elo, recent win rates, net run-rate and phase scoring/conceding rates, venue and head-to-head history, rest, season progress, toss, batting order, franchise identity, lagged player form and optional original-XI player-form summaries. Features use only earlier dates; every same-day match is held back until all that day's features are emitted. Match performance, realized batting/bowling usage and incoming Impact choices from the target game never enter a feature vector.

The original-XI summaries are a separate conditional experiment. Original starters are reconstructed from `match_players` by excluding incoming match replacements. The saved archive produces exactly eleven original players per team; their order is sorted and cannot leak the actual batting order. These lists are **not timestamp-verified announcement records**. The public IPL squads page examined during this work rendered a loading state and did not supply such verification. No private-feed credentials or access controls were bypassed. Reconstruction is saved as `outputs/winner-reconstructed-xis.json` with its source database digest, rather than mislabelled as verified pre-match data.

Twenty-eight base configurations were tested across regularized logistic regression, gradient-boosted trees, histogram boosting and random forests. Each was trained on earlier seasons and validated on 2022, 2023, 2024 and 2025, with a fixed five-season age half-life. Calibration candidates used only predictions/outcomes from earlier validation seasons. Ensemble and neutral/order-history baselines brought the total to sixty selection recipes. Accuracy averaged across validation seasons was the declared primary selection metric; log loss broke ties.

The winner was a shallow random forest (`rf_full_depth4`), with 53.73% macro-season validation accuracy across 283 validation matches. Its selected sixty-one input columns **exclude the reconstructed-XI features**. The integrity audit verifies that changing those unused features cannot change its predictions. We did not switch to a model that happened to score better on 2026 after inspecting its results.

## Locked final retrospective evaluation

The search protocol is written before training, and the chosen recipe is locked to that protocol before final evaluation. The selected estimator is fitted only on 2012-2025 feature/label rows. Model weights are frozen before 2026; earlier 2026 results may update features for later 2026 matches because those results would already be known at forecast time. Same-day and future results remain excluded.

2026 had already been inspected in earlier diagnostics. This is therefore a retrospective chronological evaluation, **not newly untouched data or a prospective trial**. A successful point estimate would still not guarantee future 70% accuracy; here even the point target failed.

| Predictor | Correct / eligible | Accuracy | Brier score | Log loss |
| --- | --- | --- | --- | --- |
| Validation-selected random forest | 39 / 70 | 55.7% | 0.24056 | 0.67372 |
| Always chase, probability 50/50 | 45 / 70 | 64.3% | 0.25000 | 0.69315 |
| Prior-only batting-order history | 45 / 70 | 64.3% | 0.23654 | 0.66620 |

Lower Brier/log loss is better. Neutral 50/50 forecasts receive half credit under the older tie-neutral accuracy metric, but their deterministic tie rule chooses the chasing team; the table explicitly shows that decision rule. The new target uses an actual pick on every game: choose batting first when its probability exceeds 0.5, otherwise choose chasing. All metrics and both tie conventions are preserved in the JSON.

The forest's approximate binomial 95% accuracy interval is **44.1%-66.8%**. Compared with always chase, it alone got nine matches right while chase alone got fifteen right; this is not evidence of superior classification. Its probability-score differences versus the baselines also have date-cluster comparison intervals crossing zero. No claimed predictive advantage, calibration guarantee or XI counterfactual benefit is justified.

## Research-only inference and safeguards

The selected model is exported as data-only JSON, not an executable pickle. Inference uses the existing NumPy/SciPy runtime. Every historical feature row was checked against native scikit-learn inference before export; maximum absolute probability error was about `1.11e-16`. A float32-to-double tree-threshold comparison issue was caught by this check before final accuracy was evaluated, corrected, and covered by a regression test.

The research forecast is an explicit CLI opt-in. It rejects dates before the training/selection cutoff, incompatible feature versions, mismatched data snapshots, unknown teams/venues and insufficient recent history. It labels stale data, unverified availability, lagged rosters and lack of production validation. It cannot set `decision_ready` or `production_validated` true. Existing simulation, optimization and HTTP defaults are unchanged.

```powershell
# Optional dependencies for training; not required for JSON inference:
.\.venv\Scripts\python.exe -m pip install -r requirements-winner-research.txt
.\.venv\Scripts\python.exe scripts/train_match_winner.py
.\.venv\Scripts\python.exe scripts/check_match_winner.py

# Hypothetical research forecast, not an actual fixture or recommendation:
.\.venv\Scripts\python.exe scripts/predict_match_winner.py --batting-first CSK --chasing MI --toss-winner MI --venue venue_4534efadc8 --as-of 2026-11-05
```

The protocol, frozen selection and model artifacts are `outputs/winner-research-protocol.json`, `outputs/winner-selection-lock.json`, `outputs/match-winner-model.json` and `outputs/match-winner-research.json`. `outputs/match-winner-checks.json` independently replays every final forecast, verifies complete coverage, source/data/selection hashes and prior-date traces, recomputes accuracy and checks the 70% claim. A checks status of `passed` means artifact integrity passed, **not** that the accuracy target passed. The source SQLite dataset remains unchanged.

The first team-only development sweep was stopped by export parity checks before final accuracy was calculated. Its protocol/selection are retained as `winner-team-only-protocol.json` and `winner-team-only-selection-lock.json`; the expanded XI-ablation protocol was written before the completed evaluation. There were no hidden test-season accuracy-based retries.

## What the result permits us to say

This implementation does not deliver the requested 70%. The available inputs and tested model families have not demonstrated that level of predictive skill. Further research needs independently sourced, date-valid lineups/substitutes, availability and broader player-performance context, with a genuinely fresh evaluation period. Those additions may help, but none is a defensible promise of 70%. Selecting only easy matches, changing to in-play predictions or repeatedly tuning against 2026 would answer a different question.

Method references: [official time-series validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-of-time-series-data), [histogram boosting documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html). The custom date-blocked splitter also excludes all same-day games, and histogram early stopping is disabled rather than using a random internal validation split.
