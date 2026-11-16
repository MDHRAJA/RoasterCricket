"""Audit the new pack without treating coverage gaps as successful verification."""

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.historical_planning import historical_cases  # noqa: E402
from backend.match_day_inputs import match_day_inputs  # noqa: E402
from backend.prematch_data import (  # noqa: E402
    availability_as_of,
    nomination_eligible,
    nomination_review_digest,
    team_membership_conflicts,
)
from scripts.build_prematch_pack import read_inputs  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-training-ready", action="store_true")
    args = parser.parse_args()
    pack = ROOT / "outputs/prematch-2025"
    report = json.loads((pack / "coverage.json").read_text("utf-8"))
    config = json.loads((ROOT / "research/prematch-2025/evidence.json").read_text("utf-8"))
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    check(
        "Frozen source DB unchanged",
        digest(Settings.from_env().database) == report["source_database_unchanged_sha256"],
    )
    check(
        "Generated DB digest matches",
        digest(pack / "prematch.sqlite") == report["generated_database_sha256"],
    )
    check(
        "Evidence config digest matches",
        digest(ROOT / "research/prematch-2025/evidence.json") == report["evidence_config_sha256"],
    )
    check(
        "Source-check report digest matches",
        digest(pack / "source_checked_nominations.json")
        == report["machine_checked_nomination_file_sha256"],
    )
    for relative, expected in report.get("pipeline_source_sha256", {}).items():
        check("Pipeline source digest " + relative, digest(ROOT / relative) == expected)
    if report.get("source_review_ledger_sha256"):
        check(
            "Recorded source-inspection ledger digest",
            digest(ROOT / "research/prematch-2025/source_review_ledger.json")
            == report["source_review_ledger_sha256"],
        )
    sources = {r["url"]: r for r in json.loads((pack / "source_manifest.json").read_text("utf-8"))}
    for source in sources.values():
        if source["status"] != "unavailable":
            check(
                "Source digest " + source["source_id"],
                digest(pack / source["relative_path"]) == source["sha256"],
            )
    db = sqlite3.connect((pack / "prematch.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    _, _, _, _, _, memberships = read_inputs(Settings.from_env())
    with connection(Settings.from_env()) as frozen:
        eligible_cases, _ = historical_cases(frozen, seasons=(2025,))
    eligible_ids = {case["match_id"] for case in eligible_cases}
    check(
        "Unchanged predefined training population",
        len(eligible_ids) == report["training_eligible_matches"] == 68,
    )
    check(
        "Additional identities retained separately",
        db.execute("SELECT COUNT(*) FROM additional_player_identities").fetchone()[0]
        == len(config.get("additional_players", [])),
    )
    check(
        "Generated SQLite integrity",
        db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        and not db.execute("PRAGMA foreign_key_check").fetchall(),
    )
    check(
        "No duplicate source match IDs",
        db.execute("SELECT COUNT(*) FROM t20_matches").fetchone()[0]
        == report["normalization"]["t20_matches"],
    )
    matches = {r["pilot_match_id"]: dict(r) for r in db.execute("SELECT * FROM pilot_matches")}
    check(
        "Complete official fixture inventory",
        len(matches) == report["official_inventory_matches"] == 75,
    )
    check(
        "Frozen ball-data matches all accounted for",
        sum(r["match_id"] is not None for r in matches.values())
        == report["frozen_ipl_recorded_matches"]
        == 74,
    )
    for rec in db.execute("SELECT * FROM player_form_snapshots"):
        match = matches[rec["pilot_match_id"]]
        form = json.loads(rec["form_json"])
        latest = form["latest_included_date"]
        if rec["player_id"].startswith("local:"):
            check(
                f"No invented registry history {rec['pilot_match_id']} {rec['player_id']}",
                not form["source_match_ids"],
            )
        check(
            f"Form cutoff {rec['pilot_match_id']} {rec['player_id']} {rec['selection_basis']}",
            form["exclusive_as_of"] == match["match_date"]
            and (latest is None or form["window_start"] <= latest < match["match_date"])
            and rec["pilot_match_id"] not in form["source_match_ids"],
        )
        availability = availability_as_of(
            config["availability"],
            rec["team_id"],
            rec["player_id"],
            match["match_date"],
            stage=match["stage"],
            match_id=match["match_id"],
        )
        check(
            f"Availability cutoff {rec['pilot_match_id']} {rec['player_id']} {rec['selection_basis']}",
            json.loads(rec["availability_json"]) == availability
            and (
                not availability.get("known_from_date")
                or availability["known_from_date"] < match["match_date"]
            ),
        )
        if rec["selection_basis"] == "previously_published_claim_watchlist":
            check(
                f"No future watchlist identity {rec['pilot_match_id']} {rec['player_id']}",
                any(
                    c["team_id"] == rec["team_id"]
                    and c["player_id"] == rec["player_id"]
                    and c["published_on"] < match["match_date"]
                    for c in config["availability"]
                ),
            )
    complete_strict = complete_source = 0
    eligible_strict = eligible_source = 0
    for mid, match in matches.items():
        strict = match_day_inputs(db, mid)
        source_checked = match_day_inputs(db, mid, allow_machine_checked=True)
        complete_strict += int(strict["lineup_features_complete"])
        complete_source += int(source_checked["lineup_features_complete"])
        if match["match_id"] in eligible_ids:
            eligible_strict += int(strict["lineup_features_complete"])
            eligible_source += int(source_checked["lineup_features_complete"])
        for result in (strict, source_checked):
            check(
                f"No validation promotion {mid} {result['evidence_threshold']}",
                result["production_validated"] is False
                and result["accuracy_target_validated"] is False,
            )
            for team in result["teams"]:
                for kind, nomination in team["nominations"].items():
                    ids = nomination["player_ids"]
                    check(
                        f"Valid nomination membership {mid} {team['team_id']} {kind} {result['evidence_threshold']}",
                        len(ids) == len(set(ids))
                        and (not ids or len(ids) == (11 if kind == "starting_xi" else 5)),
                    )
                check(
                    f"No reconstruction fallback {mid} {team['team_id']} {result['evidence_threshold']}",
                    all(
                        r["selection_basis"].startswith("source_checked_")
                        for r in team["player_features"]
                    ),
                )
        for rec in db.execute("SELECT * FROM nominations WHERE pilot_match_id=?", (mid,)):
            evidence = json.loads(rec["evidence_json"])
            ids = json.loads(rec["player_ids_json"])
            check(
                f"Team membership consistency {mid} {rec['team_id']} {rec['kind']}",
                not team_membership_conflicts(ids, rec["team_id"], memberships),
            )
            if evidence.get("source_inspection"):
                inspection = evidence["source_inspection"]
                check(
                    f"Bound source inspection {mid} {rec['team_id']} {rec['kind']}",
                    inspection["record_sha256"] == nomination_review_digest(evidence)
                    and inspection["source_sha256"] == sources[rec["source_url"]]["sha256"]
                    and inspection["reviewer"] == "assistant"
                    and inspection["human_certification"] is False,
                )
            check(
                f"Eligible retained nominations {mid} {rec['team_id']} {rec['kind']}",
                bool(ids)
                == nomination_eligible(evidence, match["start_at"], allow_machine_checked=True),
            )
    check(
        "Reviewed training-eligible coverage reproduced",
        eligible_strict == report["eligible_matches_with_complete_source_reviewed_inputs"],
    )
    check(
        "Source-checked training-eligible coverage reproduced",
        eligible_source == report["eligible_matches_with_complete_source_checked_inputs"],
    )
    check(
        "Training gate derived from reviewed nomination coverage",
        report["strict_training_ready"] == (eligible_strict == len(eligible_ids)),
    )
    db.close()
    result = {
        "status": "passed",
        "passed_checks": len(checks),
        "complete_strict_fixture_features": complete_strict,
        "complete_source_checked_fixture_features": complete_source,
        "strict_training_ready": report["strict_training_ready"],
        "eligible_matches_with_complete_source_reviewed_inputs": eligible_strict,
        "accuracy_improvement_tested": False,
        "source_database_unchanged_sha256": report["source_database_unchanged_sha256"],
        "checks": checks,
        "interpretation": "Integrity and date gates passed; incomplete source coverage remains incomplete.",
    }
    (pack / "quality_checks.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, indent=2))
    if args.require_training_ready and not report["strict_training_ready"]:
        raise SystemExit(
            "Training readiness gate FAILED: complete reviewed nomination coverage is still missing"
        )


if __name__ == "__main__":
    main()
