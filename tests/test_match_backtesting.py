import copy
import sqlite3
from collections import Counter
from datetime import date

import numpy as np
import pytest

from backend.config import Settings
from backend.historical_evidence import HistoricalEvidence, assert_adapter_equivalent
from backend.historical_planning import PriorStrategies, historical_cases, population_plan
from backend.ipl_rules import active_lineups
from backend.match_backtesting import (
    batting_first_baseline,
    corrected_score_records,
    corrected_win_records,
    fit_score_correction,
    fit_win_correction,
    innings_metrics,
    offline_request,
    prediction_record,
)
from backend.services import AnalyticsService
from backend.simulation_evidence import SimulationEvidence
from backend.simulator import MatchSimulator
from scripts.report_match_backtest import interval_score, paired_date_gain


def test_prior_strategy_ignores_target_future_and_pool_order():
    participants = [f"p{i:02}" for i in range(12)]
    before = [
        {
            "date": "2024-04-01",
            "match_id": "old",
            "player_id": pid,
            "position": i + 1,
            "bowling": {"death": 24} if i >= 6 else {},
        }
        for i, pid in enumerate(participants)
    ]
    contaminants = [
        {**r, "date": day, "position": 12 - i, "bowling": {"powerplay": 120}}
        for day in ("2025-04-01", "2026-04-01")
        for i, r in enumerate(before)
    ]
    first, trace = PriorStrategies(before).plan(
        "CSK", participants, date(2025, 4, 1), batting_first=True
    )
    second, _ = PriorStrategies(before + contaminants).plan(
        "CSK", list(reversed(participants)), date(2025, 4, 1), batting_first=True
    )
    assert first == second
    assert trace["latest_strategy_evidence_date"] == "2024-04-01"
    assert trace["actual_target_batting_order_or_bowling_usage_used"] is False
    assert set(first.batting_order) == set(active_lineups(first, True)[0])
    assert set(first.bowling_plan) <= set(active_lineups(first, True)[1])
    assert max(Counter(first.bowling_plan).values()) == 4
    assert all(a != b for a, b in zip(first.bowling_plan, first.bowling_plan[1:], strict=False))


@pytest.mark.parametrize("seed", range(12))
def test_prior_strategy_bowling_feasible_with_cold_players(seed):
    rng = np.random.default_rng(seed)
    participants = [f"p{i:02}" for i in range(12)]
    rows = [
        {
            "date": "2024-03-20",
            "match_id": "prior",
            "player_id": p,
            "position": int(rng.integers(1, 12)),
            "bowling": {
                phase: int(rng.integers(0, 40)) for phase in ("powerplay", "middle", "death")
            },
        }
        for p in participants[:seed]
    ]
    plan, trace = PriorStrategies(rows).plan(
        "MI", participants, date(2025, 4, 1), batting_first=False
    )
    assert len(plan.bowling_plan) == 20
    assert sorted(Counter(plan.bowling_plan).values()) == [4] * 5
    assert all(a != b for a, b in zip(plan.bowling_plan, plan.bowling_plan[1:], strict=False))
    assert set(plan.batting_order) == set(active_lineups(plan, False)[0])
    assert set(plan.bowling_plan) <= set(active_lineups(plan, False)[1])
    assert len(trace["participants_with_no_prior_appearances"]) == 12 - seed


def test_historical_adapter_matches_live_sampler_and_rejects_backwards(data_dir):
    db = sqlite3.connect(data_dir / "ipl.sqlite")
    db.row_factory = sqlite3.Row
    db.execute(
        "UPDATE deliveries SET wides=CASE WHEN legal_ball=0 AND ball_faced=0 THEN 1 ELSE 0 END, noballs=CASE WHEN legal_ball=0 AND ball_faced=1 THEN 1 ELSE 0 END"
    )
    settings = Settings(data_dir)
    service = AnalyticsService(db, settings, {})
    # Rows on this fixture's target date are excluded.
    as_of = date(2026, 4, 2)
    archive = HistoricalEvidence(db, as_of)
    archive.advance(as_of)
    live = SimulationEvidence(service, as_of, "venue_test")
    adapted = archive.snapshot("venue_test")
    assert_adapter_equivalent(live, adapted, [("a1111111", "b1111111", "powerplay")])
    assert adapted.training["last_included_date"] < as_of.isoformat()
    archive.advance(date(2026, 4, 3))
    with pytest.raises(ValueError, match="backwards"):
        archive.advance(as_of)
    db.close()


