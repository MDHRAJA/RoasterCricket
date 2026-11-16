# Bayesian prediction layer: model card

Raw model: `legal-delivery-eb-v1`. API: 0.5. Status: **experimental**. The separate optional joint-calibration challenger is described in the [reliability report](reliability.md); it does not replace the raw posterior intervals below.

This is an empirical-Bayes Dirichlet shrinkage model, not full hierarchical posterior sampling. It predicts the next recorded **legal, non-Super-Over delivery**, not a match winner, innings total or player fitness.

## Predictions and interpretation

The response contains a normalized 20-category joint distribution of batter runs, recorded boundary flag and striker dismissal. Run buckets are 0 through 6 and 7+; non-boundary fours/sixes are distinguished. Marginals provide scoring, boundary, zero-batter-run dot and striker-dismissal probabilities. Those three events can overlap: do not sum them to one or simulate them independently.

Event and run probabilities have equal-tailed 90% **conditional parameter credible intervals**. With `curves=true`, each event includes 61 posterior density points; density is not an event probability. The grid covers approximately the 0.5th to 99.5th percentiles, clipped away from 0/1 to avoid infinite endpoint densities.

The expected-run field caps the 7+ bucket at seven: it is a capped expectation, not an exact expected score or official strike-rate projection. Dots mean zero batter runs; byes/leg-byes may still score team runs. Wides/no-balls, extras, non-striker dismissals, retirements, wickets remaining, targets and innings completion are not modeled.

## Chronology and evidence

`as_of` is required. Training includes `as_of - 1461 days <= match_date < as_of`; every match on the target date is excluded. No illegal balls or Super Overs enter the model.

The pair model uses historical IDs, venue and fixed phase labels, not present-day rosters, roles, batting hand or ages. Bowling-type mode uses coarse enriched style/arm attributes whose historical effective dates are unknown; it is warned and not independently validated. Venue means scoring context, not measured pitch. No weather, injury, dew or fitness effects are invented. The fixed four-year window is not a fitted recent-form effect; form remains separately available as descriptive analytics.

For pair predictions, five disjoint pools prevent the target matchup entering its own prior:

| Pool | Observations |
| --- | --- |
| Background | Other batters vs other bowlers outside the selected context. |
| Context | Other batters vs other bowlers inside the context. |
| Batter | Requested batter vs other bowlers inside the context. |
| Bowler | Requested bowler vs other batters inside the context. |
| Target | Requested batter vs requested bowler inside the context. |

Requested-player observations outside the context are unused. Pool counts, training dates, prior probabilities and the direct-evidence weight are exposed for audit.

For vectors of 20 outcome counts, `normalize(v) = v / sum(v)`:

```text
league_mean  = normalize(background_counts + seed)
context_mean = normalize(context_counts + 120 * league_mean)
batter_mean  = normalize(batter_counts + 80 * context_mean)
bowler_mean  = normalize(bowler_counts + 80 * context_mean)
prior_mean   = (batter_mean + bowler_mean) / 2
alpha        = target_counts + 60 * prior_mean
predicted_joint_probabilities = alpha / sum(alpha)
```

The seed has concentration four: uniform run-bucket mass, a 5% dismissal marginal, and a 90% boundary flag conditional on four/six runs. These are disclosed weak assumptions, not learned facts. Without any retained IPL evidence, the API returns 503 rather than presenting the seed as player knowledge. Cold starts and weak population evidence are labelled.

For event categories E, the conditional posterior is `Beta(sum(alpha[E]), sum(alpha[not E]))`. Intervals use its 5th/95th percentiles. Direct-evidence weight is `target_sample / (target_sample + 60)`. Upstream prior means are plug-in estimates; their uncertainty is not integrated out. Intervals therefore do not represent all uncertainty or guarantee frequentist coverage.

Type-mode targets contain this batter's deliveries against the requested type/context. Its other-player population pools exclude that batter; it uses the context mean with strength 60, without a batter prior that would reuse target observations.

