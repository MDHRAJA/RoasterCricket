"""Full two-innings evaluation and development-only recalibration diagnostics."""

from collections import Counter
from datetime import date
from types import SimpleNamespace

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from backend.historical_planning import population_plan
from backend.reliability_backtesting import paired_gain, win_metrics

PROTOCOL_VERSION = "full-match-date-blocked-observed-pool-v1"
VARIANTS = ("population", "participant_raw", "participant_delivery_corrected")


def offline_request(case, plans, simulations, seed, corrected=False):
    """Not the public 2026 roster contract: no current-roster validation bypass in API."""
    return SimpleNamespace(
        season=case["season"],
        as_of=date.fromisoformat(case["date"]),
        venue_id=case["venue_id"],
        team_a=plans[case["team_a_id"]],
        team_b=plans[case["team_b_id"]],
        batting_first_team_id=case["batting_first_team_id"],
        simulations=simulations,
        seed=seed,
        sample_posterior=True,
        use_delivery_calibration=corrected,
        include_sample_match=False,
        allow_unknown_availability=True,
        max_super_overs=0,
    )


def anonymous_plans(case):
    return {team: population_plan(team) for team in (case["team_a_id"], case["team_b_id"])}


def prediction_record(case, result, variant, strategies=None):
    a, b = case["team_a_id"], case["team_b_id"]
    k = result["outcomes"][a]["count"]
    decisive = k + result["outcomes"][b]["count"]
    if decisive == 0:
        raise ValueError("No decisive Monte Carlo trials; cannot score conditional win probability")
    training = result["training"]
    if training["last_included_date"] >= case["date"]:
        raise AssertionError("Future or same-day evidence entered a match forecast")
    record = {
        "match_id": case["match_id"],
        "date": case["date"],
        "season": case["season"],
        "variant": variant,
        "team_a_id": a,
        "team_b_id": b,
        "team_a_is_batting_first": True,
        "venue_id": case["venue_id"],
        "probability": (k + 0.5) / (decisive + 1),
        "raw_conditional_probability": k / decisive,
        "probability_estimator": "Jeffreys_half_count_smoothing_of_decisive_Monte_Carlo_counts",
        "outcome": int(case["actual"]["winner_id"] == a),
        "winning_trials": k,
        "decisive_trials": decisive,
        "regular_tie_probability": result["outcomes"]["regular_tie_probability"],
        "sampling_interval": result["outcomes"][a]["sampling_interval"],
        "sampling_interval_scope": "unconditional_team_win_mass_not_decisive_conditional_probability",
        "latest_training_date": training["last_included_date"],
        "window_start": training["window_start"],
        "delivery_calibration": training["delivery_calibration"],
        "strategies": strategies,
        "exposures": result["reliability"]["evidence"].get("simulated_legal_delivery_exposures"),
        "first_innings": {
            **result["innings"][0],
            "actual_runs": case["actual"]["first_runs"],
            "actual_wickets": case["actual"]["first_wickets"],
        },
        "second_innings": {
            **result["innings"][1],
            "actual_runs": case["actual"]["second_runs"],
            "actual_wickets": case["actual"]["second_wickets"],
            "scope": "joint_unconditional_chase_score_NOT_conditional_on_actual_target",
        },
    }
    if strategies:
        for strategy in strategies.values():
            latest = strategy["latest_strategy_evidence_date"]
            if latest is not None and latest >= case["date"]:
                raise AssertionError("Target match entered a historical strategy")
    return record


def innings_metrics(records, key="first_innings"):
    if not records:
        return {"innings": 0}
    rows = [r[key] for r in records]
    residual = np.array([r["mean_runs"] - r["actual_runs"] for r in rows])
    result = {
        "innings": len(rows),
        "mae_runs": float(np.abs(residual).mean()),
        "rmse_runs": float(np.sqrt(np.mean(residual**2))),
        "mean_bias_runs": float(residual.mean()),
        "mean_wicket_bias": float(np.mean([r["mean_wickets"] - r["actual_wickets"] for r in rows])),
        "mean_runs_mc_standard_error": float(
            np.mean([r["mean_runs_mc_standard_error"] for r in rows])
        ),
        "predictive_coverage": {},
        "mean_interval_width": {},
    }
    for level, low, high in (("0.8", "p10", "p90"), ("0.9", "p05", "p95")):
        intervals = [(r["score_quantiles"][low], r["score_quantiles"][high]) for r in rows]
        result["predictive_coverage"][level] = float(
            np.mean(
                [
                    lower <= row["actual_runs"] <= upper
                    for row, (lower, upper) in zip(rows, intervals, strict=True)
                ]
            )
        )
        result["mean_interval_width"][level] = float(np.mean([hi - lo for lo, hi in intervals]))
    return result


