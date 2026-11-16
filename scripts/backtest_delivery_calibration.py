"""Fit correction on date-blocked 2024 predictions; evaluate fixed correction on 2025/26."""

import hashlib
import json
import sys
from collections import defaultdict, deque
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.backtesting import (  # noqa: E402
    RollingIndex,
    Score,
    cluster_comparison,
    grouped_deliveries,
)
from backend.bayesian import DEFAULT_CONFIG, K, outcome_index, posterior  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.delivery_calibration import CALIBRATION_VERSION, OFFSETS, corrected, fit  # noqa: E402


def evaluate(rows):
    index, queue = RollingIndex(), deque()
    validation_probabilities, validation_counts = [], []
    validation_raw, validation_adjusted = Score(), Score()
    holdouts = {season: {"raw": Score(), "corrected": Score()} for season in (2025, 2026)}
    offsets, last_training_date = None, None
    first_cutoffs = {}
    for day, chunk in groupby(rows, key=lambda r: r["match_date"]):
        groups = defaultdict(lambda: np.zeros(K))
        for r in chunk:
            key = (
                int(r["season"]),
                r["match_id"],
                r["batter_id"],
                r["bowler_id"],
                (r["phase"], r["venue_id"]),
            )
            groups[key][outcome_index(r["runs"], r["boundary"], r["striker_dismissed"])] += r["n"]
        cutoff = (
            date.fromisoformat(day) - timedelta(days=DEFAULT_CONFIG.lookback_days)
        ).isoformat()
        while queue and queue[0][0] < cutoff:
            _, old = queue.popleft()
            for (_, _, b, w, ctx), counts in old.items():
                index.add(b, w, ctx, counts, sign=-1)
        for (season, match, batter, bowler, context), observed in groups.items():
            if season not in (2024, 2025, 2026):
                continue
            if last_training_date and last_training_date >= day:
                raise AssertionError("Same-day or future training leakage")
            first_cutoffs.setdefault(
                season, {"prediction_date": day, "latest_training_date": last_training_date}
            )
            pools = index.pools(batter, bowler, context)
            alpha, _ = posterior(pools)
            p, n = alpha / alpha.sum(), int(pools["target"].sum())
            if season == 2024:
                validation_probabilities.append(p)
                validation_counts.append(observed)
                validation_raw.add(alpha, observed, match, n)
            else:
                if offsets is None:
                    offsets = fit(validation_probabilities, validation_counts)
                    for v, counts in zip(validation_probabilities, validation_counts, strict=True):
                        # Validation fit scores only; not out-of-sample results.
                        validation_adjusted.add(corrected(v, offsets) * 60, counts, "validation", 0)
                holdouts[season]["raw"].add(alpha, observed, match, n)
                holdouts[season]["corrected"].add(
                    corrected(p, offsets) * alpha.sum(), observed, match, n
                )
        for (_, _, b, w, ctx), counts in groups.items():
            index.add(b, w, ctx, counts)
        queue.append((day, groups))
        last_training_date = day
    if offsets is None or any(not scores["raw"].n for scores in holdouts.values()):
        raise ValueError("Missing calibration/evaluation seasons")
    return {
        "model_version": CALIBRATION_VERSION,
        "protocol": "date_blocked_prequential_joint_event_logit_correction",
        "fit_season": 2024,
        "exclusive_fit_cutoff": "2025-01-01",
        "evaluation_seasons": [2025, 2026],
        "fitted_offsets_boundary_dot_dismissal": offsets.tolist(),
        "served_offsets": OFFSETS.tolist(),
        "fitting": {
            "parameters": 3,
            "coefficient_bounds": [-0.75, 0.75],
            "l2_penalty_strength": 10,
            "training_deliveries": validation_raw.n,
            "objective": "joint_log_loss_plus_fixed_L2_penalty",
        },
        "validation_fit": {
            "raw": validation_raw.report(),
            "corrected": validation_adjusted.report(),
        },
        "holdout": {
            str(year): {
                "metrics": {name: score.report() for name, score in scores.items()},
                "paired_joint_log_loss_gain": cluster_comparison(
                    scores["corrected"], scores["raw"]
                ),
            }
            for year, scores in holdouts.items()
        },
        "first_prediction_cutoffs": first_cutoffs,
        "limitations": [
            "2025_2026_not_used_to_fit_offsets_but_previously_inspected_for_other_model_diagnostics",
            "not_prospective_validation",
            "joint_calibration_not_match_win_calibration",
            "no_type_or_omitted_context_validation",
            "score_count_intervals_from_adjusted_alpha_are_evaluation_approximations_not_served_credible_intervals",
            "upstream_and_calibration_parameter_uncertainty_not_propagated",
            "conditional_regular_legal_delivery_model",
        ],
    }


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    settings = Settings.from_env()
    original = digest(settings.database)
    with connection(replace(settings, query_timeout_seconds=30)) as db:
        rows = grouped_deliveries(db)
    print(
        "Fitting three joint correction offsets from 2024 prequential predictions only.", flush=True
    )
    report = evaluate(rows)
    assert original == digest(settings.database)
    report.update(
        database_sha256=original,
        dataset_catalog_sha256=digest(settings.data_dir / "dataset_catalog.json"),
        served_offsets_match_fitted=np.allclose(
            report["fitted_offsets_boundary_dot_dismissal"], OFFSETS, atol=1e-8
        ),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    report["served_offsets_match_fitted"] = bool(report["served_offsets_match_fitted"])
    (ROOT / "outputs/delivery-calibration-backtest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("Fitted:", report["fitted_offsets_boundary_dot_dismissal"], flush=True)
    for year, result in report["holdout"].items():
        print(
            year,
            json.dumps(
                {
                    "joint_loss": {k: v["joint_log_loss"] for k, v in result["metrics"].items()},
                    "events": {
                        k: {
                            event: values["expected_calibration_error_10_bins"]
                            for event, values in v["events"].items()
                        }
                        for k, v in result["metrics"].items()
                    },
                    "gain": result["paired_joint_log_loss_gain"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
