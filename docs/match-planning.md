# IPL match simulation and XI planning - version 0.5

Version 0.4 adds [reliability audits and historical benchmarks](reliability.md). The optional delivery correction is a challenger and defaults off; it has not established a robust overall or match-win improvement. XI comparison now falls back to the strongest surrogate candidate when sampling intervals overlap, while retaining alternatives and independent confirmation. Older descriptions of simple win-estimate ranking below are subject to this safeguard.

Version 0.5 adds [full-match backtesting](full-match-backtesting.md) and actual simulated-event support counts. Innings summaries include p05/p95, predictive score standard deviations, and Monte Carlo standard errors of the simulated means. These additions do not change the raw event sampler or turn model spread into an accuracy guarantee. The historical participant-pool diagnostic does not verify registered starting XIs or test XI counterfactuals.

Implemented locally: complete two-innings Monte Carlo simulation for an uninterrupted 20-over match, and constrained starting-XI/bowling-plan optimization. Both are experimental planning tools. Engineering checks are not evidence of calibrated match-win accuracy. The frontend is not part of this delivery.

## Try the saved examples

Start with `scripts/start_backend.ps1` and open http://127.0.0.1:8000/docs. Use the Planning section. These computation POSTs never modify the dataset:

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/simulations/match` | Simulate two explicit team plans at a venue and exclusive historical cutoff. |
| `POST /api/v1/optimization/xi` | Select your XI and bowling schedule against an explicit opponent plan. |
| `GET /api/v1/rules` | Reviewed rule profile, primary source and remaining verification gaps. |

Copy `outputs/match-simulation-request.json` or `outputs/xi-optimization-request.json` into the corresponding documentation form. Example responses are saved alongside them. These are hypothetical CSK/MI scenarios, not a scheduled fixture or registered match-ready team. Every saved roster currently has unknown match-day availability, so the examples explicitly opt into that assumption. The default API rejects unconfirmed availability.

## Team-plan contract

Provide `team_id`, eleven unique `starting_xi` IDs, an eleven-player `batting_order`, twenty `bowling_plan` IDs (one per over), and a starter `captain_id`. Captaincy is not a predictive input. Optionally nominate up to five distinct `substitutes` and an explicit domestic `impact` plan with `outgoing_id`, `incoming_id` and `timing: innings_interval`.

An interval Impact replacement changes only the second-innings active XI. When batting first, the batting order contains the starters and the bowling schedule may use the incoming player. When bowling first, the bowling schedule contains starters and the batting order contains the replacement. Replaced players are excluded from subsequent Super Overs. Automatic Impact selection, overseas Impact scenarios and mid-over substitutions are unsupported, not silently approximated as generally legal or illegal.

All nominated players must appear in that team's saved 2026 roster, and teams cannot nominate the same player. The fielding XI requires a recorded wicketkeeper. Starting overseas proxy counts cannot exceed four. A dated unavailable player is always rejected, even when unknown availability is allowed. Unknown overseas classification is rejected. Country, role and keeper metadata remain present-day proxies; registered squad membership, official overseas classification, suspension and fitness are not verified. `eligibility_verified` is always false.

## Simulator

The state machine handles legal-ball counts, wides/no-balls, byes/leg-byes, strike and end-of-over changes, free hits persisting across illegal balls, replacement batters, ten-wicket termination and chase completion. A traceable sample scorecard can be requested with `include_sample_match: true`. Batting totals plus extras reconcile to team totals; bowler conceded runs exclude byes and leg-byes. Balls faced follow the existing dataset convention: exclude wides, include no-balls, not an official scoring-adjudication claim.

Regular phases are overs 1-6, 7-16 and 17-20. A boundary-winning event retains its boundary runs; a running chase stops at the winning run, and a winning wide/no-ball penalty ends the game before subsequent action. End positions for run-outs use completed-run parity; unfinished crossing cannot be reconstructed from this archive. Extras-only boundaries are not separately adjudicated. Dead-ball, penalty-run, retired-hurt, concussion-replacement and injury scenarios are not modeled.

Ties proceed to six-legal-ball/two-wicket Super Overs, with the regular second-batting team batting first. Repeated rounds alternate batting order, exclude batters dismissed in any prior Super Over, and disallow the immediately previous Super Over bowler. This implementation chooses eligible players using deterministic plan-order heuristics. Super Over ability uses the ordinary death-phase model, not a separately fitted model. Official conditions allow further rounds; this bounded engine permits 0-6 rounds and returns `unresolved_tie` if still tied or eligible options run out. It never forces a winner.

### Probability and evidence

The legal-delivery joint scoring/boundary/striker-dismissal model is the existing empirical-Bayes model, using phase and venue contexts and a four-year rolling archive window. All performance records on/after `as_of` are excluded, as are historical Super Overs. New players borrow population evidence; pure seed-only forecasts are rejected. This is not a full hierarchical posterior: upstream prior uncertainty is not propagated.

With `sample_posterior: true`, each trial draws one conditional Dirichlet distribution per batter/bowler/phase pair and reuses it within that trial. False uses posterior means but still randomly samples deliveries. Impossible boundary/dismissal combinations transfer probability to survival. Delivery type and supplemental extras/non-striker events use venue/phase empirical bootstrap samples pooled with the global archive. Free-hit legal striker-dismissal shares use historical run-out/obstruction proportions; no mode evidence uses an explicitly warned 3% fallback. Illegal-delivery prototypes retain recorded wicket-credit flags. This supplemental layer is not individually fitted for every player.

Current score, required rate, wickets remaining, batting position, fatigue, recent form, measured pitch, weather and dew are not learned delivery-model effects. Team strength comes from historical pair/phase/venue evidence and the supplied plans. Do not present this as an AI assessment of live conditions.

Outputs contain win counts/probabilities, unresolved-tie probability, regular tie and Super Over rates, innings score quantiles/histograms, training cutoff and assumptions. The 95% Wilson intervals describe finite Monte Carlo sampling error only, not total model uncertainty or predictive accuracy. At 200 trials, a roughly 50% outcome has about a +/-7 percentage-point sampling interval. Seeded requests are reproducible under the tested runtime and dataset; changing library versions can change exact draws.

## XI optimizer

Inputs include the opponent's complete plan, batting-first team, candidate pool (11-40, or the saved roster), locked/excluded IDs, minimum batting options (default six), risk aversion (0-3), 1-3 distinct candidates and 50-500 simulations per candidate. Only known role/classification candidates passing planning availability filters enter the solver. Exclusion reasons are returned. Bowling eligibility is deliberately restricted to recorded bowler/allrounder roles, a planning choice rather than a rule that other players may never bowl.

The mixed-integer solver jointly chooses eleven selection variables and twenty overs of bowler-assignment variables. Hard constraints enforce selection count, up to four overseas proxies, at least one keeper, the requested batting-role balance, locks, four overs per bowler, one bowler per over and no adjacent overs for one bowler. Every rounded solver result is independently checked against the constraint matrix. Infeasible pools return 422, not a relaxed team. A solver timeout without a feasible solution returns 503.

The surrogate utility for a legal batting delivery is `batter_runs - 12 * striker_dismissal`. Bowling utility is its negative. Each component subtracts `risk_aversion * conditional_posterior_standard_deviation`. Batting scores assume twelve proxy delivery exposures per selected player, averaged across the supplied opponent's twenty bowling overs. Bowling-over scores assume six exposures, averaged over the opponent's first seven batters. The twelve-unit wicket cost, equal exposure and top-seven averaging are declared unfitted heuristics. Proxy scores are not expected team runs.

Up to three distinct XIs are generated with exclusion cuts. `proxy_optimality_proven` reports solver optimality for that candidate's surrogate problem, including prior-XI cuts. Batting order is then heuristically sorted by batting utility; captain is a placeholder first batter. These are not globally optimized batting orders, leadership recommendations or optimal Impact plans.

Candidates are compared using seeded match simulations. A second, independently seeded run confirms the selected XI's win estimate, reducing reuse of the selection trials. Ranking remains noisy, comparisons are not significance tests, and confirmation is not historical validation. The optimizer does not enumerate every XI by win probability. `global_win_probability_optimality_proven` is false. The supplied opponent plan is fixed, not an adversarial optimization.

## Rules and boundaries

The saved primary 2026 IPL playing-conditions PDF informed core guardrails: eleven players, four overseas starters, bowling limits, free hits and Super Over procedure. Reviewed references are clauses 1.1, 1.2.5, 13.9.1, 17.6, 21.19 and Appendix F. Its cover/introduction date discrepancy remains recorded. Full current supplementary Impact regulations and match registration still need verification, so only the conservative explicit domestic interval subset is enabled. The API supports season 2026 only; do not reuse its profile for another competition/year.

## Efficiency and verification

Evidence is loaded once per planning request, then compact sufficient statistics and cached distributions are reused across candidates/trials. Existing lightweight analytics remain SQL-based; the new planning operations do read their bounded four-year delivery window into memory. SQLite stays read-only. One planning job per process is allowed; a concurrent request receives 429. Multiple server workers would each have their own slot. Simulation limits are 50-1000 trials and about 25 seconds including preparation; optimization has a roughly 55-second soft budget, with up to five seconds per solver. Budgets are checked between stages/trials, not hard process cancellation. Pathological illegal-ball sequences fail with 503 rather than forcing legal deliveries. This is a local-development service, not a production load-tested deployment.

Run the unit/API suite and real-data checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/check_backend.py
.\.venv\Scripts\python.exe scripts/check_simulation.py
```

If the environment's default temporary folder is restricted, use a newly named directory under `work/` with pytest's `--basetemp`, plus `-p no:cacheprovider`. Never point `--basetemp` at a folder containing valuable files; pytest owns/clears it.

Unit tests include a small enumerated selection comparison, infeasible solver cases, explicit event-state tests, seeded response checks, API validation, Impact limits and tied Super Over behavior. `outputs/simulation-checks.json` records real-data reproducibility, scoring/constraint checks, unchanged database hash and local timing. These checks are not match-win calibration. Before relying on predictions: reconstruct date-valid registered rosters/lineups and availability, calibrate held-out match win rates and score distributions against simple baselines, fit state/form effects, and broaden supplemental-rule support.

Solver reference: [SciPy MILP documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html). Official source and SHA-256 are exposed by `/api/v1/rules` and the saved data pack.
