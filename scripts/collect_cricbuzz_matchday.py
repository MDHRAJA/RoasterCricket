"""Collect public prematch commentary for fixtures still missing nomination evidence."""

import hashlib
import json
import re
from datetime import datetime, timezone

from collect_prematch_sources import PACK, fetch
from discover_matchday_reports import public_next_payloads, walk

INDEX = "https://www.cricbuzz.com/cricket-series/9237/indian-premier-league-2025/matches"


def main():
    path = PACK / "source_manifest.json"
    entries = {r["url"]: r for r in json.loads(path.read_text("utf-8"))}
    index = fetch(INDEX, "news/cricbuzz-season-2025.html")
    entries[INDEX] = index
    if index["status"] == "unavailable":
        path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
        raise SystemExit("Public season index unavailable; no replacement fixture mapping inferred")
    fixtures = json.loads((PACK / "official_fixtures.json").read_text("utf-8"))
    accepted = json.loads((PACK / "source_checked_nominations.json").read_text("utf-8"))[
        "nominations"
    ]
    covered = {(r["official_gid"], r["team_id"], r["kind"]) for r in accepted}
    needed = {
        (f["startDateTimeUtc"][:10], frozenset(t["abbreviation"] for t in f["teams"]))
        for f in fixtures
        if any(
            (f["gid"], t["abbreviation"], k) not in covered
            for t in f["teams"]
            for k in ("starting_xi", "nominated_substitutes")
        )
    }
    mapped = {}
    for payload in public_next_payloads((PACK / index["relative_path"]).read_text("utf-8")):
        for obj in walk(payload):
            info = obj.get("matchInfo", {})
            if not isinstance(info, dict) or not info.get("matchId") or not info.get("startDate"):
                continue
            teams = frozenset(
                info.get(key, {}).get("teamSName", "").upper() for key in ("team1", "team2")
            )
            day = (
                datetime.fromtimestamp(int(info["startDate"]) / 1000, timezone.utc)
                .date()
                .isoformat()
            )
            if (day, teams) in needed:
                mapped[info["matchId"]] = info
    if not mapped:
        raise ValueError("Season index did not expose the expected dated fixture mapping")
    for mid, info in mapped.items():
        first = info["team1"]["teamSName"].lower()
        second = info["team2"]["teamSName"].lower()
        # Use the public route pattern observed on the retained report. IDs,
        # dates and teams come from this index, never guessed from outcomes.
        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{first}-vs-{second}-{info['matchDesc']}-indian-premier-league-2025".lower(),
        ).strip("-")
        url = f"https://www.cricbuzz.com/live-cricket-full-commentary/{mid}/{slug}"
        result = fetch(
            url, "news/recovery/" + hashlib.sha256(url.encode()).hexdigest()[:20] + ".html"
        )
        result["use_for_nomination_discovery"] = True
        result["fixture_mapping_basis"] = {
            "index_source_url": INDEX,
            "match_id": mid,
            "start_date": info["startDate"],
            "teams": [first, second],
        }
        entries[url] = result
        path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
        print("Public prematch report", mid, result["status"], flush=True)


if __name__ == "__main__":
    main()
