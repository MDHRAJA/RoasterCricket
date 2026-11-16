"""Seeded two-innings Monte Carlo planning engine for uninterrupted 20-over matches."""

import time
from collections import Counter

import numpy as np

from backend.ipl_rules import RULES_VERSION, active_lineups, bad, validate_team
from backend.reliability import match_benchmark, simulation_audit
from backend.services import ApiError
from backend.simulation_evidence import SimulationEvidence

SIMULATOR_VERSION = "ipl-uninterrupted-monte-carlo-v3-exposure-audited"
ASSUMPTIONS = [
    "experimental_full_match_model_not_match_level_calibrated",
    "uninterrupted_20_over_matches_only_no_dls",
    "conditional_empirical_prior_uncertainty_only",
    "no_learned_score_pressure_or_pitch_weather_fitness_effect",
    "supplemental_extras_and_non_striker_events_use_population_bootstrap",
    "runout_ends_approximate_completed_run_parity_not_unfinished_crossing",
    "super_overs_use_regular_death_phase_model_not_fitted_super_over_model",
    "finite_super_over_cap_can_leave_unresolved_ties",
    "role_and_overseas_flags_are_current_profile_proxies",
    "registered_squad_and_match_eligibility_not_verified",
    "only_domestic_interval_impact_scenarios_supported_not_full_supplemental_regulations",
]


def phase_at(ball):
    return "powerplay" if ball < 36 else "middle" if ball < 96 else "death"


def wilson(successes, trials):
    z = 1.959963984540054
    p = successes / trials
    center = (p + z * z / (2 * trials)) / (1 + z * z / trials)
    half = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / (1 + z * z / trials)
    return {
        "level": 0.95,
        "lower": float(max(0, center - half)),
        "upper": float(min(1, center + half)),
        "interpretation": "monte_carlo_sampling_error_not_model_accuracy",
    }


