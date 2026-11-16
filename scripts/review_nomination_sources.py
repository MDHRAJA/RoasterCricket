"""Prepare readable source packets and record explicit assistant inspection decisions.

Preparing or displaying a packet never promotes a nomination. Recording requires
an explicit list of fixture IDs already inspected by the reviewer.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone

from build_prematch_pack import PACK, ROOT, digest, nomination_review_digest, normalize
from discover_matchday_reports import candidates_from_html

LEDGER = ROOT / "research/prematch-2025/source_review_ledger.json"


def prepare():
    sources = {r["url"]: r for r in json.loads((PACK / "source_manifest.json").read_text("utf-8"))}
    machine = json.loads((PACK / "source_checked_nominations.json").read_text("utf-8"))[
        "nominations"
    ]
    by_key = {(r["match_id"], r["team_id"], r["kind"]): r for r in machine}
    db = sqlite3.connect((PACK / "prematch.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    packets, cache = [], {}
    for match in db.execute("SELECT * FROM pilot_matches ORDER BY match_date,pilot_match_id"):
        rows = list(
            db.execute(
                "SELECT * FROM nominations WHERE pilot_match_id=? ORDER BY team_id,kind",
                (match["pilot_match_id"],),
            )
        )
        if len(rows) != 4 or any(not json.loads(r["player_ids_json"]) for r in rows):
            continue
        inspected, entries = [], {}
        for row in rows:
            record = by_key.get(
                (match["match_id"], row["team_id"], row["kind"]), json.loads(row["evidence_json"])
            )
            source = sources[record["source_url"]]
            path = PACK / source["relative_path"]
            if digest(path) != source["sha256"]:
                raise ValueError("Review source digest changed")
            if record["source_url"] not in cache:
                cache[record["source_url"]] = candidates_from_html(
                    path.read_text("utf-8"), record["source_url"]
                )
            compatible = [
                e
                for e in cache[record["source_url"]]
                if e["published_at"] == record["published_at"]
                and all(normalize(n) in normalize(e["text"]) for n in record["names"])
            ]
            if not compatible:
                raise ValueError("Reviewed list has no exact retained entry")
            entry = compatible[0]
            entries[(record["source_url"], record["published_at"])] = {
                "source_id": source["source_id"],
                "published_at": entry["published_at"],
                "title": entry["title"],
                "modified_at": entry.get("modified_at"),
                "text": entry["text"],
                "timestamp_basis": entry.get("timestamp_basis", "publisher_declared_datePublished"),
            }
            inspected.append(
                {
                    "match_id": record["match_id"],
                    "team_id": record["team_id"],
                    "kind": record["kind"],
                    "record_sha256": nomination_review_digest(record),
                    "source_sha256": source["sha256"],
                    "source_url": record["source_url"],
                }
            )
        packets.append(
            {
                "match_id": match["match_id"],
                "date": match["match_date"],
                "cutoff_at": match["start_at"],
                "teams": [match["team1_id"], match["team2_id"]],
                "entries": list(entries.values()),
                "review_records": inspected,
            }
        )
    db.close()
    result = {
        "schema": "assistant-nomination-source-inspection-v1",
        "machine_file_sha256": digest(PACK / "source_checked_nominations.json"),
        "fixtures": packets,
    }
    (PACK / "source_review_packet.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print("Prepared source packets:", len(packets))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--size", type=int, default=18)
    parser.add_argument(
        "--record-inspected", help="Comma-separated fixture IDs explicitly inspected in this review"
    )
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.batch is None and not args.record_inspected:
        return
    packet_path = PACK / "source_review_packet.json"
    packet = json.loads(packet_path.read_text("utf-8"))
    if packet["machine_file_sha256"] != digest(PACK / "source_checked_nominations.json"):
        raise ValueError("Source packet is stale; inspect a newly prepared packet")
    if args.batch is not None:
        if args.batch < 0 or not 1 <= args.size <= 24:
            raise ValueError("Invalid review batch bounds")
        for fixture in packet["fixtures"][args.batch * args.size : (args.batch + 1) * args.size]:
            print(
                f"\n{fixture['match_id']} {fixture['date']} {'/'.join(fixture['teams'])} cutoff={fixture['cutoff_at']}"
            )
            for entry in fixture["entries"]:
                print(
                    f"source={entry['source_id']} time={entry['published_at']} edit={entry['modified_at']} basis={entry['timestamp_basis']}"
                )
                print(entry["title"])
                print(entry["text"])
        return
    requested = set(args.record_inspected.split(","))
    known = {f["match_id"]: f for f in packet["fixtures"]}
    if not requested or not requested <= known.keys():
        raise ValueError("Explicit reviewed fixture IDs do not match the prepared packet")
    ledger = (
        json.loads(LEDGER.read_text("utf-8"))
        if LEDGER.is_file()
        else {"schema": packet["schema"], "reviews": []}
    )
    reviews = {(r["match_id"], r["team_id"], r["kind"]): r for r in ledger["reviews"]}
    sources = {r["url"]: r for r in json.loads((PACK / "source_manifest.json").read_text("utf-8"))}
    for mid in sorted(requested):
        for record in known[mid]["review_records"]:
            if (
                digest(PACK / sources[record["source_url"]]["relative_path"])
                != record["source_sha256"]
            ):
                raise ValueError("Inspected source changed before recording the review")
            reviews[(mid, record["team_id"], record["kind"])] = record | {
                "reviewer": "assistant",
                "method": "direct_source_packet_inspection",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "review_packet_sha256": digest(packet_path),
                "human_certification": False,
                "scope": "Names, explicit nomination wording, fixture context and declared prestart timestamps inspected; no immutable publication or hidden edit history claimed.",
            }
    ledger["reviews"] = list(reviews.values())
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(
        "Recorded explicitly inspected fixtures:",
        len(requested),
        "total list reviews:",
        len(reviews),
    )


if __name__ == "__main__":
    main()
