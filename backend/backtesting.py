"""Date-blocked prequential evaluation; never update from the prediction day."""

from collections import defaultdict, deque
from datetime import date, timedelta
from itertools import groupby

import numpy as np
from scipy.stats import betabinom

from backend.bayesian import (
    DEFAULT_CONFIG,
    EVENT_MASKS,
    OUTCOMES,
    SEED,
    K,
    ModelConfig,
    outcome_index,
    posterior,
)


class RollingIndex:
    """Sufficient statistics; SQL and this evaluator share disjoint-pool equations."""

    def __init__(self):
        self.maps = [defaultdict(lambda: np.zeros(K)) for _ in range(8)]

    def add(self, batter, bowler, context, counts, sign=1):
        keys = (
            None,
            context,
            batter,
            bowler,
            (batter, bowler),
            (context, batter),
            (context, bowler),
            (context, batter, bowler),
        )
        for mapping, key in zip(self.maps, keys, strict=True):
            mapping[key] += sign * counts
            if not np.any(mapping[key]):
                del mapping[key]

    def get(self, number, key):
        return self.maps[number].get(key, np.zeros(K))

    def pools(self, batter, bowler, context):
        all_counts = self.get(0, None)
        ctx = self.get(1, context)
        b_all, w_all = self.get(2, batter), self.get(3, bowler)
        pair_all = self.get(4, (batter, bowler))
        b_ctx, w_ctx = self.get(5, (context, batter)), self.get(6, (context, bowler))
        target = self.get(7, (context, batter, bowler))
        ctx_other = ctx - b_ctx - w_ctx + target
        return {
            "target": target,
            "batter": b_ctx - target,
            "bowler": w_ctx - target,
            "context": ctx_other,
            "background": all_counts - b_all - w_all + pair_all - ctx_other,
        }

    def baselines(self, batter, context):
        all_counts = self.get(0, None) + SEED
        league = all_counts / all_counts.sum()
        ctx = self.get(1, context) + DEFAULT_CONFIG.context_strength * league
        ctx_mean = ctx / ctx.sum()
        batter_counts = self.get(5, (context, batter)) + DEFAULT_CONFIG.player_strength * ctx_mean
        return {"league": all_counts, "context": ctx, "batter_only": batter_counts}


