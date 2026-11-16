# The Concourse — Record workspace

Phase 4 presents saved evaluation evidence. It does not retrain a model, rerun a backtest, improve measured prediction accuracy or change the simulation/optimization defaults. The 70% winner-accuracy target remains unmet. The subsequent [final integration phase is complete](frontend-release.md).

## Open it

From the project root:

```powershell
.\scripts\start_frontend.ps1
```

Open http://127.0.0.1:5173/#/record?season=2026, choose **4 Record**, or press **4** outside an input. Record works without the Python service. Its evidence is explicitly labelled a saved research extract; opening Record does not request an archive API refresh. Other workspaces retain their existing API behavior.

The three evidence views are **Winner research**, **Match simulator** and **Delivery model**. Each has its own population, forecast target, protocol and serving status. They must not be pooled into a single application accuracy number. The URL identifies Record; view, season, selected bin and ledger filters are temporary and reset when Record is left or reloaded. Theme preference persists.

## Winner research

The headline is the locked direct-winner study's final 2026 result: **39/70 correct, 55.7%**, versus **45/70, 64.3%** for always choosing the chasing side. The approximate 95% accuracy interval is 44.1%–66.8%. A 70% target-success label is never inferred from artifact checks passing. The research model is not used by Match or Lab.

The selected shallow random forest was chosen from sixty recipes using earlier-season validation. Its sixty-one selected input columns exclude reconstructed-XI features. The protocol display separates earlier training history, 2022–2025 selection folds and the frozen-weight 2026 evaluation. Earlier 2026 outcomes may update later 2026 features; same-day and future observations are excluded. Because 2026 had already been inspected in other diagnostics, the evaluation is retrospective rather than a new untouched or prospective trial.

Select a season in the table to inspect that season's calibration and complete forecast ledger. The four selection years are not labelled final holdouts. The final 2026 baseline table stays explicitly labelled 2026 even while another season is selected. It shows accuracy, Brier score and log loss on the same seventy matches. Always chase uses 50/50 probabilities and a deterministic chase-at-tie decision rule; prior batting-order history is a separate probability baseline. Lower Brier/log loss is better. The paired-comparison disclosure retains date-cluster uncertainty and the model-only/chase-only correct counts.

The chronological strip and ledger expose all **353 saved forecasts** for the selected recipe: 74 from 2022, 71 from 2023, 70 from 2024, 68 from 2025 and 70 from 2026. Search team abbreviations, date, ground or match reference; combine this with All/Right/Wrong and show additional rows. Filters affect inspection only. Aggregate metrics continue to use the complete selected-season cohort, and that denominator remains visible. There is no confidence filtering, abstention or selective headline recalculation.

Selecting a strip cell or row opens a receipt, moves focus to it and brings it into view. Closing returns focus to the originating control. The receipt distinguishes batting-first probability from picked-team probability and recorded winner. At exactly 50%, the deterministic pick is chasing. Final-season receipts include the retained latest prior feature-evidence date. Selection-fold extracts lack that per-row trace, so the receipt states its absence instead of inventing one.

## Calibration chart

Native SVG plots each nonempty fixed 10% probability bin: mean batting-first forecast on the horizontal axis and observed batting-first win frequency vertically. The diagonal is the equal-rate reference. Click a point, press Enter/Space on it, or use the bin buttons to inspect its count, observed wins and mean forecast. Exact bin counts and numeric intervals are also available in a table.

Vertical whiskers are approximate **95% Wilson intervals for observed bin frequencies**, derived from integer win counts. They are not a smooth fitted confidence band, posterior credible intervals, Monte Carlo sampling intervals or a guarantee of future calibration. Independence is only an approximation; temporal/team dependence and model/selection uncertainty are not fully captured. Empty bins are omitted, and sparse bins retain their actual counts. Weighted calibration error is displayed in percentage points, not as a match error rate.

## Full-match simulator

Choose 2025/2026 and the population-only, raw-player or delivery-corrected player variant. Each comparison table matches its own baseline cohort. Simulator accuracy gives half credit at exactly 50%; its win probabilities condition on decisive trials. That differs from the winner study's deterministic chase-at-tie classification.

The evaluator uses 400 simulation draws per match/variant. Those draws are simulation precision, not independent historical forecasts. Cohort accounting retains 208 population, 204 raw-player and 135 delivery-corrected forecasts across 2024 development and 2025–2026 evaluation. Eleven format/result exclusions and four unsupported participant pools are listed by reference/reason. Delivery correction begins in 2025. In 2026, population contains seventy matches and player variants sixty-seven; the interface does not present their headline accuracies as a matched comparison.

