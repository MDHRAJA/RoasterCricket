"""Chronological benchmark evaluation: tune 2024 only, report 2025/26 separately."""

from dataclasses import asdict, replace
from datetime import date

import numpy as np
from scipy.stats import t

from backend.reliability import (
    DEFAULT_BENCHMARK,
    BenchmarkConfig,
    before_window,
    decisive,
    predictive_score,
    win_probability,
)


def win_metrics(records):
    if not records:
        return {"matches": 0}
    p = np.clip(np.array([r["probability"] for r in records]), 1e-9, 1 - 1e-9)
    y = np.array([r["outcome"] for r in records])
    buckets, calibration = [], 0.0
    indices = np.minimum(9, np.floor(p * 10).astype(int))
    for index in range(10):
        lower = index / 10
        mask = indices == index
        if not mask.any():
            continue
        count = int(mask.sum())
        expected, actual = float(p[mask].mean()), float(y[mask].mean())
        calibration += count * abs(expected - actual) / len(p)
        buckets.append(
            {
                "lower": float(lower),
                "upper_exclusive": (index + 1) / 10,
                "matches": count,
                "mean_probability": expected,
                "observed_win_frequency": actual,
            }
        )
    correct = np.where(p == 0.5, 0.5, ((p > 0.5) == y).astype(float))
    return {
        "matches": len(p),
        "brier_score": float(np.mean((p - y) ** 2)),
        "log_loss": float(np.mean(-y * np.log(p) - (1 - y) * np.log1p(-p))),
        "top_pick_accuracy_with_half_credit_for_50_percent_ties": float(correct.mean()),
        "calibration_error_10_bins": float(calibration),
        "calibration_bins": buckets,
        "accuracy_note": "threshold classification is not probability calibration; bins may be very sparse",
    }


def score_metrics(records):
    if not records:
        return {"innings": 0}
    residual = np.array([r["predicted_mean"] - r["actual_runs"] for r in records])
    return {
        "innings": len(records),
        "mae_runs": float(np.abs(residual).mean()),
        "rmse_runs": float(np.sqrt(np.mean(residual**2))),
        "mean_bias_runs": float(residual.mean()),
        "mean_negative_log_density": float(np.mean([r["negative_log_density"] for r in records])),
        "predictive_coverage": {
            str(level): float(np.mean([r[f"covered_{level}"] for r in records]))
            for level in (0.8, 0.9)
        },
        "mean_interval_width": {
            str(level): float(np.mean([r[f"width_{level}"] for r in records]))
            for level in (0.8, 0.9)
        },
    }


def score_record(row, distribution, cutoff):
    actual = row["first_innings_runs"]
    result = {
        "match_id": row["match_id"],
        "date": row["match_date"],
        "latest_training_date": cutoff,
        "actual_runs": actual,
        "predicted_mean": distribution["mean_runs"],
        "negative_log_density": float(
            -t.logpdf(
                actual,
                distribution["degrees_of_freedom"],
                loc=distribution["mean_runs"],
                scale=distribution["scale"],
            )
        ),
    }
    for level in (0.8, 0.9):
        interval = distribution["predictive_intervals"][str(level)]
        result[f"covered_{level}"] = interval["lower"] <= actual <= interval["upper"]
        result[f"width_{level}"] = interval["upper"] - interval["lower"]
    return result


def paired_gain(model, baseline, kind="log_loss"):
    if len(model) != len(baseline) or not model:
        raise ValueError("Paired comparison requires nonempty aligned predictions")
    grouped = {}

    def loss(record):
        p = min(1 - 1e-9, max(1e-9, record["probability"]))
        y = record["outcome"]
        return (p - y) ** 2 if kind == "brier" else -y * np.log(p) - (1 - y) * np.log1p(-p)

    for a, b in zip(model, baseline, strict=True):
        if a["match_id"] != b["match_id"]:
            raise ValueError("Unaligned match predictions")
        totals = grouped.setdefault(a["date"], [0.0, 0])
        totals[0] += loss(b) - loss(a)
        totals[1] += 1
    values = np.array(list(grouped.values()))
    rng = np.random.default_rng(20261002)
    samples = values[rng.integers(len(values), size=(2000, len(values)))]
    means = samples[:, :, 0].sum(axis=1) / samples[:, :, 1].sum(axis=1)
    return {
        "mean_gain": float(values[:, 0].sum() / values[:, 1].sum()),
        "95_percent_date_cluster_interval": [float(x) for x in np.quantile(means, [0.025, 0.975])],
        "interpretation": "positive favors selected model; interval does not capture all season/team dependence",
    }


