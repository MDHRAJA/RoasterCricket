"""Exercise the API against the saved real dataset and export the frontend contract."""

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.main import create_app  # noqa: E402


def file_hash(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    args = parser.parse_args()
    settings = Settings.from_env()
    original_hash = file_hash(settings.database)
    checks, timings = [], []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    with connection(settings) as db:
        counts = {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in ("players", "matches", "deliveries", "venues", "squads_current")
        }
        pair = db.execute(
            "SELECT batter_id,bowler_id,SUM(ball_faced) AS balls FROM deliveries "
            "WHERE is_super_over=0 GROUP BY batter_id,bowler_id ORDER BY balls DESC LIMIT 1"
        ).fetchone()
        batter_id, bowler_id = pair["batter_id"], pair["bowler_id"]
        reference = dict(
            db.execute(
                "SELECT COUNT(*) AS deliveries,SUM(ball_faced) AS balls_faced,"
                "SUM(legal_ball) AS legal_balls,SUM(batter_runs) AS batter_runs,"
                "SUM(bowler_runs_conceded) AS bowler_runs_conceded "
                "FROM deliveries WHERE is_super_over=0 AND batter_id=? AND bowler_id=?",
                (batter_id, bowler_id),
            ).fetchone()
        )
        latest = dict(
            db.execute("SELECT * FROM matches ORDER BY match_date DESC LIMIT 1").fetchone()
        )
        seasons = [int(r[0]) for r in db.execute("SELECT season FROM season_coverage")]

    with TestClient(create_app(settings)) as client:

        def get(path, **params):
            started = time.perf_counter()
            response = client.get(path, params=params)
            timings.append(
                {"path": path, "milliseconds": round((time.perf_counter() - started) * 1000, 3)}
            )
            check(f"GET {path} {params}: 200", response.status_code == 200)
            return response.json()

        get("/health")
        get("/ready")
        metadata = get("/api/v1/metadata")["data"]
        coverage = metadata["coverage"]
        for table, coverage_key in (
            ("players", "players"),
            ("matches", "matches"),
            ("deliveries", "deliveries"),
            ("venues", "venues"),
            ("squads_current", "current_squad_rows"),
        ):
            check(f"Saved {table} count matches coverage", counts[table] == coverage[coverage_key])
        check(
            "Predictions explicitly experimental",
            metadata["capabilities"]["bayesian_predictions"]
            and not metadata["capabilities"]["production_validated_predictions"],
        )
        catalog = get("/api/v1/datasets")["data"]
        check("All catalog entries served", len(catalog) == coverage["datasets"])
        check("All seasons served", len(get("/api/v1/seasons")["data"]) == len(seasons))
        players = get("/api/v1/players", limit=100)
        check(
            "Player count and bounded page",
            players["total"] == counts["players"] and len(players["items"]) == 100,
        )
        for player in players["items"][:3]:
            get("/api/v1/players", q=player["player_id"])
        get(f"/api/v1/players/{batter_id}")
        get(f"/api/v1/players/{batter_id}/attributes")
        get(f"/api/v1/players/{batter_id}/statistics", season=max(seasons))
        cutoff = latest["match_date"]
        for window in (5, 10):
            form = get(f"/api/v1/players/{batter_id}/form", window=window, before=cutoff)["data"]
            check(
                f"Form window {window} respects exclusive cutoff",
                all(r["match_date"] < cutoff for r in form["timeline"]),
            )
        get(f"/api/v1/players/{batter_id}/phases", before=cutoff)
        get(f"/api/v1/players/{bowler_id}/phases", side="bowling", before=cutoff)
        matchup = get("/api/v1/analytics/matchup", batter_id=batter_id, bowler_id=bowler_id)["data"]
        check(
            "Matchup counts equal independent raw-delivery sums",
            all(matchup["metrics"][k] == value for k, value in reference.items()),
        )
        check(
            "Outcome groups conserve deliveries",
            sum(r["deliveries"] for r in matchup["outcomes"]) == reference["deliveries"],
        )
        filtered = get(
            "/api/v1/analytics/matchup",
            batter_id=batter_id,
            bowler_id=bowler_id,
            before=cutoff,
            phase="powerplay",
        )["data"]
        check(
            "Filtered matchup respects cutoff",
            filtered["metrics"]["last_date"] is None or filtered["metrics"]["last_date"] < cutoff,
        )
        get(
            "/api/v1/analytics/bowling-type",
            batter_id=batter_id,
            category="spin",
            arm="right",
            before=cutoff,
        )
        forecast_payload = get(
            "/api/v1/predictions/matchup",
            batter_id=batter_id,
            bowler_id=bowler_id,
            as_of=cutoff,
            phase="powerplay",
            venue_id=latest["venue_id"],
            curves="true",
        )
        forecast = forecast_payload["data"]
        check(
            "Forecast run probabilities sum to one",
            abs(sum(r["probability"] for r in forecast["run_distribution"]) - 1) < 1e-10,
        )
        check(
            "Forecast training ends before target day",
            forecast["training"]["last_included_date"] < cutoff,
        )
        check(
            "Posterior probability curves exported",
            len(forecast["events"]["boundary"]["density_curve"]) == 61,
        )
        get("/api/v1/predictions/bowling-type", batter_id=batter_id, category="spin", as_of=cutoff)
        matches = get("/api/v1/matches", limit=100)
        check("Match count matches database", matches["total"] == counts["matches"])
        get(
            "/api/v1/matches",
            season=max(seasons),
            venue_id=latest["venue_id"],
            team_id=latest["team1_id"],
            before=cutoff,
        )
        get(f"/api/v1/matches/{latest['match_id']}")
        venues = get("/api/v1/venues")["data"]
        check("Venue count matches database", len(venues) == counts["venues"])
        get(f"/api/v1/venues/{latest['venue_id']}/profile", before=cutoff)
        get(f"/api/v1/venues/{latest['venue_id']}/phases", season=max(seasons), before=cutoff)
        teams = get("/api/v1/teams")["data"]
        get("/api/v1/teams", current_only="false")
        roster_members = 0
        for team in teams:
            roster = get(
                f"/api/v1/teams/{team['team_id']}/roster",
                season=max(metadata["roster_snapshot_seasons"]),
            )["data"]
            check(
                f"{team['team_id']} roster does not assert eligibility",
                not roster["eligibility_verified"],
            )
            roster_members += len(roster["members"])
        check("All saved current roster rows served", roster_members == counts["squads_current"])
        get(
            f"/api/v1/teams/{teams[0]['team_id']}/observed-roster",
            season=max(seasons),
            before=cutoff,
        )
        check(
            "Unknown IDs return 404", client.get("/api/v1/players/not-a-real-id").status_code == 404
        )
        check(
            "Invalid limits return 422", client.get("/api/v1/players?limit=101").status_code == 422
        )
        schema = get("/openapi.json")
        benchmark = get(
            "/api/v1/predictions/match-benchmark",
            team_a_id="CSK",
            team_b_id="MI",
            venue_id=latest["venue_id"],
            as_of=cutoff,
        )["data"]
        check(
            "Benchmark cutoff excludes same-day outcomes",
            benchmark["training"]["latest_training_date"] < cutoff,
        )
        check(
            "Validation-selected neutral benchmark is not a simulated favorite",
            benchmark["probability_team_a_wins_given_decisive_outcome"] == 0.5,
        )
        check(
            "Only analytics GETs and two computational POSTs",
            all(set(item) <= {"get", "post"} for item in schema["paths"].values())
            and sum("post" in item for item in schema["paths"].values()) == 2,
        )

    check(
        "Original database byte-for-byte unchanged", original_hash == file_hash(settings.database)
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "backend-openapi.json").write_text(
        json.dumps(schema, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "bayesian-example.json").write_text(
        json.dumps(forecast_payload, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "checked_on": date.today().isoformat(),
        "dataset_version": catalog[0]["as_of"],
        "passed_checks": len(checks),
        "checks": checks,
        "counts": counts,
        "documented_get_endpoints": sum("get" in p for p in schema["paths"].values()),
        "database_sha256_before_and_after": original_hash,
        "timings": timings,
        "timing_note": "Single local TestClient requests, including serialization; not a load test or production SLA.",
        "capabilities": metadata["capabilities"],
    }
    (args.output_dir / "backend-checks.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: report[k] for k in ("passed_checks", "counts", "documented_get_endpoints")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
