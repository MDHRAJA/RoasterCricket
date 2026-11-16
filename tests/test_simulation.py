import itertools
import sqlite3
from collections import Counter
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.ipl_rules import active_lineups, validate_team
from backend.main import create_app
from backend.match_models import ImpactPlan, TeamPlan
from backend.optimizer import solve_xi
from backend.services import ApiError
from backend.simulator import MatchSimulator, innings, phase_at, wilson

BAT = [f"p{i}" for i in range(11)]
BOWL = [f"w{i % 5}" for i in range(20)]


def scripted(events):
    source = iter(events)
    return lambda *_args: next(source, {"kind": "legal"})


def conserved(result):
    assert result["runs"] == sum(p["runs"] for p in result["batting"]) + sum(
        result["extras"].values()
    )
    assert result["legal_balls"] == sum(p["legal_balls"] for p in result["bowling"])
    assert result["wickets"] == sum(p["dismissed"] for p in result["batting"])


def test_strike_rotation_and_over_end():
    r = innings(BAT, BOWL, scripted([{"kind": "legal", "batter_runs": 1}]), trace=True)
    assert [d["striker_id"] for d in r["deliveries"][:7]] == ["p0"] + ["p1"] * 5 + ["p0"]
    assert r["legal_balls"] == 120 and r["physical_deliveries"] == 120
    conserved(r)


def test_extras_free_hit_persists_across_wide():
    r = innings(
        BAT,
        BOWL,
        scripted(
            [
                {"kind": "noball", "noballs": 1},
                {"kind": "wide", "wides": 1},
                {"kind": "legal", "dismissed_role": 1, "credited_to_bowler": True},
                {"kind": "legal", "byes": 3},
                {"kind": "legal", "dismissed_role": 1, "credited_to_bowler": True},
            ]
        ),
        trace=True,
    )
    assert [d["free_hit_next"] for d in r["deliveries"][:3]] == [True, True, False]
    assert r["wickets"] == 1 and r["runs"] == 5
    assert r["physical_deliveries"] == 122
    assert sum(p["balls_faced"] for p in r["batting"]) == 121
    assert sum(p["runs_conceded"] for p in r["bowling"]) == 2
    conserved(r)


def test_non_striker_runout_replaces_correct_end():
    r = innings(
        BAT, BOWL, scripted([{"kind": "legal", "batter_runs": 1, "dismissed_role": 2}]), trace=True
    )
    assert r["deliveries"][0]["dismissed_id"] == "p1"
    assert r["deliveries"][1]["striker_id"] == "p2"
    assert sum(p["wickets"] for p in r["bowling"]) == 0
    conserved(r)


def test_ten_wickets_stops_and_free_hit_runout_allowed():
    r = innings(
        BAT, BOWL, lambda *_: {"kind": "legal", "dismissed_role": 1, "credited_to_bowler": True}
    )
    assert r["legal_balls"] == 10 and r["wickets"] == 10 and r["termination"] == "all_out"
    conserved(r)
    r = innings(
        BAT,
        BOWL,
        scripted([{"kind": "noball", "noballs": 1}, {"kind": "legal", "dismissed_role": 1}]),
    )
    assert r["wickets"] == 1


@pytest.mark.parametrize(
    "event,score,balls",
    [
        ({"kind": "legal", "batter_runs": 6, "boundary": True}, 6, 1),
        ({"kind": "legal", "batter_runs": 3}, 1, 1),
        ({"kind": "wide", "wides": 5}, 1, 0),
        ({"kind": "noball", "noballs": 1, "batter_runs": 6, "boundary": True}, 1, 0),
    ],
)
def test_chase_ends_at_winning_event(event, score, balls):
    r = innings(BAT, BOWL, scripted([event]), target=1)
    assert r["runs"] == score and r["legal_balls"] == balls
    assert r["termination"] == "target_reached"
    conserved(r)


def test_pathological_extras_fails_instead_of_forcing_result():
    with pytest.raises(ApiError, match="physical-delivery"):
        innings(BAT, BOWL, lambda *_: {"kind": "wide", "wides": 1})
    with pytest.raises(ValueError):
        innings(BAT, BOWL, scripted([{"kind": "wide"}]))


