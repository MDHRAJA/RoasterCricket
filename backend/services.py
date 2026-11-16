"""Parameterized data queries and time-safe descriptive analytics, without HTTP coupling."""

import csv
import json
import math
import re
import sqlite3
import statistics
import unicodedata
from datetime import date

from backend.config import Settings


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def clean(row) -> dict:
    result = {}
    for key, value in dict(row).items():
        if value == "" or isinstance(value, float) and not math.isfinite(value):
            value = None
        if key.endswith("_json") and isinstance(value, str):
            value = json.loads(value)
        result[key] = value
    return result


def ratio(numerator, denominator, multiplier=1):
    return round(multiplier * numerator / denominator, 6) if denominator else None


def search_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub("[^a-z0-9]", "", value.lower())


def like_literal(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class AnalyticsService:
    def __init__(self, db: sqlite3.Connection, settings: Settings, snapshot: dict):
        self.db, self.settings, self.snapshot = db, settings, snapshot

    def rows(self, sql: str, params=()) -> list[dict]:
        return [clean(row) for row in self.db.execute(sql, params)]

    def require(self, kind: str, identifier: str) -> dict:
        table, key = {
            "player": ("players", "player_id"),
            "team": ("teams", "team_id"),
            "venue": ("venues", "venue_id"),
            "match": ("matches", "match_id"),
        }[kind]
        result = self.rows(f"SELECT * FROM {table} WHERE {key}=?", (identifier,))
        if not result:
            raise ApiError(404, f"{kind}_not_found", f"Unknown {kind} identifier")
        return result[0]

    def filters(self, *, season=None, before: date | None = None, venue_id=None, phase=None):
        clauses, params = [], []
        if season is not None:
            if season not in self.snapshot["seasons"]:
                raise ApiError(
                    422, "season_not_available", "No collected match data for this season"
                )
            clauses.append("season=?")
            params.append(str(season))
        if before is not None:
            clauses.append("match_date<?")
            params.append(before.isoformat())
        if venue_id is not None:
            self.require("venue", venue_id)
            clauses.append("venue_id=?")
            params.append(venue_id)
        if phase is not None:
            clauses.append("phase=?")
            params.append(str(phase))
        return clauses, params

    def players(self, *, q=None, role=None, hand=None, limit=50, offset=0):
        clauses, params = [], []
        if q:
            clauses.append("""(display_name LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\'
                OR player_id=? OR EXISTS (SELECT 1 FROM player_aliases a
                WHERE a.player_id=players.player_id AND a.normalized_alias=?))""")
            params += [like_literal(q), like_literal(q), q, search_key(q)]
        if role:
            clauses.append("primary_role=?")
            params.append(str(role))
        if hand:
            clauses.append("batting_hand=?")
            params.append(str(hand))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = self.db.execute("SELECT COUNT(*) FROM players" + where, params).fetchone()[0]
        items = self.rows(
            "SELECT * FROM players"
            + where
            + " ORDER BY display_name COLLATE NOCASE,player_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return items, total

    def availability(self, members: list[dict]) -> tuple[dict, list[str]]:
        path = self.settings.data_dir / "manual/availability.csv"
        warnings = [
            "roster_snapshot_is_not_verified_match_eligibility",
            "country_is_overseas_proxy",
            "availability_is_dated_manual_record_not_live_match_verification",
        ]
        entries = {}
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            for row in rows:
                key = (row["season"], row["team_id"], row["player_id"])
                if key in entries:
                    raise ValueError("Duplicate availability entries")
                status = row.get("availability", "unknown")
                if status not in {"available", "unavailable", "unknown"}:
                    raise ValueError("Invalid availability status")
                effective = row.get("effective_on", "")
                if effective:
                    date.fromisoformat(effective)
                source = row.get("source_url") or None
                # An unsourced or undated edit cannot assert match-specific fitness.
                if status != "unknown" and (not effective or not source):
                    status = "unknown"
                    warnings.append("unsourced_or_undated_availability_downgraded_to_unknown")
                entries[key] = {
                    "status": status,
                    "effective_on": effective or None,
                    "source_url": source,
                    "notes": row.get("notes") or None,
                }
        except FileNotFoundError:
            warnings.append("availability_file_missing")
        except (OSError, ValueError, KeyError, csv.Error):
            entries = {}
            warnings.append("availability_file_invalid_all_states_unknown")
        result = {}
        for row in members:
            key = (str(row["season"]), row["team_id"], row["player_id"])
            result[row["player_id"]] = entries.get(key, {"status": "unknown"})
        return result, list(dict.fromkeys(warnings))

    def roster(self, team_id: str, season: int):
        team = self.require("team", team_id)
        if season not in self.snapshot["roster_seasons"]:
            raise ApiError(
                422, "roster_snapshot_unavailable", "No official roster snapshot for this season"
            )
        members = self.rows(
            "SELECT * FROM squads_current WHERE team_id=? AND season=? ORDER BY display_name,player_id",
            (team_id, str(season)),
        )
        if not members:
            raise ApiError(404, "roster_not_found", "No official roster snapshot for this team")
        states, warnings = self.availability(members)
        profiles = {
            r["player_id"]: r
            for r in self.rows(
                "SELECT p.* FROM players p WHERE EXISTS (SELECT 1 FROM squads_current s "
                "WHERE s.player_id=p.player_id AND s.team_id=? AND s.season=?)",
                (team_id, str(season)),
            )
        }
        return {
            "team": team,
            "season": season,
            "roster_type": "official_website_snapshot",
            "members": [
                {
                    "player": profiles[r["player_id"]],
                    "roster": r,
                    "availability": states[r["player_id"]],
                }
                for r in members
            ],
            "eligibility_verified": False,
        }, warnings

    def player_statistics(self, player_id: str, **filters):
        self.require("player", player_id)
        clauses, params = self.filters(**filters)
        where = " AND ".join(["player_id=?", *clauses])
        sums = {
            "batting_innings": "batted",
            "bowling_innings": "bowled",
            "runs": "batting_runs",
            "balls_faced": "balls_faced",
            "dismissals": "dismissals",
            "fours": "fours",
            "sixes": "sixes",
            "wickets": "bowler_wickets",
            "legal_balls_bowled": "legal_balls_bowled",
            "runs_conceded": "runs_conceded",
        }
        query = ",".join(f"COALESCE(SUM({value}),0) AS {key}" for key, value in sums.items())
        row = self.rows(
            f"SELECT COUNT(*) AS matches_involved,{query} FROM player_match_stats WHERE {where}",
            [player_id, *params],
        )[0]
        row.update(
            player_id=player_id,
            batting_average=ratio(row["runs"], row["dismissals"]),
            strike_rate=ratio(row["runs"], row["balls_faced"], 100),
            economy=ratio(row["runs_conceded"], row["legal_balls_bowled"], 6),
            bowling_average=ratio(row["runs_conceded"], row["wickets"]),
        )
        return row

    def recent_form(self, player_id: str, window: int, before: date | None, timeline_limit: int):
        self.require("player", player_id)
        clauses, params = self.filters(before=before)
        where = " AND ".join(["player_id=?", *clauses])
        order = " ORDER BY match_date DESC,match_id DESC"
        base = "SELECT * FROM player_match_stats WHERE " + where
        batting = self.rows(
            base + " AND batted=1" + order + " LIMIT ?", [player_id, *params, window]
        )[::-1]
        bowling = self.rows(
            base + " AND bowled=1" + order + " LIMIT ?", [player_id, *params, window]
        )[::-1]
        timeline = self.rows(base + order + " LIMIT ?", [player_id, *params, timeline_limit])[::-1]
        runs = sum(r["batting_runs"] for r in batting) if batting else None
        balls = sum(r["balls_faced"] for r in batting) if batting else None
        weights = [0.85 ** (len(batting) - 1 - i) for i in range(len(batting))]
        weighted = (
            sum(w * r["batting_runs"] for w, r in zip(weights, batting, strict=True)) / sum(weights)
            if weights
            else None
        )
        slope = None
        if len(batting) >= 3:
            xmean = (len(batting) - 1) / 2
            ymean = runs / len(batting)
            slope = sum(
                (i - xmean) * (r["batting_runs"] - ymean) for i, r in enumerate(batting)
            ) / sum((i - xmean) ** 2 for i in range(len(batting)))
        legal = sum(r["legal_balls_bowled"] for r in bowling) if bowling else None
        summary = {
            "batting_innings": len(batting),
            "bowling_innings": len(bowling),
            "runs": runs,
            "balls_faced": balls,
            "strike_rate": ratio(runs, balls, 100),
            "runs_per_innings": ratio(runs, len(batting)),
            "recency_weighted_runs": weighted,
            "runs_trend_per_innings": slope,
            "wickets": sum(r["bowler_wickets"] for r in bowling) if bowling else None,
            "legal_balls_bowled": legal,
            "economy": ratio(sum(r["runs_conceded"] for r in bowling), legal, 6),
        }
        return {
            "player_id": player_id,
            "window": window,
            "latest_included_match_date": timeline[-1]["match_date"] if timeline else None,
            "summary": summary,
            "timeline": timeline,
        }

    def delivery_where(self, *, batter_id=None, bowler_id=None, category=None, arm=None, **filters):
        clauses, params = self.filters(**filters)
        clauses.insert(0, "is_super_over=0")
        for field, value in (
            ("batter_id", batter_id),
            ("bowler_id", bowler_id),
            ("bowling_category", category),
            ("bowling_arm", arm),
        ):
            if value is not None:
                clauses.append(field + "=?")
                params.append(str(value))
        return " AND ".join(clauses), params

    def delivery_metrics(self, where: str, params: list):
        fields = [
            "legal_ball",
            "ball_faced",
            "batter_runs",
            "total_runs",
            "bowler_runs_conceded",
            "bowler_wicket",
            "striker_dismissed",
            "four",
            "six",
            "batting_dot",
            "bowling_dot",
        ]
        names = [
            "legal_balls",
            "balls_faced",
            "batter_runs",
            "team_runs",
            "bowler_runs_conceded",
            "bowler_wickets",
            "striker_dismissals",
            "fours",
            "sixes",
            "batting_dots",
            "bowling_dots",
        ]
        sums = ",".join(f"COALESCE(SUM({f}),0) AS {n}" for f, n in zip(fields, names, strict=True))
        row = self.rows(
            f"SELECT COUNT(*) AS deliveries,COUNT(DISTINCT match_id) AS matches,{sums},"
            f"MIN(match_date) AS first_date,MAX(match_date) AS last_date FROM deliveries WHERE {where}",
            params,
        )[0]
        row.update(
            strike_rate=ratio(row["batter_runs"], row["balls_faced"], 100),
            economy=ratio(row["bowler_runs_conceded"], row["legal_balls"], 6),
            boundary_ball_rate=ratio(row["fours"] + row["sixes"], row["balls_faced"]),
            bowling_dot_rate=ratio(row["bowling_dots"], row["legal_balls"]),
        )
        return row

    def matchup(self, batter_id: str, bowler_id=None, category=None, arm=None, **filters):
        self.require("player", batter_id)
        if bowler_id is not None:
            self.require("player", bowler_id)
            if batter_id == bowler_id:
                raise ApiError(422, "self_matchup", "A player cannot face themselves")
        where, params = self.delivery_where(
            batter_id=batter_id, bowler_id=bowler_id, category=category, arm=arm, **filters
        )
        metrics = self.delivery_metrics(where, params)
        outcomes = self.rows(
            "SELECT batter_runs,striker_dismissed,COUNT(*) AS deliveries,"
            "SUM(legal_ball) AS legal_balls,SUM(ball_faced) AS balls_faced "
            f"FROM deliveries WHERE {where} GROUP BY batter_runs,striker_dismissed "
            "ORDER BY batter_runs,striker_dismissed",
            params,
        )
        warnings = ["observed_counts_not_forecast", "profile_attributes_not_time_versioned"]
        if metrics["balls_faced"] < 30:
            warnings.append("fewer_than_30_balls_faced")
        if not metrics["deliveries"]:
            warnings.append("no_observed_matchup")
        if self.db.execute(
            f"SELECT COUNT(*) FROM deliveries WHERE {where} AND bowling_metadata_conflict=1", params
        ).fetchone()[0]:
            warnings.append("bowling_style_source_conflict_in_sample")
        return {
            "batter_id": batter_id,
            "bowler_id": bowler_id,
            "metrics": metrics,
            "outcomes": outcomes,
        }, warnings

    def phases(self, player_id: str, side: str, **filters):
        self.require("player", player_id)
        key = "batter_id" if side == "batting" else "bowler_id"
        output = []
        for phase in ("powerplay", "middle", "death"):
            where, params = self.delivery_where(**{key: player_id}, phase=phase, **filters)
            output.append({"phase": phase, "metrics": self.delivery_metrics(where, params)})
        return output

    def matches(self, *, team_id=None, limit=50, offset=0, **filters):
        clauses, params = self.filters(**filters)
        if team_id is not None:
            self.require("team", team_id)
            clauses.append("(team1_id=? OR team2_id=?)")
            params += [team_id, team_id]
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = self.db.execute("SELECT COUNT(*) FROM matches" + where, params).fetchone()[0]
        rows = self.rows(
            "SELECT * FROM matches"
            + where
            + " ORDER BY match_date DESC,match_id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return rows, total

    def venue_profile(self, venue_id: str, **filters):
        venue = self.require("venue", venue_id)
        clauses, params = self.filters(venue_id=venue_id, **filters)
        where = " AND ".join(clauses)
        innings = self.rows("SELECT * FROM innings WHERE is_super_over=0 AND " + where, params)
        first = [r["total_runs"] for r in innings if r["innings"] == 1]
        runs, balls = sum(r["total_runs"] for r in innings), sum(r["legal_balls"] for r in innings)
        return {
            "venue": venue,
            "aliases": [
                r[0]
                for r in self.db.execute(
                    "SELECT venue_name_raw FROM venue_aliases WHERE venue_id=? ORDER BY venue_name_raw",
                    (venue_id,),
                )
            ],
            "matches": self.db.execute(
                "SELECT COUNT(*) FROM matches WHERE " + where, params
            ).fetchone()[0],
            "innings": len(innings),
            "runs": runs,
            "legal_balls": balls,
            "wickets": sum(r["wickets"] for r in innings),
            "runs_per_over": ratio(runs, balls, 6),
            "first_innings_count": len(first),
            "mean_first_innings_runs": statistics.mean(first) if first else None,
            "median_first_innings_runs": statistics.median(first) if first else None,
        }
