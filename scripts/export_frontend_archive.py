"""Export only public match facts for a labelled offline frontend archive.

No invented schedules, forecasts, player metadata or raw third-party pages are
included. The source database is opened read-only and checked for changes.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/ipl-data/ipl.sqlite"
TARGET = ROOT / "frontend/src/api/snapshots"


def digest():
    with SOURCE.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    original = digest()
    db = sqlite3.connect(SOURCE.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    TARGET.mkdir(parents=True, exist_ok=True)
    for season in (2025, 2026):
        matches = [dict(r) for r in db.execute(
            "SELECT match_id,match_date,CAST(season AS INTEGER) AS season,team1_id,team2_id,"
            "venue_id,venue_name_raw,city,stage,winner_id,result,win_by_runs,win_by_wickets,"
            "result_method,toss_winner_id,toss_decision,scheduled_overs FROM matches "
            "WHERE season=? ORDER BY match_date DESC,match_id DESC", (str(season),)
        )]
        innings = [dict(r) for r in db.execute(
            "SELECT match_id,innings,batting_team_id,bowling_team_id,total_runs,wickets,"
            "legal_balls,is_super_over FROM innings WHERE season=? ORDER BY match_id,innings",
            (str(season),)
        )]
        data = {
            "schema": "concourse-match-archive-v1", "season": season,
            "exported_at": datetime.now(timezone.utc).isoformat(), "source_database_sha256": original,
            "provenance": "Saved project match archive derived from Cricsheet; observed records, not a complete fixture schedule or historical predictions.",
            "matches": matches, "innings": innings,
        }
        (TARGET / f"{season}.json").write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Saved {season}: {len(matches)} match records, {len(innings)} innings")
    db.close()
    if digest() != original:
        raise AssertionError("Source database changed")


if __name__ == "__main__":
    main()