class Score:
    def __init__(self):
        self.n = self.groups = 0
        self.joint_loss = self.run_loss = self.run_squared_error = 0.0
        self.events = {
            name: {"log_loss": 0.0, "brier": 0.0, "bins": np.zeros((10, 3)), "predictive": []}
            for name in EVENT_MASKS
        }
        self.matches = defaultdict(lambda: np.zeros(2))
        self.sparse = {
            "no_direct_history": [0, 0.0],
            "one_to_29": [0, 0.0],
            "at_least_30": [0, 0.0],
        }

    def add(self, alpha, observed, match_id, direct_n):
        n = int(observed.sum())
        mean = alpha / alpha.sum()
        loss = float(-np.dot(observed, np.log(mean)))
        self.n += n
        self.groups += 1
        self.joint_loss += loss
        self.matches[match_id] += [n, loss]
        bucket = (
            "no_direct_history"
            if direct_n == 0
            else "one_to_29"
            if direct_n < 30
            else "at_least_30"
        )
        self.sparse[bucket][0] += n
        self.sparse[bucket][1] += loss
        runs = np.array([r for r, b, d in OUTCOMES])
        expected = float(np.dot(mean, runs))
        self.run_squared_error += float(np.dot(observed, (runs - expected) ** 2))
        for run in range(8):
            mask = runs == run
            self.run_loss -= float(observed[mask].sum()) * np.log(mean[mask].sum())
        for name, mask in EVENT_MASKS.items():
            a = float(alpha[mask].sum())
            b = float(alpha.sum() - a)
            p = a / (a + b)
            successes = int(observed[mask].sum())
            stats = self.events[name]
            stats["log_loss"] -= successes * np.log(p) + (n - successes) * np.log1p(-p)
            stats["brier"] += successes * (1 - p) ** 2 + (n - successes) * p**2
            stats["bins"][min(int(p * 10), 9)] += [n, n * p, successes]
            stats["predictive"].append((n, a, b, successes))

    def report(self):
        if not self.n:
            return {"deliveries": 0, "groups": 0}
        events = {}
        for name, stats in self.events.items():
            calibration = [
                {
                    "bin_lower": i / 10,
                    "bin_upper": (i + 1) / 10,
                    "deliveries": int(n),
                    "mean_probability": float(p / n),
                    "observed_frequency": float(s / n),
                }
                for i, (n, p, s) in enumerate(stats["bins"])
                if n
            ]
            trials, a, b, actual = np.array(stats["predictive"]).T
            low = betabinom.ppf(0.05, trials, a, b)
            high = betabinom.ppf(0.95, trials, a, b)
            events[name] = {
                "brier_score": float(stats["brier"] / self.n),
                "log_loss": float(stats["log_loss"] / self.n),
                "expected_calibration_error_10_bins": float(
                    sum(
                        r["deliveries"] * abs(r["mean_probability"] - r["observed_frequency"])
                        for r in calibration
                    )
                    / self.n
                ),
                "calibration_bins": calibration,
                "90_percent_predictive_count_interval_group_coverage": float(
                    np.mean((actual >= low) & (actual <= high))
                ),
                "coverage_note": "Discrete beta-binomial intervals for held-out group event counts; not latent-parameter credible interval coverage.",
            }
        return {
            "deliveries": self.n,
            "groups": self.groups,
            "matches": len(self.matches),
            "joint_log_loss": self.joint_loss / self.n,
            "run_log_loss": self.run_loss / self.n,
            "capped_run_rmse_per_delivery": float(np.sqrt(self.run_squared_error / self.n)),
            "events": events,
            "sparse_target_segments": {
                k: {"deliveries": int(n), "joint_log_loss": loss / n if n else None}
                for k, (n, loss) in self.sparse.items()
            },
        }


