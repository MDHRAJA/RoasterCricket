"""Local real-data smoke checks, not historical full-match calibration."""

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.database import connection, load_snapshot  # noqa: E402
from backend.main import create_app  # noqa: E402
from backend.optimizer import solve_xi  # noqa: E402
from backend.services import AnalyticsService  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    settings = Settings.from_env()
    before = digest(settings.database)
    plans = {}
    with connection(settings) as db:
        analytics = AnalyticsService(db, settings, load_snapshot(settings))
        for team in ("CSK", "MI"):
            roster, _ = analytics.roster(team, 2026)
            profiles = sorted(
                [m["player"] for m in roster["members"]], key=lambda p: p["player_id"]
            )
            # A role-balanced arbitrary baseline, not a match-ready XI recommendation.
            solved = solve_xi(profiles, np.zeros(len(profiles)), np.zeros((len(profiles), 20)))
            assert solved is not None
            ids = [profiles[i]["player_id"] for i in solved["indices"]]
            ids.sort(
                key=lambda p: (
                    next(q["primary_role"] for q in profiles if q["player_id"] == p) == "bowler",
                    p,
                )
            )
            plans[team] = {
                "team_id": team,
                "starting_xi": ids,
                "batting_order": ids,
                "bowling_plan": solved["bowling_plan"],
                "captain_id": ids[0],
            }
        venue = db.execute(
            "SELECT venue_id FROM venues WHERE display_name LIKE '%Chidambaram%' LIMIT 1"
        ).fetchone()[0]
    request = {
        "as_of": "2026-10-02",
        "venue_id": venue,
        "team_a": plans["CSK"],
        "team_b": plans["MI"],
        "batting_first_team_id": "CSK",
        "simulations": 200,
        "seed": 20261002,
        "allow_unknown_availability": True,
        "include_sample_match": True,
    }
    optimize = {
        "as_of": request["as_of"],
        "venue_id": venue,
        "team_id": "CSK",
        "opponent": plans["MI"],
        "batting_first_team_id": "CSK",
        "candidate_count": 3,
        "simulations": 200,
        "seed": 20261002,
        "allow_unknown_availability": True,
    }
    timings = {}
    with TestClient(create_app(settings)) as client:
        start = time.monotonic()
        response = client.post("/api/v1/simulations/match", json=request)
        timings["match_200_trials_seconds"] = round(time.monotonic() - start, 3)
        assert response.status_code == 200, response.text
        match = response.json()
        repeated = client.post("/api/v1/simulations/match", json=request)
        assert repeated.status_code == 200 and match == repeated.json()
        start = time.monotonic()
        response = client.post("/api/v1/optimization/xi", json=optimize)
        timings["xi_3_candidates_200_trials_each_plus_confirmation_seconds"] = round(
            time.monotonic() - start, 3
        )
        assert response.status_code == 200, response.text
        optimized = response.json()
        correction_request = {**request, "use_delivery_calibration": True}
        start = time.monotonic()
        response = client.post("/api/v1/simulations/match", json=correction_request)
        timings["optional_corrected_match_200_trials_seconds"] = round(time.monotonic() - start, 3)
        assert response.status_code == 200, response.text
        corrected = response.json()
        assert corrected["data"]["training"]["delivery_calibration"] == "joint-event-logit-2024-v1"
        assert match["data"]["training"]["delivery_calibration"] == "raw_default"
        assert not corrected["data"]["reliability"]["match_level_calibrated"]
    for card in match["data"]["sample_match"]["innings"]:
        assert card["runs"] == sum(p["runs"] for p in card["batting"]) + sum(
            card["extras"].values()
        )
        assert card["legal_balls"] <= 120 and card["wickets"] <= 10
        assert max(p["legal_balls"] for p in card["bowling"]) <= 24
    assert (
        abs(
            sum(
                match["data"]["outcomes"][t]["probability"] for t in ("CSK", "MI", "unresolved_tie")
            )
            - 1
        )
        < 1e-12
    )
    for alternative in [optimized["data"]["recommended"], *optimized["data"]["alternatives"]]:
        plan = alternative["plan"]
        assert len(set(plan["starting_xi"])) == 11
        assert max(Counter(plan["bowling_plan"]).values()) <= 4
        assert all(
            a != b for a, b in zip(plan["bowling_plan"], plan["bowling_plan"][1:], strict=False)
        )
    assert before == digest(settings.database)
    assert not optimized["data"]["reliability"]["win_probability_superiority_proven"]
    artifacts = {
        "match-simulation-request.json": request,
        "match-simulation-example.json": match,
        "xi-optimization-request.json": optimize,
        "xi-optimization-example.json": optimized,
        "match-simulation-corrected-request.json": correction_request,
        "match-simulation-corrected-example.json": corrected,
    }
    report = {
        "status": "passed",
        "scenario": "hypothetical CSK versus MI; not a scheduled match or verified registered XI",
        "timings": timings,
        "database_unchanged_sha256": before,
        "seeded_full_response_reproducible": True,
        "scorecard_conservation_checked": True,
        "solver_and_bowling_constraints_checked": True,
        "historical_match_level_calibration": "not_established",
        "historical_full_match_diagnostic": "see_full-match-backtest.json_not_a_production_calibration_guarantee",
        "match_outcomes": match["data"]["outcomes"],
        "independent_confirmation": optimized["data"]["confirmation"]["selected_team_outcome"],
        "timing_scope": "single-machine local smoke checks, not a load test or SLA",
    }
    artifacts["simulation-checks.json"] = report
    for name, value in artifacts.items():
        (ROOT / "outputs" / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
