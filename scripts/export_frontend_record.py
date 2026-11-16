"""Project saved research into public, attributable frontend evidence; never retrain."""

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
DATABASE = OUT / "ipl-data/ipl.sqlite"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def wilson(wins, n):
    z = 1.959963984540054
    p = wins / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"lower": max(0, center - radius), "upper": min(1, center + radius)}


def metrics(value):
    bins = []
    for row in value["calibration_bins"]:
        n = row["matches"]
        wins = round(n * row["observed_win_frequency"])
        assert abs(wins / n - row["observed_win_frequency"]) < 1e-10
        bins.append({
            "lower": row["lower"], "upper": row["upper_exclusive"], "n": n,
            "mean": row["mean_probability"], "observed": row["observed_win_frequency"],
            "wins": wins, "interval": wilson(wins, n),
        })
    n = value["matches"]
    assert sum(row["n"] for row in bins) == n
    return {
        "n": n, "correct": value.get("correct_picks_ties_choose_chase"),
        "accuracy": value.get("accuracy_ties_choose_chase", value["top_pick_accuracy_with_half_credit_for_50_percent_ties"]),
        "brier": value["brier_score"], "logLoss": value["log_loss"],
        "ece": value["calibration_error_10_bins"], "bins": bins,
    }


def gain(value):
    lower, upper = value["95_percent_date_cluster_interval"]
    return {"mean": value["mean_gain"], "lower": lower, "upper": upper}


def score_metrics(value):
    point = value["point_and_coverage"]
    interval = value["interval_scores"]["0.9"]
    return {
        "n": point["innings"], "mae": point["mae_runs"],
        "coverage": point["predictive_coverage"]["0.9"],
        "width": point["mean_interval_width"]["0.9"],
        "intervalScore": interval["mean_interval_score"],
        "covered": interval["covered_matches"],
        "interval": {k: interval["coverage_wilson_95_interval"][k] for k in ("lower", "upper")},
    }


