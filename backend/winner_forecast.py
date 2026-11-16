"""Explicit opt-in research forecast. Never replaces the simulator/optimizer."""

from datetime import date, timedelta
from itertools import groupby

from backend.prematch_features import FEATURE_VERSION, FeatureState, read_archive
from backend.winner_model import predict_json_model


def uses_original_xi(model):
    return any(
        "diff_xi_" in model["feature_names"][i]
        for component in model["components"]
        for i in component["columns"]
    )


def forecast(db, model, context):
    if model["feature_version"] != FEATURE_VERSION:
        raise ValueError("The model's feature implementation is incompatible")
    if context.match_date < model["exclusive_training_cutoff"]:
        raise ValueError("Forecast date precedes the model's training/selection cutoff")
    for team in (context.batting_first_team_id, context.chasing_team_id):
        if db.execute("SELECT 1 FROM teams WHERE team_id=?", (team,)).fetchone() is None:
            raise ValueError("Unknown forecast team")
    if db.execute("SELECT 1 FROM venues WHERE venue_id=?", (context.venue_id,)).fetchone() is None:
        raise ValueError("Unknown forecast venue")
    if uses_original_xi(model) and context.starting_xi_first is None:
        raise ValueError("This selected recipe needs explicitly supplied starting XIs")
    observations, _ = read_archive(db)
    history = [r for r in observations if r["context"].match_date < context.match_date]
    window_start = (date.fromisoformat(context.match_date) - timedelta(days=1461)).isoformat()
    recent = [r for r in history if r["context"].match_date >= window_start]
    if len(history) < 100 or len(recent) < 50:
        raise ValueError("Insufficient prior match history for this research model")
    state = FeatureState()
    for _, chunk in groupby(history, key=lambda r: r["context"].match_date):
        state.update_day(list(chunk))
    values, trace = state.predict_features(context)
    vector = [[values[k] for k in model["feature_names"]]]
    p = float(predict_json_model(vector, model)[0])
    first, chase = context.batting_first_team_id, context.chasing_team_id
    warnings = [
        "experimental_research_model_not_a_validated_recommendation",
        "70_percent_accuracy_target_not_established",
        "no_registered_eligibility_or_dated_injury_pitch_weather_verification",
        "winner_model_does_not_validate_xi_counterfactuals",
        "lagged_player_groups_are_not_announced_team_sheets",
    ]
    if context.starting_xi_first is not None:
        warnings.append("supplied_starting_xis_not_independently_verified")
    if (
        state.last_date
        and (date.fromisoformat(context.match_date) - date.fromisoformat(state.last_date)).days > 60
    ):
        warnings.append("match_archive_more_than_60_days_old_at_forecast_cutoff")
    if context.season > int(model["exclusive_training_cutoff"][:4]):
        warnings.append("model_weights_not_retrained_for_requested_season")
    return {
        "status": "research_only_not_decision_ready",
        "selected_recipe": model["selected_recipe"],
        "as_of": context.match_date,
        "conditional_on": "uninterrupted_decisive_ordinary_match_post_toss",
        "probabilities": {first: p, chase: 1 - p},
        "threshold_pick": first if p > 0.5 else chase,
        "prediction_is_not_a_recommendation": True,
        "decision_ready": False,
        "production_validated": False,
        "selected_model_uses_original_xi_features": uses_original_xi(model),
        "retrospective_evaluation_accuracy": model["evaluation_accuracy"],
        "target_met_on_evaluated_cohort": model["target_met_on_evaluated_cohort"],
        "exclusive_model_training_cutoff": model["exclusive_training_cutoff"],
        "evidence": trace,
        "warnings": warnings,
    }