## Historical evaluation

The reproducible [backtest report](../outputs/bayesian-backtest.json) includes full calibration bins, baseline scores, sparse-sample segments, database/catalog hashes and timing. Run `scripts/backtest_bayesian.py` to regenerate it. This offline aggregation has a bounded 30-second SQL budget; API queries retain the five-second budget.

Evaluation specifies both phase and venue. Predictions are frozen before each date; after all matches on that date are scored, their evidence can inform later dates. This is rolling date-blocked evaluation, not within-match updating or a permanently frozen end-2024 model.

2024 selects matchup strength from 20, 60, 120 by joint log loss, selecting **60**. Context/player strengths (120/80), the window and seed were fixed. This served configuration was not chosen using 2025/2026 results. Baselines use the same chronological boundaries and lookback: smoothed league, phase/venue, and context-conditioned batter-only models. Lower log loss is better, not a percentage of matches predicted correctly.

| Holdout | Legal deliveries / matches | Bayesian | League | Phase/venue | Batter-only |
| --- | --- | --- | --- | --- | --- |
| 2025 | 16,507 / 74 | 1.510126 | 1.535594 | 1.512027 | 1.511691 |
| 2026 | 16,664 / 74 | 1.521060 | 1.543751 | 1.523755 | 1.522246 |

Gains over league/context baselines are positive in paired 95% match-cluster bootstrap intervals in both years. The 2026 gain over batter-only is just 0.001186, interval **-0.000357 to 0.002644**: a robust advantage over that stronger baseline is not established. Bootstrap uses 2,000 paired match resamples, seed 20261002, and does not capture all player/season dependence.

| Event | 2025 Brier | 2026 Brier | 2025 / 2026 calibration error |
| --- | --- | --- | --- |
| Boundary | 0.167479 | 0.173130 | 1.90 / 2.03 percentage points |
| Zero batter runs | 0.220170 | 0.221233 | 1.41 / 1.10 percentage points |
| Striker dismissal | 0.048306 | 0.048562 | 0.13 / 0.05 percentage points |

Calibration error is delivery-weighted absolute error across ten fixed bins. Boundaries underpredict in the heavily occupied bins. Rare-event scores and coarse dismissal bins do not establish exceptional discrimination. Discrete 90% Beta-binomial predictive count intervals cover approximately 97-98% of held-out groups, reflecting small samples and discrete intervals; this does not prove parameter credible-interval coverage.

Most exact-context targets have no direct history, and neither holdout has a 30+ direct-history segment. That segment's reliability is untested. Bowling-type and omitted-phase/venue modes are also unvalidated; the API flags them.

## API and remaining work

```text
GET /api/v1/predictions/matchup?batter_id=<id>&bowler_id=<id>&as_of=2026-10-02&phase=powerplay&venue_id=<id>&curves=true
GET /api/v1/predictions/bowling-type?batter_id=<id>&category=spin&arm=left&as_of=2026-10-02
```

Use canonical IDs from browse endpoints. Display the named event, legal-delivery conditioning, experimental status, sample count, uncertainty range, training cutoff and warnings. Do not label the output a generic "player success chance" or confirmation of eligibility. Invalid parameters return 422, unknown IDs 404, unavailable evidence 503. `curves` defaults to false. Inference is read-only and does not load unsafe pickled model artifacts.

Before production recommendations: prospective testing, sensitivity checks, validation of other context modes, historically valid type labels, fitted form/state effects and propagation of upstream uncertainty. The simulator and constrained XI optimizer are implemented, with reliability audits and an optional delivery correction; full-match calibration and verified eligibility remain outstanding. `production_validated_predictions` remains false. Delivery calibration results must not be represented as match-win accuracy.

Implementation references: [Dirichlet distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.dirichlet.html), [Beta quantiles](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.beta.html), [Beta-binomial counts](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.betabinom.html).