def fit_win_correction(records):
    """Two fixed-penalty coefficients; development diagnostic, never auto-promoted."""
    if len(records) < 20:
        return {"status": "insufficient_development_matches", "matches": len(records)}
    p = np.clip([r["probability"] for r in records], 1e-6, 1 - 1e-6)
    x = np.column_stack([np.ones(len(p)), np.log(p / (1 - p))])
    y = np.array([r["outcome"] for r in records])
    penalty = 4.0

    def objective(theta):
        z = x @ theta
        delta = theta - np.array([0.0, 1.0])
        loss = np.sum(np.logaddexp(0, z) - y * z) + penalty * np.dot(delta, delta) / 2
        gradient = x.T @ (expit(z) - y) + penalty * delta
        return float(loss), gradient

    fitted = minimize(
        objective, [0.0, 1.0], jac=True, method="L-BFGS-B", bounds=[(-0.7, 0.7), (0, 2)]
    )
    if not fitted.success:
        raise RuntimeError("Match correction fitting failed")
    return {
        "status": "diagnostic_only_not_served",
        "intercept": float(fitted.x[0]),
        "logit_scale": float(fitted.x[1]),
        "development_matches": len(records),
        "latest_development_date": max(r["date"] for r in records),
        "l2_penalty": penalty,
        "exclusive_fit_cutoff": "2025-01-01",
        "automatic_promotion": False,
    }


def corrected_win_records(records, fitted):
    if "intercept" not in fitted:
        return []
    result = []
    for r in records:
        if r["date"] < fitted["exclusive_fit_cutoff"]:
            raise ValueError("Diagnostic win correction cannot evaluate fitting-period games")
        p = np.clip(r["probability"], 1e-6, 1 - 1e-6)
        q = float(expit(fitted["intercept"] + fitted["logit_scale"] * np.log(p / (1 - p))))
        result.append({**r, "probability": q})
    return result


def fit_score_correction(records):
    """2024-only location/interval-scale diagnostic; not a physical match model."""
    if len(records) < 20:
        return {"status": "insufficient_development_matches", "matches": len(records)}
    rows = [r["first_innings"] for r in records]
    bias = float(np.clip(np.mean([r["actual_runs"] - r["mean_runs"] for r in rows]), -40, 40))
    errors = []
    for row in rows:
        residual = row["actual_runs"] - row["mean_runs"] - bias
        quantile = "p95" if residual >= 0 else "p05"
        half_width = max(1.0, abs(row["score_quantiles"][quantile] - row["mean_runs"]))
        errors.append(abs(residual) / half_width)
    # Predeclared finite-sample rank; time dependence means NO conformal guarantee.
    rank = min(len(errors), int(np.ceil((len(errors) + 1) * 0.9)))
    scale = float(np.clip(sorted(errors)[rank - 1], 0.5, 3))
    return {
        "status": "diagnostic_only_not_served",
        "mean_shift_runs": bias,
        "interval_scale": scale,
        "development_matches": len(records),
        "latest_development_date": max(r["date"] for r in records),
        "exclusive_fit_cutoff": "2025-01-01",
        "bounds": {"mean_shift_runs": [-40, 40], "interval_scale": [0.5, 3]},
        "scope": "first_innings_distribution_only_not_a_rerun_or_win_probability_correction",
        "coverage_guaranteed": False,
        "automatic_promotion": False,
    }


def corrected_score_records(records, fitted):
    if "mean_shift_runs" not in fitted:
        return []
    result = []
    for r in records:
        if r["date"] < fitted["exclusive_fit_cutoff"]:
            raise ValueError("Diagnostic score correction cannot evaluate fitting-period games")
        row = r["first_innings"]
        mean = max(0.0, row["mean_runs"] + fitted["mean_shift_runs"])
        quantiles = {
            k: max(0.0, mean + fitted["interval_scale"] * (q - row["mean_runs"]))
            for k, q in row["score_quantiles"].items()
        }
        result.append(
            {**r, "first_innings": {**row, "mean_runs": mean, "score_quantiles": quantiles}}
        )
    return result


def batting_first_baseline(cases, target):
    start = target["window_start"]
    earlier = [c for c in cases if start <= c["date"] < target["date"]]
    wins = sum(c["actual"]["winner_id"] == c["team_a_id"] for c in earlier)
    return {**target, "probability": (wins + 5) / (len(earlier) + 10)}


