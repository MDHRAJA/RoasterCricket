"""Independently audit frozen winner predictions, full coverage and the 70% claim."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.prematch_features import feature_table, read_archive  # noqa: E402
from backend.winner_forecast import uses_original_xi  # noqa: E402
from backend.winner_model import load_json_model, predict_json_model  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    report_path = ROOT / "outputs/match-winner-research.json"
    model_path = ROOT / "outputs/match-winner-model.json"
    report = json.loads(report_path.read_text("utf-8"))
    model = load_json_model(model_path)
    lock_path = ROOT / "outputs/winner-selection-lock.json"
    protocol_path = ROOT / "outputs/winner-research-protocol.json"
    lock = json.loads(lock_path.read_text("utf-8"))
    protocol = json.loads(protocol_path.read_text("utf-8"))
    settings = Settings(Settings.from_env().data_dir, query_timeout_seconds=30)
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    check(
        "Source data digest matches",
        digest(settings.database) == report["database_sha256"] == model["database_sha256"],
    )
    check("Selection is sealed against protocol", lock["protocol_sha256"] == digest(protocol_path))
    check(
        "Model points to exact selection lock", model["selection_lock_sha256"] == digest(lock_path)
    )
    check(
        "Model chosen before final evaluation",
        lock["locked_before_test_evaluation"] is True
        and report["final_evaluation"]["selected"] == lock["selected"] == model["selected_recipe"],
    )
    for name, path in (
        ("train_match_winner.py", ROOT / "scripts/train_match_winner.py"),
        ("prematch_features.py", ROOT / "backend/prematch_features.py"),
        ("winner_model.py", ROOT / "backend/winner_model.py"),
    ):
        check(
            f"Exact research source: {name}",
            digest(path) == report["source_sha256"][name] == protocol["source_sha256"][name],
        )
    check("No production-validation promotion", model["production_validated"] is False)
    with connection(settings) as db:
        observations, _ = read_archive(db)
    rows = [r for r in feature_table(observations) if r["context"]["season"] == 2026]
    saved = report["final_evaluation"]["predictions"]
    check(
        "All eligible final-season IDs covered exactly once",
        len(saved) == len(rows) == len({r["match_id"] for r in saved})
        and {r["match_id"] for r in saved} == {r["context"]["match_id"] for r in rows},
    )
    x = np.array([[r["features"][k] for k in model["feature_names"]] for r in rows])
    probabilities = predict_json_model(x, model)
    for row, prediction, p in zip(rows, saved, probabilities, strict=True):
        check(
            f"Prediction replay {prediction['match_id']}",
            row["context"]["match_id"] == prediction["match_id"]
            and abs(float(p) - prediction["probability"]) < 1e-8,
        )
        check(
            f"True source outcome {prediction['match_id']}", row["outcome"] == prediction["outcome"]
        )
        check(
            f"Prior-date feature cutoff {prediction['match_id']}",
            row["trace"]["latest_feature_evidence_date"] < row["context"]["match_date"],
        )
    outcomes = np.array([r["outcome"] for r in rows])
    accuracy = float(np.mean((probabilities > 0.5) == outcomes))
    check(
        "Independent accuracy recomputation",
        abs(accuracy - report["final_evaluation"]["metrics"]["accuracy_ties_choose_chase"]) < 1e-12,
    )
    check(
        "70 percent claim matches actual result",
        report["target_met"] == model["target_met_on_evaluated_cohort"] == (accuracy >= 0.7),
    )
    check(
        "100 percent eligible-match coverage",
        report["final_evaluation"]["metrics"]["predictions_covered_fraction"] == 1.0,
    )
    if not uses_original_xi(model):
        perturbed = x.copy()
        for i, name in enumerate(model["feature_names"]):
            if "diff_xi_" in name:
                perturbed[:, i] = 1000
        check(
            "Selected model ignores reconstructed-XI inputs",
            np.array_equal(probabilities, predict_json_model(perturbed, model)),
        )
    reconstruction = {
        "status": "reconstructed_not_timestamp_verified",
        "method": "match_players excluding incoming match replacements; sorted names, no target batting order",
        "database_sha256": report["database_sha256"],
        "matches": [
            {
                "match_id": r["context"].match_id,
                "match_date": r["context"].match_date,
                "starting_xis": {
                    r["context"].batting_first_team_id: list(r["context"].starting_xi_first),
                    r["context"].chasing_team_id: list(r["context"].starting_xi_chase),
                },
            }
            for r in observations
        ],
    }
    (ROOT / "outputs/winner-reconstructed-xis.json").write_text(
        json.dumps(reconstruction, indent=2) + "\n", encoding="utf-8"
    )
    result = {
        "status": "passed",
        "passed_checks": len(checks),
        "target_met": accuracy >= 0.7,
        "evaluated_matches": len(rows),
        "correct_picks": int(np.sum((probabilities > 0.5) == outcomes)),
        "accuracy": accuracy,
        "all_eligible_matches_covered": True,
        "selected_model_uses_reconstructed_xis": uses_original_xi(model),
        "research_report_sha256": digest(report_path),
        "model_sha256": digest(model_path),
        "database_unchanged_sha256": digest(settings.database),
        "checks": checks,
        "interpretation": "integrity checks passed; this does NOT mean the accuracy target passed",
    }
    (ROOT / "outputs/match-winner-checks.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, indent=2))


if __name__ == "__main__":
    main()
