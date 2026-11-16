"""Cross-check dated report candidates; retain every unresolved/conflicting claim."""

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_prematch_pack import PACK, normalize, read_inputs  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.prematch_data import team_membership_conflicts  # noqa: E402


def names_in_list(text):
    # Captain/keeper/change notes can themselves contain commas or "and".
    # Remove complete annotations before splitting player delimiters.
    text = re.sub(r"\([^)]*\)|\*|†", "", text)
    text = re.sub(r",\s+and\s+", ",", text, flags=re.I)
    return [name.strip().rstrip(".") for name in re.split(r",|\s+and\s+", text.strip())]


def without_projected_choices(text, team_names):
    headers = "|".join(re.escape(n) for n in sorted(team_names, key=len, reverse=True))
    separated = re.sub(
        r"((?:" + headers + r")\s+(?:(?:Playing|first)\s+)?XI\s*:)",
        r"\n\1",
        text,
        flags=re.I,
    )
    return re.sub(
        r"(?i)(?:possible|likely)\s+impact(?:\s+(?:sub|player))?\s*:[^\n]*",
        "",
        separated,
    )


def segments(candidate, team_names):
    # Full names can follow a lost HTML paragraph boundary; short codes still
    # require a word boundary. Colon/role labels prevent player-name collisions.
    names = sorted(team_names, key=len, reverse=True)
    alternatives = "|".join((r"\b" if len(n) <= 4 else "") + re.escape(n) for n in names)
    expression = re.compile(
        r"(?P<team>"
        + alternatives
        + r")\s*(?P<role>\((?:Unchanged\s+)?(?:Playing\s*)?XI\)|(?:(?:Playing|first)\s*)?XIs?|(?:Impact\s*)?Subs?(?:titutes)?(?:\s*options)?|Bench)?\s*(?::|[-–—])",
        re.I,
    )
    text = candidate["text"]
    text = re.sub(
        r"(?i)Impact\s+(?:players|subs(?:titutes)?)\s+(?:of|for|nominated\s+by)\s+("
        + alternatives
        + r")\s*[-–—:]",
        r"\1 Impact Subs:",
        text,
    )
    text = re.sub(
        r"(?i)Impact\s+subs\s+nominated\s+by\s+(" + alternatives + r")\s*[-–—:]",
        r"\1 Impact Subs:",
        text,
    )
    short_codes = "|".join(re.escape(n) for n in names if len(n) <= 4)
    text = re.sub(
        r"(?<!\s)(" + short_codes + r")\s+((?:first|Playing)\s+XI\s*:)",
        r"\n\1 \2",
        text,
    )
    # A team header may be followed by two separately labelled lists.
    # Preserve that explicit structure rather than classifying the whole entry
    # as substitutes merely because its headline mentions both categories.
    text = re.sub(
        r"(?i)(?<!\w)((?:Impact\s*)?Subs?(?:titutes)?(?:\s*options)?)\s*:",
        r"\n\1:",
        text,
    )
    markers = list(expression.finditer(text))
    if not markers:
        header = candidate["title"].rsplit(":", 1)[-1]
        named_teams = {
            team_names[name]
            for name in names
            if re.search(r"\b" + re.escape(name) + r"\b", header, re.I)
        }
        if len(named_teams) == 1 and re.search(r"playing\s*xi|\bXI\b|sub|bench", header, re.I):
            kind = (
                "nominated_substitutes" if re.search("sub|bench", header, re.I) else "starting_xi"
            )
            listed = names_in_list(text)
            yield next(iter(named_teams)), kind, listed
        return
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        label = marker.group("team")
        team = next(team_names[n] for n in names if n.lower() == label.lower())
        role = marker.group("role") or candidate["title"]
        content = text[marker.end() : end].strip().rstrip(".; ")
        if not content:
            continue  # Repeated adjacent team labels do not create empty lists.
        split = re.split(r"(?i)\b(?:Impact\s*)?Subs?(?:titutes)?(?:\s*options)?\s*:", content)
        if len(split) == 2:
            for kind, part in zip(("starting_xi", "nominated_substitutes"), split, strict=True):
                yield team, kind, names_in_list(part)
            continue
        kind = "nominated_substitutes" if re.search("sub|bench", role, re.I) else "starting_xi"
        names_in_report = names_in_list(content)
        yield team, kind, names_in_report


