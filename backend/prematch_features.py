"""Date-blocked POST-TOSS features. Target performance never enters X.

Current profile attributes/rosters are deliberately not used. Lagged player-form
features describe the previous observed team. Optional original-XI inputs have
separate conditional provenance and never include future incoming Impact choices.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from itertools import groupby

import numpy as np
from scipy.special import expit

from backend.historical_planning import historical_cases

FEATURE_VERSION = "post-toss-prior-team-player-form-with-conditional-original-xi-v2"
TEAM_IDS = (
    "CSK",
    "DC",
    "DCH",
    "GL",
    "GT",
    "KKR",
    "KTK",
    "LSG",
    "MI",
    "PBKS",
    "PW",
    "RCB",
    "RPS",
    "RR",
    "SRH",
)
PHASES = ("powerplay", "middle", "death")


@dataclass(frozen=True)
class MatchContext:
    match_id: str
    match_date: str
    season: int
    venue_id: str
    batting_first_team_id: str
    chasing_team_id: str
    toss_winner_id: str
    stage: str = ""
    starting_xi_first: tuple[str, ...] | None = None
    starting_xi_chase: tuple[str, ...] | None = None

    def __post_init__(self):
        date.fromisoformat(self.match_date)
        if self.batting_first_team_id == self.chasing_team_id or self.toss_winner_id not in (
            self.batting_first_team_id,
            self.chasing_team_id,
        ):
            raise ValueError("Two distinct teams and their toss winner are required")
        if self.season != int(self.match_date[:4]):
            raise ValueError("Calendar-year season and date disagree")
        if (self.starting_xi_first is None) != (self.starting_xi_chase is None):
            raise ValueError("Supply both starting XIs or neither")
        if self.starting_xi_first is not None and (
            len(set(self.starting_xi_first)) != 11
            or len(self.starting_xi_first) != 11
            or len(set(self.starting_xi_chase)) != 11
            or len(self.starting_xi_chase) != 11
            or set(self.starting_xi_first) & set(self.starting_xi_chase)
        ):
            raise ValueError("Starting XIs must contain eleven distinct, disjoint players")


def read_archive(db):
    cases, excluded = historical_cases(db, seasons=range(2008, 2100))
    metadata = {r["match_id"]: dict(r) for r in db.execute("SELECT * FROM matches")}
    originals = defaultdict(lambda: defaultdict(list))
    for row in db.execute(
        "SELECT match_id,team_id,player_id FROM match_players WHERE is_incoming_match_replacement=0"
    ):
        originals[row["match_id"]][row["team_id"]].append(row["player_id"])
    innings = defaultdict(dict)
    for row in db.execute("SELECT * FROM innings WHERE is_super_over=0"):
        innings[row["match_id"]][row["batting_team_id"]] = dict(row)
    phase_stats = defaultdict(dict)
    for row in db.execute("""SELECT match_id,batting_team_id,phase,SUM(total_runs) AS runs,
        SUM(legal_ball) AS balls,SUM(team_wickets) AS wickets FROM deliveries
        WHERE is_super_over=0 GROUP BY match_id,batting_team_id,phase"""):
        phase_stats[row["match_id"]][row["batting_team_id"], row["phase"]] = {
            "runs": float(row["runs"]),
            "balls": int(row["balls"]),
            "wickets": int(row["wickets"]),
        }
    player_stats = defaultdict(list)
    for row in db.execute(
        "SELECT * FROM player_match_stats ORDER BY match_date,match_id,player_id"
    ):
        player_stats[row["match_id"]].append(dict(row))
    observations = []
    for case in cases:
        meta = metadata[case["match_id"]]
        first, second = case["team_a_id"], case["team_b_id"]
        # Known order is reconstructed from toss metadata, NOT target deliveries.
        toss = meta["toss_winner_id"]
        decision = meta["toss_decision"]
        if toss not in (first, second) or decision not in ("bat", "field"):
            excluded.append(
                {
                    "match_id": case["match_id"],
                    "season": case["season"],
                    "reason": "missing_toss_context",
                }
            )
            continue
        expected_first = toss if decision == "bat" else (second if toss == first else first)
        if expected_first != first:
            excluded.append(
                {
                    "match_id": case["match_id"],
                    "season": case["season"],
                    "reason": "toss_and_innings_order_disagree",
                }
            )
            continue
        context = MatchContext(
            case["match_id"],
            case["date"],
            case["season"],
            case["venue_id"],
            first,
            second,
            toss,
            meta["stage"] or "",
            tuple(sorted(originals[case["match_id"]][first])),
            tuple(sorted(originals[case["match_id"]][second])),
        )
        observations.append(
            {
                "context": context,
                "outcome": int(case["actual"]["winner_id"] == first),
                "winner_id": case["actual"]["winner_id"],
                "innings": innings[case["match_id"]],
                "phases": phase_stats[case["match_id"]],
                "players": case["participant_pools"],
                "player_stats": player_stats[case["match_id"]],
            }
        )
    return observations, excluded


def smoothed_rate(values, strength=6.0, mean=0.5):
    return (sum(values) + strength * mean) / (len(values) + strength)


class FeatureState:
    def __init__(self):
        self.history = []
        self.teams = defaultdict(list)
        self.player_batting = defaultdict(list)
        self.player_bowling = defaultdict(list)
        self.ratings = {20: defaultdict(float), 40: defaultdict(float)}
        self.rating_year = None
        self.last_date = None
        self.total_bat_runs = self.total_balls_faced = self.total_bowl_runs = self.total_legal = 0

    def _team_rows(self, team, context):
        start = (date.fromisoformat(context.match_date) - timedelta(days=1461)).isoformat()
        return [r for r in self.teams[team] if start <= r["date"] < context.match_date]

    def _summary(self, team, context):
        rows = self._team_rows(team, context)
        year = [r for r in rows if r["season"] == context.season]
        venue = [r for r in rows if r["venue_id"] == context.venue_id]
        result = {
            "win5": smoothed_rate([r["won"] for r in rows[-5:]]),
            "win10": smoothed_rate([r["won"] for r in rows[-10:]]),
            "win20": smoothed_rate([r["won"] for r in rows[-20:]]),
            "season_win": smoothed_rate([r["won"] for r in year]),
            "venue_win": smoothed_rate([r["won"] for r in venue[-20:]]),
            "first_win": smoothed_rate([r["won"] for r in rows[-40:] if r["batting_first"]]),
            "chase_win": smoothed_rate([r["won"] for r in rows[-40:] if not r["batting_first"]]),
            "history_count": float(np.log1p(len(rows))),
            "season_count": float(len(year)),
            "venue_count": float(np.log1p(len(venue))),
            "rest_days": min(
                60,
                (
                    date.fromisoformat(context.match_date) - date.fromisoformat(rows[-1]["date"])
                ).days,
            )
            if rows
            else 60,
        }
        for n in (5, 10):
            recent = rows[-n:]
            for name, prior in (
                ("bat_rr", 8.0),
                ("bowl_rr", 8.0),
                ("bat_wickets", 6.0),
                ("bowl_wickets", 6.0),
                ("nrr", 0.0),
            ):
                result[f"{name}{n}"] = (sum(r[name] for r in recent) + 3 * prior) / (
                    len(recent) + 3
                )
        for phase in PHASES:
            for side in ("bat", "bowl"):
                recent = rows[-10:]
                runs = sum(r[f"{side}_phases"].get(phase, {}).get("runs", 0) for r in recent)
                balls = sum(r[f"{side}_phases"].get(phase, {}).get("balls", 0) for r in recent)
                result[f"{side}_{phase}_rr"] = 6 * (runs + 60 * 1.3) / (balls + 60)
        return result, rows

    def _lagged_players(self, rows, explicit_players=None):
        # Last observed participants are a historical proxy, never target inputs.
        players = (
            explicit_players
            if explicit_players is not None
            else rows[-1]["players"]
            if rows
            else []
        )
        bat_prior = (
            self.total_bat_runs / max(1, self.total_balls_faced) if self.total_balls_faced else 1.3
        )
        bowl_prior = self.total_bowl_runs / max(1, self.total_legal) if self.total_legal else 1.3
        batting, bowling, dismissals, boundaries, bowling_wickets, familiar = [], [], [], [], [], []
        for player in players:
            bat = self.player_batting[player][-10:]
            bowl = self.player_bowling[player][-10:]
            br, bf = (
                sum(r["batting_runs"] or 0 for r in bat),
                sum(r["balls_faced"] or 0 for r in bat),
            )
            batting.append((br + 30 * bat_prior) / (bf + 30))
            dismissals.append((sum(r["dismissals"] or 0 for r in bat) + 1.5) / (bf + 30))
            boundaries.append(
                (sum((r["fours"] or 0) + (r["sixes"] or 0) for r in bat) + 5) / (bf + 30)
            )
            legal = sum(r["legal_balls_bowled"] or 0 for r in bowl)
            bowling.append(
                (sum(r["runs_conceded"] or 0 for r in bowl) + 30 * bowl_prior) / (legal + 30)
            )
            bowling_wickets.append(
                (sum(r["bowler_wickets"] or 0 for r in bowl) + 1.5) / (legal + 30)
            )
            familiar.append(int(bool(bat or bowl)))
        return {
            "lagged_top7_bat_runs_per_ball": float(np.mean(sorted(batting, reverse=True)[:7]))
            if batting
            else bat_prior,
            "lagged_top5_bowl_runs_per_ball": float(np.mean(sorted(bowling)[:5]))
            if bowling
            else bowl_prior,
            "lagged_bat_dismissal_rate": float(np.mean(dismissals)) if dismissals else 0.05,
            "lagged_boundary_rate": float(np.mean(boundaries)) if boundaries else 0.17,
            "lagged_bowling_wicket_rate": float(np.mean(sorted(bowling_wickets, reverse=True)[:5]))
            if bowling_wickets
            else 0.05,
            "lagged_experienced_players": sum(familiar),
        }

    def predict_features(self, context):
        if self.last_date is not None and self.last_date >= context.match_date:
            raise ValueError("Same-day/future performance in feature state")
        first, chase = context.batting_first_team_id, context.chasing_team_id
        a, ar = self._summary(first, context)
        b, br = self._summary(chase, context)
        features = {f"diff_{k}": float(a[k] - b[k]) for k in sorted(a)}
        features.update(
            {
                f"diff_{k}": float(v - self._lagged_players(br)[k])
                for k, v in self._lagged_players(ar).items()
            }
        )
        # Optional original starters only: no target batting order or incoming
        # Impact Player selection. Archive reconstruction is NOT timestamp-verified.
        xi_a = self._lagged_players(ar, context.starting_xi_first)
        xi_b = self._lagged_players(br, context.starting_xi_chase)
        features.update({f"diff_xi_{k}": float(value - xi_b[k]) for k, value in xi_a.items()})
        for k, ratings in self.ratings.items():
            carry = 0.8 ** max(0, context.season - (self.rating_year or context.season))
            features[f"elo{k}_diff"] = (ratings[first] - ratings[chase]) * carry / 400
        start = (date.fromisoformat(context.match_date) - timedelta(days=1461)).isoformat()
        history = [r for r in self.history if start <= r["context"].match_date < context.match_date]
        venue = [r for r in history if r["context"].venue_id == context.venue_id]
        season = [r for r in history if r["context"].season == context.season]
        h2h = [r for r in ar if r["opponent"] == chase]
        features.update(
            {
                "league_first_win50": smoothed_rate([r["outcome"] for r in history[-50:]], 10),
                "season_first_win": smoothed_rate([r["outcome"] for r in season], 20),
                "venue_first_win40": smoothed_rate([r["outcome"] for r in venue[-40:]], 10),
                "venue_history": float(np.log1p(len(venue))),
                "h2h_first_team_win": smoothed_rate([r["won"] for r in h2h[-20:]]),
                "first_team_won_toss": float(context.toss_winner_id == first),
                "season_progress": float(len(season) / 74),
                "impact_era": float(context.season >= 2023),
                "season_trend": float((context.season - 2018) / 8),
                "knockout": float(bool(context.stage)),
                "league_first_score50": float(
                    np.mean(
                        [
                            r["innings"][r["context"].batting_first_team_id]["total_runs"]
                            for r in history[-50:]
                        ]
                    )
                )
                if history
                else 160.0,
            }
        )
        for team in TEAM_IDS:
            features[f"identity_{team}"] = float(first == team) - float(chase == team)
        if not all(np.isfinite(v) for v in features.values()):
            raise ValueError("Non-finite historical feature")
        trace = {
            "latest_feature_evidence_date": self.last_date,
            "prior_eligible_matches": len(history),
            "starting_xis_supplied": context.starting_xi_first is not None,
            "starting_xi_provenance": "archive_original_players_excluding_incoming_replacements_not_timestamp_verified"
            if context.starting_xi_first is not None
            else "not_supplied_lagged_proxy_only",
            "target_performance_or_incoming_impact_players_used": False,
            "lagged_roster_dates": {
                first: ar[-1]["date"] if ar else None,
                chase: br[-1]["date"] if br else None,
            },
            "information_scope": "post_toss_known_teams_venue_order_plus_earlier_observations",
        }
        return features, trace

    def update_day(self, observations):
        if not observations:
            return
        day = observations[0]["context"].match_date
        if any(r["context"].match_date != day for r in observations) or (
            self.last_date and self.last_date >= day
        ):
            raise ValueError("Updates must be strictly increasing whole date blocks")
        year = observations[0]["context"].season
        if self.rating_year is not None and year > self.rating_year:
            for ratings in self.ratings.values():
                for team in ratings:
                    ratings[team] *= 0.8 ** (year - self.rating_year)
        self.rating_year = year
        deltas = {k: Counter() for k in self.ratings}
        for r in observations:
            context = r["context"]
            first, chase = context.batting_first_team_id, context.chasing_team_id
            for k, ratings in self.ratings.items():
                expected = float(expit(np.log(10) * (ratings[first] - ratings[chase]) / 400))
                delta = k * (r["outcome"] - expected)
                deltas[k][first] += delta
                deltas[k][chase] -= delta
            for team, other in ((first, chase), (chase, first)):
                bat, bowl = r["innings"][team], r["innings"][other]
                bat_rr = (
                    6
                    * bat["total_runs"]
                    / max(1, 120 if bat["wickets"] == 10 else bat["legal_balls"])
                )
                bowl_rr = (
                    6
                    * bowl["total_runs"]
                    / max(1, 120 if bowl["wickets"] == 10 else bowl["legal_balls"])
                )
                self.teams[team].append(
                    {
                        "date": day,
                        "season": year,
                        "venue_id": context.venue_id,
                        "won": int(r["winner_id"] == team),
                        "batting_first": team == first,
                        "opponent": other,
                        "bat_rr": bat_rr,
                        "bowl_rr": bowl_rr,
                        "nrr": bat_rr - bowl_rr,
                        "bat_wickets": bat["wickets"],
                        "bowl_wickets": bowl["wickets"],
                        "players": r["players"].get(team, []),
                        "bat_phases": {
                            phase: r["phases"].get((team, phase), {}) for phase in PHASES
                        },
                        "bowl_phases": {
                            phase: r["phases"].get((other, phase), {}) for phase in PHASES
                        },
                    }
                )
            for stats in r["player_stats"]:
                pid = stats["player_id"]
                if stats["batted"]:
                    self.player_batting[pid].append(stats)
                    self.total_bat_runs += stats["batting_runs"] or 0
                    self.total_balls_faced += stats["balls_faced"] or 0
                if (stats["legal_balls_bowled"] or 0) > 0:
                    self.player_bowling[pid].append(stats)
                    self.total_bowl_runs += stats["runs_conceded"] or 0
                    self.total_legal += stats["legal_balls_bowled"] or 0
        for k, changes in deltas.items():
            for team, change in changes.items():
                self.ratings[k][team] += change
        self.history.extend(observations)
        self.last_date = day


def feature_table(observations):
    rows, state = [], FeatureState()
    ordered = sorted(observations, key=lambda r: (r["context"].match_date, r["context"].match_id))
    for _, chunk in groupby(ordered, key=lambda r: r["context"].match_date):
        chunk = list(chunk)
        for r in chunk:
            values, trace = state.predict_features(r["context"])
            rows.append(
                {
                    "context": asdict(r["context"]),
                    "outcome": r["outcome"],
                    "features": values,
                    "trace": trace,
                }
            )
        state.update_day(chunk)
    return rows
