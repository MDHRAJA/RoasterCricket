"""Conditional empirical-Bayes Dirichlet model for the next legal IPL delivery.

Evidence pools are disjoint. Upstream distributions are plug-in prior means;
intervals condition on those means, rather than claiming full hierarchical inference.
"""

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import numpy as np
from scipy.stats import beta

from backend.services import ApiError

MODEL_VERSION = "legal-delivery-eb-v1"
# Run slots separate actual recorded boundaries from non-boundary fours/sixes.
RUN_SLOTS = ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (4, 1), (5, 0), (6, 0), (6, 1), (7, 0))
OUTCOMES = tuple(
    (runs, boundary, dismissed) for runs, boundary in RUN_SLOTS for dismissed in (0, 1)
)
K = len(OUTCOMES)
EVENT_MASKS = {
    "boundary": np.array([bool(b) for r, b, d in OUTCOMES]),
    "dot": np.array([r == 0 for r, b, d in OUTCOMES]),
    "striker_dismissal": np.array([bool(d) for r, b, d in OUTCOMES]),
}
# Weak seed: concentration 4; uniform run buckets, 5% dismissal and 90% of
# recorded four/six outcomes marked boundaries. Never served without IPL evidence.
SEED = np.array(
    [
        0.5 * (0.05 if dismissed else 0.95) * ((0.9 if boundary else 0.1) if runs in (4, 6) else 1)
        for runs, boundary, dismissed in OUTCOMES
    ]
)


@dataclass(frozen=True)
class ModelConfig:
    context_strength: float = 120
    player_strength: float = 80
    matchup_strength: float = 60
    lookback_days: int = 1461

    def __post_init__(self):
        if any(
            not np.isfinite(v) or v <= 0
            for v in (self.context_strength, self.player_strength, self.matchup_strength)
        ):
            raise ValueError("Prior strengths must be positive and finite")
        if not 1 <= self.lookback_days <= 7305:
            raise ValueError("Invalid lookback window")


DEFAULT_CONFIG = ModelConfig()


def outcome_index(runs: int, boundary: int, dismissed: int) -> int:
    if runs < 0 or dismissed not in (0, 1) or boundary not in (0, 1):
        raise ValueError("Invalid delivery outcome")
    run_bucket = min(runs, 7)
    return RUN_SLOTS.index((run_bucket, boundary)) * 2 + dismissed


def posterior(pools: dict[str, np.ndarray], config=DEFAULT_CONFIG, *, mode="matchup"):
    """Return final alpha and auditable component prior means; no random draws."""
    for counts in pools.values():
        if counts.shape != (K,) or not np.all(np.isfinite(counts)) or np.any(counts < 0):
            raise ValueError("Invalid evidence counts")
    if sum(float(v.sum()) for v in pools.values()) == 0:
        raise ApiError(
            503,
            "no_training_evidence",
            "No eligible IPL deliveries before this cutoff in the model window",
        )
    outside = pools["background"] + SEED
    league_mean = outside / outside.sum()
    context = pools["context"] + config.context_strength * league_mean
    context_mean = context / context.sum()
    if mode == "matchup":
        batter = pools["batter"] + config.player_strength * context_mean
        bowler = pools["bowler"] + config.player_strength * context_mean
        prior_mean = (batter / batter.sum() + bowler / bowler.sum()) / 2
    else:
        # Type targets already include every observation by this batter in the
        # requested type/context. Do not reuse them as a batter prior.
        prior_mean = context_mean
    alpha = config.matchup_strength * prior_mean + pools["target"]
    return alpha, {"league": league_mean, "context": context_mean, "target_prior": prior_mean}


def interval(a: float, b: float):
    lower, upper = beta.ppf([0.05, 0.95], a, b)
    return {
        "level": 0.90,
        "lower": float(lower),
        "upper": float(upper),
        "interpretation": "conditional_parameter_credible_interval",
    }