def test_phase_and_mc_interval():
    assert [phase_at(b) for b in [0, 35, 36, 95, 96, 119]] == ["powerplay"] * 2 + ["middle"] * 2 + [
        "death"
    ] * 2
    assert 0 <= wilson(0, 50)["lower"] <= wilson(0, 50)["upper"] < 1
    assert wilson(50, 50)["upper"] == 1


def profiles(n=13):
    return [
        {
            "player_id": f"p{i}",
            "is_overseas": int(i >= 8),
            "is_wicketkeeper": int(i == 0),
            "primary_role": "allrounder",
        }
        for i in range(n)
    ]


def test_milp_matches_small_enumerated_selection_and_locks():
    ps = profiles()
    scores = np.arange(13, dtype=float)
    result = solve_xi(ps, scores, np.zeros((13, 20)), locked=["p1"])
    feasible = [
        c
        for c in itertools.combinations(range(13), 11)
        if 0 in c and 1 in c and sum(i >= 8 for i in c) <= 4
    ]
    assert result["proxy_score"] == max(sum(scores[i] for i in c) for c in feasible)
    assert result["proxy_optimality_proven"]
    plan = result["bowling_plan"]
    assert len(plan) == 20 and max(Counter(plan).values()) <= 4
    assert all(a != b for a, b in zip(plan, plan[1:], strict=False))
    second = solve_xi(ps, scores, np.zeros((13, 20)), cuts=[result["indices"]])
    assert set(second["indices"]) != set(result["indices"])


@pytest.mark.parametrize("failure", ["keeper", "bowling", "overseas", "batting"])
def test_infeasible_milp_returns_no_lineup(failure):
    ps = profiles(11)
    if failure == "keeper":
        for p in ps:
            p["is_wicketkeeper"] = 0
    if failure == "bowling":
        for p in ps[4:]:
            p["primary_role"] = "batter"
    if failure == "overseas":
        for p in ps:
            p["is_overseas"] = 1
    if failure == "batting":
        for p in ps:
            p["primary_role"] = "bowler"
    assert solve_xi(ps, np.zeros(11), np.zeros((11, 20))) is None


def team_plan(team):
    ids = [f"{team}{i}" for i in range(11)]
    return {
        "team_id": team,
        "starting_xi": ids,
        "batting_order": ids,
        "bowling_plan": [ids[6 + i % 5] for i in range(20)],
        "captain_id": ids[0],
    }


@pytest.fixture
def planning_client(data_dir):
    db = sqlite3.connect(data_dir / "ipl.sqlite")
    for team in ("CSK", "MI"):
        for i in range(13):
            pid = f"{team}{i}"
            db.execute(
                "INSERT INTO players (player_id,display_name,primary_role,is_overseas,is_wicketkeeper) VALUES (?,?,?,?,?)",
                (
                    pid,
                    pid,
                    "wicketkeeper_batter" if i == 0 else "batter" if i < 6 else "allrounder",
                    0,
                    int(i == 0),
                ),
            )
            db.execute(
                "INSERT INTO squads_current (player_id,team_id,season,roster_type) VALUES (?,?,?,?)",
                (pid, team, "2026", "official_website_snapshot"),
            )
    # Existing old pair acts as disjoint background; add valid illegal prototypes.
    db.execute("UPDATE deliveries SET noballs=1 WHERE delivery_id='2:1:3'")
    db.execute("UPDATE deliveries SET wides=1 WHERE delivery_id='2:1:4'")
    db.commit()
    db.close()
    with TestClient(create_app(Settings(data_dir))) as client:
        yield client


def payload():
    return {
        "as_of": "2026-04-02",
        "venue_id": "venue_test",
        "team_a": team_plan("CSK"),
        "team_b": team_plan("MI"),
        "batting_first_team_id": "CSK",
        "simulations": 50,
        "seed": 42,
        "allow_unknown_availability": True,
        "include_sample_match": True,
    }