def innings(
    batting_order, bowling_plan, draw, *, target=None, ball_limit=120, wicket_limit=10, trace=False
):
    """draw(striker_id,bowler_id,phase,free_hit) returns a physically scored event."""
    batting = {
        p: {"player_id": p, "runs": 0, "balls_faced": 0, "dismissed": False, "entered": False}
        for p in batting_order
    }
    bowling = {
        p: {"player_id": p, "legal_balls": 0, "runs_conceded": 0, "wickets": 0}
        for p in set(bowling_plan)
    }
    ends, next_batter = [0, 1], 2
    for p in batting_order[:2]:
        batting[p]["entered"] = True
    runs = wickets = legal = physical = 0
    free_hit = False
    extras = {"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0}
    dismissed_ids, events = [], []
    while legal < ball_limit and wickets < wicket_limit and (target is None or runs < target):
        if physical >= ball_limit * 6:
            raise ApiError(
                503,
                "simulation_delivery_guard",
                "A pathological extras sequence exceeded the physical-delivery safety bound",
            )
        striker, non_striker = (batting_order[i] for i in ends)
        bowler = bowling_plan[legal // 6]
        phase = "death" if ball_limit == 6 else phase_at(legal)
        event = dict(draw(striker, bowler, phase, free_hit))
        kind = event["kind"]
        bat, wide, nb, bye, lb = (
            int(event.get(k, 0)) for k in ("batter_runs", "wides", "noballs", "byes", "legbyes")
        )
        role = int(event.get("dismissed_role", 0))
        boundary = bool(event.get("boundary", False))
        credited = bool(event.get("credited_to_bowler", False))
        if any(v < 0 for v in (bat, wide, nb, bye, lb)) or kind not in ("legal", "wide", "noball"):
            raise ValueError("Invalid scored delivery event")
        if (
            kind == "wide"
            and (bat or nb or not wide)
            or kind == "noball"
            and (not nb or wide)
            or kind == "legal"
            and (wide or nb)
        ):
            raise ValueError("Delivery type and extras disagree")
        if role not in (0, 1, 2):
            raise ValueError("Invalid dismissal role")
        # Prevent forbidden dismissals even if an upstream sampler is malformed.
        if role and (free_hit or kind == "noball") and credited:
            role, credited = 0, False
        if role == 2:
            credited = False
        if boundary and role:
            role, credited = 0, False
        if target is not None:
            needed = target - runs
            penalty = 1 if kind == "wide" else nb
            if penalty >= needed:
                bat = bye = lb = 0
                wide = 1 if kind == "wide" else 0
                nb = needed if kind == "noball" else 0
                role, credited = 0, False
            elif not boundary and bat + wide + nb + bye + lb >= needed:
                remaining = needed - penalty
                bat = min(bat, remaining)
                remaining -= bat
                bye = min(bye, remaining)
                remaining -= bye
                lb = min(lb, remaining)
                remaining -= lb
                wide = 1 + remaining if kind == "wide" else 0
                role, credited = 0, False
        total = bat + wide + nb + bye + lb
        old_legal = legal
        physical += 1
        runs += total
        batting[striker]["runs"] += bat
        batting[striker]["balls_faced"] += int(kind != "wide")
        bowling[bowler]["runs_conceded"] += bat + wide + nb
        for key, value in zip(extras, (wide, nb, bye, lb), strict=True):
            extras[key] += value
        if kind == "legal":
            legal += 1
            bowling[bowler]["legal_balls"] += 1
        completed = 0 if boundary else bat + bye + lb + max(0, wide - 1)
        if completed % 2:
            ends.reverse()
        out_id = striker if role == 1 else non_striker if role == 2 else None
        if out_id:
            wickets += 1
            batting[out_id]["dismissed"] = True
            dismissed_ids.append(out_id)
            bowling[bowler]["wickets"] += int(credited)
            slot = ends.index(batting_order.index(out_id))
            ends[slot] = next_batter if next_batter < len(batting_order) else -1
            if next_batter < len(batting_order):
                batting[batting_order[next_batter]]["entered"] = True
            next_batter += 1
        free_hit = True if kind == "noball" else free_hit if kind == "wide" else False
        if legal > old_legal and legal % 6 == 0:
            ends.reverse()
        if trace:
            events.append(
                {
                    "physical_delivery": physical,
                    "legal_balls_before": old_legal,
                    "striker_id": striker,
                    "non_striker_id": non_striker,
                    "bowler_id": bowler,
                    "kind": kind,
                    "batter_runs": bat,
                    "extras": total - bat,
                    "dismissed_id": out_id,
                    "score": runs,
                    "wickets": wickets,
                    "free_hit_next": free_hit,
                }
            )
    return {
        "runs": runs,
        "wickets": wickets,
        "legal_balls": legal,
        "overs": f"{legal // 6}.{legal % 6}",
        "physical_deliveries": physical,
        "extras": extras,
        "batting": list(batting.values()),
        "bowling": [bowling[p] for p in sorted(bowling)],
        "dismissed_ids": dismissed_ids,
        "termination": "target_reached"
        if target is not None and runs >= target
        else "all_out"
        if wickets >= wicket_limit
        else "overs_complete",
        "deliveries": events if trace else [],
    }


class MatchSimulator:
    def __init__(self, analytics, evidence=None, benchmark=None):
        self.analytics, self.evidence, self.benchmark = analytics, evidence, benchmark

    def validate(self, request):
        a, b = request.team_a, request.team_b
        if a.team_id == b.team_id or request.batting_first_team_id not in (a.team_id, b.team_id):
            bad(
                "invalid_match_teams",
                "Two different teams and an explicit batting-first team are required",
            )
        a_ids = set(a.starting_xi + a.substitutes)
        if a_ids & set(b.starting_xi + b.substitutes):
            bad("player_on_both_teams", "A player cannot be nominated on both teams")
        self.analytics.require("venue", request.venue_id)
        lineups, warnings = {}, list(ASSUMPTIONS)
        for plan in (a, b):
            roster, roster_warnings = self.analytics.roster(plan.team_id, request.season)
            lineups[plan.team_id] = validate_team(
                plan,
                roster["members"],
                batting_first=plan.team_id == request.batting_first_team_id,
                as_of=request.as_of,
                allow_unknown=request.allow_unknown_availability,
            )
            warnings += roster_warnings
        if request.allow_unknown_availability:
            warnings.append("unknown_availability_explicitly_assumed_for_planning")
        return lineups, list(dict.fromkeys(warnings))

    def run(self, request, *, validated=None, cpu_seconds=25):
        started = time.monotonic()
        lineups, warnings = validated or self.validate(request)
        warnings = list(dict.fromkeys(ASSUMPTIONS + warnings))
        if request.allow_unknown_availability:
            warnings.append("unknown_availability_explicitly_assumed_for_planning")
        benchmark = self.benchmark
        if benchmark is None and self.analytics is not None:
            benchmark = match_benchmark(
                self.analytics,
                request.team_a.team_id,
                request.team_b.team_id,
                request.venue_id,
                request.as_of,
            )
        evidence = self.evidence or SimulationEvidence(
            self.analytics,
            request.as_of,
            request.venue_id,
            use_calibration=request.use_delivery_calibration,
        )
        a, b = request.team_a, request.team_b
        first, second = (a, b) if request.batting_first_team_id == a.team_id else (b, a)
        for bat_team, bowl_team in ((first, second), (second, first)):
            evidence.prepared(bat_team.batting_order, bowl_team.bowling_plan)
        wins = Counter()
        regular_ties = super_over_games = 0
        all_innings = [[], []]
        exposures = Counter()
        sample = None
        for trial in range(request.simulations):
            if time.monotonic() - started > cpu_seconds:
                raise ApiError(
                    503,
                    "simulation_time_budget",
                    "Simulation exceeded its computation budget; request fewer trials",
                )
            rng = np.random.default_rng(np.random.SeedSequence([request.seed, trial]))
            draws = {}

            def draw(striker, bowler, phase, free_hit, rng=rng, draws=draws):
                kind = min(
                    2, int(np.searchsorted(evidence.type_cdfs[phase], rng.random(), side="right"))
                )
                if kind == 0:
                    runs, boundary, dismissed = evidence.sample_joint(
                        rng, striker, bowler, phase, draws, request.sample_posterior, free_hit
                    )
                    cached = getattr(evidence, "cache", {}).get((striker, bowler, phase))
                    if cached is not None:
                        exposures["legal_delivery_draws"] += 1
                        exposures["no_direct_history_draws"] += int(cached[1] == 0)
                        exposures["under_30_direct_history_draws"] += int(cached[1] < 30)
                    byes = legbyes = 0
                    role = int(dismissed)
                    if not runs and not dismissed:
                        byes, legbyes, role = evidence.prototype(
                            rng, phase, "legal_zero", (0, 0, 0)
                        )
                    elif runs and not boundary and not dismissed:
                        role = (
                            2 if evidence.prototype(rng, phase, "running_non_striker_out", 0) else 0
                        )
                    credited = bool(
                        role == 1
                        and not free_hit
                        and not runs
                        and rng.random() >= evidence.free_hit_dismissal_share
                    )
                    return {
                        "kind": "legal",
                        "batter_runs": runs,
                        "byes": byes,
                        "legbyes": legbyes,
                        "boundary": boundary,
                        "dismissed_role": role,
                        "credited_to_bowler": credited,
                    }
                runs, wide, nb, bye, lb, boundary, role, credited = evidence.prototype(
                    rng,
                    phase,
                    kind,
                    (0, 1, 0, 0, 0, False, 0, False)
                    if kind == 1
                    else (0, 0, 1, 0, 0, False, 0, False),
                )
                if role == 1 and kind == 1 and free_hit and credited:
                    role = 0
                return {
                    "kind": "wide" if kind == 1 else "noball",
                    "batter_runs": runs,
                    "wides": wide,
                    "noballs": nb,
                    "byes": bye,
                    "legbyes": lb,
                    "boundary": boundary,
                    "dismissed_role": role,
                    "credited_to_bowler": bool(
                        credited and role == 1 and kind == 1 and not free_hit
                    ),
                }

            tracing = request.include_sample_match and trial == 0
            one = innings(first.batting_order, second.bowling_plan, draw, trace=tracing)
            two = innings(
                second.batting_order,
                first.bowling_plan,
                draw,
                target=one["runs"] + 1,
                trace=tracing,
            )
            all_innings[0].append(one)
            all_innings[1].append(two)
            winner = (
                second.team_id
                if two["runs"] > one["runs"]
                else first.team_id
                if two["runs"] < one["runs"]
                else None
            )
            super_overs = []
            if winner is None:
                regular_ties += 1
                super_over_games += int(request.max_super_overs > 0)
                blocked = {a.team_id: set(), b.team_id: set()}
                previous_bowler = {a.team_id: None, b.team_id: None}
                batting_first = second
                for round_index in range(request.max_super_overs):
                    batting_second = a if batting_first.team_id == b.team_id else b
                    bat_orders, bowlers = {}, {}
                    for team in (a, b):
                        # Use the post-interval active players, not replaced starters.
                        active = active_lineups(team, team.team_id == first.team_id)[
                            1 if team.team_id == first.team_id else 0
                        ]
                        order = [
                            p
                            for p in team.batting_order
                            if p in active and p not in blocked[team.team_id]
                        ]
                        order += [
                            p for p in active if p not in order and p not in blocked[team.team_id]
                        ]
                        choices = [
                            p
                            for p in dict.fromkeys(team.bowling_plan)
                            if p in active and p != previous_bowler[team.team_id]
                        ]
                        if len(order) < 3 or not choices:
                            break
                        bat_orders[team.team_id] = order[:3]
                        bowlers[team.team_id] = choices[0]
                    if len(bat_orders) < 2:
                        break
                    s1 = innings(
                        bat_orders[batting_first.team_id],
                        [bowlers[batting_second.team_id]],
                        draw,
                        ball_limit=6,
                        wicket_limit=2,
                        trace=tracing,
                    )
                    s2 = innings(
                        bat_orders[batting_second.team_id],
                        [bowlers[batting_first.team_id]],
                        draw,
                        target=s1["runs"] + 1,
                        ball_limit=6,
                        wicket_limit=2,
                        trace=tracing,
                    )
                    for team, result in ((batting_first, s1), (batting_second, s2)):
                        blocked[team.team_id].update(result["dismissed_ids"])
                        previous_bowler[team.team_id] = bowlers[team.team_id]
                    super_overs.append(
                        {
                            "round": round_index + 1,
                            "batting_first_team_id": batting_first.team_id,
                            "innings": [s1, s2],
                            "bowling_choices": dict(bowlers),
                        }
                    )
                    if s1["runs"] != s2["runs"]:
                        winner = (
                            batting_first.team_id
                            if s1["runs"] > s2["runs"]
                            else batting_second.team_id
                        )
                        break
                    batting_first = batting_second
            wins[winner or "unresolved_tie"] += 1
            if tracing:
                sample = {
                    "innings": [
                        {"team_id": first.team_id, **one},
                        {"team_id": second.team_id, **two},
                    ],
                    "super_overs": super_overs,
                    "winner_id": winner,
                }
        outcomes = {
            team: {
                "count": wins[team],
                "probability": wins[team] / request.simulations,
                "sampling_interval": wilson(wins[team], request.simulations),
            }
            for team in (a.team_id, b.team_id, "unresolved_tie")
        }
        outcomes.update(
            regular_tie_probability=regular_ties / request.simulations,
            super_over_probability=super_over_games / request.simulations,
        )
        summaries = []
        for team, records in zip((first, second), all_innings, strict=True):
            scores = np.array([r["runs"] for r in records])
            histogram = Counter(int(r // 10 * 10) for r in scores)
            summaries.append(
                {
                    "team_id": team.team_id,
                    "mean_runs": float(scores.mean()),
                    "score_quantiles": {
                        "p05": float(np.quantile(scores, 0.05)),
                        "p10": float(np.quantile(scores, 0.1)),
                        "p50": float(np.quantile(scores, 0.5)),
                        "p90": float(np.quantile(scores, 0.9)),
                        "p95": float(np.quantile(scores, 0.95)),
                    },
                    "score_standard_deviation": float(scores.std(ddof=1)),
                    "mean_runs_mc_standard_error": float(scores.std(ddof=1) / np.sqrt(len(scores))),
                    "mean_wickets": float(np.mean([r["wickets"] for r in records])),
                    "mean_legal_balls": float(np.mean([r["legal_balls"] for r in records])),
                    "score_histogram": [
                        {"lower": bucket, "upper_exclusive": bucket + 10, "count": count}
                        for bucket, count in sorted(histogram.items())
                    ],
                }
            )
        if not evidence.training["legal_striker_wicket_mode_records"]:
            warnings.append("free_hit_wicket_mode_share_uses_declared_3_percent_fallback")
        audit = simulation_audit(request, evidence, outcomes, benchmark, exposures=exposures)
        warnings = list(dict.fromkeys(warnings + audit["flags"]))
        return {
            "reliability": audit,
            "simulator_version": SIMULATOR_VERSION,
            "status": "experimental_planning",
            "eligibility_verified": False,
            "simulations": request.simulations,
            "seed": request.seed,
            "outcomes": outcomes,
            "innings": summaries,
            "training": {
                **evidence.training,
                "rules_profile": RULES_VERSION,
                "posterior_sampling": request.sample_posterior,
                "max_super_overs": request.max_super_overs,
            },
            "assumptions": warnings,
            "sample_match": sample,
        }, warnings
