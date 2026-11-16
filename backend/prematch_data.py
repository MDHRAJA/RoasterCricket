"""Pilot data contracts: explicit missingness, conservative dates and real innings."""

import hashlib
import json
from datetime import date, datetime, timezone

PACK_SCHEMA = "ipl-match-day-evidence-v1"
BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
NOT_DISMISSED = {"retired hurt", "retired not out"}


def normalized_t20(match_id, doc, *, source_file):
    """Return match + per-innings player stats; no Test/ODI/Hundred/T10 leakage."""
    info = doc["info"]
    if (
        info.get("gender") != "male"
        or info.get("match_type") != "T20"
        or info.get("balls_per_over") != 6
        or info.get("overs", 20) != 20
    ):
        return None
    days = sorted(str(d) for d in info["dates"])
    if not days:
        raise ValueError("Match has no date")
    for day in days:
        date.fromisoformat(day)
    people = info["registry"]["people"]
    event = info.get("event", {})
    league = event.get("name") or (
        "T20 internationals" if info.get("team_type") == "international" else "unclassified T20"
    )
    match = {
        "match_id": str(match_id),
        "match_date": days[0],
        "available_after_date": days[-1],
        "competition": league,
        "team_type": info.get("team_type", "unknown"),
        "teams_json": json.dumps(info["teams"]),
        "is_ipl": int(league == "Indian Premier League"),
        "source_file": source_file,
        "result_method": info.get("outcome", {}).get("method", ""),
    }
    rows = []
    for number, inning in enumerate(doc["innings"], 1):
        if inning.get("super_over"):
            continue
        batting_team = inning["team"]
        bowling_team = next(t for t in info["teams"] if t != batting_team)
        stats = {}

        def player(name, team, stats=stats, number=number):
            pid = people[name]
            if pid not in stats:
                stats[pid] = {
                    "match_id": str(match_id),
                    "innings": number,
                    "player_id": pid,
                    "team_name": team,
                    "batted": 0,
                    "bowled": 0,
                    "batting_runs": 0,
                    "balls_faced": 0,
                    "dismissals": 0,
                    "fours": 0,
                    "sixes": 0,
                    "legal_balls_bowled": 0,
                    "runs_conceded": 0,
                    "bowler_wickets": 0,
                }
            return stats[pid]

        for over in inning.get("overs", []):
            for delivery in over["deliveries"]:
                batter = player(delivery["batter"], batting_team)
                non_striker = player(delivery["non_striker"], batting_team)
                bowler = player(delivery["bowler"], bowling_team)
                extras, runs = delivery.get("extras", {}), delivery["runs"]
                batter["batted"] = non_striker["batted"] = bowler["bowled"] = 1
                batter["batting_runs"] += int(runs["batter"])
                batter["balls_faced"] += int(not extras.get("wides"))
                batter["fours"] += int(runs["batter"] == 4 and not runs.get("non_boundary"))
                batter["sixes"] += int(runs["batter"] == 6 and not runs.get("non_boundary"))
                bowler["legal_balls_bowled"] += int(
                    not extras.get("wides") and not extras.get("noballs")
                )
                bowler["runs_conceded"] += int(
                    runs["total"]
                    - extras.get("byes", 0)
                    - extras.get("legbyes", 0)
                    - extras.get("penalty", 0)
                )
                for wicket in delivery.get("wickets", []):
                    out = player(wicket["player_out"], batting_team)
                    out["batted"] = 1
                    out["dismissals"] += int(wicket["kind"] not in NOT_DISMISSED)
                    bowler["bowler_wickets"] += int(wicket["kind"] in BOWLER_WICKETS)
        rows.extend(stats.values())
    return match, rows


def player_form(db, player_id, as_of, *, window_days=365, count=10):
    """Date blocked across competitions; DNB/DNBowl are not zero performances."""
    from datetime import timedelta

    if not 1 <= window_days <= 3653 or not 1 <= count <= 50:
        raise ValueError("Invalid form window or innings count")
    end = date.fromisoformat(as_of)
    start = (end - timedelta(days=window_days)).isoformat()
    rows = [
        dict(r)
        for r in db.execute(
            """SELECT s.*,m.available_after_date,m.competition,m.is_ipl
        FROM t20_player_innings s JOIN t20_matches m USING(match_id)
        WHERE s.player_id=? AND m.available_after_date>=? AND m.available_after_date<?
        ORDER BY m.available_after_date DESC,m.match_id DESC,s.innings DESC""",
            (player_id, start, as_of),
        )
    ]
    batting = [r for r in rows if r["batted"]][:count]
    bowling = [r for r in rows if r["bowled"]][:count]

    def aggregate(records, keys):
        return {key: int(sum(r[key] for r in records)) for key in keys}

    bat = aggregate(batting, ("batting_runs", "balls_faced", "dismissals", "fours", "sixes"))
    bowl = aggregate(bowling, ("legal_balls_bowled", "runs_conceded", "bowler_wickets"))
    used = batting + bowling
    return {
        "player_id": player_id,
        "exclusive_as_of": as_of,
        "window_start": start,
        "batting_innings": len(batting),
        "bowling_innings": len(bowling),
        "batting": bat,
        "bowling": bowl,
        "strike_rate": 100 * bat["batting_runs"] / bat["balls_faced"]
        if bat["balls_faced"]
        else None,
        "economy": 6 * bowl["runs_conceded"] / bowl["legal_balls_bowled"]
        if bowl["legal_balls_bowled"]
        else None,
        "non_ipl_batting_innings": sum(not r["is_ipl"] for r in batting),
        "non_ipl_bowling_innings": sum(not r["is_ipl"] for r in bowling),
        "latest_included_date": max((r["available_after_date"] for r in used), default=None),
        "source_match_ids": sorted({r["match_id"] for r in used}),
        "coverage": "available_Cricsheet_six_ball_twenty_over_men_matches_not_all_world_T20_cricket",
        "publication_time_of_raw_score_data_verified": False,
    }