def cluster_comparison(model: Score, baseline: Score):
    """Paired match-cluster bootstrap; avoids pretending balls are independent."""
    keys = sorted(model.matches)
    if not keys:
        return None
    deltas = np.array([baseline.matches[k][1] - model.matches[k][1] for k in keys])
    sizes = np.array([model.matches[k][0] for k in keys])
    rng = np.random.default_rng(20261002)
    draws = rng.integers(0, len(keys), size=(2000, len(keys)))
    gains = deltas[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    lower, upper = np.quantile(gains, [0.025, 0.975])
    return {
        "joint_log_loss_improvement": float(deltas.sum() / sizes.sum()),
        "95_percent_match_cluster_bootstrap_interval": {
            "lower": float(lower),
            "upper": float(upper),
        },
        "resamples": 2000,
        "seed": 20261002,
        "positive_means_model_better": True,
    }


def grouped_deliveries(db):
    return db.execute("""SELECT match_date,match_id,season,batter_id,bowler_id,phase,venue_id,
        MIN(batter_runs,7) AS runs,CASE WHEN four=1 OR six=1 THEN 1 ELSE 0 END AS boundary,
        striker_dismissed,COUNT(*) AS n FROM deliveries WHERE legal_ball=1 AND is_super_over=0
        GROUP BY match_date,match_id,season,batter_id,bowler_id,phase,venue_id,runs,boundary,striker_dismissed
        ORDER BY match_date,match_id,batter_id,bowler_id,phase,venue_id""").fetchall()


def evaluate(db, *, validation_season=2024, test_seasons=(2025, 2026), progress=None):
    if not test_seasons or any(year <= validation_season for year in test_seasons):
        raise ValueError("Holdout seasons must follow validation")
    candidates = [ModelConfig(matchup_strength=s) for s in (20, 60, 120)]
    validation = {c.matchup_strength: Score() for c in candidates}
    validation_baselines = {name: Score() for name in ("league", "context", "batter_only")}
    holdout = {
        season: {name: Score() for name in ("bayesian", "league", "context", "batter_only")}
        for season in test_seasons
    }
    index, queue = RollingIndex(), deque()
    selected = None
    last_training_date = None
    scored_first_dates = {}
    rows = grouped_deliveries(db)
    for day, chunk in groupby(rows, key=lambda row: row["match_date"]):
        season_groups = defaultdict(lambda: np.zeros(K))
        for row in chunk:
            key = (
                int(row["season"]),
                row["match_id"],
                row["batter_id"],
                row["bowler_id"],
                (row["phase"], row["venue_id"]),
            )
            season_groups[key][
                outcome_index(row["runs"], row["boundary"], row["striker_dismissed"])
            ] += row["n"]
        cutoff = (
            date.fromisoformat(day) - timedelta(days=DEFAULT_CONFIG.lookback_days)
        ).isoformat()
        while queue and queue[0][0] < cutoff:
            _, old_groups = queue.popleft()
            for (_, _match, batter, bowler, context), counts in old_groups.items():
                index.add(batter, bowler, context, counts, sign=-1)
        for (season, match, batter, bowler, context), observed in season_groups.items():
            if season != validation_season and season not in test_seasons:
                continue
            if last_training_date is not None and last_training_date >= day:
                raise AssertionError("Same-day leakage")
            scored_first_dates.setdefault(
                season, {"prediction_date": day, "latest_training_date": last_training_date}
            )
            pools = index.pools(batter, bowler, context)
            direct_n = int(pools["target"].sum())
            baseline_alphas = index.baselines(batter, context)
            if season == validation_season:
                for config in candidates:
                    alpha, _ = posterior(pools, config)
                    validation[config.matchup_strength].add(alpha, observed, match, direct_n)
                for name, alpha in baseline_alphas.items():
                    validation_baselines[name].add(alpha, observed, match, direct_n)
            else:
                if selected is None:
                    if not all(score.n for score in validation.values()):
                        raise ValueError("Missing validation deliveries")
                    selected = min(
                        candidates,
                        key=lambda c: (
                            validation[c.matchup_strength].joint_loss
                            / validation[c.matchup_strength].n
                        ),
                    )
                    if progress:
                        progress(
                            f"Validation selected matchup prior strength {selected.matchup_strength}"
                        )
                alpha, _ = posterior(pools, selected)
                holdout[season]["bayesian"].add(alpha, observed, match, direct_n)
                for name, alpha in baseline_alphas.items():
                    holdout[season][name].add(alpha, observed, match, direct_n)
        # All matches on this date finish before any evidence becomes available.
        for (_, _match, batter, bowler, context), counts in season_groups.items():
            index.add(batter, bowler, context, counts)
        queue.append((day, season_groups))
        last_training_date = day
        if progress and day.endswith("-12-31"):
            progress(f"Processed {day}")
    if selected is None or any(not scores["bayesian"].n for scores in holdout.values()):
        raise ValueError("Validation and all requested holdout seasons must be present")
    from dataclasses import asdict

    return {
        "protocol": "date_blocked_prequential",
        "validation_season": validation_season,
        "test_seasons": list(test_seasons),
        "selected_configuration": asdict(selected),
        "selection_metric": "validation_joint_log_loss",
        "served_configuration": asdict(DEFAULT_CONFIG),
        "validation_candidates": {str(s): score.report() for s, score in validation.items()},
        "validation_baselines": {k: score.report() for k, score in validation_baselines.items()},
        "holdout": {
            str(season): {
                "metrics": {k: score.report() for k, score in scores.items()},
                "comparisons": {
                    k: cluster_comparison(scores["bayesian"], scores[k])
                    for k in ("league", "context", "batter_only")
                },
            }
            for season, scores in holdout.items()
        },
        "first_prediction_cutoffs": scored_first_dates,
        "limitations": [
            "conditional_empirical_bayes_not_full_hierarchical_posterior",
            "predictions_fixed_before_each_date_no_within_match_updates",
            "no_current_attributes_used_in_primary_backtest",
            "legal_deliveries_only",
            "match_cluster_intervals_do_not_account_for_all_season_or_player_dependence",
            "no_independent_type_feature_backtest",
            "backtest_conditions_on_phase_and_venue_unfiltered_context_modes_unvalidated",
        ],
    }