def test_simulation_api_reproducible_readonly_and_cutoff(planning_client):
    first = planning_client.post("/api/v1/simulations/match", json=payload())
    assert first.status_code == 200, first.text
    assert first.json() == planning_client.post("/api/v1/simulations/match", json=payload()).json()
    data = first.json()["data"]
    assert not data["eligibility_verified"]
    assert data["training"]["last_included_date"] < "2026-04-02"
    assert sum(
        data["outcomes"][t]["probability"] for t in ("CSK", "MI", "unresolved_tie")
    ) == pytest.approx(1)
    for card in data["sample_match"]["innings"]:
        conserved(card)
        assert card["legal_balls"] <= 120 and card["wickets"] <= 10
        assert max(b["legal_balls"] for b in card["bowling"]) <= 24


@pytest.mark.parametrize(
    "change",
    [
        "availability",
        "quota",
        "duplicate",
        "size",
        "unknown_field",
        "inactive",
        "same_team",
        "season",
    ],
)
def test_invalid_planning_requests_fail_closed(planning_client, change):
    p = payload()
    if change == "availability":
        p["allow_unknown_availability"] = False
    if change == "quota":
        p["team_a"]["bowling_plan"] = ["CSK6"] * 20
    if change == "duplicate":
        p["team_a"]["starting_xi"][1] = "CSK0"
    if change == "size":
        p["simulations"] = 1001
    if change == "unknown_field":
        p["rain"] = True
    if change == "inactive":
        p["team_a"]["batting_order"][0] = "CSK12"
    if change == "same_team":
        p["team_b"] = p["team_a"]
    if change == "season":
        p["season"] = 2025
    assert planning_client.post("/api/v1/simulations/match", json=p).status_code == 422


def test_optimizer_api_confirmation_and_constraints(planning_client):
    request = {
        "as_of": "2026-04-02",
        "venue_id": "venue_test",
        "team_id": "CSK",
        "opponent": team_plan("MI"),
        "batting_first_team_id": "MI",
        "candidate_ids": [f"CSK{i}" for i in range(13)],
        "locked_ids": ["CSK1"],
        "excluded_ids": ["CSK12"],
        "allow_unknown_availability": True,
        "candidate_count": 2,
        "simulations": 50,
    }
    response = planning_client.post("/api/v1/optimization/xi", json=request)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert "CSK1" in result["recommended"]["plan"]["starting_xi"]
    assert "CSK12" not in result["recommended"]["plan"]["starting_xi"]
    assert len(result["alternatives"]) == 1
    assert result["confirmation"]["seed"] != request.get("seed", 20261002)
    assert not result["objective"]["global_win_probability_optimality_proven"]
    assert not result["eligibility_verified"]
    assert not result["reliability"]["win_probability_superiority_proven"]
    assert not result["reliability"]["confirmation"]["match_level_calibrated"]


