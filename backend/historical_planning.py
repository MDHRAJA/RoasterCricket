"""Offline historical scenarios, explicitly NOT verified pre-match team sheets.

Target deliveries are used only to screen/score outcomes, never to select batting
positions or a bowling schedule. Participant pools are post-match observations.
"""

from collections import Counter, defaultdict
from datetime import timedelta

import numpy as np

from backend.bayesian import DEFAULT_CONFIG
from backend.match_models import ImpactPlan, TeamPlan

STRATEGY_VERSION = "prior-only-position-phase-usage-v1"


def historical_cases(db, seasons=(2024, 2025, 2026)):
    """Every requested match gets a case or an attributable exclusion record."""
    seasons = set(seasons)
    matches = [dict(r) for r in db.execute("SELECT * FROM matches ORDER BY match_date,match_id")]
    innings = defaultdict(list)
    for row in db.execute("SELECT * FROM innings ORDER BY match_id,innings"):
        innings[row["match_id"]].append(dict(row))
    pools = defaultdict(lambda: defaultdict(list))
    for row in db.execute("SELECT match_id,team_id,player_id FROM match_players"):
        pools[row["match_id"]][row["team_id"]].append(row["player_id"])
    cases, exclusions = [], []
    for match in matches:
        if int(match["season"]) not in seasons:
            continue
        mid = match["match_id"]
        records = innings[mid]
        regular = [i for i in records if not i["is_super_over"]]
        reason = None
        if match["scheduled_overs"] != 20 or match["balls_per_over"] != 6:
            reason = "not_scheduled_twenty_six_ball_overs"
        elif match["result_method"]:
            reason = "adjusted_result_method"
        elif len(regular) != 2:
            reason = "not_two_recorded_regular_innings"
        elif any(i["is_super_over"] for i in records) or match["result"] != "win":
            reason = "tie_super_over_or_no_decisive_regular_result"
        elif match["winner_id"] not in (match["team1_id"], match["team2_id"]):
            reason = "winner_missing_or_invalid"
        else:
            one, two = regular
            if (
                one["innings"] != 1
                or two["innings"] != 2
                or one["batting_team_id"] != two["bowling_team_id"]
                or two["batting_team_id"] != one["bowling_team_id"]
                or set((one["batting_team_id"], two["batting_team_id"]))
                != set((match["team1_id"], match["team2_id"]))
            ):
                reason = "inconsistent_innings_teams"
            elif any(i["penalty_runs_pre"] or i["penalty_runs_post"] for i in regular):
                reason = "innings_penalties_not_supported"
            elif any(
                not 0 < i["legal_balls"] <= 120
                or not 0 <= i["wickets"] <= 10
                or i["total_runs"] < 0
                for i in regular
            ):
                reason = "invalid_or_reduced_innings_length"
            elif not (one["legal_balls"] == 120 or one["wickets"] == 10):
                reason = "first_innings_not_complete"
            elif two["target_runs"] not in (None, one["total_runs"] + 1) or two[
                "target_overs"
            ] not in (None, 20, 20.0):
                reason = "revised_or_inconsistent_target"
            elif not (
                two["total_runs"] > one["total_runs"]
                or two["legal_balls"] == 120
                or two["wickets"] == 10
            ):
                reason = "chase_incomplete"
            elif two["total_runs"] == one["total_runs"] or match["winner_id"] != (
                two["batting_team_id"]
                if two["total_runs"] > one["total_runs"]
                else one["batting_team_id"]
            ):
                reason = "score_and_winner_disagree"
        if reason:
            exclusions.append({"match_id": mid, "season": int(match["season"]), "reason": reason})
            continue
        one, two = regular
        participants = {
            t: sorted(set(pools[mid][t])) for t in (match["team1_id"], match["team2_id"])
        }
        supports_players = all(11 <= len(ids) <= 12 for ids in participants.values())
        if set(participants[match["team1_id"]]) & set(participants[match["team2_id"]]):
            supports_players = False
        cases.append(
            {
                "match_id": mid,
                "date": match["match_date"],
                "season": int(match["season"]),
                "venue_id": match["venue_id"],
                "team_a_id": one["batting_team_id"],
                "team_b_id": two["batting_team_id"],
                "batting_first_team_id": one["batting_team_id"],
                "participant_pools": participants,
                "participant_conditioned_supported": supports_players,
                "actual": {
                    "first_runs": int(one["total_runs"]),
                    "second_runs": int(two["total_runs"]),
                    "first_wickets": int(one["wickets"]),
                    "second_wickets": int(two["wickets"]),
                    "winner_id": match["winner_id"],
                },
            }
        )
    return cases, exclusions


