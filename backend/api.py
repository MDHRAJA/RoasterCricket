"""Versioned HTTP routes. Response contracts keep observations separate from forecasts."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from threading import BoundedSemaphore
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from backend.bayesian import DEFAULT_CONFIG, MODEL_VERSION, PredictionService
from backend.database import connection
from backend.ipl_rules import RULES_SOURCE, RULES_VERSION
from backend.match_models import (
    OptimizationRequest,
    OptimizationResult,
    SimulationRequest,
    SimulationResult,
)
from backend.models import (
    BowlingArm,
    BowlingCategory,
    DatasetInfo,
    Envelope,
    ErrorResponse,
    FormWindow,
    Hand,
    Match,
    MatchDetail,
    Matchup,
    Metadata,
    Page,
    Phase,
    PhaseMetrics,
    Player,
    PlayerStatistics,
    Prediction,
    RecentForm,
    Role,
    Roster,
    Side,
    Team,
    Venue,
    VenueProfile,
)
from backend.optimizer import XIOptimizer
from backend.reliability import match_benchmark
from backend.services import AnalyticsService, ApiError
from backend.simulator import MatchSimulator

PLANNING_SLOT = BoundedSemaphore(1)


@contextmanager
def planning_slot():
    if not PLANNING_SLOT.acquire(blocking=False):
        raise ApiError(
            429, "planning_busy", "A planning job is already running; retry after it finishes"
        )
    try:
        yield
    finally:
        PLANNING_SLOT.release()


router = APIRouter(
    prefix="/api/v1",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


def get_service(request: Request) -> Iterator[AnalyticsService]:
    with connection(request.app.state.settings) as db:
        yield AnalyticsService(db, request.app.state.settings, request.app.state.snapshot)


Service = Annotated[AnalyticsService, Depends(get_service)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=100000)]
Season = Annotated[int | None, Query(ge=2008, le=2100)]
Before = Annotated[date | None, Query(description="Exclusive cutoff: only match_date < before")]


def metadata(service: AnalyticsService, before=None, warnings=None):
    return Metadata(
        dataset_version=service.snapshot["version"], before=before, warnings=warnings or []
    )


def envelope(service: AnalyticsService, data, before=None, warnings=None):
    return {"data": data, "meta": metadata(service, before, warnings)}


@router.get("/metadata", response_model=Envelope[dict], tags=["Dataset"])
def dataset_metadata(service: Service):
    return envelope(
        service,
        {
            "coverage": service.snapshot["coverage"],
            "roster_snapshot_seasons": sorted(service.snapshot["roster_seasons"]),
            "capabilities": {
                "descriptive_analytics": True,
                "bayesian_predictions": True,
                "production_validated_predictions": False,
                "match_simulation": True,
                "xi_optimization": True,
                "verified_match_eligibility": False,
                "historically_evaluated_match_benchmarks": True,
                "optional_delivery_calibration_candidate": True,
            },
            "conventions": {
                "before": "exclusive match-date cutoff; all matches on cutoff date excluded",
                "balls_faced": "recorded deliveries excluding wides; includes no-balls",
                "overs": "six legal balls; overs notation is not a decimal",
                "super_overs": "excluded from ordinary performance analytics",
                "phases": "powerplay overs 1-6; middle 7-16; death 17-20; not rescaled for shortened games",
                "form": "last actual IPL batting/bowling innings; DNB is not zero performance",
            },
            "prediction_model": {
                "version": MODEL_VERSION,
                "status": "experimental",
                "unit": "next_legal_delivery",
                "lookback_days": DEFAULT_CONFIG.lookback_days,
                "requires_exclusive_as_of": True,
            },
        },
        warnings=[
            "roster_snapshot_not_eligibility",
            "profile_attributes_not_time_versioned",
            "no_measured_pitch_or_live_injury_feed",
            "annual_rules_review_pending",
        ],
    )


@router.post(
    "/simulations/match",
    response_model=Envelope[SimulationResult],
    tags=["Planning"],
    responses={429: {"model": ErrorResponse}},
)
def simulate_match(payload: SimulationRequest, service: Service):
    with planning_slot():
        data, warnings = MatchSimulator(service).run(payload)
        return envelope(service, data, payload.as_of, warnings)


@router.post(
    "/optimization/xi",
    response_model=Envelope[OptimizationResult],
    tags=["Planning"],
    responses={429: {"model": ErrorResponse}},
)
def optimize_xi(payload: OptimizationRequest, service: Service):
    with planning_slot():
        data, warnings = XIOptimizer(service).run(payload)
        return envelope(service, data, payload.as_of, warnings)


@router.get("/rules", response_model=Envelope[dict], tags=["Planning"])
def rules(service: Service):
    return envelope(
        service,
        {
            "version": RULES_VERSION,
            "season": 2026,
            "source_url": RULES_SOURCE,
            "source_sha256": "8cb00c8428262988b147823628dd78c1e0ef7e623d2aa0a5d456eb7183bae655",
            "review": "core_constraints_reviewed_supplemental_impact_rules_pending",
            "clauses": ["1.1", "1.2.5", "13.9.1", "17.6", "21.19", "Appendix F"],
            "format": "uninterrupted_20_overs",
            "max_overseas_proxy": 4,
            "max_substitutes": 5,
            "impact": "explicit_domestic_innings_interval_only",
            "registered_eligibility_verified": False,
            "source_date_note": "2026 cover; introduction still says March 2024",
        },
    )


@router.get("/predictions/match-benchmark", response_model=Envelope[dict], tags=["Prediction"])
def historical_match_benchmark(
    team_a_id: Annotated[str, Query(min_length=1, max_length=80)],
    team_b_id: Annotated[str, Query(min_length=1, max_length=80)],
    venue_id: Annotated[str, Query(min_length=1, max_length=80)],
    as_of: Annotated[date, Query(ge=date(2008, 4, 19), le=date(2099, 12, 31))],
    service: Service,
):
    data = match_benchmark(service, team_a_id, team_b_id, venue_id, as_of)
    return envelope(service, data, as_of, data["warnings"])


@router.get("/datasets", response_model=Envelope[list[DatasetInfo]], tags=["Dataset"])
def datasets(service: Service):
    return envelope(service, service.snapshot["catalog"])


@router.get("/seasons", response_model=Envelope[list[dict]], tags=["Dataset"])
def seasons(service: Service):
    return envelope(service, service.rows("SELECT * FROM season_coverage ORDER BY season"))


@router.get("/teams", response_model=Envelope[list[Team]], tags=["Teams"])
def teams(service: Service, current_only: bool = True):
    where = " WHERE is_current=1" if current_only else ""
    return envelope(service, service.rows("SELECT * FROM teams" + where + " ORDER BY display_name"))


@router.get("/teams/{team_id}/roster", response_model=Envelope[Roster], tags=["Teams"])
def roster(service: Service, team_id: str, season: Annotated[int, Query(ge=2008, le=2100)]):
    data, warnings = service.roster(team_id, season)
    return envelope(service, data, warnings=warnings)


@router.get("/teams/{team_id}/observed-roster", response_model=Envelope[list[dict]], tags=["Teams"])
def observed_roster(
    service: Service,
    team_id: str,
    season: Annotated[int, Query(ge=2008, le=2100)],
    before: Before = None,
):
    service.require("team", team_id)
    clauses, params = service.filters(season=season, before=before)
    where = " AND ".join(["team_id=?", *clauses])
    rows = service.rows(
        "SELECT s.player_id,p.display_name,MIN(match_date) AS first_appearance,"
        "MAX(match_date) AS last_appearance,COUNT(*) AS matches_involved "
        "FROM player_match_stats s JOIN players p USING(player_id) "
        f"WHERE {where} GROUP BY s.player_id,p.display_name ORDER BY p.display_name,s.player_id",
        [team_id, *params],
    )
    return envelope(service, rows, before, ["observed_participants_not_full_registered_squad"])


@router.get("/players", response_model=Page[Player], tags=["Players"])
def players(
    service: Service,
    q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    role: Role | None = None,
    hand: Hand | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    items, total = service.players(q=q, role=role, hand=hand, limit=limit, offset=offset)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "meta": metadata(service, warnings=["profile_attributes_not_time_versioned"]),
    }


@router.get("/players/{player_id}", response_model=Envelope[Player], tags=["Players"])
def player(service: Service, player_id: str):
    return envelope(
        service,
        service.require("player", player_id),
        warnings=["profile_attributes_not_time_versioned"],
    )


@router.get(
    "/players/{player_id}/attributes", response_model=Envelope[list[dict]], tags=["Players"]
)
def attributes(service: Service, player_id: str):
    service.require("player", player_id)
    return envelope(
        service,
        service.rows(
            "SELECT * FROM player_attributes WHERE player_id=? ORDER BY field", (player_id,)
        ),
        warnings=["source_observation_is_not_historical_effective_date"],
    )


@router.get(
    "/players/{player_id}/statistics", response_model=Envelope[PlayerStatistics], tags=["Analytics"]
)
def player_statistics(
    service: Service,
    player_id: str,
    season: Season = None,
    before: Before = None,
    venue_id: str | None = None,
):
    return envelope(
        service,
        service.player_statistics(player_id, season=season, before=before, venue_id=venue_id),
        before,
        ["observed_statistics_not_prediction"],
    )


@router.get("/players/{player_id}/form", response_model=Envelope[RecentForm], tags=["Analytics"])
def form(
    service: Service,
    player_id: str,
    window: FormWindow = FormWindow.last5,
    before: Before = None,
    timeline_limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    data = service.recent_form(player_id, int(window), before, timeline_limit)
    warnings = [
        "form_is_descriptive_not_forecast",
        "timeline_batted_false_means_dnb",
        "recency_decay_0_85_is_an_unfitted_heuristic",
    ]
    if data["summary"]["batting_innings"] < window or data["summary"]["bowling_innings"] < window:
        warnings.append("one_or_more_form_windows_incomplete")
    return envelope(service, data, before, warnings)


@router.get(
    "/players/{player_id}/phases", response_model=Envelope[list[PhaseMetrics]], tags=["Analytics"]
)
def player_phases(
    service: Service,
    player_id: str,
    side: Side = Side.batting,
    season: Season = None,
    before: Before = None,
    venue_id: str | None = None,
):
    return envelope(
        service,
        service.phases(player_id, side, season=season, before=before, venue_id=venue_id),
        before,
        ["fixed_20_over_phases_not_rescaled_for_shortened_games"],
    )


@router.get("/analytics/matchup", response_model=Envelope[Matchup], tags=["Analytics"])
def matchup(
    service: Service,
    batter_id: str,
    bowler_id: str,
    season: Season = None,
    before: Before = None,
    phase: Phase | None = None,
    venue_id: str | None = None,
):
    data, warnings = service.matchup(
        batter_id, bowler_id, season=season, before=before, phase=phase, venue_id=venue_id
    )
    if phase:
        warnings.append("fixed_20_over_phases_not_rescaled_for_shortened_games")
    return envelope(service, data, before, warnings)


@router.get("/analytics/bowling-type", response_model=Envelope[Matchup], tags=["Analytics"])
def bowling_type(
    service: Service,
    batter_id: str,
    category: BowlingCategory,
    arm: BowlingArm | None = None,
    season: Season = None,
    before: Before = None,
    phase: Phase | None = None,
    venue_id: str | None = None,
):
    data, warnings = service.matchup(
        batter_id,
        category=category,
        arm=arm,
        season=season,
        before=before,
        phase=phase,
        venue_id=venue_id,
    )
    warnings.append("career_bowling_category_not_per_delivery_variation")
    if phase:
        warnings.append("fixed_20_over_phases_not_rescaled_for_shortened_games")
    return envelope(service, data, before, warnings)


@router.get("/matches", response_model=Page[Match], tags=["Matches"])
def matches(
    service: Service,
    season: Season = None,
    before: Before = None,
    venue_id: str | None = None,
    team_id: str | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    items, total = service.matches(
        season=season, before=before, venue_id=venue_id, team_id=team_id, limit=limit, offset=offset
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "meta": metadata(service, before, ["archive_not_complete_scheduled_fixture_census"]),
    }


@router.get("/matches/{match_id}", response_model=Envelope[MatchDetail], tags=["Matches"])
def match_detail(service: Service, match_id: str):
    match = service.require("match", match_id)
    return envelope(
        service,
        {
            "match": match,
            "innings": service.rows(
                "SELECT * FROM innings WHERE match_id=? ORDER BY innings", (match_id,)
            ),
            "participants": service.rows(
                "SELECT m.*,p.display_name FROM match_players m JOIN players p USING(player_id) WHERE match_id=? ORDER BY team_id,player_id",
                (match_id,),
            ),
            "replacements": service.rows(
                "SELECT * FROM replacements WHERE match_id=? ORDER BY delivery_id,replacement_index",
                (match_id,),
            ),
        },
        warnings=["listed_participants_not_confirmed_starting_xi"],
    )


@router.get("/venues", response_model=Envelope[list[Venue]], tags=["Venues"])
def venues(service: Service):
    return envelope(service, service.rows("SELECT * FROM venues ORDER BY display_name,venue_id"))


@router.get("/venues/{venue_id}/profile", response_model=Envelope[VenueProfile], tags=["Venues"])
def venue_profile(service: Service, venue_id: str, season: Season = None, before: Before = None):
    return envelope(
        service,
        service.venue_profile(venue_id, season=season, before=before),
        before,
        [
            "venue_scoring_profile_not_measured_pitch_condition",
            "includes_recorded_shortened_and_no_result_innings",
        ],
    )


@router.get(
    "/venues/{venue_id}/phases", response_model=Envelope[list[PhaseMetrics]], tags=["Venues"]
)
def venue_phases(service: Service, venue_id: str, season: Season = None, before: Before = None):
    service.require("venue", venue_id)
    data = []
    for phase in Phase:
        where, params = service.delivery_where(
            venue_id=venue_id, season=season, before=before, phase=phase
        )
        data.append({"phase": phase, "metrics": service.delivery_metrics(where, params)})
    return envelope(
        service,
        data,
        before,
        [
            "fixed_20_over_phases_not_rescaled_for_shortened_games",
            "venue_scoring_profile_not_measured_pitch_condition",
        ],
    )


AsOf = Annotated[
    date,
    Query(
        ge=date(2008, 4, 19),
        le=date(2099, 12, 31),
        description="Required exclusive training cutoff; all results on this date are excluded",
    ),
]


@router.get("/predictions/matchup", response_model=Envelope[Prediction], tags=["Predictions"])
def predict_matchup(
    service: Service,
    batter_id: str,
    bowler_id: str,
    as_of: AsOf,
    phase: Phase | None = None,
    venue_id: str | None = None,
    curves: bool = False,
):
    data, warnings = PredictionService(service).predict(
        batter_id, bowler_id=bowler_id, as_of=as_of, phase=phase, venue_id=venue_id, curves=curves
    )
    return envelope(service, data, as_of, warnings)


@router.get("/predictions/bowling-type", response_model=Envelope[Prediction], tags=["Predictions"])
def predict_type(
    service: Service,
    batter_id: str,
    category: BowlingCategory,
    as_of: AsOf,
    arm: BowlingArm | None = None,
    phase: Phase | None = None,
    venue_id: str | None = None,
    curves: bool = False,
):
    data, warnings = PredictionService(service).predict(
        batter_id,
        category=category,
        arm=arm,
        as_of=as_of,
        phase=phase,
        venue_id=venue_id,
        curves=curves,
    )
    return envelope(service, data, as_of, warnings)
