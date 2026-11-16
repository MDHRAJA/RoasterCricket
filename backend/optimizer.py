"""Bounded MILP selection and independent Monte Carlo confirmation, not win-optimality."""

import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from backend.bayesian import OUTCOMES
from backend.ipl_rules import bad, validate_team
from backend.match_models import SimulationRequest, TeamPlan
from backend.reliability import match_benchmark, ranking_decision
from backend.services import ApiError
from backend.simulation_evidence import SimulationEvidence
from backend.simulator import MatchSimulator, phase_at

OPTIMIZER_VERSION = "ipl-proxy-milp-monte-carlo-v2-audited"
BATTING_ROLES = {"batter", "wicketkeeper_batter", "allrounder"}
BOWLING_ROLES = {"bowler", "allrounder"}


def utility(alpha, weights, risk):
    mean = alpha / alpha.sum()
    value = float(mean @ weights)
    variance = max(0, float(mean @ (weights * weights) - value * value)) / (alpha.sum() + 1)
    return value - risk * np.sqrt(variance)


def solve_xi(profiles, batting_scores, bowling_scores, *, minimum_batting=6, locked=(), cuts=()):
    """x[player] plus y[player,over]; maximize explicitly documented proxy utility."""
    n = len(profiles)
    size = n * 21
    objective = np.concatenate([np.asarray(batting_scores), np.asarray(bowling_scores).ravel()])
    rows, lows, highs = [], [], []

    def constraint(entries, low=-np.inf, high=np.inf):
        row = np.zeros(size)
        for index, value in entries:
            row[index] = value
        rows.append(row)
        lows.append(low)
        highs.append(high)

    def y(i, over):
        return n + 20 * i + over

    constraint([(i, 1) for i in range(n)], 11, 11)
    constraint([(i, int(bool(p["is_overseas"]))) for i, p in enumerate(profiles)], high=4)
    constraint([(i, int(bool(p.get("is_wicketkeeper")))) for i, p in enumerate(profiles)], low=1)
    constraint(
        [(i, int(p.get("primary_role") in BATTING_ROLES)) for i, p in enumerate(profiles)],
        low=minimum_batting,
    )
    for i, p in enumerate(profiles):
        if p["player_id"] in locked:
            constraint([(i, 1)], 1, 1)
        capacity = 4 if p.get("primary_role") in BOWLING_ROLES else 0
        constraint([(y(i, over), 1) for over in range(20)] + [(i, -capacity)], high=0)
        for over in range(19):
            constraint([(y(i, over), 1), (y(i, over + 1), 1)], high=1)
    for over in range(20):
        constraint([(y(i, over), 1) for i in range(n)], 1, 1)
    for cut in cuts:
        constraint([(i, 1) for i in cut], high=10)
    matrix = np.asarray(rows)
    low, high = np.asarray(lows), np.asarray(highs)
    result = milp(
        -objective,
        integrality=np.ones(size),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, low, high),
        options={"time_limit": 5.0, "mip_rel_gap": 0.0},
    )
    if result.x is None:
        if result.status == 2:
            return None
        raise ApiError(
            503,
            "optimizer_solver_budget",
            "The solver did not find a feasible XI within its budget",
        )
    decision = np.rint(result.x)
    values = matrix @ decision
    if (
        not np.all(np.isfinite(result.x))
        or np.any(decision < 0)
        or np.any(decision > 1)
        or np.max(np.abs(result.x - decision)) > 1e-5
        or np.any(values < low - 1e-6)
        or np.any(values > high + 1e-6)
    ):
        raise ApiError(
            503, "optimizer_invalid_solution", "Solver result failed independent constraint checks"
        )
    chosen = [i for i in range(n) if decision[i] == 1]
    plan = [
        profiles[int(np.argmax(decision[n:].reshape(n, 20)[:, over]))]["player_id"]
        for over in range(20)
    ]
    return {
        "indices": chosen,
        "bowling_plan": plan,
        "proxy_score": float(objective @ decision),
        "proxy_optimality_proven": result.status == 0,
        "solver_status": int(result.status),
        "relative_mip_gap": float(result.mip_gap) if result.mip_gap is not None else None,
    }


