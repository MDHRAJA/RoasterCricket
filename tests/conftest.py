"""Synthetic, tiny fixtures. Tests do not need the private/raw 119 MB data pack."""

import csv
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app

ROOT = Path(__file__).resolve().parents[1]
A, B, C, D = "a1111111", "b1111111", "ipl:999", "d1111111"


@pytest.fixture
def data_dir(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    catalog = json.loads((ROOT / "outputs/ipl-data/dataset_catalog.json").read_text("utf-8"))
    db = sqlite3.connect(data / "ipl.sqlite")
    for entry in catalog:
        columns = ",".join('"' + col + '"' for col in entry["columns"])
        db.execute(f'CREATE TABLE "{entry["dataset"]}" ({columns})')

    def insert(table, row):
        cols = ",".join('"' + key + '"' for key in row)
        placeholders = ",".join("?" for _ in row)
        db.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})', tuple(row.values()))

    for pid, name, role, hand, history in [
        (A, "Test Batter", "batter", "right", 1),
        (B, "Test Bowler", "bowler", "left", 1),
        (C, "Test Newcomer", "allrounder", "left", 0),
        (D, "Test Unknown", "", "right", 1),
    ]:
        insert(
            "players",
            {
                "player_id": pid,
                "display_name": name,
                "full_name": name,
                "primary_role": role,
                "batting_hand": hand,
                "has_ipl_history": history,
                "country": "India",
                "is_overseas": 0,
                "is_wicketkeeper": 0,
                "metadata_conflict": "",
                "bowling_category": "spin" if pid == B else "pace",
            },
        )
        insert(
            "player_attributes",
            {
                "player_id": pid,
                "field": "batting_style",
                "value": hand,
                "source_url": "https://example.test/profile",
                "historical_validity": "not_established",
            },
        )
    for pid, alias in [(A, "tbatter"), (A, "shared"), (B, "shared")]:
        insert("player_aliases", {"player_id": pid, "normalized_alias": alias})
    for tid, current in [("CSK", 1), ("MI", 1), ("DCH", 0)]:
        insert("teams", {"team_id": tid, "display_name": tid, "is_current": current})
    insert(
        "venues",
        {"venue_id": "venue_test", "display_name": "Synthetic ground", "city": "Test city"},
    )
    for alias in ["Synthetic ground", "Renamed synthetic ground"]:
        insert("venue_aliases", {"venue_id": "venue_test", "venue_name_raw": alias})
    for pid, team in [(A, "CSK"), (B, "MI"), (C, "CSK"), (D, "CSK")]:
        insert(
            "squads_current",
            {
                "player_id": pid,
                "team_id": team,
                "season": "2026",
                "display_name": pid,
                "roster_type": "official_website_snapshot",
            },
        )
    dates = ["2026-03-28", "2026-03-29", "2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02"]
    for i, match_date in enumerate(dates, 1):
        mid = str(i)
        insert(
            "matches",
            {
                "match_id": mid,
                "match_date": match_date,
                "season": "2026",
                "team1_id": "CSK",
                "team2_id": "MI",
                "venue_id": "venue_test",
                "winner_id": "CSK",
            },
        )
        for pid, team in [(A, "CSK"), (B, "MI")]:
            insert(
                "match_players",
                {
                    "match_id": mid,
                    "player_id": pid,
                    "team_id": team,
                    "starting_status": "listed_original_or_unresolved",
                },
            )
    balls = [
        ("1", A, 4, 4, 1, 1, 0, "powerplay", 0),
        ("1", A, 0, 0, 1, 1, 0, "powerplay", 0),
        ("2", A, 6, 7, 0, 1, 0, "powerplay", 0),  # No-ball: counts faced, not legal.
        ("2", A, 0, 1, 0, 0, 0, "powerplay", 0),  # Wide: counts neither.
        ("2", A, 0, 0, 1, 1, 0, "powerplay", 0),
        ("3", A, 2, 2, 1, 1, 1, "middle", 0),
        ("5", D, 1, 1, 1, 1, 0, "death", 0),
        ("6", A, 6, 6, 1, 1, 0, "death", 1),  # Super Over excluded.
    ]
    for seq, (mid, batter, runs, total, legal, faced, out, phase, super_over) in enumerate(
        balls, 1
    ):
        insert(
            "deliveries",
            {
                "delivery_id": f"{mid}:1:{seq}",
                "match_id": mid,
                "match_date": dates[int(mid) - 1],
                "season": "2026",
                "venue_id": "venue_test",
                "innings": 1,
                "batter_id": batter,
                "bowler_id": B,
                "non_striker_id": A if mid == "5" else D,
                "batter_runs": runs,
                "total_runs": total,
                "legal_ball": legal,
                "ball_faced": faced,
                "bowler_runs_conceded": total,
                "striker_dismissed": out,
                "bowler_wicket": out,
                "team_wickets": out,
                "four": int(runs == 4),
                "six": int(runs == 6),
                "batting_dot": int(faced and not runs),
                "bowling_dot": int(legal and not total),
                "is_super_over": super_over,
                "phase": phase,
                "bowling_category": "spin",
                "bowling_arm": "left",
                "bowling_metadata_conflict": int(mid == "3"),
            },
        )
    # Prescribed match stats intentionally independent of API aggregation logic.
    batting = [
        (4, 2, 1, 2, 0),
        (6, 2, 1, 3, 0),
        (2, 1, 1, 1, 1),
        (0, 0, 0, 0, 0),
        (0, 0, 1, 0, 1),
        (0, 0, 0, 0, 0),
    ]
    for i, (runs, faced, batted, deliveries, dismissals) in enumerate(batting, 1):
        mid, match_date = str(i), dates[i - 1]
        subset = [b for b in balls if b[0] == mid and not b[-1]]
        for pid in (A, B):
            insert(
                "player_match_stats",
                {
                    "player_id": pid,
                    "match_id": mid,
                    "match_date": match_date,
                    "season": "2026",
                    "team_id": "CSK" if pid == A else "MI",
                    "venue_id": "venue_test",
                    "batting_runs": runs if pid == A else 0,
                    "balls_faced": faced if pid == A else 0,
                    "batted": batted if pid == A else 0,
                    "dismissals": dismissals if pid == A else 0,
                    "batting_deliveries": deliveries if pid == A else 0,
                    "fours": int(pid == A and i == 1),
                    "sixes": int(pid == A and i == 2),
                    "bowled": int(bool(subset)) if pid == B else 0,
                    "bowling_deliveries": len(subset) if pid == B else 0,
                    "legal_balls_bowled": sum(b[4] for b in subset) if pid == B else 0,
                    "runs_conceded": sum(b[3] for b in subset) if pid == B else 0,
                    "bowler_wickets": int(i == 3) if pid == B else 0,
                },
            )
        if subset:
            insert(
                "innings",
                {
                    "match_id": mid,
                    "match_date": match_date,
                    "season": "2026",
                    "venue_id": "venue_test",
                    "innings": 1,
                    "is_super_over": 0,
                    "total_runs": sum(b[3] for b in subset),
                    "legal_balls": sum(b[4] for b in subset),
                    "wickets": int(i == 3),
                    "powerplays_json": "[]",
                },
            )
    insert(
        "season_coverage",
        {"season": "2026", "matches": 6, "first_date": dates[0], "last_date": dates[-1]},
    )
    for item in catalog:
        item["rows"] = db.execute(f'SELECT COUNT(*) FROM "{item["dataset"]}"').fetchone()[0]
    db.commit()
    db.close()
    (data / "dataset_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (data / "coverage_summary.json").write_text(
        json.dumps({"players": 4, "matches": 6}), encoding="utf-8"
    )
    manual = data / "manual"
    manual.mkdir()
    with (manual / "availability.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "season",
                "team_id",
                "player_id",
                "availability",
                "effective_on",
                "source_url",
                "notes",
            ],
        )
        writer.writeheader()
        for pid in (A, C, D):
            writer.writerow(
                {"season": "2026", "team_id": "CSK", "player_id": pid, "availability": "unknown"}
            )
    return data


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(Settings(data_dir))) as client:
        yield client
