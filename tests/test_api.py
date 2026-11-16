import csv
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.database import connection
from backend.main import create_app
from backend.services import AnalyticsService
from tests.conftest import A, B, C


def test_health_readiness_and_documentation(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["data"]["database"] == "read_only"
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/analytics/matchup" in schema["paths"]
    assert "PlayerStatistics" in schema["components"]["schemas"]


def test_capabilities_are_honest(client):
    meta = client.get("/api/v1/metadata").json()
    assert meta["data"]["capabilities"]["descriptive_analytics"]
    assert meta["data"]["capabilities"]["bayesian_predictions"]
    assert not meta["data"]["capabilities"]["production_validated_predictions"]
    assert meta["data"]["capabilities"]["xi_optimization"]
    assert meta["data"]["capabilities"]["match_simulation"]
    assert not meta["data"]["capabilities"]["verified_match_eligibility"]


def test_catalog_and_seasons(client):
    assert len(client.get("/api/v1/datasets").json()["data"]) == 31
    assert client.get("/api/v1/seasons").json()["data"][0]["season"] == "2026"


def test_player_pagination_and_nulls(client):
    first = client.get("/api/v1/players?limit=2").json()
    second = client.get("/api/v1/players?limit=2&offset=2").json()
    assert first["total"] == 4
    assert {p["player_id"] for p in first["items"]}.isdisjoint(
        p["player_id"] for p in second["items"]
    )
    unknown = client.get("/api/v1/players/d1111111").json()["data"]
    assert unknown["primary_role"] is None
    assert unknown["metadata_conflict"] is None


@pytest.mark.parametrize(
    "query,count",
    [
        ("q=tBatter", 1),
        ("q=shared", 2),
        ("q=%25", 0),
        ("role=batter", 1),
        ("hand=left", 2),
        ("q=%27%20OR%201%3D1%20--", 0),
    ],
)
def test_safe_player_filters(client, query, count):
    response = client.get("/api/v1/players?" + query)
    assert response.status_code == 200
    assert response.json()["total"] == count


def test_local_player_ids_and_attribute_sources(client):
    response = client.get("/api/v1/players/ipl%3A999")
    assert response.status_code == 200
    assert response.json()["data"]["player_id"] == C
    assert not response.json()["data"]["has_ipl_history"]
    attributes = client.get(f"/api/v1/players/{A}/attributes").json()
    assert attributes["data"][0]["source_url"]
    assert "source_observation_is_not_historical_effective_date" in attributes["meta"]["warnings"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/players/absent",
        "/api/v1/venues/absent/profile",
        "/api/v1/teams/absent/roster?season=2026",
        "/api/v1/matches/absent",
    ],
)
def test_unknown_entity_errors(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"].endswith("_not_found")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/players?limit=0",
        "/api/v1/players?limit=101",
        "/api/v1/players?offset=-1",
        "/api/v1/players?role=opener",
        "/api/v1/players?q=",
        "/api/v1/matches?before=2026-02-30",
        "/api/v1/matches?season=2027",
        "/api/v1/matches?season=1900",
        f"/api/v1/players/{A}/form?window=7",
        "/api/v1/teams/CSK/roster?season=2025",
        f"/api/v1/analytics/matchup?batter_id={A}&bowler_id={B}&phase=nonsense",
        f"/api/v1/analytics/matchup?batter_id={A}&bowler_id={A}",
    ],
)
def test_invalid_parameters(client, path):
    response = client.get(path)
    assert response.status_code == 422
    assert "error" in response.json()


def test_statistical_cutoff_is_strict_and_excludes_cutoff_day(client):
    first = client.get(f"/api/v1/players/{A}/statistics?before=2026-03-29").json()
    assert first["data"]["runs"] == 4
    assert first["data"]["batting_innings"] == 1
    assert first["meta"]["before"] == "2026-03-29"
    second = client.get(f"/api/v1/players/{A}/statistics?before=2026-03-30").json()["data"]
    assert second["runs"] == 10


def test_form_excludes_dnb_and_includes_zero_faced_innings(client):
    result = client.get(f"/api/v1/players/{A}/form?window=5").json()["data"]
    assert result["summary"]["batting_innings"] == 4
    assert result["summary"]["runs"] == 12
    assert result["summary"]["runs_trend_per_innings"] is not None
    assert len(result["timeline"]) == 6


def test_form_before_cutoff_and_weights(client):
    result = client.get(f"/api/v1/players/{A}/form?before=2026-03-30").json()["data"]
    assert result["summary"]["batting_innings"] == 2
    assert result["summary"]["runs"] == 10
    assert result["summary"]["recency_weighted_runs"] == pytest.approx((4 * 0.85 + 6) / 1.85)
    assert all(r["match_date"] < "2026-03-30" for r in result["timeline"])
    assert result["summary"]["runs_trend_per_innings"] is None


