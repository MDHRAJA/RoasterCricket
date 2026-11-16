import math
import sqlite3
from datetime import date

import numpy as np
import pytest
from scipy.stats import beta

from backend.backtesting import RollingIndex, Score, evaluate
from backend.bayesian import (
    DEFAULT_CONFIG,
    EVENT_MASKS,
    SEED,
    K,
    ModelConfig,
    PredictionService,
    outcome_index,
    posterior,
    summarize,
)
from backend.config import Settings
from backend.database import connection, load_snapshot
from backend.services import AnalyticsService, ApiError
from tests.conftest import A, B, C, D


def empty_pools():
    return {key: np.zeros(K) for key in ("target", "batter", "bowler", "context", "background")}


def add_delivery(data_dir, **changes):
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.row_factory = sqlite3.Row
        template = dict(db.execute("SELECT * FROM deliveries LIMIT 1").fetchone())
        template.update(changes)
        db.execute(
            f"INSERT INTO deliveries ({','.join(template)}) VALUES ({','.join('?' for _ in template)})",
            list(template.values()),
        )


def prediction(client, **params):
    response = client.get(
        "/api/v1/predictions/matchup",
        params={"batter_id": A, "bowler_id": B, "as_of": "2026-04-03", **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_seed_support_and_conjugate_update():
    assert SEED.sum() == pytest.approx(4)
    assert np.all(SEED > 0)
    pools = empty_pools()
    pools["target"][outcome_index(4, 1, 0)] = 2
    pools["target"][outcome_index(0, 0, 1)] = 1
    alpha, means = posterior(pools)
    np.testing.assert_allclose(
        alpha, DEFAULT_CONFIG.matchup_strength * SEED / SEED.sum() + pools["target"]
    )
    expected = (
        DEFAULT_CONFIG.matchup_strength * means["target_prior"][EVENT_MASKS["boundary"]].sum() + 2
    ) / (DEFAULT_CONFIG.matchup_strength + 3)
    assert summarize(alpha, pools["target"])["events"]["boundary"]["probability"] == pytest.approx(
        expected
    )


def test_intervals_use_beta_marginals_and_mass_conserved():
    alpha = np.arange(1, K + 1, dtype=float)
    result = summarize(alpha, np.zeros(K), curves=True)
    assert sum(r["probability"] for r in result["run_distribution"]) == pytest.approx(1)
    assert sum(r["probability"] for r in result["joint_outcomes"]) == pytest.approx(1)
    event = result["events"]["striker_dismissal"]
    a, b = event["posterior_alpha"], event["posterior_beta"]
    assert event["credible_interval"]["lower"] == pytest.approx(beta.ppf(0.05, a, b))
    assert event["credible_interval"]["upper"] == pytest.approx(beta.ppf(0.95, a, b))
    assert all(math.isfinite(p["density"]) for p in event["density_curve"])


def test_more_target_evidence_narrows_interval():
    pools = empty_pools()
    pools["background"][:] = 1
    alpha, _ = posterior(pools)
    sparse = summarize(alpha, pools["target"])["events"]["boundary"]["credible_interval"]
    pools["target"] = alpha / alpha.sum() * 1000
    dense_alpha, _ = posterior(pools)
    dense = summarize(dense_alpha, pools["target"])["events"]["boundary"]["credible_interval"]
    assert dense["upper"] - dense["lower"] < sparse["upper"] - sparse["lower"]


def test_finite_curves_with_extreme_prior_shapes():
    result = summarize(SEED * 1e-4, np.zeros(K), curves=True)
    for event in result["events"].values():
        assert all(
            math.isfinite(p["density"]) and 0 < p["probability"] < 1 for p in event["density_curve"]
        )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_strengths(value):
    with pytest.raises(ValueError):
        ModelConfig(matchup_strength=value)


def test_no_evidence_does_not_publish_seed_as_prediction():
    with pytest.raises(ApiError, match="No eligible IPL"):
        posterior(empty_pools())
    pools = empty_pools()
    pools["target"][0] = -1
    with pytest.raises(ValueError, match="evidence"):
        posterior(pools)


def test_api_prediction_contract_and_legal_delivery_denominator(client):
    result = prediction(client, curves=True)
    data = result["data"]
    assert data["status"] == "experimental"
    assert data["training"]["disjoint_pool_deliveries"]["target"] == 4
    assert data["training"]["direct_evidence_weight"] == pytest.approx(
        4 / (4 + DEFAULT_CONFIG.matchup_strength)
    )
    assert data["events"]["boundary"]["observed_successes"] == 1  # Illegal six excluded.
    assert data["events"]["dot"]["observed_successes"] == 2
    assert data["events"]["striker_dismissal"]["observed_successes"] == 1
    assert len(data["events"]["boundary"]["density_curve"]) == 61
    assert sum(r["probability"] for r in data["joint_outcomes"]) == pytest.approx(1)
    assert result["meta"]["before"] == "2026-04-03"


def test_cutoff_excludes_all_target_day_results(client, data_dir):
    first = prediction(client, as_of="2026-03-29")
    assert first["data"]["training"]["disjoint_pool_deliveries"]["target"] == 2
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.execute(
            "UPDATE deliveries SET batter_runs=6,four=0,six=1,striker_dismissed=1 WHERE match_date>=?",
            ("2026-03-29",),
        )
    assert prediction(client, as_of="2026-03-29") == first


def test_rolling_window_excludes_ancient_results(client, data_dir):
    before = prediction(client)
    add_delivery(
        data_dir, delivery_id="ancient", match_date="2010-01-01", batter_runs=6, four=0, six=1
    )
    assert prediction(client) == before


def test_no_history_player_has_population_forecast_not_invented_player_history(client):
    result = prediction(client, batter_id=C)
    assert result["data"]["training"]["disjoint_pool_deliveries"]["target"] == 0
    assert result["data"]["training"]["direct_evidence_weight"] == 0
    assert "no_direct_history_prior_only_prediction" in result["meta"]["warnings"]


@pytest.mark.parametrize(
    "params,status",
    [
        ({"as_of": "2008-04-19"}, 503),
        ({"as_of": "2026-02-30"}, 422),
        ({"as_of": "0001-01-01"}, 422),
        ({"bowler_id": A}, 422),
        ({"batter_id": "unknown"}, 404),
        ({"venue_id": "missing"}, 404),
        ({"phase": "invalid"}, 422),
    ],
)
def test_prediction_errors(client, params, status):
    response = client.get(
        "/api/v1/predictions/matchup",
        params={"batter_id": A, "bowler_id": B, "as_of": "2026-04-03", **params},
    )
    assert response.status_code == status
    assert "error" in response.json()


def test_explicit_cutoff_is_required(client):
    assert client.get(f"/api/v1/predictions/matchup?batter_id={A}&bowler_id={B}").status_code == 422


def test_type_prediction_warns_attribute_history_not_verified(client):
    response = client.get(
        "/api/v1/predictions/bowling-type",
        params={
            "batter_id": A,
            "category": "spin",
            "arm": "left",
            "as_of": "2026-04-03",
            "phase": "powerplay",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["data"]["training"]["disjoint_pool_deliveries"]["target"] == 3
    assert (
        "profile_attributes_not_time_versioned_type_backtest_not_leakage_free"
        in result["meta"]["warnings"]
    )


def test_stale_training_is_labelled(client):
    response = prediction(client, as_of="2027-04-03")
    assert "training_data_stale_for_requested_date" in response["meta"]["warnings"]


def test_sql_and_incremental_evidence_partitions_agree(data_dir):
    for i, (batter, bowler, phase) in enumerate(
        [
            (A, C, "powerplay"),
            (D, B, "powerplay"),
            (D, C, "powerplay"),
            (D, C, "middle"),
            (A, B, "middle"),
        ]
    ):
        add_delivery(
            data_dir, delivery_id=f"extra-{i}", batter_id=batter, bowler_id=bowler, phase=phase
        )
    settings = Settings(data_dir)
    index = RollingIndex()
    with connection(settings) as db:
        rows = db.execute(
            "SELECT * FROM deliveries WHERE legal_ball=1 AND is_super_over=0 AND match_date<?",
            ("2026-03-30",),
        ).fetchall()
        for row in rows:
            counts = np.zeros(K)
            counts[
                outcome_index(
                    row["batter_runs"], int(row["four"] or row["six"]), row["striker_dismissed"]
                )
            ] = 1
            index.add(row["batter_id"], row["bowler_id"], (row["phase"], row["venue_id"]), counts)
        expected = index.pools(A, B, ("powerplay", "venue_test"))
        service = AnalyticsService(db, settings, load_snapshot(settings))
        data, _ = PredictionService(service).predict(
            A, bowler_id=B, phase="powerplay", venue_id="venue_test", as_of=date(2026, 3, 30)
        )
    assert data["training"]["disjoint_pool_deliveries"] == {
        key: int(counts.sum()) for key, counts in expected.items()
    }
    assert data["training"]["disjoint_pool_deliveries"] == {
        "target": 3,
        "batter": 1,
        "bowler": 1,
        "context": 1,
        "background": 1,
    }
    alpha, _ = posterior(expected)
    expected_forecast = summarize(alpha, expected["target"])
    assert data["events"] == expected_forecast["events"]


def test_incremental_counts_can_expire():
    index = RollingIndex()
    counts = np.ones(K)
    index.add(A, B, ("powerplay", "venue"), counts)
    index.add(A, B, ("powerplay", "venue"), counts, sign=-1)
    assert all(not mapping for mapping in index.maps)


def test_scores_match_hand_computed_binary_brier():
    score = Score()
    observed = np.zeros(K)
    observed[outcome_index(4, 1, 0)] = 1
    observed[outcome_index(0, 0, 0)] = 3
    alpha = np.ones(K)
    score.add(alpha, observed, "match", 0)
    report = score.report()
    p = EVENT_MASKS["boundary"].sum() / K
    assert report["events"]["boundary"]["brier_score"] == pytest.approx(
        ((1 - p) ** 2 + 3 * p**2) / 4
    )


def test_future_holdout_changes_cannot_affect_validation_selection(data_dir):
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.execute("UPDATE deliveries SET match_date='2025-01-01',season='2025' WHERE match_id='1'")
    # Supply historical population evidence even for a new phase/context.
    add_delivery(
        data_dir,
        delivery_id="population",
        match_date="2025-01-01",
        season="2025",
        match_id="0",
        batter_id=D,
        bowler_id=C,
    )
    add_delivery(
        data_dir,
        delivery_id="population-other",
        match_date="2025-01-01",
        season="2025",
        match_id="0",
        batter_id=A,
        bowler_id=C,
    )
    add_delivery(
        data_dir, delivery_id="holdout", match_date="2027-03-01", season="2027", match_id="7"
    )
    with connection(Settings(data_dir)) as db:
        first = evaluate(db, validation_season=2026, test_seasons=(2027,))
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.execute(
            "UPDATE deliveries SET batter_runs=0,four=0,six=0,striker_dismissed=1 WHERE season='2027'"
        )
    with connection(Settings(data_dir)) as db:
        second = evaluate(db, validation_season=2026, test_seasons=(2027,))
    assert first["validation_candidates"] == second["validation_candidates"]
    assert first["selected_configuration"] == second["selected_configuration"]
    assert first["first_prediction_cutoffs"][2027]["latest_training_date"] < "2027-03-01"
    assert first["holdout"]["2027"]["metrics"] != second["holdout"]["2027"]["metrics"]
