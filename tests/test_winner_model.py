import copy
import json
import sqlite3
from datetime import date, timedelta

import numpy as np
import pytest

from backend.prematch_features import FEATURE_VERSION, FeatureState, MatchContext, feature_table
from backend.winner_forecast import forecast
from backend.winner_model import MODEL_SCHEMA, load_json_model, predict_json_model


def observation(mid, day, first="CSK", chase="MI", outcome=1):
    context = MatchContext(mid, day, int(day[:4]), "v", first, chase, first)
    return {
        "context": context,
        "outcome": outcome,
        "winner_id": first if outcome else chase,
        "innings": {
            first: {"total_runs": 180, "legal_balls": 120, "wickets": 5},
            chase: {"total_runs": 160, "legal_balls": 120, "wickets": 8},
        },
        "phases": {},
        "players": {first: ["p1"], chase: ["p2"]},
        "player_stats": [
            {
                "player_id": "p1",
                "batted": 1,
                "batting_runs": 30,
                "balls_faced": 20,
                "dismissals": 1,
                "fours": 3,
                "sixes": 1,
                "legal_balls_bowled": 0,
            },
            {
                "player_id": "p2",
                "batted": 0,
                "legal_balls_bowled": 24,
                "runs_conceded": 30,
                "bowler_wickets": 2,
            },
        ],
    }


def test_target_performance_and_participant_poison_cannot_enter_own_features():
    old = observation("1", "2024-04-01")
    target = observation("2", "2025-04-01")
    future = observation("3", "2026-04-01")
    original = feature_table([old, target, future])
    poisoned = copy.deepcopy(target)
    poisoned["outcome"] = 0
    poisoned["winner_id"] = "MI"
    poisoned["innings"]["CSK"]["total_runs"] = 400
    poisoned["players"] = {"CSK": ["future_star"], "MI": []}
    poisoned["player_stats"] = []
    changed = feature_table([old, poisoned, future])
    assert original[1]["features"] == changed[1]["features"]
    assert original[1]["trace"] == changed[1]["trace"]
    assert original[1]["outcome"] != changed[1]["outcome"]
    assert original[2]["features"] != changed[2]["features"]


def test_same_day_results_never_cross_into_other_forecasts():
    a = observation("a", "2025-04-01")
    b = observation("b", "2025-04-01", "KKR", "CSK")
    first = feature_table([a, b])
    a["winner_id"], a["outcome"] = "MI", 0
    second = feature_table([b, a])
    assert first[1]["features"] == second[1]["features"]
    assert first[1]["trace"]["latest_feature_evidence_date"] is None


def test_feature_state_requires_strict_day_blocks_and_valid_context():
    state = FeatureState()
    old = observation("1", "2025-04-01")
    state.update_day([old])
    with pytest.raises(ValueError, match="Same-day"):
        state.predict_features(old["context"])
    with pytest.raises(ValueError, match="increasing"):
        state.update_day([old])
    with pytest.raises(ValueError, match="distinct"):
        MatchContext("bad", "2026-04-01", 2026, "v", "CSK", "CSK", "CSK")
    with pytest.raises(ValueError, match="disagree"):
        MatchContext("bad", "2026-04-01", 2025, "v", "CSK", "MI", "CSK")


def test_json_logistic_inference_and_baseline_feature(tmp_path):
    model = {
        "schema": MODEL_SCHEMA,
        "feature_names": ["a", "b"],
        "components": [
            {
                "family": "logistic",
                "columns": [0, 1],
                "center": [0, 0],
                "scale": [1, 1],
                "weights": [1, -1],
                "intercept": 0,
            }
        ],
        "calibration": {"intercept": 0, "slope": 1},
    }
    x = np.array([[1, 1], [2, 0], [0, 2]])
    p = predict_json_model(x, model)
    assert p[0] == 0.5 and p[1] > 0.5 > p[2]
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    assert np.array_equal(p, predict_json_model(x, load_json_model(path)))
    baseline = {
        "schema": MODEL_SCHEMA,
        "feature_names": ["prior"],
        "components": [],
        "baseline_feature": "prior",
    }
    assert predict_json_model([[0.3], [0.7]], baseline) == pytest.approx([0.3, 0.7])
    with pytest.raises(ValueError, match="schema mismatch"):
        predict_json_model([[1]], model)