def main():
    matches, originals, aliases, player_ids, team_names, memberships = read_inputs(
        Settings.from_env()
    )
    team_names.update({code: code for code in set(team_names.values())})
    team_names.update(
        {
            "Chennai": "CSK",
            "Delhi": "DC",
            "Gujarat": "GT",
            "Kolkata": "KKR",
            "Lucknow": "LSG",
            "Mumbai": "MI",
            "Punjab": "PBKS",
            "Rajasthan": "RR",
            "Bengaluru": "RCB",
            "Bangalore": "RCB",
            "Hyderabad": "SRH",
        }
    )
    config = json.loads((ROOT / "research/prematch-2025/evidence.json").read_text("utf-8"))
    for name, pid in config["reviewed_identity_mappings"].items():
        aliases[normalize(name)] = {pid}
    fixtures = json.loads((PACK / "official_fixtures.json").read_text("utf-8"))
    candidates = json.loads((PACK / "lineup_source_candidates.json").read_text("utf-8"))
    local = {
        (r["match_date"], frozenset((r["team1_id"], r["team2_id"]))): r["match_id"] for r in matches
    }
    by_day = defaultdict(list)
    for fixture in fixtures:
        by_day[fixture["startDateTimeUtc"][:10]].append(fixture)
    checked, unresolved = [], []
    for candidate in candidates:
        # A confirmed XI report may separately predict the later Impact choice.
        # Exclude that explicitly labelled prediction, never use it as a list.
        segment_candidate = {
            **candidate,
            "text": without_projected_choices(candidate["text"], team_names),
        }
        if re.search(
            r"predict|probable|likely|expected|dream11",
            candidate["title"] + " " + segment_candidate["text"],
            re.I,
        ):
            unresolved.append({**candidate, "reason": "not_an_unqualified_nomination_report"})
            continue
        stamp = datetime.fromisoformat(candidate["published_at"].replace("Z", "+00:00"))
        for team, kind, names in segments(segment_candidate, team_names):
            options = [
                f
                for f in by_day[stamp.date().isoformat()]
                if team in {t["abbreviation"] for t in f["teams"]}
            ]
            if len(options) != 1:
                unresolved.append(
                    {
                        **candidate,
                        "team_id": team,
                        "kind": kind,
                        "reason": "ambiguous_fixture_context",
                    }
                )
                continue
            fixture = options[0]
            cutoff = datetime.fromisoformat(fixture["startDateTimeUtc"].replace("Z", "+00:00"))
            modified = (
                datetime.fromisoformat(candidate["modified_at"].replace("Z", "+00:00"))
                if candidate.get("modified_at")
                else stamp
            )
            if (
                stamp.tzinfo is None
                or modified.tzinfo is None
                or not cutoff - timedelta(hours=1) <= stamp < cutoff
                or modified >= cutoff
            ):
                unresolved.append(
                    {
                        **candidate,
                        "team_id": team,
                        "kind": kind,
                        "reason": "declared_timestamps_outside_prestart_window",
                    }
                )
                continue
            teams = frozenset(t["abbreviation"] for t in fixture["teams"])
            mid = local.get((fixture["startDateTimeUtc"][:10], teams))
            identifiers, failures = [], []
            for name in names:
                found = aliases[normalize(name)]
                if len(found) != 1:
                    failures.append(name)
                else:
                    identifiers.append(next(iter(found)))
            required = 11 if kind == "starting_xi" else 5
            reason = ""
            if failures:
                reason = "unresolved_or_ambiguous_player_identities"
            elif len(identifiers) != required or len(set(identifiers)) != required:
                reason = "not_a_complete_unique_nomination_list"
            elif team_membership_conflicts(identifiers, team, memberships):
                reason = "reported_player_team_membership_conflict"
            elif kind == "starting_xi" and (
                not mid or set(identifiers) != set(originals[mid][team])
            ):
                reason = "reported_xi_does_not_match_independent_original_starter_record"
            elif kind == "nominated_substitutes" and (
                not mid or set(identifiers) & set(originals[mid][team])
            ):
                reason = "substitute_list_overlaps_original_starters_or_no_independent_context"
            if reason:
                unresolved.append(
                    {
                        **candidate,
                        "team_id": team,
                        "kind": kind,
                        "names": names,
                        "unresolved_names": failures,
                        "reason": reason,
                    }
                )
                continue
            checked.append(
                {
                    "match_id": mid,
                    "official_gid": fixture["gid"],
                    "team_id": team,
                    "kind": kind,
                    "status": "timestamped_report_machine_checked",
                    "published_at": candidate["published_at"],
                    "modified_at": candidate.get("modified_at"),
                    "timestamp_basis": candidate.get(
                        "timestamp_basis", "publisher_declared_datePublished"
                    ),
                    "modification_timestamp_available": bool(candidate.get("modified_at")),
                    "player_ids": sorted(identifiers),
                    "names": names,
                    "source_url": candidate["source_url"],
                    "source_locator": candidate["title"],
                    "checks": {
                        "known_unique_identities": True,
                        "complete_membership": True,
                        "no_known_team_membership_conflict": True,
                        "independent_fixture_match": True,
                        "original_starter_agreement_or_substitute_disjointness": True,
                        "declared_timestamps_before_scheduled_start": True,
                        "published_within_declared_one_hour_window": True,
                    },
                    "historical_snapshot_at_publication_available": False,
                    "verification_scope": "publisher_report_timestamp_and_content_cross_checks_not_official_team_sheet_or_immutable_publication_proof",
                }
            )
    grouped = defaultdict(list)
    for record in checked:
        grouped[record["match_id"], record["team_id"], record["kind"]].append(record)
    accepted = []
    for records in grouped.values():
        if len({tuple(r["player_ids"]) for r in records}) != 1:
            unresolved.extend({**r, "reason": "conflicting_reported_nominations"} for r in records)
            continue
        accepted.append(
            min(
                records,
                key=lambda r: datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")),
            )
        )
    report = {
        "status": "machine_cross_checked_reports_not_human_certified_team_sheets",
        "nominations": accepted,
        "counts": dict(Counter(r["kind"] for r in accepted)),
        "unresolved": unresolved,
        "candidate_file_sha256": hashlib.sha256(
            (PACK / "lineup_source_candidates.json").read_bytes()
        ).hexdigest(),
        "policy": "Known unique identities; complete 11/5 lists; independent fixture and original-starter/disjointness match; publisher-declared entry timestamp and any declared modification before scheduled start, within one-hour prestart window; no predicted lists; conflicts withheld. Absence of a modification timestamp is recorded, never proof that an entry was not edited.",
    }
    (PACK / "source_checked_nominations.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("nominations", "unresolved")}, indent=2
        )
    )
    print("Unresolved records:", len(unresolved))


if __name__ == "__main__":
    main()