def evaluate(rows, validation_season=2024, test_seasons=(2025, 2026)):
    if not test_seasons or any(year <= validation_season for year in test_seasons):
        raise ValueError("Holdout seasons must follow validation")
    candidates = [
        BenchmarkConfig(k=k, season_carry=carry, temperature=temp)
        for k in (10, 20, 40)
        for carry in (0.5, 1.0)
        for temp in (1.0, 2.0)
    ]
    candidates += [BenchmarkConfig(family="neutral"), BenchmarkConfig(family="form")]
    validation_wins = [[] for _ in candidates]
    strengths = (5, 10, 20)
    validation_scores = {strength: [] for strength in strengths}
    validation_rows = [r for r in rows if int(r["season"]) == validation_season]
    for r in validation_rows:
        history = before_window(rows, date.fromisoformat(r["match_date"]))
        latest = max((x["match_date"] for x in history), default=None)
        if latest is not None and latest >= r["match_date"]:
            raise AssertionError("Same-day/future leakage")
        if decisive(r):
            for i, config in enumerate(candidates):
                p, _ = win_probability(
                    history, r["team1_id"], r["team2_id"], validation_season, config
                )
                validation_wins[i].append(
                    {
                        "match_id": r["match_id"],
                        "date": r["match_date"],
                        "latest_training_date": latest,
                        "probability": p,
                        "outcome": int(r["winner_id"] == r["team1_id"]),
                    }
                )
        distributions = {s: predictive_score(history, r["venue_id"], s) for s in strengths}
        if all(d is not None for d in distributions.values()):
            for strength, distribution in distributions.items():
                validation_scores[strength].append(score_record(r, distribution, latest))
    if len(validation_wins[0]) < 20 or len(validation_scores[5]) < 20:
        raise ValueError("At least twenty validation games/innings required")
    winner = min(range(len(candidates)), key=lambda i: win_metrics(validation_wins[i])["log_loss"])
    strength = min(
        strengths, key=lambda s: score_metrics(validation_scores[s])["mean_negative_log_density"]
    )
    selected = replace(candidates[winner], score_strength=strength)
    holdout = {}
    for season in test_seasons:
        models = {
            "selected": selected,
            "neutral": BenchmarkConfig(family="neutral"),
            "smoothed_form": BenchmarkConfig(family="form"),
            "untempered_elo": BenchmarkConfig(k=20, season_carry=1, temperature=1),
        }
        wins = {name: [] for name in models}
        scores = {name: [] for name in ("venue", "global")}
        for r in rows:
            if int(r["season"]) != season:
                continue
            history = before_window(rows, date.fromisoformat(r["match_date"]))
            latest = max((x["match_date"] for x in history), default=None)
            if latest is not None and latest >= r["match_date"]:
                raise AssertionError("Same-day/future leakage")
            if decisive(r):
                for name, config in models.items():
                    p, _ = win_probability(history, r["team1_id"], r["team2_id"], season, config)
                    wins[name].append(
                        {
                            "match_id": r["match_id"],
                            "date": r["match_date"],
                            "latest_training_date": latest,
                            "probability": p,
                            "outcome": int(r["winner_id"] == r["team1_id"]),
                        }
                    )
            venue = predictive_score(history, r["venue_id"], selected.score_strength)
            global_distribution = predictive_score(history, r["venue_id"], global_only=True)
            if venue is not None and global_distribution is not None:
                scores["venue"].append(score_record(r, venue, latest))
                scores["global"].append(score_record(r, global_distribution, latest))
        if not wins["selected"] or not scores["venue"]:
            raise ValueError("Every holdout must contain evaluated games/innings")
        holdout[str(season)] = {
            "win_metrics": {name: win_metrics(predictions) for name, predictions in wins.items()},
            "win_comparisons": {
                name: {
                    metric: paired_gain(wins["selected"], wins[name], metric)
                    for metric in ("log_loss", "brier")
                }
                for name in models
                if name != "selected"
            },
            "score_metrics": {
                name: score_metrics(predictions) for name, predictions in scores.items()
            },
            "predictions": {"win": wins, "score": scores},
        }
    return {
        "protocol": "date_blocked_pre_match_rolling_4_year_window",
        "validation_season": validation_season,
        "test_seasons": list(test_seasons),
        "selected_configuration": asdict(selected),
        "served_configuration": asdict(DEFAULT_BENCHMARK),
        "selection_metrics": {
            "wins": "validation_log_loss_including_neutral_fallback",
            "scores": "validation_negative_log_predictive_density",
        },
        "validation_candidates": [
            {"configuration": asdict(c), "metrics": win_metrics(records)}
            for c, records in zip(candidates, validation_wins, strict=True)
        ],
        "validation_score_strengths": {
            str(s): score_metrics(records) for s, records in validation_scores.items()
        },
        "holdout": holdout,
        "limitations": [
            "benchmark_backtest_not_full_match_simulator_or_XI_validation",
            "no_lineup_toss_injury_or_weather_inputs",
            "normal_first_innings_and_no_DLS_screen_not_complete_historical_rules_reconstruction",
            "win_probabilities_condition_on_decisive_outcomes_no_tie_or_no_result_model",
            "current_metadata_rosters_not_used",
            "prequential_evidence_updates_after_dates_but_hyperparameters_frozen",
            "small_holdouts_and_sparse_calibration_bins",
            "bootstrap_does_not_model_all_team_season_dependence",
            "conditional_empirical_score_prior_uncertainty_not_propagated",
            "continuous_score_distribution_not_physical_score_generator",
        ],
    }