def test_actual_exposure_audit_and_score_mc_error(data_dir):
    db = sqlite3.connect(data_dir / "ipl.sqlite")
    db.row_factory = sqlite3.Row
    db.execute(
        "UPDATE deliveries SET wides=CASE WHEN legal_ball=0 AND ball_faced=0 THEN 1 ELSE 0 END, noballs=CASE WHEN legal_ball=0 AND ball_faced=1 THEN 1 ELSE 0 END"
    )
    evidence = SimulationEvidence(
        AnalyticsService(db, Settings(data_dir), {}), date(2026, 4, 2), "venue_test"
    )
    case = {
        "season": 2025,
        "date": "2026-04-02",
        "venue_id": "venue_test",
        "team_a_id": "CSK",
        "team_b_id": "MI",
        "batting_first_team_id": "CSK",
    }
    plans = {team: population_plan(team) for team in ("CSK", "MI")}
    result, _ = MatchSimulator(None, evidence=evidence).run(
        offline_request(case, plans, 50, 11), validated=({}, []), cpu_seconds=30
    )
    exposures = result["reliability"]["evidence"]["simulated_legal_delivery_exposures"]
    assert exposures["legal_delivery_draws"] > 0
    assert exposures["no_direct_history_fraction"] == 1
    assert (
        "majority_of_simulated_legal_draws_have_no_direct_matchup_history"
        in result["reliability"]["flags"]
    )
    one = result["innings"][0]
    assert one["score_quantiles"]["p05"] <= one["score_quantiles"]["p10"]
    assert one["score_quantiles"]["p95"] >= one["score_quantiles"]["p90"]
    assert one["mean_runs_mc_standard_error"] == pytest.approx(
        one["score_standard_deviation"] / np.sqrt(50)
    )
    target = {
        **case,
        "match_id": "target",
        "actual": {
            "winner_id": "CSK",
            "first_runs": 150,
            "second_runs": 149,
            "first_wickets": 5,
            "second_wickets": 8,
        },
    }
    record = prediction_record(target, result, "population")
    assert 0 < record["probability"] < 1
    assert innings_metrics([record])["innings"] == 1
    db.close()


def test_match_win_correction_is_development_only():
    rows = [
        {"date": f"2024-04-{i + 1:02}", "probability": 0.7, "outcome": i % 2} for i in range(24)
    ]
    fitted = fit_win_correction(rows)
    assert fitted["automatic_promotion"] is False
    with pytest.raises(ValueError, match="fitting-period"):
        corrected_win_records(rows, fitted)
    corrected = corrected_win_records([{**rows[0], "date": "2025-04-01"}], fitted)
    assert 0 < corrected[0]["probability"] < 1
    assert fit_win_correction([])["status"] == "insufficient_development_matches"


def test_score_correction_cutoff_order_and_scope():
    rows = [
        {
            "date": f"2024-04-{i + 1:02}",
            "first_innings": {
                "mean_runs": 150.0,
                "actual_runs": 160 + i,
                "score_quantiles": {
                    "p05": 130.0,
                    "p10": 140.0,
                    "p50": 150.0,
                    "p90": 160.0,
                    "p95": 170.0,
                },
            },
            "probability": 0.6,
        }
        for i in range(24)
    ]
    fitted = fit_score_correction(rows)
    assert fitted["automatic_promotion"] is False
    assert fitted["coverage_guaranteed"] is False
    with pytest.raises(ValueError, match="fitting-period"):
        corrected_score_records(rows, fitted)
    candidate = corrected_score_records([{**rows[0], "date": "2025-04-01"}], fitted)[0]
    assert candidate["probability"] == 0.6
    assert candidate["first_innings"]["actual_runs"] == 160
    quantiles = list(candidate["first_innings"]["score_quantiles"].values())
    assert quantiles == sorted(quantiles)
    assert fit_score_correction([])["status"] == "insufficient_development_matches"


