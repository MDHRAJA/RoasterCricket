"""Read prepared match-day features with an explicit nomination evidence threshold."""

import json

from backend.prematch_data import nomination_eligible


def match_day_inputs(db, pilot_match_id, *, allow_machine_checked=False):
    row = db.execute(
        "SELECT * FROM pilot_matches WHERE pilot_match_id=?", (pilot_match_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown pilot match")
    match = dict(row)
    teams = []
    for team in (match["team1_id"], match["team2_id"]):
        nominations = {}
        permitted_bases = set()
        for rec in db.execute(
            "SELECT * FROM nominations WHERE pilot_match_id=? AND team_id=?", (pilot_match_id, team)
        ):
            evidence = json.loads(rec["evidence_json"])
            valid = nomination_eligible(
                evidence, match["start_at"], allow_machine_checked=allow_machine_checked
            )
            nominations[rec["kind"]] = {
                "status": rec["status"] if valid else "withheld_insufficient_evidence",
                "retained_evidence_status": rec["status"],
                "player_ids": json.loads(rec["player_ids_json"]) if valid else [],
                "published_at": rec["published_at"],
                "source_url": rec["source_url"],
                "timestamp_basis": evidence.get(
                    "timestamp_basis", "publisher_declared_datePublished"
                ),
                "modification_timestamp_available": bool(evidence.get("modified_at")),
                "historical_snapshot_at_publication_available": False,
            }
            if valid:
                permitted_bases.add("source_checked_" + rec["kind"])
        starters = set(nominations.get("starting_xi", {}).get("player_ids", []))
        substitutes = set(nominations.get("nominated_substitutes", {}).get("player_ids", []))
        if starters & substitutes:
            raise ValueError("Nominated substitutes overlap the starting XI")
        forms, watchlist = [], []
        for rec in db.execute(
            "SELECT * FROM player_form_snapshots WHERE pilot_match_id=? AND team_id=? ORDER BY selection_basis,player_id",
            (pilot_match_id, team),
        ):
            value = {
                "player_id": rec["player_id"],
                "selection_basis": rec["selection_basis"],
                "recent_t20_form": json.loads(rec["form_json"]),
                "availability": json.loads(rec["availability_json"]),
            }
            if rec["selection_basis"] in permitted_bases:
                forms.append(value)
            elif rec["selection_basis"] == "previously_published_claim_watchlist":
                watchlist.append(value)
            # Reconstructed XIs NEVER substitute for missing sourced nominations.
        teams.append(
            {
                "team_id": team,
                "nominations": nominations,
                "player_features": forms,
                "known_claim_watchlist": watchlist,
                "lineup_and_substitute_features_complete": all(
                    nominations.get(k, {}).get("player_ids")
                    for k in ("starting_xi", "nominated_substitutes")
                ),
            }
        )
    represented = [
        set(p for n in t["nominations"].values() for p in n["player_ids"]) for t in teams
    ]
    if represented[0] & represented[1]:
        raise ValueError("A player is nominated for both teams")
    return {
        "pilot_match_id": pilot_match_id,
        "match_id": match["match_id"],
        "match_date": match["match_date"],
        "exclusive_nomination_cutoff": match["start_at"],
        "exclusive_performance_and_date_only_news_cutoff": match["match_date"],
        "evidence_threshold": "timestamped_source_cross_checks_allowed"
        if allow_machine_checked
        else "manually_reviewed_timestamped_reports_only",
        "teams": teams,
        "lineup_features_complete": all(
            t["lineup_and_substitute_features_complete"] for t in teams
        ),
        "production_validated": False,
        "accuracy_target_validated": False,
        "availability_rule": "missing evidence remains unknown; nomination is not a medical or registration certificate",
    }