class XIOptimizer:
    def __init__(self, analytics):
        self.analytics = analytics

    def run(self, request):
        started = time.monotonic()
        if request.team_id == request.opponent.team_id or request.batting_first_team_id not in (
            request.team_id,
            request.opponent.team_id,
        ):
            bad("invalid_match_teams", "Select distinct teams and a batting-first team")
        self.analytics.require("venue", request.venue_id)
        own, own_warnings = self.analytics.roster(request.team_id, request.season)
        opponent, opponent_warnings = self.analytics.roster(
            request.opponent.team_id, request.season
        )
        opponent_lineups = validate_team(
            request.opponent,
            opponent["members"],
            batting_first=request.opponent.team_id == request.batting_first_team_id,
            as_of=request.as_of,
            allow_unknown=request.allow_unknown_availability,
        )
        members = {m["player"]["player_id"]: m for m in own["members"]}
        requested = sorted(members) if request.candidate_ids is None else request.candidate_ids
        if len(requested) > 40 or not set(requested) <= members.keys():
            bad("invalid_candidate_pool", "Select at most 40 players from the saved team roster")
        if (
            not set(request.locked_ids) <= set(requested)
            or not set(request.excluded_ids) <= members.keys()
        ):
            bad(
                "invalid_player_constraints",
                "Locks must be candidates and exclusions must be roster members",
            )
        exclusions, profiles = [], []
        for pid in requested:
            member = members[pid]
            p, availability = member["player"], member["availability"]
            dated = str(availability.get("effective_on") or "") == request.as_of.isoformat()
            reason = None
            if pid in request.excluded_ids:
                reason = "user_excluded"
            elif pid in request.opponent.starting_xi + request.opponent.substitutes:
                reason = "nominated_on_opponent"
            elif dated and availability["status"] == "unavailable":
                reason = "dated_unavailable"
            elif not request.allow_unknown_availability and not (
                dated and availability["status"] == "available"
            ):
                reason = "availability_not_confirmed"
            elif (
                p.get("is_overseas") is None
                or p.get("primary_role") not in BATTING_ROLES | BOWLING_ROLES
            ):
                reason = "required_profile_attribute_unknown"
            if reason:
                exclusions.append({"player_id": pid, "reason": reason})
                if pid in request.locked_ids:
                    bad(
                        "locked_player_ineligible_for_planning",
                        "A locked player fails a planning constraint",
                    )
            else:
                profiles.append(p)
        if len(profiles) < 11:
            bad(
                "insufficient_planning_candidates",
                "Fewer than eleven candidates pass the explicit planning filters",
            )
        benchmark = match_benchmark(
            self.analytics,
            request.team_id,
            request.opponent.team_id,
            request.venue_id,
            request.as_of,
        )
        evidence = SimulationEvidence(
            self.analytics,
            request.as_of,
            request.venue_id,
            use_calibration=request.use_delivery_calibration,
        )
        batting_weights = np.array([runs - 12 * out for runs, _, out in OUTCOMES], dtype=float)
        bowling_weights = -batting_weights
        batting, bowling = [], []
        opponent_bowlers = request.opponent.bowling_plan
        for p in profiles:
            pid = p["player_id"]
            bat = (
                np.mean(
                    [
                        utility(
                            evidence.alpha(pid, w, phase_at(over * 6))[0],
                            batting_weights,
                            request.risk_aversion,
                        )
                        for over, w in enumerate(opponent_bowlers)
                    ]
                )
                * 12
            )
            bat_scores = [
                np.mean(
                    [
                        utility(
                            evidence.alpha(b, pid, phase_at(over * 6))[0],
                            bowling_weights,
                            request.risk_aversion,
                        )
                        for b in request.opponent.batting_order[:7]
                    ]
                )
                * 6
                for over in range(20)
            ]
            batting.append(float(bat))
            bowling.append(bat_scores)
        alternatives, cuts = [], []
        for candidate in range(request.candidate_count):
            if time.monotonic() - started > 55:
                raise ApiError(
                    503, "optimization_time_budget", "Optimization exceeded its computation budget"
                )
            solved = solve_xi(
                profiles,
                batting,
                bowling,
                minimum_batting=request.minimum_batting_options,
                locked=request.locked_ids,
                cuts=cuts,
            )
            if solved is None:
                if not alternatives:
                    bad(
                        "no_feasible_xi",
                        "No XI satisfies the keeper, batting balance, overseas proxy and 20-over bowling constraints",
                    )
                break
            chosen = solved.pop("indices")
            cuts.append(chosen)
            # Heuristic batting order: proxy rank, not a globally optimized order.
            order = [
                profiles[i]["player_id"]
                for i in sorted(chosen, key=lambda i: (-batting[i], profiles[i]["player_id"]))
            ]
            plan = TeamPlan(
                team_id=request.team_id,
                starting_xi=order,
                batting_order=order,
                bowling_plan=solved["bowling_plan"],
                captain_id=order[0],
            )
            own_lineups = validate_team(
                plan,
                own["members"],
                batting_first=request.team_id == request.batting_first_team_id,
                as_of=request.as_of,
                allow_unknown=request.allow_unknown_availability,
            )
            scenario = SimulationRequest(
                season=request.season,
                as_of=request.as_of,
                venue_id=request.venue_id,
                team_a=plan,
                team_b=request.opponent,
                batting_first_team_id=request.batting_first_team_id,
                simulations=request.simulations,
                seed=request.seed,
                allow_unknown_availability=request.allow_unknown_availability,
                use_delivery_calibration=request.use_delivery_calibration,
            )
            validated = (
                {request.team_id: own_lineups, request.opponent.team_id: opponent_lineups},
                own_warnings + opponent_warnings,
            )
            result, _ = MatchSimulator(self.analytics, evidence, benchmark).run(
                scenario,
                validated=validated,
                cpu_seconds=max(0, min(25, 55 - (time.monotonic() - started))),
            )
            alternatives.append(
                {
                    "candidate_rank_by_proxy": candidate + 1,
                    "plan": plan.model_dump(),
                    **solved,
                    "simulation": result["outcomes"][request.team_id],
                }
            )
        recommended, alternatives, ranking_audit = ranking_decision(alternatives)
        confirmation_request = scenario.model_copy(
            update={"team_a": TeamPlan(**recommended["plan"]), "seed": request.seed ^ 0xA5A5A5A5}
        )
        # Revalidate chosen lineups without another SQL query after long CPU work.
        confirmation_lineups = validate_team(
            confirmation_request.team_a,
            own["members"],
            batting_first=request.team_id == request.batting_first_team_id,
            as_of=request.as_of,
            allow_unknown=request.allow_unknown_availability,
        )
        confirmation, _ = MatchSimulator(self.analytics, evidence, benchmark).run(
            confirmation_request,
            cpu_seconds=max(0, min(25, 55 - (time.monotonic() - started))),
            validated=(
                {request.team_id: confirmation_lineups, request.opponent.team_id: opponent_lineups},
                own_warnings + opponent_warnings,
            ),
        )
        confirmation["assumptions"].append(
            "candidate_ranking_is_noisy_not_a_significance_test_or_global_search"
        )
        return {
            "reliability": {**ranking_audit, "confirmation": confirmation["reliability"]},
            "optimizer_version": OPTIMIZER_VERSION,
            "status": "experimental_planning",
            "eligibility_verified": False,
            "objective": {
                "name": "risk_adjusted_legal_delivery_proxy",
                "wicket_utility": 12,
                "batting_exposure_per_selected_player": 12,
                "risk_aversion": request.risk_aversion,
                "scope": "MILP optimum of surrogate, then noisy simulation ranking of at most three distinct XIs",
                "global_win_probability_optimality_proven": False,
                "batting_order": "heuristic_proxy_rank",
                "impact_optimized": False,
                "captain": "placeholder_first_batter_not_leadership_recommendation",
            },
            "recommended": recommended,
            "alternatives": alternatives,
            "candidate_scores": [
                {
                    "player_id": p["player_id"],
                    "batting_proxy": batting[i],
                    "bowling_proxy_by_over": bowling[i],
                }
                for i, p in enumerate(profiles)
            ],
            "exclusions": exclusions,
            "constraints": {
                "xi_size": 11,
                "max_overseas_proxy": 4,
                "min_keeper": 1,
                "minimum_batting_options": request.minimum_batting_options,
                "max_overs_per_bowler": 4,
                "consecutive_overs_forbidden": True,
                "bowling_roles": sorted(BOWLING_ROLES),
                "locked_ids": request.locked_ids,
                "availability_assumed": request.allow_unknown_availability,
            },
            "confirmation": {
                "seed": confirmation_request.seed,
                "simulations": request.simulations,
                "selected_team_outcome": confirmation["outcomes"][request.team_id],
                "training": evidence.training,
                "interpretation": "independent_trials_for_selected_XI_not_historical_validation",
            },
        }, confirmation["assumptions"]
