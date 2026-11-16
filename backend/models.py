"""Frontend-facing, documented data contracts. Missing facts serialize as JSON null."""

from datetime import date
from enum import IntEnum, StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Phase(StrEnum):
    powerplay = "powerplay"
    middle = "middle"
    death = "death"


class FormWindow(IntEnum):
    last5 = 5
    last10 = 10


class Role(StrEnum):
    batter = "batter"
    bowler = "bowler"
    allrounder = "allrounder"
    wicketkeeper_batter = "wicketkeeper_batter"


class Hand(StrEnum):
    left = "left"
    right = "right"


class BowlingCategory(StrEnum):
    pace = "pace"
    spin = "spin"
    mixed = "mixed"
    unknown = "unknown"


class BowlingArm(StrEnum):
    left = "left"
    right = "right"
    mixed = "mixed"
    unknown = "unknown"


class Side(StrEnum):
    batting = "batting"
    bowling = "bowling"


class Metadata(BaseModel):
    dataset_version: str
    before: date | None = Field(default=None, description="Exclusive match-date cutoff")
    warnings: list[str] = Field(default_factory=list)


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Metadata


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    meta: Metadata


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Player(BaseModel):
    model_config = ConfigDict(extra="allow")
    player_id: str
    display_name: str
    full_name: str | None = None
    cricsheet_name: str | None = None
    country: str | None = None
    primary_role: str | None = None
    batting_hand: str | None = None
    bowling_style: str | None = None
    bowling_category: str | None = None
    bowling_arm: str | None = None
    is_wicketkeeper: bool | None = None
    is_overseas: bool | None = None
    has_ipl_history: bool = False
    metadata_conflict: str | None = None
    metadata_confidence: str | None = None
    identity_status: str | None = None


class Team(BaseModel):
    team_id: str
    display_name: str
    is_current: bool


class Availability(BaseModel):
    status: str = "unknown"
    effective_on: date | None = None
    source_url: str | None = None
    notes: str | None = None


class RosterMember(BaseModel):
    player: Player
    roster: dict[str, Any]
    availability: Availability


class Roster(BaseModel):
    team: Team
    season: int
    roster_type: str
    members: list[RosterMember]
    eligibility_verified: bool = False


class Match(BaseModel):
    model_config = ConfigDict(extra="allow")
    match_id: str
    match_date: date
    season: int
    team1_id: str
    team2_id: str
    venue_id: str
    winner_id: str | None = None


class MatchDetail(BaseModel):
    match: Match
    innings: list[dict[str, Any]]
    participants: list[dict[str, Any]]
    replacements: list[dict[str, Any]]


class PlayerStatistics(BaseModel):
    player_id: str
    matches_involved: int
    batting_innings: int
    bowling_innings: int
    runs: int
    balls_faced: int
    dismissals: int
    fours: int
    sixes: int
    wickets: int
    legal_balls_bowled: int
    runs_conceded: int
    batting_average: float | None
    strike_rate: float | None
    economy: float | None
    bowling_average: float | None


class FormSummary(BaseModel):
    batting_innings: int
    bowling_innings: int
    runs: int | None
    balls_faced: int | None
    strike_rate: float | None
    runs_per_innings: float | None
    recency_weighted_runs: float | None
    runs_trend_per_innings: float | None
    wickets: int | None
    legal_balls_bowled: int | None
    economy: float | None


class RecentForm(BaseModel):
    player_id: str
    window: int
    latest_included_match_date: date | None
    summary: FormSummary
    timeline: list[dict[str, Any]]


class DeliveryMetrics(BaseModel):
    deliveries: int
    matches: int
    legal_balls: int
    balls_faced: int
    batter_runs: int
    team_runs: int
    bowler_runs_conceded: int
    bowler_wickets: int
    striker_dismissals: int
    fours: int
    sixes: int
    batting_dots: int
    bowling_dots: int
    strike_rate: float | None
    economy: float | None
    boundary_ball_rate: float | None
    bowling_dot_rate: float | None
    first_date: date | None
    last_date: date | None


class OutcomeCount(BaseModel):
    batter_runs: int
    striker_dismissed: int
    deliveries: int
    legal_balls: int
    balls_faced: int


class Matchup(BaseModel):
    batter_id: str
    bowler_id: str | None = None
    metrics: DeliveryMetrics
    outcomes: list[OutcomeCount]
    interpretation: str = "Observed event counts; not predicted success probabilities"


class PhaseMetrics(BaseModel):
    phase: Phase
    metrics: DeliveryMetrics


class Venue(BaseModel):
    venue_id: str
    display_name: str
    city: str | None = None


class VenueProfile(BaseModel):
    venue: Venue
    aliases: list[str]
    matches: int
    innings: int
    runs: int
    legal_balls: int
    wickets: int
    runs_per_over: float | None
    first_innings_count: int
    mean_first_innings_runs: float | None
    median_first_innings_runs: float | None


class DatasetInfo(BaseModel):
    model_config = ConfigDict(extra="allow")
    dataset: str
    path: str
    rows: int
    columns: list[str]
    sha256: str


class CredibleInterval(BaseModel):
    level: float
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    interpretation: str


class DensityPoint(BaseModel):
    probability: float = Field(gt=0, lt=1)
    density: float = Field(ge=0, allow_inf_nan=False)


class PredictedEvent(BaseModel):
    probability: float = Field(ge=0, le=1)
    observed_successes: int
    observed_deliveries: int
    posterior_alpha: float = Field(gt=0)
    posterior_beta: float = Field(gt=0)
    credible_interval: CredibleInterval
    density_curve: list[DensityPoint] | None = None


class PredictedRun(BaseModel):
    batter_runs: str
    probability: float = Field(ge=0, le=1)
    observed_deliveries: int
    credible_interval: CredibleInterval


class JointOutcome(BaseModel):
    batter_runs: str
    boundary: bool
    striker_dismissed: bool
    probability: float = Field(ge=0, le=1)


class Prediction(BaseModel):
    calibrated_forecast: dict | None = None
    model_version: str
    status: str
    batter_id: str
    bowler_id: str | None
    as_of: date
    context: dict[str, str | None]
    training: dict[str, Any]
    prior_event_probabilities: dict[str, float]
    events: dict[str, PredictedEvent]
    run_distribution: list[PredictedRun]
    expected_capped_batter_runs_per_legal_delivery: float
    joint_outcomes: list[JointOutcome]
