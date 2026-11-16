"""Reviewed 2026 core constraints; no claim of registered match eligibility."""

from collections import Counter

from backend.services import ApiError

RULES_VERSION = "ipl-2026-core-planning-v1"
RULES_SOURCE = "https://www.iplt20.com/cms/files/jot2qw8s50z1/7DScv8UxUc6AJcrXDon2yW/bdc93c1c438bfafad464f2a334862d59/1775736835406_TATA_IPL_2026_Match_Playing_Conditions.pdf"


def bad(code, message):
    raise ApiError(422, code, message)


def active_lineups(plan, batting_first):
    initial = list(plan.starting_xi)
    second = list(initial)
    if plan.impact:
        if (
            plan.impact.outgoing_id not in initial
            or plan.impact.incoming_id not in plan.substitutes
        ):
            bad(
                "invalid_impact_plan",
                "Interval Impact Player must replace a starter and be a nominated substitute",
            )
        second[second.index(plan.impact.outgoing_id)] = plan.impact.incoming_id
    return (initial, second) if batting_first else (second, initial)


def validate_team(plan, members, *, batting_first, as_of, allow_unknown):
    by_id = {m["player"]["player_id"]: m for m in members}
    nominated = [*plan.starting_xi, *plan.substitutes]
    if not set(nominated) <= by_id.keys():
        bad(
            "player_not_in_roster_snapshot",
            "All nominated players must belong to the selected team's saved roster",
        )
    for pid in nominated:
        member = by_id[pid]
        status = member["availability"]
        dated = str(status.get("effective_on") or "") == as_of.isoformat()
        if dated and status["status"] == "unavailable":
            bad("player_unavailable", "A nominated player has a dated unavailable record")
        if not allow_unknown and not (dated and status["status"] == "available"):
            bad(
                "availability_not_confirmed",
                "Match-date availability is not confirmed; use explicit planning opt-in or provide sourced dated availability",
            )
        if member["player"].get("is_overseas") is None:
            bad(
                "overseas_classification_unknown",
                "Unknown overseas classifications cannot pass the quota check",
            )

    def overseas(ids):
        return sum(bool(by_id[p]["player"]["is_overseas"]) for p in ids)

    if overseas(plan.starting_xi) > 4:
        bad("overseas_quota_exceeded", "Starting XI exceeds the four-player overseas proxy quota")
    if plan.impact and by_id[plan.impact.incoming_id]["player"]["is_overseas"]:
        # Supplementary current-season regulation is not in the saved conditions.
        bad(
            "overseas_impact_not_supported",
            "Only domestic interval Impact plans are supported pending full supplemental-rule verification",
        )
    batting, bowling = active_lineups(plan, batting_first)
    if set(plan.batting_order) != set(batting):
        bad(
            "invalid_batting_order",
            "Batting order must name exactly the eleven active batting players",
        )
    if not set(plan.bowling_plan) <= set(bowling):
        bad("invalid_bowling_plan", "Bowling plan contains an inactive player")
    counts = Counter(plan.bowling_plan)
    if max(counts.values()) > 4 or any(
        a == b for a, b in zip(plan.bowling_plan, plan.bowling_plan[1:], strict=False)
    ):
        bad("invalid_bowling_quota", "No bowler may bowl more than four overs or consecutive overs")
    if not any(by_id[p]["player"].get("is_wicketkeeper") for p in bowling):
        bad("wicketkeeper_missing", "The active fielding XI needs a recorded wicketkeeper")
    return batting, bowling