def test_zero_history_is_not_zero_ability(client):
    result = client.get(f"/api/v1/players/{C}/statistics").json()["data"]
    assert result["matches_involved"] == 0
    assert result["strike_rate"] is None
    form = client.get(f"/api/v1/players/{C}/form").json()["data"]
    assert form["summary"]["runs"] is None
    assert form["summary"]["batting_innings"] == 0
    assert not form["timeline"]


def test_matchup_extra_denominators_and_super_over_exclusion(client):
    result = client.get(f"/api/v1/analytics/matchup?batter_id={A}&bowler_id={B}").json()
    m = result["data"]["metrics"]
    assert m["deliveries"] == 6
    assert m["legal_balls"] == 4
    assert m["balls_faced"] == 5
    assert m["batter_runs"] == 12
    assert m["bowler_runs_conceded"] == 14
    assert m["strike_rate"] == 240
    assert m["economy"] == 21
    assert sum(r["deliveries"] for r in result["data"]["outcomes"]) == m["deliveries"]
    assert "bowling_style_source_conflict_in_sample" in result["meta"]["warnings"]


def test_matchup_filters_are_combined(client):
    result = client.get(
        f"/api/v1/analytics/matchup?batter_id={A}&bowler_id={B}&phase=powerplay&before=2026-03-29&venue_id=venue_test&season=2026"
    ).json()["data"]
    assert result["metrics"]["deliveries"] == 2
    assert result["metrics"]["batter_runs"] == 4


def test_bowling_type_is_descriptive(client):
    response = client.get(f"/api/v1/analytics/bowling-type?batter_id={A}&category=spin&arm=left")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["metrics"]["batter_runs"] == 12
    assert "career_bowling_category_not_per_delivery_variation" in body["meta"]["warnings"]


def test_empty_matchup_has_null_rates(client):
    result = client.get(f"/api/v1/analytics/matchup?batter_id={C}&bowler_id={B}").json()
    assert result["data"]["metrics"]["deliveries"] == 0
    assert result["data"]["metrics"]["strike_rate"] is None
    assert result["data"]["outcomes"] == []
    assert "no_observed_matchup" in result["meta"]["warnings"]


def test_phase_profiles_honor_cutoff(client):
    body = client.get(f"/api/v1/players/{A}/phases?before=2026-03-30").json()
    assert len(body["data"]) == 3
    assert body["data"][0]["metrics"]["batter_runs"] == 10
    assert body["data"][1]["metrics"]["batter_runs"] == 0
    bowler = client.get(f"/api/v1/players/{B}/phases?side=bowling").json()["data"]
    assert sum(r["metrics"]["bowler_runs_conceded"] for r in bowler) == 15


def test_roster_is_not_verified_eligibility(client):
    result = client.get("/api/v1/teams/CSK/roster?season=2026").json()
    assert len(result["data"]["members"]) == 3
    assert not result["data"]["eligibility_verified"]
    assert all(r["availability"]["status"] == "unknown" for r in result["data"]["members"])


def test_unsourced_availability_is_downgraded(client, data_dir):
    path = data_dir / "manual/availability.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[0]["availability"] = "available"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    result = client.get("/api/v1/teams/CSK/roster?season=2026").json()
    assert result["data"]["members"][0]["availability"]["status"] == "unknown"
    assert "unsourced_or_undated_availability_downgraded_to_unknown" in result["meta"]["warnings"]


def test_missing_availability_stays_unknown(client, data_dir):
    (data_dir / "manual/availability.csv").unlink()
    body = client.get("/api/v1/teams/CSK/roster?season=2026").json()
    assert "availability_file_missing" in body["meta"]["warnings"]
    assert all(r["availability"]["status"] == "unknown" for r in body["data"]["members"])


def test_observed_membership_is_time_safe(client):
    result = client.get("/api/v1/teams/CSK/observed-roster?season=2026&before=2026-03-29").json()
    assert len(result["data"]) == 1
    assert result["data"][0]["matches_involved"] == 1
    assert "observed_participants_not_full_registered_squad" in result["meta"]["warnings"]


def test_team_and_match_filters(client):
    assert len(client.get("/api/v1/teams").json()["data"]) == 2
    assert len(client.get("/api/v1/teams?current_only=false").json()["data"]) == 3
    matches = client.get("/api/v1/matches?team_id=MI&before=2026-03-30&limit=1").json()
    assert matches["total"] == 2
    assert matches["items"][0]["match_id"] == "2"
    detail = client.get("/api/v1/matches/1").json()
    assert len(detail["data"]["participants"]) == 2
    assert "listed_participants_not_confirmed_starting_xi" in detail["meta"]["warnings"]


