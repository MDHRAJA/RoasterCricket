from datetime import date

import numpy as np
import pytest

from backend.bayesian import K
from backend.delivery_calibration import corrected, corrected_draw, eligible, fit, forecast
from backend.reliability import (
    BenchmarkConfig,
    archive,
    before_window,
    benchmark_from_rows,
    predictive_score,
    ranking_decision,
    team_state,
    win_probability,
)
from backend.reliability_backtesting import evaluate, paired_gain, win_metrics
from tests.conftest import A, B


def record(year=2023, day=1, winner="A", venue="v", runs=180):
    return {
        "match_id": f"{year}-{day}",
        "match_date": f"{year}-01-{day:02}",
        "season": str(year),
        "team1_id": "A",
        "team2_id": "B",
        "winner_id": winner,
        "venue_id": venue,
        "first_innings_runs": runs,
    }


def test_window_and_benchmark_do_not_use_same_day_or_future():
    historical = [
        record(day=i, venue="v" if i % 2 else "other", runs=150 + i) for i in range(1, 21)
    ]
    cutoff = date(2023, 1, 22)
    extra = [record(day=22, winner="B", runs=400), record(year=2026, day=1, winner="B", runs=400)]
    assert before_window(historical + extra, cutoff) == historical
    baseline = benchmark_from_rows(historical, "A", "B", "v", cutoff)
    assert baseline == benchmark_from_rows(historical + extra, "A", "B", "v", cutoff)
    assert baseline["training"]["latest_training_date"] < cutoff.isoformat()
    assert baseline["configuration"]["score_strength"] == 10  # Not the later fitted strength.


def test_same_date_elo_updates_are_frozen_and_order_independent():
    first = record()
    second = {**record(), "match_id": "another", "team2_id": "C"}
    config = BenchmarkConfig(k=20)
    a, *_ = team_state([first, second], config)
    b, *_ = team_state([second, first], config)
    assert a["A"] == pytest.approx(20)
    assert dict(a) == dict(b)


def test_season_regression_and_unknown_team_fallback():
    config = BenchmarkConfig(family="elo", k=20, season_carry=0.5, temperature=1)
    same, _ = win_probability([record()], "A", "B", 2023, config)
    later, _ = win_probability([record()], "A", "B", 2024, config)
    assert 0.5 < later < same
    unknown, played = win_probability([], "A", "B", 2024, config)
    assert unknown == 0.5 and played == {"A": 0, "B": 0}
    _, played = win_probability([record(winner=None)], "A", "B", 2024, config)
    assert played == {"A": 0, "B": 0}


def test_score_distribution_has_support_and_no_fake_precision():
    history = [
        record(day=i, venue="v" if i % 2 else "other", runs=130 + i * 4) for i in range(1, 25)
    ]
    predicted = predictive_score(history, "v", 5)
    assert predicted["venue_innings"] == 12 and predicted["background_innings"] == 12
    assert predicted["scale"] > 0
    interval = predicted["predictive_intervals"]["0.9"]
    assert interval["lower"] < predicted["mean_runs"] < interval["upper"]
    assert predictive_score(history[:2], "v") is None
    assert predictive_score([record(day=i) for i in range(1, 20)], "v") is None


def test_calibration_normalizes_and_does_not_change_raw_probabilities():
    raw = np.arange(1, K + 1, dtype=float)
    raw /= raw.sum()
    saved = raw.copy()
    adjusted = corrected(raw)
    assert adjusted.sum() == pytest.approx(1)
    assert np.all(adjusted > 0) and np.array_equal(raw, saved)
    assert np.allclose(corrected(raw, np.zeros(3)), raw)
    assert np.allclose(corrected_draw(raw), adjusted)


def test_underflow_zero_draw_categories_are_preserved():
    raw = np.zeros(K)
    raw[0] = 1
    assert np.array_equal(corrected(raw), raw)
    assert np.array_equal(corrected_draw(raw), raw)


@pytest.mark.parametrize("bad", [np.full(K, np.nan), np.ones(K), np.array(1.0), np.full(K, -1 / K)])
def test_bad_calibration_inputs_fail(bad):
    with pytest.raises(ValueError):
        corrected(bad)


def test_fitter_recovers_regularized_small_correction():
    probabilities = np.ones((2, K)) / K
    truth = np.array([0.2, -0.1, 0.3])
    counts = corrected(probabilities, truth) * 10000
    offsets = fit(probabilities, counts)
    assert np.max(np.abs(offsets - truth)) < 0.01
    assert np.all(np.abs(offsets) <= 0.75)
    with pytest.raises(ValueError):
        fit(probabilities, np.zeros((2, K)))


def test_correction_is_gated_by_context_and_fit_cutoff():
    raw = np.ones(K) / K
    assert not eligible(date(2024, 12, 31))
    assert forecast(raw, date(2024, 12, 31), supported_context=True)["status"] == "not_applied"
    assert forecast(raw, date(2026, 1, 1), supported_context=False)["status"] == "not_applied"
    corrected_result = forecast(raw, date(2026, 1, 1), supported_context=True)
    assert corrected_result["status"] == "experimental_calibration_candidate"
    assert corrected_result["intervals"] is None