def test_tree_threshold_comparison_preserves_native_float32_to_double_semantics():
    # The float32 value 0.1 is slightly ABOVE the double threshold 0.1.
    # NumPy weak-scalar comparison can round the threshold back to float32.
    tree = {
        "left": [1, -1, -1],
        "right": [2, -1, -1],
        "feature": [0, -2, -2],
        "threshold": [0.1, -2, -2],
        "value": [0, 0.2, 0.8],
    }
    model = {
        "schema": MODEL_SCHEMA,
        "feature_names": ["x"],
        "components": [{"family": "forest", "columns": [0], "trees": [tree]}],
    }
    assert predict_json_model([[0.1]], model)[0] == pytest.approx(0.8)


def test_original_xi_features_use_only_prior_player_performance():
    from dataclasses import replace

    prior = observation("1", "2025-04-01")
    current = observation("2", "2026-04-01")
    current["context"] = replace(
        current["context"],
        starting_xi_first=tuple(["p1"] + [f"a{i}" for i in range(10)]),
        starting_xi_chase=tuple(["p2"] + [f"b{i}" for i in range(10)]),
    )
    original = feature_table([prior, current])
    current["player_stats"][0]["batting_runs"] = 500
    changed = feature_table([prior, current])
    assert original[1]["features"] == changed[1]["features"]
    assert original[1]["trace"]["starting_xis_supplied"] is True
    assert original[1]["trace"]["target_performance_or_incoming_impact_players_used"] is False
    with pytest.raises(ValueError, match="both"):
        replace(current["context"], starting_xi_chase=None)


def test_research_forecast_is_gated_and_cannot_auto_promote(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE teams(team_id)")
    db.executemany("INSERT INTO teams VALUES(?)", [("CSK",), ("MI",)])
    db.execute("CREATE TABLE venues(venue_id)")
    db.execute("INSERT INTO venues VALUES('v')")
    model = {
        "schema": MODEL_SCHEMA,
        "feature_version": FEATURE_VERSION,
        "feature_names": ["elo20_diff"],
        "components": [
            {
                "family": "logistic",
                "columns": [0],
                "center": [0],
                "scale": [1],
                "weights": [0],
                "intercept": -0.1,
            }
        ],
        "exclusive_training_cutoff": "2026-01-01",
        "selected_recipe": "synthetic",
        "evaluation_accuracy": 0.55,
        "target_met_on_evaluated_cohort": False,
    }
    context = MatchContext("test", "2026-04-01", 2026, "v", "CSK", "MI", "MI")
    history = [
        observation(str(i), (date(2025, 1, 1) + timedelta(days=i)).isoformat()) for i in range(100)
    ]
    monkeypatch.setattr("backend.winner_forecast.read_archive", lambda _db: (history, []))
    result = forecast(db, model, context)
    assert result["decision_ready"] is False
    assert result["production_validated"] is False
    assert result["prediction_is_not_a_recommendation"] is True
    assert result["target_met_on_evaluated_cohort"] is False
    assert sum(result["probabilities"].values()) == pytest.approx(1)
    assert result["selected_model_uses_original_xi_features"] is False
    earlier = MatchContext("old", "2025-04-01", 2025, "v", "CSK", "MI", "MI")
    with pytest.raises(ValueError, match="cutoff"):
        forecast(db, model, earlier)
    monkeypatch.setattr("backend.winner_forecast.read_archive", lambda _db: (history[:2], []))
    with pytest.raises(ValueError, match="Insufficient"):
        forecast(db, model, context)
    db.close()


@pytest.mark.parametrize("family", ["logistic", "gradient", "histogram", "forest"])
def test_all_research_exports_match_native_probabilities(family):
    pytest.importorskip("sklearn")
    from scripts.train_match_winner import (
        Candidate,
        export_component,
        fit_candidate,
        predict_fitted,
    )

    rng = np.random.default_rng(42)
    x = rng.normal(size=(100, 4))
    y = (x[:, 0] + x[:, 1] > 0).astype(int)
    parameter = {"logistic": 0.3, "gradient": 1, "histogram": 7, "forest": 4}[family]
    spec = Candidate("test", family, "full", parameter)
    fitted = fit_candidate(spec, x, y, np.ones(len(y)))
    component = export_component(spec, fitted, list(range(4)))
    model = {"schema": MODEL_SCHEMA, "feature_names": list("abcd"), "components": [component]}
    assert predict_json_model(x, model) == pytest.approx(predict_fitted(fitted, x), abs=1e-7)
