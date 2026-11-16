"""Build a separate full-season evidence pack; existing model/data artifacts stay frozen."""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import time
import unicodedata
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from discover_matchday_reports import candidates_from_html  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.historical_planning import historical_cases  # noqa: E402
from backend.match_day_inputs import match_day_inputs  # noqa: E402
from backend.prematch_data import (  # noqa: E402
    PACK_SCHEMA,
    SCHEMA,
    availability_as_of,
    insert_dict,
    nomination_eligible,
    nomination_review_digest,
    normalized_t20,
    player_form,
    team_membership_conflicts,
)

PACK = ROOT / "outputs/prematch-2025"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def normalize(text):
    return re.sub(
        "[^a-z0-9]",
        "",
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower(),
    )


def read_inputs(settings):
    with connection(Settings(settings.data_dir, query_timeout_seconds=30)) as db:
        matches = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM matches WHERE season='2025' ORDER BY match_date,match_id"
            )
        ]
        originals = defaultdict(lambda: defaultdict(list))
        for r in db.execute(
            "SELECT mp.* FROM match_players mp JOIN matches m USING(match_id) WHERE m.season='2025' AND mp.is_incoming_match_replacement=0"
        ):
            originals[r["match_id"]][r["team_id"]].append(r["player_id"])
        aliases = defaultdict(set)
        players = set()
        for r in db.execute("SELECT player_id,display_name,full_name,cricsheet_name FROM players"):
            players.add(r["player_id"])
            for value in r[1:]:
                if value:
                    aliases[normalize(value)].add(r["player_id"])
        for r in db.execute("SELECT player_id,normalized_alias FROM player_aliases"):
            aliases[normalize(r["normalized_alias"])].add(r["player_id"])
        team_names = {
            r["team_name_raw"]: r["team_id"] for r in db.execute("SELECT * FROM team_aliases")
        }
        memberships = defaultdict(set)
        for row in db.execute(
            "SELECT DISTINCT mp.player_id,mp.team_id FROM match_players mp JOIN matches m USING(match_id) WHERE m.season='2025'"
        ):
            memberships[row["player_id"]].add(row["team_id"])
    config = json.loads((ROOT / "research/prematch-2025/evidence.json").read_text("utf-8"))
    supplements = config.get("additional_players", [])
    if supplements:
        sources = {
            r["url"]: r for r in json.loads((PACK / "source_manifest.json").read_text("utf-8"))
        }
        registry_path = PACK / "raw/cricsheet/people.csv"
        registry_source = sources.get("https://cricsheet.org/register/people.csv", {})
        if registry_source.get("sha256") != digest(registry_path):
            raise ValueError("Additional identities require the retained register digest")
        with registry_path.open(encoding="utf-8", newline="") as handle:
            registry = {r["identifier"]: r for r in csv.DictReader(handle)}
        for player in supplements:
            pid = player["player_id"]
            source = sources.get(player["source_url"], {})
            if source.get("status") == "unavailable" or not source.get("relative_path"):
                raise ValueError("Additional identity has no retained franchise source")
            path = PACK / source["relative_path"]
            if digest(path) != source.get("sha256") or normalize(
                player["reviewed_support"]
            ) not in normalize(path.read_text("utf-8")):
                raise ValueError("Additional identity source changed or does not support the name")
            if not pid.startswith("local:"):
                registered = registry.get(pid, {})
                if registered.get("name") != player.get("registry_name") or registered.get(
                    "key_cricinfo"
                ) != player.get("registry_espn_id"):
                    raise ValueError("Additional identity conflicts with the retained register")
            elif player.get("registry_name"):
                raise ValueError("A local-only identity cannot imply linked Cricsheet history")
            if pid in players:
                raise ValueError("Additional identity unexpectedly overwrites a frozen player")
            players.add(pid)
            for alias in player["aliases"]:
                aliases[normalize(alias)].add(pid)
    for pid, team in config.get("reviewed_2025_team_memberships", {}).items():
        if memberships[pid] and team not in memberships[pid]:
            raise ValueError("Reviewed team mapping conflicts with frozen 2025 appearances")
        memberships[pid].add(team)
    return matches, originals, aliases, players, team_names, memberships


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage-review",
        action="store_true",
        help="Build unreviewed source inputs for inspection; ignore prior approvals and keep the strict training gate closed",
    )
    args = parser.parse_args()
    started = time.monotonic()
    settings = Settings.from_env()
    original_hash = digest(settings.database)
    matches, originals, aliases, player_ids, team_names, memberships = read_inputs(settings)
    config_path = ROOT / "research/prematch-2025/evidence.json"
    config = json.loads(config_path.read_text("utf-8"))
    for name, pid in config["reviewed_identity_mappings"].items():
        if pid not in player_ids:
            raise ValueError("Reviewed identity points outside the saved player register")
        aliases[normalize(name)] = {pid}
    sources = json.loads((PACK / "source_manifest.json").read_text("utf-8"))
    sources_by_url = {r["url"]: r for r in sources if r["status"] != "unavailable"}
    for record in sources_by_url.values():
        if digest(PACK / record["relative_path"]) != record["sha256"]:
            raise ValueError("Cached source digest mismatch")
    temporary = PACK / f"prematch.building-{uuid.uuid4().hex}.sqlite"
    db = sqlite3.connect(temporary)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    for player in config.get("additional_players", []):
        insert_dict(
            db,
            "additional_player_identities",
            {
                "player_id": player["player_id"],
                "display_name": player["display_name"],
                "identity_json": json.dumps(player),
            },
        )
    counters = Counter()
    competitions = Counter()
    seen = set()
    archive_paths = [
        settings.data_dir / "raw/cricsheet/ipl_json.zip",
        PACK / "raw/cricsheet/all_male_json.zip",
    ]
    for archive_index, path in enumerate(archive_paths):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if not member.filename.endswith(".json"):
                    continue
                if member.file_size > 8 * 1024 * 1024:
                    raise ValueError("Oversized source JSON member")
                mid = Path(member.filename).stem
                if mid in seen:
                    counters["duplicate_matches_skipped"] += 1
                    continue
                doc = json.loads(archive.read(member))
                result = normalized_t20(mid, doc, source_file=f"{path.name}:{member.filename}")
                if result is None:
                    counters["non_supported_format_skipped"] += 1
                    continue
                match, rows = result
                if archive_index and match["is_ipl"]:
                    counters["fresh_ipl_matches_ignored_to_preserve_frozen_source"] += 1
                    continue
                seen.add(mid)
                insert_dict(db, "t20_matches", match)
                for row in rows:
                    insert_dict(db, "t20_player_innings", row)
                competitions[match["competition"]] += 1
                counters["t20_matches"] += 1
                counters["player_innings_rows"] += len(rows)
            db.commit()
        print("Normalized", path.name, dict(counters), flush=True)
    fixtures = json.loads((PACK / "official_fixtures.json").read_text("utf-8"))
    local = {(r["match_date"], frozenset((r["team1_id"], r["team2_id"]))): r for r in matches}
    pilot = []
    for card in fixtures:
        teams = [t.get("abbreviation") or team_names.get(t["name"]) for t in card["teams"]]
        if len(teams) != 2 or not all(teams):
            raise ValueError("Unmapped official fixture teams")
        day = card["startDateTimeUtc"][:10]
        original = local.get((day, frozenset(teams)))
        mid = original["match_id"] if original else None
        row = {
            "pilot_match_id": mid or "official:" + card["gid"],
            "match_id": mid,
            "official_gid": card["gid"],
            "match_date": day,
            "start_at": card["startDateTimeUtc"],
            "team1_id": teams[0],
            "team2_id": teams[1],
            "stage": original["stage"] or ""
            if original
            else (card.get("title") if not str(card.get("title", "")).startswith("Match") else ""),
            "fixture_json": json.dumps(card),
        }
        insert_dict(db, "pilot_matches", row)
        pilot.append(row)
    if len({p["match_id"] for p in pilot if p["match_id"]}) != len(matches):
        raise ValueError("The official inventory does not account for every frozen 2025 match")
    raw_cache = {}

    def source_text(url):
        record = sources_by_url.get(url)
        if record is None:
            raise ValueError("Reviewed evidence has no retained public-source snapshot")
        if url not in raw_cache:
            raw_cache[url] = (PACK / record["relative_path"]).read_text("utf-8")
        return raw_cache[url]

    for claim in config["availability"]:
        if claim["player_id"] not in player_ids or normalize(
            claim["reviewed_support"]
        ) not in normalize(source_text(claim["source_url"])):
            raise ValueError("Availability claim does not match reviewed retained source")
        insert_dict(
            db,
            "availability_claims",
            {
                k: claim[k]
                for k in (
                    "claim_id",
                    "team_id",
                    "player_id",
                    "published_on",
                    "effective_from",
                    "status",
                    "source_url",
                )
            }
            | {"claim_json": json.dumps(claim)},
        )
    reviewed = {}
    ledger_path = ROOT / "research/prematch-2025/source_review_ledger.json"
    ledger = (
        json.loads(ledger_path.read_text("utf-8"))
        if ledger_path.is_file() and not args.stage_review
        else {"reviews": []}
    )
    inspections = {(r["match_id"], r["team_id"], r["kind"]): r for r in ledger["reviews"]}
    machine_path = PACK / "source_checked_nominations.json"
    machine = (
        json.loads(machine_path.read_text("utf-8"))
        if machine_path.is_file()
        else {"nominations": []}
    )
    if machine.get("candidate_file_sha256") and machine["candidate_file_sha256"] != digest(
        PACK / "lineup_source_candidates.json"
    ):
        raise ValueError("Machine nomination checks refer to a different candidate extraction")
    # Direct source inspection overrides machine-checked copies, not vice versa.
    for nomination in (
        machine["nominations"]
        + config["nominations"]
        + config.get("reviewed_punctuation_nominations", [])
    ):
        record = dict(nomination)
        inspection = inspections.get((record["match_id"], record["team_id"], record["kind"]))
        text = source_text(record["source_url"])
        entries = candidates_from_html(text, record["source_url"])
        compatible = [
            e
            for e in entries
            if e["published_at"][:16] == record["published_at"][:16]
            and all(normalize(name) in normalize(e["text"]) for name in record["names"])
        ]
        if (
            len(
                {
                    (e["published_at"], e.get("modified_at"), normalize(e["text"]))
                    for e in compatible
                }
            )
            != 1
        ):
            raise ValueError(
                "Nomination entry/date could not be uniquely verified against retained source"
            )
        entry = compatible[0]
        record["published_at"] = entry["published_at"]
        record["modified_at"] = entry.get("modified_at")
        record["timestamp_basis"] = entry.get("timestamp_basis", "publisher_declared_datePublished")
        record["modification_timestamp_available"] = bool(entry.get("modified_at"))
        ids = []
        for name in record["names"]:
            resolved = aliases[normalize(name)]
            if len(resolved) != 1:
                raise ValueError(f"Ambiguous/unresolved nomination name: {name}")
            ids.append(next(iter(resolved)))
        required = 11 if record["kind"] == "starting_xi" else 5
        if len(set(ids)) != required:
            raise ValueError("Reviewed nomination has invalid membership count")
        if team_membership_conflicts(ids, record["team_id"], memberships):
            raise ValueError(
                "Nominated player conflicts with independently known 2025 team membership"
            )
        record["player_ids"] = sorted(ids)
        if record["kind"] == "starting_xi" and set(ids) != set(
            originals[record["match_id"]][record["team_id"]]
        ):
            raise ValueError(
                "Independent reported XI conflicts with reconstructed original starters"
            )
        if record["kind"] == "nominated_substitutes" and set(ids) & set(
            originals[record["match_id"]][record["team_id"]]
        ):
            raise ValueError("Nominated substitutes overlap original starters")
        if inspection:
            if (
                inspection["record_sha256"] != nomination_review_digest(record)
                or inspection["source_sha256"] != sources_by_url[record["source_url"]]["sha256"]
                or inspection["source_url"] != record["source_url"]
                or inspection.get("method") != "direct_source_packet_inspection"
                or inspection.get("reviewer") != "assistant"
                or inspection.get("human_certification") is not False
            ):
                raise ValueError(
                    "Recorded source inspection is stale or does not match the retained evidence"
                )
            record["status"] = "timestamped_report_reviewed"
            record["source_inspection"] = inspection
        elif args.stage_review:
            fixture = next(p for p in pilot if p["match_id"] == record["match_id"])
            cutoff = datetime.fromisoformat(fixture["start_at"].replace("Z", "+00:00"))
            stamp = datetime.fromisoformat(record["published_at"].replace("Z", "+00:00"))
            modified = (
                datetime.fromisoformat(record["modified_at"].replace("Z", "+00:00"))
                if record.get("modified_at")
                else None
            )
            record["status"] = "timestamped_report_machine_checked"
            record["checks"] = {
                "known_unique_identities": True,
                "complete_membership": True,
                "no_known_team_membership_conflict": True,
                "independent_fixture_match": True,
                "original_starter_agreement_or_substitute_disjointness": True,
                "declared_timestamps_before_scheduled_start": stamp < cutoff
                and (modified is None or modified < cutoff),
                "published_within_declared_one_hour_window": cutoff - timedelta(hours=1)
                <= stamp
                < cutoff,
            }
        elif record["status"] == "timestamped_report_reviewed":
            raise ValueError(
                "Reviewed source needs a current hash-bound inspection; use --stage-review to prepare a new inspection packet"
            )
        reviewed[record["match_id"], record["team_id"], record["kind"]] = record
    queue, coverage = [], Counter()
    for match in sorted(pilot, key=lambda r: (r["match_date"], r["pilot_match_id"])):
        for team in (match["team1_id"], match["team2_id"]):
            selections = []
            for kind in ("starting_xi", "nominated_substitutes"):
                rec = reviewed.get((match["match_id"], team, kind))
                if rec and nomination_eligible(rec, match["start_at"], allow_machine_checked=True):
                    status, stamp, ids, url, evidence = (
                        rec["status"],
                        rec["published_at"],
                        rec["player_ids"],
                        rec["source_url"],
                        rec,
                    )
                    coverage[kind + "_timestamp_source_checked_team_slots"] += 1
                    coverage[
                        kind
                        + (
                            "_manually_reviewed_team_slots"
                            if status == "timestamped_report_reviewed"
                            else "_machine_checked_team_slots"
                        )
                    ] += 1
                    selections += [(p, "source_checked_" + kind) for p in ids]
                else:
                    status, stamp, ids, url, evidence = (
                        "unknown_unverified",
                        None,
                        [],
                        None,
                        {"reason": "no_reviewed_pre_cutoff_announcement"},
                    )
                    coverage[kind + "_missing_team_slots"] += 1
                    queue.append(
                        {
                            "pilot_match_id": match["pilot_match_id"],
                            "match_id": match["match_id"],
                            "date": match["match_date"],
                            "team_id": team,
                            "kind": kind,
                            "status": status,
                            "required": "dated announcement before cutoff, complete identities, source snapshot; not a post-match player list",
                        }
                    )
                insert_dict(
                    db,
                    "nominations",
                    {
                        "pilot_match_id": match["pilot_match_id"],
                        "team_id": team,
                        "kind": kind,
                        "status": status,
                        "published_at": stamp,
                        "player_ids_json": json.dumps(ids),
                        "source_url": url,
                        "evidence_json": json.dumps(evidence),
                    },
                )
            for pid in originals[match["match_id"]][team] if match["match_id"] else []:
                selections.append((pid, "reconstructed_conditional_not_strict"))
            known_claim_players = {
                c["player_id"]
                for c in config["availability"]
                if c["team_id"] == team and c["published_on"] < match["match_date"]
            }
            selections.extend(
                (pid, "previously_published_claim_watchlist") for pid in known_claim_players
            )
            for pid, basis in sorted(set(selections)):
                form = player_form(db, pid, match["match_date"])
                availability = availability_as_of(
                    config["availability"],
                    team,
                    pid,
                    match["match_date"],
                    stage=match["stage"],
                    match_id=match["match_id"],
                )
                insert_dict(
                    db,
                    "player_form_snapshots",
                    {
                        "pilot_match_id": match["pilot_match_id"],
                        "team_id": team,
                        "player_id": pid,
                        "selection_basis": basis,
                        "form_json": json.dumps(form),
                        "availability_json": json.dumps(availability),
                    },
                )
                coverage["form_snapshots"] += 1
                coverage["snapshots_with_non_ipl_history"] += int(
                    bool(form["non_ipl_batting_innings"] or form["non_ipl_bowling_innings"])
                )
                coverage["snapshots_with_no_recent_batting_or_bowling"] += int(
                    not (form["batting_innings"] or form["bowling_innings"])
                )
    db.commit()
    if (
        db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
        or db.execute("PRAGMA foreign_key_check").fetchall()
    ):
        raise ValueError("Generated pack database failed integrity checks")
    with connection(Settings(settings.data_dir, query_timeout_seconds=30)) as original_db:
        eligible_cases, _ = historical_cases(original_db, seasons=(2025,))
    eligible_ids = {c["match_id"] for c in eligible_cases}
    eligible_pilot = [p for p in pilot if p["match_id"] in eligible_ids]
    strict_complete = sum(
        match_day_inputs(db, p["pilot_match_id"])["lineup_features_complete"]
        for p in eligible_pilot
    )
    source_complete = sum(
        match_day_inputs(db, p["pilot_match_id"], allow_machine_checked=True)[
            "lineup_features_complete"
        ]
        for p in eligible_pilot
    )
    summary = {
        "schema": PACK_SCHEMA,
        "development_season": 2025,
        "official_inventory_matches": len(pilot),
        "frozen_ipl_recorded_matches": len(matches),
        "official_matches_without_frozen_ball_data": [r for r in pilot if r["match_id"] is None],
        "expected_team_slots_per_nomination_kind": len(pilot) * 2,
        "coverage": dict(coverage),
        "normalization": dict(counters),
        "competitions": dict(competitions),
        "reviewed_availability_claims": len(config["availability"]),
        "full_season_lineups_verified": coverage["starting_xi_manually_reviewed_team_slots"]
        == len(pilot) * 2,
        "full_season_substitutes_verified": coverage[
            "nominated_substitutes_manually_reviewed_team_slots"
        ]
        == len(pilot) * 2,
        "training_eligible_matches": len(eligible_pilot),
        "eligible_matches_with_complete_source_reviewed_inputs": strict_complete,
        "source_review_method": config.get("nomination_review_method")
        if not args.stage_review
        else "Unreviewed staging build; no inspection approvals applied",
        "human_certification_provided": False,
        "source_review_ledger_sha256": digest(ledger_path)
        if ledger_path.is_file() and not args.stage_review
        else None,
        "readiness_scope": "Nomination-source research coverage only; historical publisher timestamp assumptions apply. Availability, calibration and production validity are not certified.",
        "team_membership_audit_scope": "Retrospective 2025 appearance/franchise consistency checks validate sourced identities; they do not create dated availability features.",
        "eligible_matches_with_complete_source_checked_inputs": source_complete,
        "strict_training_ready": bool(eligible_pilot) and strict_complete == len(eligible_pilot),
        "machine_checked_nomination_file_sha256": digest(machine_path)
        if machine_path.is_file()
        else None,
        "source_database_unchanged_sha256": original_hash,
        "evidence_config_sha256": digest(config_path),
        "pipeline_source_sha256": {
            str(p.relative_to(ROOT)).replace("\\", "/"): digest(p)
            for p in (
                Path(__file__),
                ROOT / "backend/prematch_data.py",
                ROOT / "backend/match_day_inputs.py",
                ROOT / "scripts/discover_matchday_reports.py",
                ROOT / "scripts/check_nomination_sources.py",
                ROOT / "scripts/collect_matchday_pages.py",
                ROOT / "scripts/collect_matchday_recovery.py",
                ROOT / "scripts/collect_public_liveblog_pages.py",
                ROOT / "scripts/collect_cricbuzz_matchday.py",
                ROOT / "scripts/collect_prematch_sources.py",
                ROOT / "scripts/review_nomination_sources.py",
                ROOT / "scripts/check_prematch_pack.py",
            )
        },
        "raw_archives": {p.name: digest(p) for p in archive_paths},
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "limitations": [
            "Only available Cricsheet six-ball scheduled-20-over men's records, not complete global T20 coverage.",
            "Raw match-score publication times are not reconstructed; complete prior-date scores are assumed observable after match completion.",
            "Retained news pages are contemporary retrievals of historical timestamped reports, not immutable snapshots captured at announcement time.",
            "Incomplete nomination slots remain explicitly unverified; reconstructed starters never enter strict nominal lineups. Source inspection was performed by the assistant, not a human certifier.",
            "Date-only availability reports are excluded on publication day; missing information remains unknown.",
            "A complete fixture inventory is not complete verified feature coverage, and this pipeline does not establish 70 percent accuracy.",
        ],
    }
    db.close()
    if digest(settings.database) != original_hash:
        raise AssertionError("Frozen source database changed")
    temporary.replace(PACK / "prematch.sqlite")
    summary["generated_database_sha256"] = digest(PACK / "prematch.sqlite")
    (PACK / "coverage.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (PACK / "lineup_review_queue.json").write_text(
        json.dumps(queue, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ("competitions", "official_matches_without_frozen_ball_data")
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