def candidate(rank, probability, low, high, proxy):
    return {
        "candidate_rank_by_proxy": rank,
        "proxy_score": proxy,
        "simulation": {
            "probability": probability,
            "sampling_interval": {"lower": low, "upper": high},
        },
    }


def test_overlapping_xis_choose_surrogate_not_noisy_winner():
    strongest_proxy = candidate(1, 0.51, 0.44, 0.58, 10)
    noisy_top = candidate(2, 0.54, 0.47, 0.61, 9)
    selected, alternatives, audit = ranking_decision([strongest_proxy, noisy_top])
    assert selected is strongest_proxy and alternatives == [noisy_top]
    assert not audit["sampling_intervals_nonoverlapping"]
    assert audit["selection_basis"] == "surrogate_proxy_when_sampling_intervals_overlap"
    assert not audit["win_probability_superiority_proven"]


def test_nonoverlapping_xis_and_single_candidate_are_not_global_proofs():
    strong = candidate(2, 0.8, 0.75, 0.85, 9)
    selected, _, audit = ranking_decision([candidate(1, 0.55, 0.5, 0.6, 10), strong])
    assert selected is strong and audit["sampling_intervals_nonoverlapping"]
    _, alternatives, audit = ranking_decision([strong])
    assert not alternatives and not audit["sampling_intervals_nonoverlapping"]


def test_calibration_bins_partition_boundary_probabilities():
    records = [{"probability": i / 10, "outcome": i % 2} for i in range(11)]
    metrics = win_metrics(records)
    assert sum(b["matches"] for b in metrics["calibration_bins"]) == len(records)
    neutral = win_metrics([{"probability": 0.5, "outcome": 1}, {"probability": 0.5, "outcome": 0}])
    assert neutral["brier_score"] == 0.25
    assert neutral["top_pick_accuracy_with_half_credit_for_50_percent_ties"] == 0.5


def test_evaluator_freezes_config_and_all_prediction_cutoffs():
    rows = [
        record(
            year=year,
            day=day,
            winner="A" if day % 2 else "B",
            venue="v" if day % 2 else "other",
            runs=140 + (day % 5) * 15,
        )
        for year, length in [(2022, 30), (2024, 24), (2025, 8), (2026, 8)]
        for day in range(1, length + 1)
    ]
    report = evaluate(rows)
    assert report["validation_season"] == 2024
    for holdout in report["holdout"].values():
        for models in holdout["predictions"].values():
            for records in models.values():
                assert all(r["latest_training_date"] < r["date"] for r in records)
        same = holdout["predictions"]["win"]["selected"]
        comparison = paired_gain(same, same)
        assert comparison["mean_gain"] == 0
        assert comparison["95_percent_date_cluster_interval"] == [0, 0]
    with pytest.raises(ValueError):
        evaluate(rows, test_seasons=(2024,))


def test_archive_scope_filter_is_explicit(data_dir):
    import sqlite3

    db = sqlite3.connect(data_dir / "ipl.sqlite")
    db.row_factory = sqlite3.Row
    db.execute("UPDATE matches SET scheduled_overs=20,balls_per_over=6")
    db.execute("UPDATE innings SET legal_balls=120")
    db.execute("UPDATE matches SET result_method='D/L' WHERE match_id='2'")
    db.execute("UPDATE innings SET total_runs=NULL WHERE match_id='3'")
    records = archive(db)
    assert "1" in {r["match_id"] for r in records}
    assert not {"2", "3"} & {r["match_id"] for r in records}
    db.close()


def test_benchmark_api_flags_empty_evidence_and_never_claims_simulator_validation(client):
    params = {
        "team_a_id": "CSK",
        "team_b_id": "MI",
        "venue_id": "venue_test",
        "as_of": "2026-04-02",
    }
    response = client.get("/api/v1/predictions/match-benchmark", params=params)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["probability_team_a_wins_given_decisive_outcome"] == 0.5
    assert data["first_innings_score"] is None
    assert "fewer_than_10_recent_team_matches" in data["warnings"]
    assert (
        client.get(
            "/api/v1/predictions/match-benchmark", params={**params, "team_b_id": "CSK"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/predictions/match-benchmark", params={**params, "team_b_id": "unknown"}
        ).status_code
        == 404
    )


def test_prediction_candidate_is_separate_and_unsupported_context_not_corrected(client):
    params = {
        "batter_id": A,
        "bowler_id": B,
        "phase": "powerplay",
        "venue_id": "venue_test",
        "as_of": "2026-04-02",
    }
    result = client.get("/api/v1/predictions/matchup", params=params).json()["data"]
    assert result["calibrated_forecast"]["status"] == "experimental_calibration_candidate"
    assert result["events"]["boundary"]["credible_interval"]
    params.pop("phase")
    assert (
        client.get("/api/v1/predictions/matchup", params=params).json()["data"][
            "calibrated_forecast"
        ]["status"]
        == "not_applied"
    )
