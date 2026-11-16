"""Pre-match benchmarks using outcomes only; never infer a XI from post-match balls."""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from itertools import groupby

import numpy as np
from scipy.special import expit
from scipy.stats import t

from backend.bayesian import DEFAULT_CONFIG
from backend.services import ApiError

BENCHMARK_VERSION = "date-blocked-team-score-benchmark-v1"


@dataclass(frozen=True)
class BenchmarkConfig:
    family: str = "elo"
    k: float = 20
    season_carry: float = 0.5
    temperature: float = 2
    score_strength: float = 10


DEFAULT_BENCHMARK = BenchmarkConfig(family="neutral", score_strength=5)


def archive(db):
    return [
        dict(row)
        for row in db.execute("""SELECT m.match_id,m.match_date,m.season,
        m.team1_id,m.team2_id,m.winner_id,m.venue_id,i.batting_team_id AS batting_first_team_id,
        i.total_runs AS first_innings_runs
        FROM matches m JOIN innings i USING(match_id)
        WHERE i.innings=1 AND i.is_super_over=0 AND m.scheduled_overs=20
        AND m.balls_per_over=6 AND COALESCE(m.result_method,'')='' AND i.total_runs>=0
        AND (i.legal_balls=120 OR (i.wickets=10 AND i.legal_balls<=120))
        ORDER BY m.match_date,m.match_id""")
    ]


def before_window(rows, as_of):
    end = as_of.isoformat()
    start = (as_of - timedelta(days=DEFAULT_CONFIG.lookback_days)).isoformat()
    return [r for r in rows if start <= r["match_date"] < end]


def decisive(row):
    return row["team1_id"] != row["team2_id"] and row["winner_id"] in (
        row["team1_id"],
        row["team2_id"],
    )


def team_state(history, config):
    ratings = defaultdict(float)
    played, won = Counter(), Counter()
    year = None
    for _, group in groupby(
        sorted(history, key=lambda r: (r["match_date"], r["match_id"])),
        key=lambda r: r["match_date"],
    ):
        group = list(group)
        current = int(group[0]["season"])
        if year is not None and current != year:
            for team in ratings:
                ratings[team] *= config.season_carry ** max(1, current - year)
        year = current
        changes = Counter()
        for r in group:
            if not decisive(r):
                continue
            a, b = r["team1_id"], r["team2_id"]
            outcome = int(r["winner_id"] == a)
            expected = float(expit(np.log(10) * (ratings[a] - ratings[b]) / 400))
            delta = config.k * (outcome - expected)
            changes[a] += delta
            changes[b] -= delta
            played[a] += 1
            played[b] += 1
            won[r["winner_id"]] += 1
        # All predictions/updates for one date use the same preceding ratings.
        for team, delta in changes.items():
            ratings[team] += delta
    return ratings, played, won, year


def win_probability(history, team_a, team_b, season, config=DEFAULT_BENCHMARK):
    ratings, played, won, last_season = team_state(history, config)
    carry = config.season_carry ** max(0, season - last_season) if last_season is not None else 1
    difference = (ratings[team_a] - ratings[team_b]) * carry
    if config.family == "neutral":
        probability = 0.5
    elif config.family == "form":
        rates = [(won[p] + 5) / (played[p] + 10) for p in (team_a, team_b)]
        probability = float(
            expit(np.log(rates[0] / (1 - rates[0])) - np.log(rates[1] / (1 - rates[1])))
        )
    else:
        probability = float(expit(np.log(10) * difference / (400 * config.temperature)))
    return probability, {team: played[team] for team in (team_a, team_b)}


