"""Predeclared multi-family search, locked before one retrospective 2026 evaluation."""

import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sklearn
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import binomtest
from sklearn.ensemble import (
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.prematch_features import FEATURE_VERSION, feature_table, read_archive  # noqa: E402
from backend.reliability_backtesting import paired_gain, win_metrics  # noqa: E402
from backend.simulator import wilson  # noqa: E402
from backend.winner_model import MODEL_SCHEMA, calibrate, predict_json_model  # noqa: E402

VALIDATION_YEARS = (2022, 2023, 2024, 2025)
TEST_YEAR = 2026
SEED = 20261105


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    group: str
    parameter: float


def candidates():
    result = [
        Candidate(f"logit_{group}_C{c}", "logistic", group, c)
        for group in ("compact", "team", "full", "xi")
        for c in (0.03, 0.3, 3)
    ]
    result += [
        Candidate(f"gb_{group}_depth{d}", "gradient", group, d)
        for group in ("team", "full", "xi")
        for d in (1, 2)
    ]
    result += [
        Candidate(f"hgb_{group}_leaves{leaves}", "histogram", group, leaves)
        for group in ("team", "full", "xi")
        for leaves in (7, 15)
    ]
    result += [
        Candidate(f"rf_{group}_depth{d}", "forest", group, d)
        for group in ("full", "xi")
        for d in (4, 8)
    ]
    return result


def columns_for(names, group):
    if group == "xi":
        return list(range(len(names)))
    if group == "full":
        return [i for i, n in enumerate(names) if "diff_xi_" not in n]
    if group == "team":
        return [
            i
            for i, n in enumerate(names)
            if not n.startswith("identity_") and "lagged_" not in n and "diff_xi_" not in n
        ]
    return [
        i
        for i, n in enumerate(names)
        if n.startswith(("elo", "diff_win", "diff_season_win", "diff_nrr", "diff_rest"))
        or n
        in (
            "league_first_win50",
            "season_first_win",
            "venue_first_win40",
            "first_team_won_toss",
            "h2h_first_team_win",
            "impact_era",
            "season_progress",
        )
    ]


def fit_candidate(spec, x, y, weights):
    scaler = None
    if spec.family == "logistic":
        scaler = StandardScaler().fit(x)
        x = scaler.transform(x)
        estimator = LogisticRegression(C=spec.parameter, max_iter=2000, random_state=SEED)
    elif spec.family == "gradient":
        estimator = GradientBoostingClassifier(
            n_estimators=160,
            learning_rate=0.035,
            max_depth=int(spec.parameter),
            min_samples_leaf=20,
            random_state=SEED,
        )
    elif spec.family == "histogram":
        estimator = HistGradientBoostingClassifier(
            max_iter=180,
            learning_rate=0.04,
            max_leaf_nodes=int(spec.parameter),
            min_samples_leaf=25,
            l2_regularization=10,
            early_stopping=False,
            random_state=SEED,
        )
    else:
        estimator = RandomForestClassifier(
            n_estimators=240,
            max_depth=int(spec.parameter),
            min_samples_leaf=14,
            max_features=0.7,
            n_jobs=1,
            random_state=SEED,
        )
    estimator.fit(x, y, sample_weight=weights)
    return estimator, scaler


def predict_fitted(fitted, x):
    estimator, scaler = fitted
    return estimator.predict_proba(scaler.transform(x) if scaler is not None else x)[:, 1]


def calibration_fit(p, y):
    if len(y) < 30:
        return {"intercept": 0.0, "slope": 1.0}
    p = np.clip(p, 1e-6, 1 - 1e-6)
    design = np.column_stack([np.ones(len(p)), np.log(p / (1 - p))])

    def objective(theta):
        z = design @ theta
        difference = theta - [0, 1]
        return float(
            np.sum(np.logaddexp(0, z) - y * z) + 2 * (difference @ difference)
        ), design.T @ (expit(z) - y) + 4 * difference

    fitted = minimize(
        objective, [0.0, 1.0], jac=True, method="L-BFGS-B", bounds=[(-0.7, 0.7), (0, 2)]
    )
    if not fitted.success:
        raise RuntimeError("Nested calibration fitting failed")
    return {"intercept": float(fitted.x[0]), "slope": float(fitted.x[1])}


def records(rows, probabilities):
    return [
        {
            "match_id": r["context"]["match_id"],
            "date": r["context"]["match_date"],
            "season": r["context"]["season"],
            "probability": float(p),
            "outcome": r["outcome"],
        }
        for r, p in zip(rows, probabilities, strict=True)
    ]


def metrics(predictions):
    result = win_metrics(predictions)
    p = np.array([r["probability"] for r in predictions])
    y = np.array([r["outcome"] for r in predictions])
    correct = int(np.sum((p > 0.5) == y))
    result["correct_picks_ties_choose_chase"] = correct
    result["accuracy_ties_choose_chase"] = correct / len(y)
    result["accuracy_wilson_95_interval"] = {
        **wilson(correct, len(y)),
        "interpretation": "binomial_approximation_not_a_future_accuracy_guarantee",
    }
    result["predictions_covered_fraction"] = 1.0
    return result


def nested_calibrated(predictions):
    result = []
    for year in VALIDATION_YEARS:
        old = [r for r in predictions if r["season"] < year]
        current = [r for r in predictions if r["season"] == year]
        fit = calibration_fit(
            np.array([r["probability"] for r in old]), np.array([r["outcome"] for r in old])
        )
        q = calibrate([r["probability"] for r in current], fit)
        result += [{**r, "probability": float(p)} for r, p in zip(current, q, strict=True)]
    return result


def rank_key(predictions):
    accuracy = [
        metrics([r for r in predictions if r["season"] == year])["accuracy_ties_choose_chase"]
        for year in VALIDATION_YEARS
    ]
    # Accuracy is the declared primary target; log loss breaks ties. No test ranking.
    return (-float(np.mean(accuracy)), metrics(predictions)["log_loss"])


def export_tree(tree, *, classification=False):
    values = tree.value[:, 0]
    output = values[:, 1] / values.sum(axis=1) if classification else values[:, 0]
    return {
        "left": tree.children_left.tolist(),
        "right": tree.children_right.tolist(),
        "feature": tree.feature.tolist(),
        "threshold": tree.threshold.tolist(),
        "value": output.tolist(),
    }


def export_component(spec, fitted, columns):
    estimator, scaler = fitted
    result = {"family": spec.family, "columns": columns}
    if spec.family == "logistic":
        result.update(
            center=scaler.mean_.tolist(),
            scale=scaler.scale_.tolist(),
            weights=estimator.coef_[0].tolist(),
            intercept=float(estimator.intercept_[0]),
        )
    elif spec.family == "forest":
        result["trees"] = [export_tree(t.tree_, classification=True) for t in estimator.estimators_]
    elif spec.family == "gradient":
        result.update(
            trees=[export_tree(t[0].tree_) for t in estimator.estimators_],
            initial_logit=float(
                np.log(estimator.init_.class_prior_[1] / estimator.init_.class_prior_[0])
            ),
            learning_rate=float(estimator.learning_rate),
        )
    else:
        # Version-pinned research export of histogram nodes. Every export MUST
        # pass numerical parity on all feature rows before it is written.
        trees = []
        for group in estimator._predictors:
            nodes = group[0].nodes
            if np.any(nodes["is_categorical"]):
                raise ValueError("Categorical histogram splits cannot be exported")
            leaf = nodes["is_leaf"].astype(bool)
            trees.append(
                {
                    "left": np.where(leaf, -1, nodes["left"].astype(int)).tolist(),
                    "right": np.where(leaf, -1, nodes["right"].astype(int)).tolist(),
                    "feature": nodes["feature_idx"].astype(int).tolist(),
                    "threshold": nodes["num_threshold"].tolist(),
                    "value": nodes["value"].tolist(),
                }
            )
        result.update(
            trees=trees,
            initial_logit=float(estimator._baseline_prediction[0, 0]),
            learning_rate=1.0,
            exporter_sklearn_version=sklearn.__version__,
        )
    return result


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    started = time.monotonic()
    settings = Settings(Settings.from_env().data_dir, query_timeout_seconds=30)
    data_hash = digest(settings.database)
    protocol = {
        "target": "at_least_70_percent_deterministic_winner_accuracy_all_eligible_2026_post_toss_matches",
        "training_start_season": 2012,
        "validation_seasons": list(VALIDATION_YEARS),
        "final_evaluation_season": TEST_YEAR,
        "selection": "mean_validation_season_accuracy_then_pooled_log_loss",
        "classification_rule": "batting_first_probability_greater_than_0.5_else_chasing_team",
        "coverage": "all_format_eligible_games_no_confidence_filter_or_abstention",
        "fixed_match_age_half_life_seasons": 5,
        "candidate_specs": [asdict(c) for c in candidates()],
        "additional_candidates": "prequentially_calibrated_each_model_and_top_three_validation_ensemble",
        "feature_version": FEATURE_VERSION,
        "xi_scope": "XI feature candidates condition on reconstructed original starters, NOT timestamp-verified announcements; team/full/compact candidates exclude XI features",
        "seed": SEED,
        "database_sha256": data_hash,
        "source_sha256": {
            p.name: digest(p)
            for p in (
                Path(__file__),
                ROOT / "backend/prematch_features.py",
                ROOT / "backend/winner_model.py",
            )
        },
        "test_status": "2026_previously_inspected_for_other_diagnostics_not_new_untouched_or_prospective_data",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save(ROOT / "outputs/winner-research-protocol.json", protocol)
    with connection(settings) as db:
        observations, exclusions = read_archive(db)
    table = feature_table(observations)
    feature_names = sorted(table[0]["features"])
    x = np.array([[r["features"][k] for k in feature_names] for r in table])
    seasons = np.array([r["context"]["season"] for r in table])
    y = np.array([r["outcome"] for r in table])
    dev_indices = np.flatnonzero(np.isin(seasons, VALIDATION_YEARS))
    development_rows = [table[i] for i in dev_indices]
    development = {}
    with threadpool_limits(limits=2):
        for spec in candidates():
            cols = columns_for(feature_names, spec.group)
            predictions = []
            for year in VALIDATION_YEARS:
                train = np.flatnonzero((seasons >= 2012) & (seasons < year))
                valid = np.flatnonzero(seasons == year)
                if not len(train) or max(table[i]["context"]["match_date"] for i in train) >= min(
                    table[i]["context"]["match_date"] for i in valid
                ):
                    raise AssertionError("Chronological training split violated")
                weights = np.power(0.5, (year - seasons[train]) / 5)
                fitted = fit_candidate(spec, x[train][:, cols], y[train], weights)
                predictions.extend(
                    records([table[i] for i in valid], predict_fitted(fitted, x[valid][:, cols]))
                )
            development[spec.name] = predictions
            development[spec.name + ":calibrated"] = nested_calibrated(predictions)
            scores = metrics(predictions)
            print(
                spec.name,
                json.dumps(
                    {
                        k: scores[k]
                        for k in (
                            "matches",
                            "accuracy_ties_choose_chase",
                            "brier_score",
                            "log_loss",
                        )
                    }
                ),
                flush=True,
            )
        raw_order = sorted(
            [c.name for c in candidates()], key=lambda name: rank_key(development[name])
        )
        members = raw_order[:3]
        pooled = np.mean(
            [[r["probability"] for r in development[name]] for name in members], axis=0
        )
        development["ensemble_top3"] = records(development_rows, pooled)
        development["ensemble_top3:calibrated"] = nested_calibrated(development["ensemble_top3"])
        # Baselines compete under the same predeclared rule; no automatic complex-model preference.
        for name, probabilities in (
            ("baseline_neutral", np.full(len(development_rows), 0.5)),
            (
                "baseline_order_history",
                np.array([r["features"]["league_first_win50"] for r in development_rows]),
            ),
        ):
            development[name] = records(development_rows, probabilities)
        selected = min(development, key=lambda name: rank_key(development[name]))
        selection = {
            "protocol_sha256": digest(ROOT / "outputs/winner-research-protocol.json"),
            "selected": selected,
            "ensemble_members_if_selected": members,
            "leaderboard": [
                {
                    "name": name,
                    "macro_season_accuracy": -rank_key(pred)[0],
                    "metrics": metrics(pred),
                    "by_season": {
                        str(year): metrics([r for r in pred if r["season"] == year])
                        for year in VALIDATION_YEARS
                    },
                }
                for name, pred in sorted(development.items(), key=lambda item: rank_key(item[1]))
            ],
            "locked_before_test_evaluation": True,
            "locked_at": datetime.now(timezone.utc).isoformat(),
        }
        save(ROOT / "outputs/winner-selection-lock.json", selection)
        print(
            "LOCKED:",
            selected,
            "validation accuracy",
            selection["leaderboard"][0]["macro_season_accuracy"],
            flush=True,
        )
        train = np.flatnonzero((seasons >= 2012) & (seasons < TEST_YEAR))
        test = np.flatnonzero(seasons == TEST_YEAR)
        model = {
            "schema": MODEL_SCHEMA,
            "feature_version": FEATURE_VERSION,
            "feature_names": feature_names,
            "components": [],
            "selected_recipe": selected,
            "calibration": {"intercept": 0.0, "slope": 1.0},
            "exclusive_training_cutoff": "2026-01-01",
            "database_sha256": data_hash,
            "information_scope": "post_toss_team_form_with_optional_conditional_original_xi_not_timestamp_verified",
            "status": "experimental_not_prospectively_validated",
            "production_validated": False,
            "selection_lock_sha256": digest(ROOT / "outputs/winner-selection-lock.json"),
        }
        if selected.startswith("baseline"):
            raw_test = (
                np.full(len(test), 0.5)
                if selected == "baseline_neutral"
                else np.array([table[i]["features"]["league_first_win50"] for i in test])
            )
            model["constant_probability"] = 0.5
            model["baseline_feature"] = (
                None if selected == "baseline_neutral" else "league_first_win50"
            )
        else:
            selected_names = (
                members if selected.startswith("ensemble_top3") else [selected.split(":")[0]]
            )
            spec_map = {s.name: s for s in candidates()}
            expected = []
            for name in selected_names:
                spec = spec_map[name]
                cols = columns_for(feature_names, spec.group)
                fitted = fit_candidate(
                    spec,
                    x[train][:, cols],
                    y[train],
                    np.power(0.5, (TEST_YEAR - seasons[train]) / 5),
                )
                model["components"].append(export_component(spec, fitted, cols))
                expected.append(predict_fitted(fitted, x[:, cols]))
            raw_all = np.mean(expected, axis=0)
            exported_all = predict_json_model(x, model)
            if not np.allclose(raw_all, exported_all, rtol=1e-7, atol=1e-8):
                raise AssertionError("JSON model export failed full-table numerical parity")
            model["maximum_json_export_parity_error"] = float(
                np.max(np.abs(raw_all - exported_all))
            )
            raw_test = raw_all[test]
        if selected.endswith(":calibrated"):
            raw_dev = development[selected.removesuffix(":calibrated")]
            model["calibration"] = calibration_fit(
                np.array([r["probability"] for r in raw_dev]),
                np.array([r["outcome"] for r in raw_dev]),
            )
        test_p = calibrate(raw_test, model["calibration"])
        tested = records([table[i] for i in test], test_p)
    test_metrics = metrics(tested)
    achieved = test_metrics["accuracy_ties_choose_chase"] >= 0.7
    baselines = {
        "neutral_50_percent_ties_choose_chase": records(
            [table[i] for i in test], np.full(len(test), 0.5)
        ),
        "prior_order_history": records(
            [table[i] for i in test], [table[i]["features"]["league_first_win50"] for i in test]
        ),
    }
    target_picks = np.array([r["probability"] > 0.5 for r in tested])
    actual = y[test]
    baseline_correct = actual == 0
    model_correct = target_picks == actual
    wins, losses = (
        int(np.sum(model_correct & ~baseline_correct)),
        int(np.sum(~model_correct & baseline_correct)),
    )
    report = {
        "status": "target_met_on_retrospective_point_estimate_not_a_guarantee"
        if achieved
        else "target_not_met",
        "target_accuracy": 0.7,
        "target_met": achieved,
        "scope": model["information_scope"],
        "validation_selection": selection,
        "final_evaluation": {
            "season": TEST_YEAR,
            "selected": selected,
            "metrics": test_metrics,
            "baselines": {n: metrics(r) for n, r in baselines.items()},
            "paired_score_gains": {
                name: {metric: paired_gain(tested, r, metric) for metric in ("brier", "log_loss")}
                for name, r in baselines.items()
            },
            "paired_vs_always_chase": {
                "model_only_correct": wins,
                "chase_only_correct": losses,
                "one_sided_exact_p_value": float(
                    binomtest(wins, wins + losses, 0.5, alternative="greater").pvalue
                )
                if wins + losses
                else 1.0,
            },
            "predictions": [
                {**r, "trace": table[i]["trace"], "context": table[i]["context"]}
                for r, i in zip(tested, test, strict=True)
            ],
        },
        "excluded_matches": exclusions,
        "database_sha256": data_hash,
        "database_unchanged": digest(settings.database) == data_hash,
        "source_sha256": protocol["source_sha256"],
        "sklearn_version": sklearn.__version__,
        "development_predictions": development,
        "feature_names": feature_names,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "limitations": [
            "2026 was inspected in prior projects/diagnostics; this is not a new untouched or prospective trial.",
            "A single season point estimate does not prove a long-run 70 percent success rate; inspect its interval and paired baseline comparison.",
            "Original-XI feature candidates condition on reconstructed original starters excluding incoming match replacements; they are NOT timestamp-verified announcement forecasts.",
            "Team/full/compact candidates exclude original-XI features. No target score, realized batting/bowling usage, incoming Impact choices, outcome or current roster/profile metadata enter any feature vector.",
            "Lagged observed player groups can differ substantially from the actual announced XI, especially after auctions.",
            "The cohort is completed uninterrupted decisive ordinary matches; it does not establish accuracy on rain-adjusted, abandoned or tied/Super-Over matches.",
            "No live pitch, weather or time-stamped injury/availability feed is included.",
            "The candidate search introduces selection uncertainty; retrospective bootstrap intervals do not capture every source of uncertainty.",
            "This winner challenger does not validate the delivery simulator, hypothetical XI choices or optimizer counterfactual benefits.",
        ],
    }
    if not report["database_unchanged"]:
        raise AssertionError("Training mutated the source database")
    model["evaluation_accuracy"] = test_metrics["accuracy_ties_choose_chase"]
    model["target_met_on_evaluated_cohort"] = achieved
    save(ROOT / "outputs/match-winner-model.json", model)
    save(ROOT / "outputs/match-winner-research.json", report)
    print(
        json.dumps(
            {
                "target_met": achieved,
                "selected": selected,
                "evaluation": test_metrics,
                "elapsed_seconds": report["elapsed_seconds"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