def test_planning_slot_and_cors(planning_client):
    from backend.api import PLANNING_SLOT

    assert PLANNING_SLOT.acquire(blocking=False)
    try:
        assert planning_client.post("/api/v1/simulations/match", json=payload()).status_code == 429
    finally:
        PLANNING_SLOT.release()
    response = planning_client.options(
        "/api/v1/simulations/match",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert planning_client.get("/api/v1/rules").json()["data"]["season"] == 2026


def test_domestic_interval_impact_validation():
    plan = TeamPlan(
        **team_plan("CSK"),
        substitutes=["CSK11"],
        impact=ImpactPlan(outgoing_id="CSK1", incoming_id="CSK11"),
    )
    members = [
        {
            "player": {"player_id": f"CSK{i}", "is_overseas": 0, "is_wicketkeeper": i == 0},
            "availability": {"status": "unknown"},
        }
        for i in range(12)
    ]
    bat, bowl = validate_team(
        plan, members, batting_first=True, as_of=date(2026, 4, 2), allow_unknown=True
    )
    assert "CSK1" in bat and "CSK11" in bowl and "CSK1" not in bowl
    assert active_lineups(plan, False)[0] == bowl
    members[-1]["player"]["is_overseas"] = 1
    with pytest.raises(ApiError, match="Only domestic"):
        validate_team(plan, members, batting_first=True, as_of=date(2026, 4, 2), allow_unknown=True)


@pytest.mark.parametrize("dismissal", [False, True])
def test_super_over_repeat_cap_and_alternation(dismissal):
    from backend.match_models import SimulationRequest

    class ZeroEvidence:
        training = {"legal_striker_wicket_mode_records": 1}
        type_cdfs = {phase: np.array([1, 1, 1]) for phase in ("powerplay", "middle", "death")}
        free_hit_dismissal_share = 0

        def prepared(self, *_):
            pass

        def sample_joint(self, *_):
            return 0, False, dismissal

        def prototype(self, *args):
            return args[-1]

    request = SimulationRequest(**payload(), max_super_overs=3)
    result, _ = MatchSimulator(None, ZeroEvidence()).run(request, validated=({}, []))
    assert result["outcomes"]["unresolved_tie"]["count"] == 50
    overs = result["sample_match"]["super_overs"]
    assert [s["batting_first_team_id"] for s in overs] == ["MI", "CSK", "MI"]
    for team in ("CSK", "MI"):
        assert overs[0]["bowling_choices"][team] != overs[1]["bowling_choices"][team]
    assert result["sample_match"]["winner_id"] is None
    if dismissal:
        for inning_index in (0, 1):
            seen = set()
            for s in (overs[0], overs[2]):
                current = set(s["innings"][inning_index]["dismissed_ids"])
                assert not seen & current
                seen.update(current)


@pytest.mark.parametrize("failure", ["overseas", "keeper", "unknown_country", "unavailable"])
def test_profile_and_availability_checks_never_relax(failure):
    plan = TeamPlan(**team_plan("CSK"))
    members = [
        {
            "player": {
                "player_id": f"CSK{i}",
                "is_overseas": int(i < 5) if failure == "overseas" else 0,
                "is_wicketkeeper": i == 0 and failure != "keeper",
            },
            "availability": {"status": "unknown"},
        }
        for i in range(11)
    ]
    if failure == "unknown_country":
        members[0]["player"]["is_overseas"] = None
    if failure == "unavailable":
        members[0]["availability"] = {"status": "unavailable", "effective_on": "2026-04-02"}
    with pytest.raises(ApiError):
        validate_team(plan, members, batting_first=True, as_of=date(2026, 4, 2), allow_unknown=True)


def test_many_generated_scorecards_conserve_runs_and_balls():
    for seed in range(20):
        rng = np.random.default_rng(seed)

        def event(*_args, rng=rng):
            kind = int(rng.integers(20))
            if kind == 0:
                return {"kind": "wide", "wides": 1}
            if kind == 1:
                return {"kind": "noball", "noballs": 1, "batter_runs": 1}
            if kind == 2:
                return {"kind": "legal", "dismissed_role": 1, "credited_to_bowler": True}
            runs = int(rng.integers(4))
            return {"kind": "legal", "batter_runs": runs}

        r = innings(BAT, BOWL, event, target=100 if seed % 2 else None)
        conserved(r)
        assert 0 <= r["wickets"] <= 10 and 0 <= r["legal_balls"] <= 120


def test_optional_delivery_correction_and_reliability_flags(planning_client):
    raw = planning_client.post("/api/v1/simulations/match", json=payload())
    request = {**payload(), "use_delivery_calibration": True}
    response = planning_client.post("/api/v1/simulations/match", json=request)
    assert response.status_code == 200, response.text
    assert raw.json()["data"]["training"]["delivery_calibration"] == "raw_default"
    data = response.json()["data"]
    assert data["training"]["delivery_calibration"] == "joint-event-logit-2024-v1"
    assert not data["reliability"]["match_level_calibrated"]
    assert not data["reliability"]["decision_ready"]
    assert "availability_assumed_not_verified" in data["reliability"]["flags"]
    assert data["reliability"]["evidence"]["no_direct_history_fraction"] == 1