def test_venues_and_profiles(client):
    assert len(client.get("/api/v1/venues").json()["data"]) == 1
    result = client.get("/api/v1/venues/venue_test/profile?before=2026-03-29").json()
    assert result["data"]["matches"] == 1
    assert result["data"]["mean_first_innings_runs"] == 4
    assert result["data"]["runs_per_over"] == 12
    assert len(result["data"]["aliases"]) == 2
    assert "venue_scoring_profile_not_measured_pitch_condition" in result["meta"]["warnings"]
    phases = client.get("/api/v1/venues/venue_test/phases?before=2026-03-29").json()["data"]
    assert sum(r["metrics"]["batter_runs"] for r in phases) == 4


def test_cors_is_explicit(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = client.get("/health", headers={"Origin": "https://untrusted.test"})
    assert "access-control-allow-origin" not in blocked.headers


def test_database_connection_cannot_write(data_dir):
    with connection(Settings(data_dir)) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("DELETE FROM players")


def test_missing_database_fails_without_creating_file(tmp_path):
    with pytest.raises(RuntimeError, match="missing"), TestClient(create_app(Settings(tmp_path))):
        pass
    assert not (tmp_path / "ipl.sqlite").exists()


def test_incomplete_database_fails_fast(data_dir):
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.execute("DROP TABLE deliveries")
    with (
        pytest.raises(RuntimeError, match="schema is incomplete"),
        TestClient(create_app(Settings(data_dir))),
    ):
        pass


def test_inconsistent_snapshot_fails_fast(data_dir):
    path = data_dir / "dataset_catalog.json"
    catalog = json.loads(path.read_text("utf-8"))
    catalog[0]["as_of"] = "2020-01-01"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    with (
        pytest.raises(RuntimeError, match="consistent"),
        TestClient(create_app(Settings(data_dir))),
    ):
        pass


@pytest.mark.parametrize(
    "message,code", [("secret SQL path", "data_unavailable"), ("interrupted", "query_timeout")]
)
def test_database_errors_do_not_leak_details(client, monkeypatch, message, code):
    def fail(*_args, **_kwargs):
        raise sqlite3.OperationalError(message)

    monkeypatch.setattr(AnalyticsService, "rows", fail)
    result = client.get(f"/api/v1/players/{A}")
    assert result.status_code == 503
    assert result.json()["error"]["code"] == code
    assert message not in result.text


def test_query_budget_interrupts_long_sql(data_dir):
    with connection(Settings(data_dir, query_timeout_seconds=0.000001)) as db:
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            db.execute(
                "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1000000) SELECT SUM(n) FROM x"
            ).fetchone()


def test_form_window_10_and_empty_history_cutoff(client):
    response = client.get(f"/api/v1/players/{A}/form?window=10&before=2000-01-01")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["window"] == 10
    assert body["summary"]["runs"] is None
    assert body["latest_included_match_date"] is None
    assert body["timeline"] == []


@pytest.mark.parametrize("mutation", ["duplicate", "invalid_date", "invalid_status"])
def test_invalid_availability_fails_closed(client, data_dir, mutation):
    path = data_dir / "manual/availability.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    if mutation == "duplicate":
        rows.append(dict(rows[0]))
    elif mutation == "invalid_date":
        rows[0]["effective_on"] = "2026-02-30"
    else:
        rows[0]["availability"] = "fit_probably"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    result = client.get("/api/v1/teams/CSK/roster?season=2026").json()
    assert "availability_file_invalid_all_states_unknown" in result["meta"]["warnings"]
    assert all(r["availability"]["status"] == "unknown" for r in result["data"]["members"])


def test_dated_sourced_availability_is_record_not_verified_eligibility(client, data_dir):
    path = data_dir / "manual/availability.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[0].update(
        availability="unavailable",
        effective_on="2026-03-29",
        source_url="https://example.test/official-update",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    result = client.get("/api/v1/teams/CSK/roster?season=2026").json()
    assert result["data"]["members"][0]["availability"]["status"] == "unavailable"
    assert result["data"]["members"][0]["availability"]["effective_on"] == "2026-03-29"
    assert not result["data"]["eligibility_verified"]


def test_missing_columns_fail_at_startup(data_dir):
    with sqlite3.connect(data_dir / "ipl.sqlite") as db:
        db.execute("ALTER TABLE deliveries DROP COLUMN phase")
    with (
        pytest.raises(RuntimeError, match="columns are incomplete"),
        TestClient(create_app(Settings(data_dir))),
    ):
        pass


def test_empty_catalog_fails_at_startup(data_dir):
    (data_dir / "dataset_catalog.json").write_text("[]", encoding="utf-8")
    with pytest.raises(RuntimeError, match="metadata"), TestClient(create_app(Settings(data_dir))):
        pass


def test_mutations_are_not_exposed(client):
    assert client.post("/api/v1/players", json={"display_name": "Intruder"}).status_code == 405