class PriorStrategies:
    """Date-filtered usage only; no current profile/role/country metadata."""

    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: (r["date"], r["match_id"], r["player_id"]))

    @classmethod
    def from_database(cls, db):
        # First appearance includes the non-striker, so openers both rank first.
        # It intentionally does NOT use the ordering of info.players.
        appearances = defaultdict(dict)
        for r in db.execute("""SELECT match_id,innings,batter_id,non_striker_id,
            MIN(sequence_in_innings) AS first_sequence FROM deliveries
            WHERE is_super_over=0 GROUP BY match_id,innings,batter_id,non_striker_id"""):
            key = (r["match_id"], r["innings"])
            for pid in (r["batter_id"], r["non_striker_id"]):
                appearances[key][pid] = min(
                    appearances[key].get(pid, float("inf")), r["first_sequence"]
                )
        positions = {}
        for (mid, _), players in appearances.items():
            for pid, first in players.items():
                positions[mid, pid] = 1 + sum(n < first for n in players.values())
        phases = defaultdict(Counter)
        for r in db.execute("""SELECT match_id,bowler_id,phase,SUM(legal_ball) AS n
            FROM deliveries WHERE is_super_over=0 GROUP BY match_id,bowler_id,phase"""):
            phases[r["match_id"], r["bowler_id"]][r["phase"]] = int(r["n"])
        rows = []
        for r in db.execute("SELECT * FROM player_match_stats ORDER BY match_date,match_id"):
            rows.append(
                {
                    "date": r["match_date"],
                    "match_id": r["match_id"],
                    "player_id": r["player_id"],
                    "position": positions.get((r["match_id"], r["player_id"])),
                    "bowling": dict(phases[r["match_id"], r["player_id"]]),
                }
            )
        return cls(rows)

    def plan(self, team_id, participants, as_of, *, batting_first):
        if len(set(participants)) != len(participants) or not 11 <= len(participants) <= 12:
            raise ValueError(
                "Participant-conditioned strategy needs eleven or twelve unique players"
            )
        allowed = set(participants)
        start = (as_of - timedelta(days=DEFAULT_CONFIG.lookback_days)).isoformat()
        cutoff = as_of.isoformat()
        positions, usage, appearances = defaultdict(list), defaultdict(Counter), Counter()
        dates = []
        for row in self.rows:
            if start <= row["date"] < cutoff and row["player_id"] in allowed:
                pid = row["player_id"]
                dates.append(row["date"])
                appearances[pid] += 1
                if row["position"] is not None:
                    positions[pid].append(row["position"])
                usage[pid].update(row["bowling"])

        def position(pid):
            return float(np.median(positions[pid][-10:])) if positions[pid] else 8.0

        # Smooth an early-career player's exposure toward six balls per appearance.
        def bowling_rate(pid, phase=None):
            balls = usage[pid][phase] if phase else sum(usage[pid].values())
            return (balls + (2 if phase else 6)) / (appearances[pid] + 2)

        batting = sorted(participants, key=lambda pid: (position(pid), -len(positions[pid]), pid))[
            :11
        ]
        bowling_active = sorted(participants, key=lambda pid: (-bowling_rate(pid), pid))[:11]
        bowlers = bowling_active[:5]
        # Alternating the chosen five guarantees <=4 overs and no adjacent repeats.
        # Phase-specific assignment is fixed using only preceding-match usage.
        counts, schedule = Counter(), []
        for over in range(20):
            phase = "powerplay" if over < 6 else "middle" if over < 16 else "death"
            remaining = 20 - over
            choices = [p for p in bowlers if counts[p] < 4 and (not schedule or p != schedule[-1])]
            # Prevent starving a bowler until consecutive final overs are necessary.
            forced = [p for p in choices if 4 - counts[p] > (remaining - 1) // 2]
            choices = forced or choices
            selected = min(choices, key=lambda pid: (-bowling_rate(pid, phase), counts[pid], pid))
            schedule.append(selected)
            counts[selected] += 1
        initial, later = (batting, bowling_active) if batting_first else (bowling_active, batting)
        outgoing, incoming = set(initial) - set(later), set(later) - set(initial)
        impact = (
            ImpactPlan(outgoing_id=next(iter(outgoing)), incoming_id=next(iter(incoming)))
            if outgoing
            else None
        )
        plan = TeamPlan(
            team_id=team_id,
            starting_xi=initial,
            batting_order=batting,
            bowling_plan=schedule,
            captain_id=initial[0],
            substitutes=sorted(incoming),
            impact=impact,
        )
        return plan, {
            "strategy_version": STRATEGY_VERSION,
            "latest_strategy_evidence_date": max(dates, default=None),
            "participants_with_no_prior_appearances": sorted(allowed - appearances.keys()),
            "selected_bowlers_without_prior_bowling": [
                p for p in bowlers if not sum(usage[p].values())
            ],
            "participant_pool_source": "post_match_cricsheet_match_players_not_verified_announced_xi",
            "impact_policy": "hypothetical_interval_swap_selected_from_observed_pool_using_prior_usage",
            "actual_target_batting_order_or_bowling_usage_used": False,
            "historical_registration_and_overseas_eligibility_checked": False,
        }


def population_plan(team_id):
    """Fixed anonymous XI; neither a participant list nor player ability is used."""
    players = [f"anonymous:{team_id}:{i}" for i in range(11)]
    return TeamPlan(
        team_id=team_id,
        starting_xi=players,
        batting_order=players,
        bowling_plan=[players[6 + i % 5] for i in range(20)],
        captain_id=players[0],
    )