def summarize(records, cases, simulations):
    development = {
        name: [r for r in records if r["season"] == 2024 and r["variant"] == name]
        for name in VARIANTS
    }
    fits = {name: fit_win_correction(rows) for name, rows in development.items()}
    score_fits = {name: fit_score_correction(rows) for name, rows in development.items()}
    seasons = sorted({r["season"] for r in records})
    results = {}
    for season in seasons:
        variants = {}
        for name in VARIANTS:
            rows = [r for r in records if r["season"] == season and r["variant"] == name]
            if not rows:
                continue
            neutral = [{**r, "probability": 0.5} for r in rows]
            order = [batting_first_baseline(cases, r) for r in rows]
            calibrated = corrected_win_records(rows, fits[name]) if season >= 2025 else []
            score_calibrated = (
                corrected_score_records(rows, score_fits[name]) if season >= 2025 else []
            )
            variants[name] = {
                "win_metrics": win_metrics(rows),
                "first_innings_metrics": innings_metrics(rows),
                "second_innings_metrics": innings_metrics(rows, "second_innings"),
                "neutral_win_metrics": win_metrics(neutral),
                "prior_only_batting_first_baseline_metrics": win_metrics(order),
                "paired_win_gain_vs_neutral": {
                    metric: paired_gain(rows, neutral, metric) for metric in ("brier", "log_loss")
                },
                "paired_win_gain_vs_batting_first": {
                    metric: paired_gain(rows, order, metric) for metric in ("brier", "log_loss")
                },
                "mean_simulated_regular_tie_probability": float(
                    np.mean([r["regular_tie_probability"] for r in rows])
                ),
                "mean_unconditional_win_sampling_interval_half_width": float(
                    np.mean(
                        [
                            (r["sampling_interval"]["upper"] - r["sampling_interval"]["lower"]) / 2
                            for r in rows
                        ]
                    )
                ),
            }
            if calibrated:
                variants[name]["development_fitted_win_correction"] = {
                    "metrics": win_metrics(calibrated),
                    "paired_gain_vs_uncorrected": {
                        metric: paired_gain(calibrated, rows, metric)
                        for metric in ("brier", "log_loss")
                    },
                    "promotion": "not_served_requires_prospective_and_verified_lineup_validation",
                }
            if score_calibrated:
                variants[name]["development_fitted_first_innings_correction"] = {
                    "metrics": innings_metrics(score_calibrated),
                    "promotion": "not_served_no_temporal_coverage_guarantee",
                }
        raw = [r for r in records if r["season"] == season and r["variant"] == "participant_raw"]
        matched = {}
        if raw:
            ids = {r["match_id"] for r in raw}
            for name in ("population", "participant_delivery_corrected"):
                comparison = [
                    r
                    for r in records
                    if r["season"] == season and r["variant"] == name and r["match_id"] in ids
                ]
                if len(comparison) == len(raw):
                    matched[name] = {
                        "matches": len(raw),
                        "compared_win_metrics": win_metrics(comparison),
                        "raw_win_gain_vs_compared": {
                            metric: paired_gain(raw, comparison, metric)
                            for metric in ("brier", "log_loss")
                        },
                    }
        results[str(season)] = {
            "variants": variants,
            "matched_participant_cohort_comparisons": matched,
        }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "status": "completed_retrospective_diagnostic_not_prospective_validation",
        "simulations_per_match_per_variant": simulations,
        "development_season": 2024,
        "evaluation_seasons": [year for year in seasons if year >= 2025],
        "cohort_counts": dict(Counter((r["variant"] for r in records))),
        "win_correction_fits_development_only": fits,
        "score_correction_fits_development_only": score_fits,
        "results_by_season": results,
        "predictions": records,
        "limitations": [
            "Participant models condition on post-match observed participant pools, NOT verified announced XIs.",
            "Participant strategies are hypothetical interval swaps/order/schedules selected solely from earlier usage; actual tactical choices are not reconstructed.",
            "Historical overseas/registration/concussion eligibility and actual impact timing are not validated.",
            "Population forecasts do not use participant identities; they are post-toss, venue/phase-only complete two-innings simulations.",
            "Both models lack learned score pressure, pitch, weather and dated injury information.",
            "2024 delivery hyperparameters and correction were already selected/fitted on 2024; 2024 match results are development diagnostics.",
            "2025/2026 archive data were previously inspected for other model diagnostics; these are retrospective evaluations, not newly untouched data.",
            "Win metrics condition on decisive outcomes and exclude observed ties/super overs/no-results; simulated ties are retained and reported separately.",
            "Finite Monte Carlo estimates add scoring noise; half-count smoothing prevents infinite estimated log loss, not model misspecification.",
            "Second-innings scores are unconditional joint predictions with simulated targets; they are not forecasts conditioned on the observed first-innings target.",
            "Date-cluster bootstrap intervals do not capture all team/season dependencies or model-selection uncertainty.",
            "No XI counterfactual benefit or global win-optimality is established; challenger corrections are not automatically served.",
        ],
    }