def summarize(alpha: np.ndarray, target: np.ndarray, *, curves=False):
    total, sample = float(alpha.sum()), int(target.sum())
    events = {}
    for name, mask in EVENT_MASKS.items():
        a = float(alpha[mask].sum())
        b = total - a
        events[name] = {
            "probability": a / total,
            "observed_successes": int(target[mask].sum()),
            "observed_deliveries": sample,
            "posterior_alpha": a,
            "posterior_beta": b,
            "credible_interval": interval(a, b),
        }
        if curves:
            # Quantile range avoids infinite endpoint densities and captures narrow peaks.
            x = np.linspace(beta.ppf(0.005, a, b), beta.ppf(0.995, a, b), 61)
            x = np.clip(x, 1e-12, 1 - 1e-12)
            y = beta.pdf(x, a, b)
            events[name]["density_curve"] = [
                {"probability": float(px), "density": float(py)}
                for px, py in zip(x, y, strict=True)
            ]
    run_distribution = []
    for run in range(8):
        mask = np.array([r == run for r, boundary, dismissed in OUTCOMES])
        a = float(alpha[mask].sum())
        run_distribution.append(
            {
                "batter_runs": str(run) if run < 7 else "7+",
                "probability": a / total,
                "observed_deliveries": int(target[mask].sum()),
                "credible_interval": interval(a, total - a),
            }
        )
    return {
        "events": events,
        "run_distribution": run_distribution,
        "expected_capped_batter_runs_per_legal_delivery": float(
            sum(r * p for (r, b, d), p in zip(OUTCOMES, alpha / total, strict=True))
        ),
        "joint_outcomes": [
            {
                "batter_runs": str(r) if r < 7 else "7+",
                "boundary": bool(b),
                "striker_dismissed": bool(d),
                "probability": float(a / total),
            }
            for (r, b, d), a in zip(OUTCOMES, alpha, strict=True)
        ],
    }