def test_interval_score_penalizes_excessive_width_and_misses():
    assert interval_score(10, 5, 15, 0.1) == 10
    assert interval_score(20, 5, 15, 0.1) == 110
    assert interval_score(0, 5, 15, 0.1) == 110
    assert interval_score(10, -100, 100, 0.1) > interval_score(10, 5, 15, 0.1)
    with pytest.raises(ValueError):
        interval_score(10, 15, 5, 0.1)


def test_score_comparison_requires_matched_ids_and_zero_gain_when_identical():
    rows = [{"match_id": str(i), "date": f"2025-04-{i + 1:02}", "loss": i} for i in range(8)]
    result = paired_date_gain(rows, rows, lambda r: r["loss"])
    assert result["mean_gain"] == 0
    assert result["95_percent_date_cluster_interval"] == [0.0, 0.0]
    with pytest.raises(ValueError, match="aligned"):
        paired_date_gain(rows, list(reversed(rows)), lambda r: r["loss"])


def test_batting_first_baseline_excludes_same_day_and_future():
    old = {"date": "2024-04-01", "team_a_id": "A", "actual": {"winner_id": "A"}}
    case = {"window_start": "2024-01-01", "date": "2025-04-01"}
    cases = [old, {**old, "date": "2025-04-01"}, {**old, "date": "2026-04-01"}]
    assert batting_first_baseline(cases, case)["probability"] == 6 / 11


def screening_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE matches(match_id,match_date,season,team1_id,team2_id,venue_id,
            winner_id,result,scheduled_overs,balls_per_over,result_method);
        CREATE TABLE innings(match_id,innings,is_super_over,batting_team_id,bowling_team_id,
            penalty_runs_pre,penalty_runs_post,total_runs,legal_balls,wickets,target_runs,target_overs);
        CREATE TABLE match_players(match_id,team_id,player_id);
        INSERT INTO matches VALUES('1','2025-04-01',2025,'A','B','v','B','win',20,6,'');
        INSERT INTO innings VALUES('1',1,0,'A','B',0,0,150,120,5,NULL,NULL);
        INSERT INTO innings VALUES('1',2,0,'B','A',0,0,151,110,6,151,20);
    """)
    for team in ("A", "B"):
        db.executemany(
            "INSERT INTO match_players VALUES('1',?,?)", [(team, team + str(i)) for i in range(12)]
        )
    return db


def test_case_screen_and_no_silent_player_pool_exclusion():
    db = screening_db()
    cases, excluded = historical_cases(db, (2025,))
    assert len(cases) == 1 and not excluded
    assert cases[0]["participant_conditioned_supported"] is True
    db.execute("INSERT INTO match_players VALUES('1','A','A12')")
    cases, excluded = historical_cases(db, (2025,))
    assert len(cases) == 1 and not excluded
    assert cases[0]["participant_conditioned_supported"] is False
    db.execute("UPDATE innings SET target_runs=140 WHERE innings=2")
    cases, excluded = historical_cases(db, (2025,))
    assert not cases and excluded[0]["reason"] == "revised_or_inconsistent_target"
    db.close()


def test_case_target_trajectory_not_a_strategy_input():
    db = screening_db()
    first, _ = historical_cases(db, (2025,))
    db.execute("UPDATE innings SET total_runs=total_runs+50")
    db.execute("UPDATE innings SET target_runs=201 WHERE innings=2")
    second, _ = historical_cases(db, (2025,))
    a, b = copy.deepcopy(first[0]), copy.deepcopy(second[0])
    assert a.pop("actual") != b.pop("actual")
    assert a == b
    db.close()
