"""Bounded, explicit planning contracts: computation POSTs never write the dataset."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlayerId = Annotated[str, Field(min_length=1, max_length=80)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImpactPlan(InputModel):
    outgoing_id: PlayerId
    incoming_id: PlayerId
    timing: str = Field(default="innings_interval", pattern="^innings_interval$")


class TeamPlan(InputModel):
    team_id: PlayerId
    starting_xi: list[PlayerId] = Field(min_length=11, max_length=11)
    batting_order: list[PlayerId] = Field(min_length=11, max_length=11)
    bowling_plan: list[PlayerId] = Field(min_length=20, max_length=20)
    captain_id: PlayerId
    substitutes: list[PlayerId] = Field(default_factory=list, max_length=5)
    impact: ImpactPlan | None = None

    @model_validator(mode="after")
    def unique(self):
        for ids in (self.starting_xi, self.batting_order, self.substitutes):
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate player identifiers")
        if self.captain_id not in self.starting_xi:
            raise ValueError("Captain must be in the starting XI")
        if set(self.starting_xi) & set(self.substitutes):
            raise ValueError("Substitutes cannot be in the starting XI")
        return self


class SimulationRequest(InputModel):
    season: int = Field(default=2026, ge=2026, le=2026)
    as_of: date = Field(ge=date(2008, 4, 19), le=date(2099, 12, 31))
    venue_id: PlayerId
    team_a: TeamPlan
    team_b: TeamPlan
    batting_first_team_id: PlayerId
    simulations: int = Field(default=500, ge=50, le=1000)
    seed: int = Field(default=20261002, ge=0, le=4294967295)
    sample_posterior: bool = True
    use_delivery_calibration: bool = False
    include_sample_match: bool = False
    allow_unknown_availability: bool = False
    max_super_overs: int = Field(default=6, ge=0, le=6)


class OptimizationRequest(InputModel):
    season: int = Field(default=2026, ge=2026, le=2026)
    as_of: date = Field(ge=date(2008, 4, 19), le=date(2099, 12, 31))
    venue_id: PlayerId
    team_id: PlayerId
    opponent: TeamPlan
    batting_first_team_id: PlayerId
    candidate_ids: list[PlayerId] | None = Field(default=None, min_length=11, max_length=40)
    locked_ids: list[PlayerId] = Field(default_factory=list, max_length=11)
    excluded_ids: list[PlayerId] = Field(default_factory=list, max_length=40)
    allow_unknown_availability: bool = False
    minimum_batting_options: int = Field(default=6, ge=0, le=11)
    risk_aversion: float = Field(default=1, ge=0, le=3, allow_inf_nan=False)
    use_delivery_calibration: bool = False
    candidate_count: int = Field(default=3, ge=1, le=3)
    simulations: int = Field(default=200, ge=50, le=500)
    seed: int = Field(default=20261002, ge=0, le=4294967295)

    @model_validator(mode="after")
    def unique(self):
        for ids in (self.locked_ids, self.excluded_ids, self.candidate_ids or []):
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate player identifiers")
        if set(self.locked_ids) & set(self.excluded_ids):
            raise ValueError("A player cannot be locked and excluded")
        return self


class SimulationResult(BaseModel):
    reliability: dict = Field(default_factory=dict)
    simulator_version: str
    status: str
    eligibility_verified: bool
    simulations: int
    seed: int
    outcomes: dict
    innings: list[dict]
    training: dict
    assumptions: list[str]
    sample_match: dict | None = None


class OptimizationResult(BaseModel):
    reliability: dict = Field(default_factory=dict)
    optimizer_version: str
    status: str
    eligibility_verified: bool
    objective: dict
    recommended: dict
    alternatives: list[dict]
    candidate_scores: list[dict]
    exclusions: list[dict]
    constraints: dict
    confirmation: dict