def predictive_score(history, venue_id, strength=10, *, global_only=False):
    """Conditional empirical normal-inverse-gamma Student-t predictive distribution."""
    local = np.array(
        [r["first_innings_runs"] for r in history if r["venue_id"] == venue_id], dtype=float
    )
    background = np.array(
        [r["first_innings_runs"] for r in history if r["venue_id"] != venue_id], dtype=float
    )
    if global_only:
        local = np.array([r["first_innings_runs"] for r in history], dtype=float)
        mean, variance, strength = 170.0, 1600.0, 2.0
    elif len(background) < 10:
        return None
    else:
        mean, variance = float(background.mean()), max(25.0, float(background.var(ddof=1)))
    if len(history) < 10:
        return None
    n = len(local)
    sample_mean = float(local.mean()) if n else mean
    kappa = strength + n
    location = (strength * mean + n * sample_mean) / kappa
    alpha = 3 + n / 2
    beta = 2 * variance + float(np.sum((local - sample_mean) ** 2)) / 2
    beta += strength * n * (sample_mean - mean) ** 2 / (2 * kappa)
    scale = float(np.sqrt(beta * (kappa + 1) / (alpha * kappa)))
    degrees = 2 * alpha
    intervals = {
        str(level): {
            "lower": float(t.ppf((1 - level) / 2, degrees, loc=location, scale=scale)),
            "upper": float(t.ppf((1 + level) / 2, degrees, loc=location, scale=scale)),
        }
        for level in (0.8, 0.9)
    }
    return {
        "mean_runs": float(location),
        "degrees_of_freedom": float(degrees),
        "scale": scale,
        "predictive_intervals": intervals,
        "venue_innings": n,
        "background_innings": len(background),
        "interpretation": "first_innings_score_benchmark_not_player_lineup_simulator",
        "distribution": "continuous_student_t_no_physical_score_truncation",
    }


def benchmark_from_rows(rows, team_a, team_b, venue_id, as_of, config=DEFAULT_BENCHMARK):
    pre_selection = as_of < date(2025, 1, 1)
    if pre_selection and config == DEFAULT_BENCHMARK:
        config = BenchmarkConfig(family="neutral", score_strength=10)
    history = before_window(rows, as_of)
    probability, played = win_probability(history, team_a, team_b, as_of.year, config)
    score = predictive_score(history, venue_id, config.score_strength)
    warnings = [
        "benchmark_not_lineup_aware_not_simulator_calibration",
        "conditional_empirical_score_prior_not_full_uncertainty",
    ]
    if config.family == "neutral":
        warnings.append(
            "predeclared_neutral_before_selection_cutoff"
            if pre_selection
            else "2024_validation_did_not_support_promoting_team_strength_over_neutral"
        )
    if min(played.values()) < 10:
        warnings.append("fewer_than_10_recent_team_matches")
    latest = max((r["match_date"] for r in history), default=None)
    if latest is None or (as_of - date.fromisoformat(latest)).days > 60:
        warnings.append("training_archive_stale_or_empty_at_cutoff")
    if score is None:
        warnings.append("insufficient_independent_first_innings_score_evidence")
    elif score["venue_innings"] < 10:
        warnings.append("fewer_than_10_recent_venue_first_innings")
    return {
        "model_version": BENCHMARK_VERSION,
        "status": "experimental_pre_match_benchmark",
        "configuration": asdict(config),
        "team_a_id": team_a,
        "team_b_id": team_b,
        "probability_team_a_wins_given_decisive_outcome": probability,
        "probability_team_b_wins_given_decisive_outcome": 1 - probability,
        "no_result_or_tie_probability_modeled": False,
        "first_innings_score": score,
        "training": {
            "exclusive_cutoff": as_of.isoformat(),
            "window_days": DEFAULT_CONFIG.lookback_days,
            "included_matches": len(history),
            "team_decisive_matches": played,
            "latest_training_date": latest,
        },
        "warnings": warnings,
    }


def match_benchmark(analytics, team_a, team_b, venue_id, as_of):
    if team_a == team_b:
        raise ApiError(422, "invalid_match_teams", "Two distinct teams are required")
    analytics.require("team", team_a)
    analytics.require("team", team_b)
    analytics.require("venue", venue_id)
    return benchmark_from_rows(archive(analytics.db), team_a, team_b, venue_id, as_of)