def availability_as_of(claims, team_id, player_id, match_date, *, stage="", match_id=None):
    """No evidence is unknown, not available. Date-only claims exclude same day."""
    eligible = []
    for c in claims:
        if (
            c["team_id"] != team_id
            or c["player_id"] != player_id
            or c["season"] != int(match_date[:4])
        ):
            continue
        if c["published_on"] >= match_date or c["effective_from"] > match_date:
            continue
        if c.get("effective_through") and match_date > c["effective_through"]:
            continue
        if c.get("only_match_id") and c["only_match_id"] != match_id:
            continue
        if c.get("stage_scope") == "playoffs" and not stage:
            continue
        eligible.append(c)
    if not eligible:
        return {
            "status": "unknown",
            "claim_ids": [],
            "reason": "no_date_eligible_reviewed_evidence",
        }
    latest_day = max(c["published_on"] for c in eligible)
    latest = [c for c in eligible if c["published_on"] == latest_day]
    statuses = {c["status"] for c in latest}
    return {
        "status": next(iter(statuses)) if len(statuses) == 1 else "conflicting",
        "claim_ids": [c["claim_id"] for c in latest],
        "known_from_date": latest_day,
        "scope": "reviewed_public_reports_not_medical_or_registration_verification",
    }


def nomination_eligible(record, cutoff_at, *, allow_machine_checked=False):
    """Only explicitly reviewed, timestamped announcements enter strict lineups."""
    accepted = record.get("status") == "timestamped_report_reviewed"
    if allow_machine_checked and record.get("status") == "timestamped_report_machine_checked":
        required = (
            "known_unique_identities",
            "complete_membership",
            "no_known_team_membership_conflict",
            "independent_fixture_match",
            "original_starter_agreement_or_substitute_disjointness",
            "declared_timestamps_before_scheduled_start",
            "published_within_declared_one_hour_window",
        )
        accepted = all(record.get("checks", {}).get(key) is True for key in required)
    if not accepted or not record.get("published_at"):
        return False
    stamp = datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
    cutoff = datetime.fromisoformat(cutoff_at.replace("Z", "+00:00"))
    if stamp.tzinfo is None or cutoff.tzinfo is None:
        raise ValueError("Nomination/cutoff timestamps require explicit time zones")
    if record.get("modified_at"):
        changed = datetime.fromisoformat(record["modified_at"].replace("Z", "+00:00"))
        if changed.tzinfo is None or changed >= cutoff:
            return False
    return stamp.astimezone(timezone.utc) < cutoff.astimezone(timezone.utc)


SCHEMA = """
CREATE TABLE t20_matches(match_id TEXT PRIMARY KEY,match_date TEXT,available_after_date TEXT,
 competition TEXT,team_type TEXT,teams_json TEXT,is_ipl INTEGER,source_file TEXT,result_method TEXT);
CREATE TABLE t20_player_innings(match_id TEXT,innings INTEGER,player_id TEXT,team_name TEXT,
 batted INTEGER,bowled INTEGER,batting_runs INTEGER,balls_faced INTEGER,dismissals INTEGER,
 fours INTEGER,sixes INTEGER,legal_balls_bowled INTEGER,runs_conceded INTEGER,bowler_wickets INTEGER,
 PRIMARY KEY(match_id,innings,player_id),FOREIGN KEY(match_id) REFERENCES t20_matches(match_id));
CREATE INDEX player_form_lookup ON t20_player_innings(player_id,match_id);
CREATE INDEX match_completion_lookup ON t20_matches(available_after_date,match_id);
CREATE TABLE pilot_matches(pilot_match_id TEXT PRIMARY KEY,match_id TEXT,official_gid TEXT,
 match_date TEXT,start_at TEXT,team1_id TEXT,team2_id TEXT,stage TEXT,fixture_json TEXT);
CREATE TABLE additional_player_identities(player_id TEXT PRIMARY KEY,display_name TEXT,
 identity_json TEXT);
CREATE TABLE availability_claims(claim_id TEXT PRIMARY KEY,team_id TEXT,player_id TEXT,published_on TEXT,
 effective_from TEXT,status TEXT,source_url TEXT,claim_json TEXT);
CREATE TABLE nominations(pilot_match_id TEXT,team_id TEXT,kind TEXT,status TEXT,published_at TEXT,
 player_ids_json TEXT,source_url TEXT,evidence_json TEXT,PRIMARY KEY(pilot_match_id,team_id,kind));
CREATE TABLE player_form_snapshots(pilot_match_id TEXT,team_id TEXT,player_id TEXT,selection_basis TEXT,
 form_json TEXT,availability_json TEXT,PRIMARY KEY(pilot_match_id,team_id,player_id,selection_basis));
"""


def insert_dict(db, table, row):
    # Table/column names are internally defined, not public request parameters.
    columns = list(row)
    db.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
        [row[k] for k in columns],
    )


def nomination_review_digest(record):
    fields = (
        "match_id",
        "team_id",
        "kind",
        "published_at",
        "modified_at",
        "names",
        "player_ids",
        "source_url",
        "timestamp_basis",
    )
    value = {k: record.get(k) for k in fields}
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def team_membership_conflicts(player_ids, team_id, memberships):
    """Retrospective consistency audit only; never a dated availability feature."""
    return sorted(
        pid for pid in player_ids if memberships.get(pid) and team_id not in memberships[pid]
    )