Population forecasts use prior deliveries and known post-toss venue/order. Player variants additionally condition on recorded post-match participant pools with hypothetical prior-only tactics, not timestamp-verified announced XIs. This does not validate a historical optimizer benefit. Brier/log-loss gains and 95% date-cluster intervals are shown against neutral. Interpretation follows their signs: the delivery-corrected 2025 variant's intervals favor neutral, while the other saved variant/year pairs include zero.

The first-innings score audit covers population and raw-player variants. It pairs empirical nominal-90% coverage with mean interval width, mean absolute error, interval score, historical coverage intervals and paired gains. The frozen 2024 score correction improves coverage with wider intervals; it is diagnostic only and not enabled in serving. It changes score summaries, not winner probabilities or physical match simulations. Missing score-audit evidence for the delivery-corrected variant is explicitly absent. Coverage alone is not treated as proof of reliability.

## Delivery model

The optional joint-event correction was fitted to 16,299 date-blocked 2024 legal deliveries, with coefficients frozen before 2025. The view preserves delivery and match counts, raw/corrected joint log loss, paired match-cluster intervals and ten-bin event calibration errors for boundaries, zero batter runs and striker dismissal. Joint-loss comparison intervals cross zero; event improvements are mixed. Delivery calibration does not validate match-win probabilities or XI counterfactual benefits. The experimental correction remains off by default; it is not a newly promoted model.

## Sources and regeneration

`frontend/src/api/snapshots/record.json` is the public projection of nine existing JSON artifacts. Its receipt retains source filenames/SHA-256 values, database hash, extract timestamp and saved integrity-check counts. Passing those checks means artifact/temporal integrity, not a passed accuracy target or production validation. Source limitations remain available for the active view.

**Save evidence extract** downloads the complete public projection, including all 353 research rows and all displayed aggregate audits. Filters do not truncate that export. It is not the raw database or all source reports. Original artifacts remain in `outputs/` and the receipt identifies them exactly.

Regenerate from the project root:

```powershell
.venv\Scripts\python.exe -m scripts.export_frontend_record
```

The exporter verifies the winner-report/model/protocol/selection-lock hash chain, full-match report/audit hashes, failed target, non-promotion flags and source-database consistency. It opens SQLite read-only to add public match labels and independently reconciles research outcomes, counts and Brier scores. It stores only public forecast context and selected aggregate evidence; no raw source pages or private notes are exported. It checks the database digest again before writing the frontend file.

The frontend additionally checks forecast uniqueness, probabilities, per-season counts and accuracy, aggregate Brier correspondence, calibration count reconciliation, prior-date traces, baseline cohorts and coverage counts. Inconsistent evidence is withheld behind an unavailable message. The full research protocol and historical caveats remain in [winner research](winner-research.md), [full-match results](full-match-results.md), [full-match backtesting](full-match-backtesting.md) and [reliability](reliability.md).

## Verification

The combined suite has **86 passing tests**. New checks cover exact source-artifact hashes, all season/forecast totals, target failure and baselines, simulator population differences, score coverage/width accounting, delivery units, malformed evidence, tie rules, search/filter partitioning, retained versus missing prior-date traces, Record routing and negative versus zero-spanning comparison intervals. TypeScript, production build, formatting and exporter lint pass. The SQLite digest still matches Phase 1.

Focused local Chromium checks covered all three evidence views, selection/final seasons, calibration details by mouse and keyboard, exact-count disclosures, Right/Wrong and no-result filters, forecast receipts/focus return, source receipts, export activation, numbered navigation, theme persistence and fresh loading with Python stopped. The final fresh Record load showed no browser warnings/errors. During development, changing the archive hook's dependency list generated a hot-reload warning; it was absent on a fresh load. This was UI/source verification, not a new model evaluation. The generated download payload is covered by the source/serialization path; browser download-file contents were not independently inspected in this phase.

Both themes were reviewed at 1440px and narrow layouts at 390px/320px, with no horizontal page overflow. Wide tables scroll inside labelled keyboard-focusable regions; calibration redraws to the actual panel width. Review images are in `docs/frontend-review/phase4-record-*.jpg`. This is focused Chromium QA, not a formal accessibility or cross-browser certification. No dependencies, backend/model changes or deployment were added. Temporary review servers were stopped.