def ranking_decision(candidates):
    ordered = sorted(candidates, key=lambda c: (-c["simulation"]["probability"], -c["proxy_score"]))
    top_interval = ordered[0]["simulation"]["sampling_interval"]
    overlapping = [
        c
        for c in ordered
        if c["simulation"]["sampling_interval"]["lower"] <= top_interval["upper"]
        and c["simulation"]["sampling_interval"]["upper"] >= top_interval["lower"]
    ]
    selected = (
        max(overlapping, key=lambda c: c["proxy_score"]) if len(overlapping) > 1 else ordered[0]
    )
    reliability = {
        "selection_basis": "surrogate_proxy_when_sampling_intervals_overlap"
        if len(overlapping) > 1
        else "highest_simulated_win_estimate",
        "sampling_intervals_nonoverlapping": len(overlapping) == 1 and len(ordered) > 1,
        "win_probability_superiority_proven": False,
        "overlapping_candidate_proxy_ranks": [c["candidate_rank_by_proxy"] for c in overlapping],
        "interpretation": "conservative_interval_overlap_screen_not_a_significance_test",
        "historical_xi_benefit_validated": False,
    }
    return selected, [c for c in ordered if c is not selected], reliability


def simulation_audit(request, evidence, outcomes, benchmark, *, exposures=None):
    keys = set()
    for batting, bowling in ((request.team_a, request.team_b), (request.team_b, request.team_a)):
        keys.update(
            (b, w, phase)
            for b in batting.batting_order
            for w in set(bowling.bowling_plan)
            for phase in ("powerplay", "middle", "death")
        )
    cache = getattr(evidence, "cache", {})
    counts = [cache[key][1] for key in sorted(keys) if key in cache]
    flags = [
        "full_match_win_estimate_not_historically_calibrated",
        "registered_eligibility_unverified",
    ]
    no_history = sum(n == 0 for n in counts) / len(counts) if counts else None
    if no_history is not None and no_history > 0.5:
        flags.append("majority_of_prepared_matchup_contexts_have_no_direct_history")
    interval = outcomes[request.team_a.team_id]["sampling_interval"]
    if (interval["upper"] - interval["lower"]) / 2 > 0.05:
        flags.append("monte_carlo_interval_half_width_exceeds_5_percentage_points")
    if request.allow_unknown_availability:
        flags.append("availability_assumed_not_verified")
    latest = evidence.training.get("last_included_date")
    if latest is not None and (request.as_of - date.fromisoformat(latest)).days > 60:
        flags.append("delivery_archive_more_than_60_days_old_at_cutoff")
    if request.use_delivery_calibration:
        flags.append(
            "delivery_correction_is_optional_candidate_not_proven_overall_or_match_level_gain"
        )
    exposures = dict(exposures or {})
    draws = exposures.get("legal_delivery_draws", 0)
    exposed_no_history = exposures.get("no_direct_history_draws", 0) / draws if draws else None
    if exposed_no_history is not None and exposed_no_history > 0.5:
        flags.append("majority_of_simulated_legal_draws_have_no_direct_matchup_history")
    comparison = None
    if benchmark is not None:
        decisive_mass = 1 - outcomes["unresolved_tie"]["probability"]
        simulated = (
            outcomes[request.team_a.team_id]["probability"] / decisive_mass
            if decisive_mass
            else None
        )
        reference = benchmark["probability_team_a_wins_given_decisive_outcome"]
        gap = simulated - reference if simulated is not None else None
        comparison = {
            "simulated_team_a_probability_given_decisive_outcome": simulated,
            "benchmark_team_a_probability_given_decisive_outcome": reference,
            "difference": gap,
            "interpretation": "different_models_not_a_calibration_test_or_evidence_of_error",
        }
        if gap is not None and abs(gap) >= 0.15:
            flags.append("large_unvalidated_departure_from_neutral_or_team_benchmark")
    return {
        "status": "experimental_not_decision_validated",
        "match_level_calibrated": False,
        "decision_ready": False,
        "flags": flags,
        "evidence": {
            "prepared_contexts_checked": len(counts),
            "no_direct_history_fraction": no_history,
            "interpretation": "prepared_pair_phase_contexts_not_actual_ball_exposure_weights",
            "simulated_legal_delivery_exposures": {
                **exposures,
                "no_direct_history_fraction": exposed_no_history,
                "interpretation": "actual_sampled_legal_events_including_any_super_overs_not_independent_observations",
            },
        },
        "benchmark": benchmark,
        "benchmark_comparison": comparison,
        "thresholds": {
            "archive_staleness_days": 60,
            "sampling_interval_half_width": 0.05,
            "model_probability_gap": 0.15,
            "interpretation": "declared_unfitted_safety_heuristics",
        },
    }