def main():
    original = digest(DATABASE)
    names = [
        "match-winner-research.json", "match-winner-checks.json", "match-winner-model.json",
        "winner-research-protocol.json", "winner-selection-lock.json",
        "full-match-backtest.json", "match-backtest-checks.json", "match-score-calibration-audit.json",
        "delivery-calibration-backtest.json",
    ]
    sources = {name: json.loads((OUT / name).read_text(encoding="utf-8")) for name in names}
    winner, check, model, protocol, lock, full, full_check, score, delivery = (sources[n] for n in names)
    assert original == winner["database_sha256"] == full["signature"]["database_sha256"] == delivery["database_sha256"]
    assert check["status"] == full_check["status"] == "passed"
    assert check["research_report_sha256"] == digest(OUT / names[0])
    assert check["model_sha256"] == digest(OUT / names[2])
    assert full_check["report_sha256"] == score["source_report_sha256"] == digest(OUT / names[5])
    assert lock["protocol_sha256"] == winner["validation_selection"]["protocol_sha256"] == digest(OUT / names[3])
    assert model["selection_lock_sha256"] == digest(OUT / names[4])
    assert model["production_validated"] is False and winner["target_met"] is False
    assert score["score_correction_enabled_in_serving"] is False
    assert full["complete_requested_cohort"] and full["database_unchanged"] and winner["database_unchanged"]
    selected = winner["final_evaluation"]["selected"]
    assert selected == lock["selected"] == model["selected_recipe"]
    assert check["all_eligible_matches_covered"] and not check["selected_model_uses_reconstructed_xis"]
    leader = next(row for row in lock["leaderboard"] if row["name"] == selected)
    forecasts = winner["development_predictions"][selected] + winner["final_evaluation"]["predictions"]
    assert len(forecasts) == len({p["match_id"] for p in forecasts})
    with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        archive = {row["match_id"]: dict(row) for row in db.execute(
            "SELECT m.match_id,m.match_date,m.season,m.venue_name_raw,m.winner_id,"
            "i.batting_team_id,i.bowling_team_id FROM matches m JOIN innings i "
            "ON m.match_id=i.match_id AND i.innings=1 AND i.is_super_over=0"
        )}
    public_forecasts = []
    for p in forecasts:
        context = archive[p["match_id"]]
        assert context["match_date"] == p["date"] and int(context["season"]) == p["season"]
        assert int(context["winner_id"] == context["batting_team_id"]) == p["outcome"]
        latest = p.get("trace", {}).get("latest_feature_evidence_date")
        assert latest is None or latest < p["date"]
        public_forecasts.append({
            "id": p["match_id"], "date": p["date"], "season": p["season"],
            "first": context["batting_team_id"], "chase": context["bowling_team_id"],
            "ground": context["venue_name_raw"], "probability": p["probability"],
            "outcome": p["outcome"], "latestEvidence": latest,
        })
    seasons = [{"season": int(year), "phase": "selection", "metrics": metrics(value)}
               for year, value in leader["by_season"].items()]
    seasons.append({"season": 2026, "phase": "final", "metrics": metrics(winner["final_evaluation"]["metrics"])})
    for season in seasons:
        rows = [p for p in public_forecasts if p["season"] == season["season"]]
        assert len(rows) == season["metrics"]["n"]
        assert sum((p["probability"] > 0.5) == bool(p["outcome"]) for p in rows) == season["metrics"]["correct"]
        brier = sum((p["probability"] - p["outcome"]) ** 2 for p in rows) / len(rows)
        assert abs(brier - season["metrics"]["brier"]) < 1e-10
    sim_seasons = []
    for year in (2025, 2026):
        variants = {}
        for key, value in full["results_by_season"][str(year)]["variants"].items():
            variants[key] = {
                "metrics": metrics(value["win_metrics"]), "neutral": metrics(value["neutral_win_metrics"]),
                "orderBaseline": metrics(value["prior_only_batting_first_baseline_metrics"]),
                "gain": {k: gain(v) for k, v in value["paired_win_gain_vs_neutral"].items()},
            }
        scores = {}
        for key, value in score["results"][str(year)].items():
            scores[key] = {
                "raw": score_metrics(value["raw"]), "candidate": score_metrics(value["candidate"]),
                "maeGain": gain(value["paired_gain"]["absolute_run_error"]),
                "intervalGain": gain(value["paired_gain"]["interval_score_0.9"]),
            }
        sim_seasons.append({"season": year, "variants": variants, "scores": scores})
    delivery_seasons = []
    for year, value in delivery["holdout"].items():
        projected = {}
        for variant, value_metrics in value["metrics"].items():
            projected[variant] = {
                "n": value_metrics["deliveries"], "matches": value_metrics["matches"],
                "loss": value_metrics["joint_log_loss"],
                "events": {key: {"ece": row["expected_calibration_error_10_bins"], "brier": row["brier_score"]}
                           for key, row in value_metrics["events"].items()},
            }
        paired = value["paired_joint_log_loss_gain"]
        delivery_seasons.append({"season": int(year), **projected, "gain": {
            "mean": paired["joint_log_loss_improvement"],
            **paired["95_percent_match_cluster_bootstrap_interval"],
        }})
    final = winner["final_evaluation"]
    snapshot = {
        "schema": "concourse-research-record-v1", "exportedAt": datetime.now(timezone.utc).isoformat(),
        "databaseSha256": original,
        "sources": [{"path": "outputs/" + n, "sha256": digest(OUT / n)} for n in names],
        "winner": {
            "recipe": selected, "target": winner["target_accuracy"], "targetMet": winner["target_met"],
            "lockedAt": lock["locked_at"], "trainingStart": protocol["training_start_season"],
            "selectionRecipes": len(winner["development_predictions"]),
            "macroValidationAccuracy": leader["macro_season_accuracy"],
            "integrityChecks": check["passed_checks"], "seasons": seasons,
            "accuracyInterval": {k: final["metrics"]["accuracy_wilson_95_interval"][k] for k in ("lower", "upper")},
            "baselines": {k: metrics(v) for k, v in final["baselines"].items()},
            "pairedGains": {k: {metric: gain(v) for metric, v in values.items()}
                            for k, values in final["paired_score_gains"].items()},
            "discordance": {k: final["paired_vs_always_chase"][k] for k in ("model_only_correct", "chase_only_correct")},
            "forecasts": sorted(public_forecasts, key=lambda p: (p["date"], p["id"])),
            "limitations": winner["limitations"],
        },
        "simulator": {
            "completedAt": full["completed_at"], "version": full["signature"]["simulator_version"],
            "trials": full["simulations_per_match_per_variant"], "cohorts": full["cohort_counts"],
            "eligible": full["total_format_eligible_matches"],
            "formatExclusions": full["format_result_exclusions"],
            "poolExclusions": full["participant_pool_cohort_exclusions"],
            "integrityChecks": full_check["passed_checks"], "seasons": sim_seasons,
            "scoreFit": full["score_correction_fits_development_only"],
            "limitations": full["limitations"],
        },
        "delivery": {
            "version": delivery["model_version"], "completedAt": delivery["completed_at"],
            "fitDeliveries": delivery["fitting"]["training_deliveries"],
            "fitCutoff": delivery["exclusive_fit_cutoff"], "seasons": delivery_seasons,
            "limitations": delivery["limitations"],
        },
    }
    assert digest(DATABASE) == original
    target = ROOT / "frontend/src/api/snapshots/record.json"
    target.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(public_forecasts)} research forecasts, simulator and delivery audits; database unchanged")


if __name__ == "__main__":
    main()