class PredictionService:
    def __init__(self, analytics, config=DEFAULT_CONFIG):
        self.analytics, self.config = analytics, config

    def predict(
        self,
        batter_id,
        *,
        as_of: date,
        bowler_id=None,
        category=None,
        arm=None,
        phase=None,
        venue_id=None,
        curves=False,
    ):
        self.analytics.require("player", batter_id)
        if bowler_id:
            self.analytics.require("player", bowler_id)
            if bowler_id == batter_id:
                raise ApiError(422, "self_matchup", "A player cannot face themselves")
        if venue_id:
            self.analytics.require("venue", venue_id)
        if (bowler_id is None) == (category is None):
            raise ValueError("Specify exactly one opponent mode")
        start = (as_of - timedelta(days=self.config.lookback_days)).isoformat()
        context_clauses, context_params = [], []
        for key, value in (
            ("phase", phase),
            ("venue_id", venue_id),
            ("bowling_category", category),
            ("bowling_arm", arm),
        ):
            if value is not None:
                context_clauses.append(key + "=?")
                context_params.append(str(value))
        ctx = " AND ".join(context_clauses) or "1=1"
        if bowler_id is not None:
            pool_sql = "CASE WHEN in_context AND batter_id=? AND bowler_id=? THEN 'target' WHEN in_context AND batter_id=? THEN 'batter' WHEN in_context AND bowler_id=? THEN 'bowler' WHEN batter_id<>? AND bowler_id<>? THEN CASE WHEN in_context THEN 'context' ELSE 'background' END ELSE 'unused' END"
            identity_params = [batter_id, bowler_id, batter_id, bowler_id, batter_id, bowler_id]
        else:
            pool_sql = "CASE WHEN in_context AND batter_id=? THEN 'target' WHEN batter_id<>? THEN CASE WHEN in_context THEN 'context' ELSE 'background' END ELSE 'unused' END"
            identity_params = [batter_id, batter_id]
        # The pool partition is exhaustive and disjoint; target observations
        # cannot appear in the learned background/context/player prior.
        sql = f"""WITH eligible AS (
            SELECT *, ({ctx}) AS in_context FROM deliveries
            WHERE is_super_over=0 AND legal_ball=1 AND match_date>=? AND match_date<?
        ), partitioned AS (SELECT *,{pool_sql} AS pool FROM eligible)
        SELECT pool,MIN(batter_runs,7) AS runs,CASE WHEN four=1 OR six=1 THEN 1 ELSE 0 END AS boundary,
        striker_dismissed,COUNT(*) AS n,MIN(match_date) AS first_date,MAX(match_date) AS last_date,
        SUM(bowling_metadata_conflict) AS style_conflicts
        FROM partitioned WHERE pool<>'unused' GROUP BY pool,runs,boundary,striker_dismissed"""
        rows = self.analytics.rows(
            sql, [*context_params, start, as_of.isoformat(), *identity_params]
        )
        pools = {
            key: np.zeros(K) for key in ("background", "context", "batter", "bowler", "target")
        }
        for row in rows:
            pools[row["pool"]][
                outcome_index(row["runs"], row["boundary"], row["striker_dismissed"])
            ] += row["n"]
        mode = "matchup" if bowler_id else "bowling_type"
        alpha, priors = posterior(pools, self.config, mode=mode)
        warnings = [
            "experimental_prediction_not_production_validated",
            "intervals_condition_on_empirical_prior",
            "legal_deliveries_only_no_extras_or_super_overs",
            "not_an_innings_or_match_win_prediction",
            "no_pitch_weather_or_injury_effects",
            "four_year_window_not_fitted_recent_form_effect",
            "seven_plus_runs_bucket_is_capped_for_expectation",
        ]
        n = int(pools["target"].sum())
        if n < 30:
            warnings.append("sparse_target_evidence_shrunk_to_prior")
        if n == 0:
            warnings.append("no_direct_history_prior_only_prediction")
        if sum(pools[key].sum() for key in ("background", "context")) < 100:
            warnings.append("weak_population_evidence")
        if phase:
            warnings.append("fixed_20_over_phases_not_rescaled_for_shortened_games")
        if venue_id:
            warnings.append("venue_is_scoring_context_not_measured_pitch")
        if category:
            warnings.extend(
                [
                    "career_bowling_category_not_per_delivery_variation",
                    "profile_attributes_not_time_versioned_type_backtest_not_leakage_free",
                ]
            )
            if any(r["style_conflicts"] for r in rows):
                warnings.append("bowling_style_source_conflict_in_training")
        if phase is None or venue_id is None:
            warnings.append(
                "backtest_scope_requires_both_phase_and_venue_other_context_modes_unvalidated"
            )
        first, last = min(r["first_date"] for r in rows), max(r["last_date"] for r in rows)
        if (as_of - date.fromisoformat(last)).days > 180:
            warnings.append("training_data_stale_for_requested_date")
        result = {
            "model_version": MODEL_VERSION,
            "status": "experimental",
            "batter_id": batter_id,
            "bowler_id": bowler_id,
            "as_of": as_of,
            "context": {
                "phase": phase,
                "venue_id": venue_id,
                "bowling_category": category,
                "bowling_arm": arm,
            },
            "training": {
                "window_start": start,
                "exclusive_cutoff": as_of,
                "first_included_date": first,
                "last_included_date": last,
                "disjoint_pool_deliveries": {k: int(v.sum()) for k, v in pools.items()},
                "prior_strength": self.config.matchup_strength,
                "direct_evidence_weight": n / (n + self.config.matchup_strength),
                "configuration": asdict(self.config),
            },
            "prior_event_probabilities": {
                name: float(priors["target_prior"][mask].sum())
                for name, mask in EVENT_MASKS.items()
            },
            **summarize(alpha, pools["target"], curves=curves),
        }
        from backend.delivery_calibration import CALIBRATION_CUTOFF, forecast

        if as_of < CALIBRATION_CUTOFF:
            warnings.append(
                "raw_hyperparameters_selected_using_2024_not_prospective_for_earlier_cutoffs"
            )

        result["calibrated_forecast"] = forecast(
            alpha / alpha.sum(),
            as_of,
            supported_context=bool(
                bowler_id and phase and venue_id and self.config == DEFAULT_CONFIG
            ),
        )
        if result["calibrated_forecast"]["status"] != "not_applied":
            warnings.append("corrected_forecast_separate_from_raw_posterior_credible_intervals")
        return result, warnings
