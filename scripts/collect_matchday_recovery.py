"""Retain explicitly discovered public recovery reports with source provenance."""

import hashlib
import json
from pathlib import Path

from collect_prematch_sources import PACK, fetch

ROOT = Path(__file__).resolve().parents[1]


def main():
    urls = json.loads((ROOT / "research/prematch-2025/recovery_sources.json").read_text("utf-8"))
    path = PACK / "source_manifest.json"
    entries = {r["url"]: r for r in json.loads(path.read_text("utf-8"))}
    for url in urls:
        if entries.get(url, {}).get("status") == "unavailable":
            print("Retaining prior unavailable status", url.split("/")[2], flush=True)
            continue
        result = fetch(
            url, "news/recovery/" + hashlib.sha256(url.encode()).hexdigest()[:20] + ".html"
        )
        result["use_for_nomination_discovery"] = True
        entries[url] = result
        path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
        print(
            result["status"],
            url.split("/")[2],
            result.get("bytes", result.get("error")),
            flush=True,
        )


if __name__ == "__main__":
    main()
