"""Summarize measured lineup recovery and the remaining inventory exceptions."""

import json
import sqlite3
from collections import Counter, defaultdict

from build_prematch_pack import PACK, ROOT, digest


def main():
    coverage = json.loads((PACK / "coverage.json").read_text("utf-8"))
    quality = json.loads((PACK / "quality_checks.json").read_text("utf-8"))
    ledger = ROOT / "research/prematch-2025/source_review_ledger.json"
    db = sqlite3.connect((PACK / "prematch.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    if digest(PACK / "prematch.sqlite") != coverage["generated_database_sha256"]:
        raise ValueError("Recovery report requires the audited database")
    missing, timestamps = defaultdict(list), Counter()
    for row in db.execute("SELECT * FROM nominations"):
        ids = json.loads(row["player_ids_json"])
        if not ids:
            missing[row["pilot_match_id"]].append({"team_id": row["team_id"], "kind": row["kind"]})
            continue
        evidence = json.loads(row["evidence_json"])
        timestamps[evidence.get("timestamp_basis", "publisher_declared_datePublished")] += 1
        timestamps[
            "with_declared_modification_time"
            if evidence.get("modified_at")
            else "without_declared_modification_time"
        ] += 1
    notes = {
        "1473471": "Rain-delayed 18 April fixture: retained nomination reports were after the scheduled-start cutoff and remain withheld. Outside the existing uninterrupted-match training population.",
        "1473495": "Abandoned 8 May fixture: retained nomination reports were after the scheduled-start cutoff and remain withheld. The replay on 24 May is a separate inventory entry with sourced lists.",
        "official:a80f1839-0588-43dc-afc7-ec3f2a4fca2a": "17 May fixture abandoned without a ball bowled; no admissible nomination reports were located. Retained in the official inventory, absent from frozen ball data.",
    }
    exceptions = []
    for mid, slots in missing.items():
        fixture = dict(
            db.execute("SELECT * FROM pilot_matches WHERE pilot_match_id=?", (mid,)).fetchone()
        )
        official = json.loads(fixture["fixture_json"])
        exceptions.append(
            {
                "pilot_match_id": mid,
                "date": fixture["match_date"],
                "teams": [fixture["team1_id"], fixture["team2_id"]],
                "cutoff_at": fixture["start_at"],
                "official_gid": fixture["official_gid"],
                "official_result": official.get("resultString"),
                "missing_slots": slots,
                "decision": notes.get(
                    mid, "No admissible complete source was established; remains unknown."
                ),
            }
        )
    db.close()
    result = {
        "scope": "2025 IPL original starting XIs and five nominated substitutes; research source coverage",
        "baseline_previously_reported": {
            "starting_xi_team_slots": 103,
            "substitute_team_slots": 81,
            "complete_source_checked_fixtures": 30,
            "complete_source_reviewed_fixtures": 1,
        },
        "current": {
            "starting_xi_team_slots": coverage["coverage"][
                "starting_xi_timestamp_source_checked_team_slots"
            ],
            "substitute_team_slots": coverage["coverage"][
                "nominated_substitutes_timestamp_source_checked_team_slots"
            ],
            "complete_source_reviewed_fixtures": quality["complete_strict_fixture_features"],
            "reviewed_training_eligible_matches": coverage[
                "eligible_matches_with_complete_source_reviewed_inputs"
            ],
            "training_eligible_population": coverage["training_eligible_matches"],
            "integrity_checks_passed": quality["passed_checks"],
        },
        "source_review_ledger_sha256": digest(ledger),
        "source_packet_sha256": digest(PACK / "source_review_packet.json"),
        "database_sha256": coverage["generated_database_sha256"],
        "source_database_unchanged_sha256": coverage["source_database_unchanged_sha256"],
        "timestamp_evidence_counts": dict(timestamps),
        "inventory_exceptions": exceptions,
        "quality_improvements": [
            "Preserved explicit XI/bench boundaries and rejected projected Impact choices.",
            "Resolved reviewed spelling variants and separately registered bench-only identities; never invented their history.",
            "Retained public older-update pages and commentary entry timestamps.",
            "Source inspection caught swapped PBKS/KKR bench labels on 15 April; team-membership checks now reject those records and independent correctly labelled reports replace them.",
            "Retained incompatible reports and unknowns rather than altering reconstructed originals to fit them.",
            "Exact nomination/source hashes bind the assistant's inspection decisions; changed evidence requires renewed review.",
        ],
        "nomination_research_gate_passed": coverage["strict_training_ready"],
        "production_validated": False,
        "accuracy_improvement_tested": False,
        "last_measured_winner_accuracy": 39 / 70,
        "limitations": [
            "Current retrievals of historical publisher reports are not immutable announcement-time captures; undeclared edits remain possible.",
            "Some commentary entries expose an entry timestamp without modification history; this absence remains explicit.",
            "Fourteen availability claims are not comprehensive date-valid player availability coverage.",
            "Nomination coverage readiness is not production readiness or proof of a 70 percent accuracy target.",
        ],
    }
    (PACK / "lineup_recovery_report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "current": result["current"],
                "timestamp_evidence_counts": result["timestamp_evidence_counts"],
                "remaining_fixture_exceptions": len(exceptions),
                "nomination_research_gate_passed": result["nomination_research_gate_passed"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
