"""Cache attributable public sources in a NEW pack, never refresh the frozen IPL DB."""

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "outputs/prematch-2025"


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fetch(
    url,
    relative,
    *,
    kind="html",
    limit_mb=8,
    license_note="Publisher terms apply; research snapshot",
):
    target = PACK / "raw" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "source_id": hashlib.sha256(url.encode()).hexdigest()[:20],
        "url": url,
        "relative_path": str(target.relative_to(PACK)).replace("\\", "/"),
        "kind": kind,
        "license_note": license_note,
    }
    if target.is_file():
        record.update(
            status="cached",
            sha256=digest(target),
            bytes=target.stat().st_size,
            retrieved_at=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
        )
        return record
    temporary = target.with_suffix(target.suffix + ".partial")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "IPLResearchDataset/0.3", "Accept-Language": "en-US"}
        )
        with (
            urllib.request.urlopen(request, timeout=30) as response,
            temporary.open("wb") as handle,
        ):
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > limit_mb * 1024 * 1024:
                    raise ValueError("Source exceeded declared size limit")
                handle.write(chunk)
            record.update(
                http_status=response.status,
                content_type=response.headers.get("Content-Type"),
                last_modified=response.headers.get("Last-Modified"),
            )
        with temporary.open("rb") as handle:
            prefix = handle.read(8)
        if kind == "zip" and not prefix.startswith(b"PK"):
            raise ValueError("Archive source returned non-ZIP content")
        if kind == "json":
            json.loads(temporary.read_text("utf-8"))
        temporary.replace(target)
        record.update(
            status="downloaded",
            sha256=digest(target),
            bytes=target.stat().st_size,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        record.update(
            status="unavailable",
            error=str(exc),
            attempted_at=datetime.now(timezone.utc).isoformat(),
        )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-male", action="store_true")
    parser.add_argument("--probe-ipl", action="store_true")
    parser.add_argument("--ipl-season", action="store_true")
    parser.add_argument("--claims", action="store_true")
    parser.add_argument("--identities", action="store_true")
    parser.add_argument("--discover-news", action="store_true")
    args = parser.parse_args()
    PACK.mkdir(parents=True, exist_ok=True)
    manifest_path = PACK / "source_manifest.json"
    previous = json.loads(manifest_path.read_text("utf-8")) if manifest_path.is_file() else []
    entries = {r["url"]: r for r in previous}
    sources = [
        (
            "https://cricsheet.org/downloads/",
            "cricsheet/downloads.html",
            "html",
            8,
            "Cricsheet reference snapshot",
        ),
        (
            "https://cricsheet.org/licensing/",
            "cricsheet/licensing.html",
            "html",
            8,
            "Cricsheet reference snapshot",
        ),
    ]
    if args.all_male:
        sources += [
            (
                "https://cricsheet.org/downloads/all_male_json.zip",
                "cricsheet/all_male_json.zip",
                "zip",
                256,
                "Cricsheet; Open Data Commons Attribution 1.0; retain bundled notices",
            )
        ]
    if args.identities:
        sources += [
            (
                f"https://cricsheet.org/register/{name}.csv",
                f"cricsheet/{name}.csv",
                "csv",
                8,
                "Cricsheet register identity cross-reference; retain attribution",
            )
            for name in ("people", "names")
        ]
    if args.probe_ipl:
        sources += [
            (
                "https://www.iplt20.com/api/bff/feed/v1/matches/list?status=results&season=2025&page=1",
                "ipl/results-2025-1.json",
                "json",
                8,
                "Official IPL public same-origin match feed; publisher terms apply",
            ),
            (
                "https://www.iplt20.com/api/bff/feed/v1/matches/21da6f47-8d35-4afa-ac54-0a950de18ec4/scorecard",
                "ipl/first-match-scorecard-2025.json",
                "json",
                8,
                "Official IPL public same-origin match feed; publisher terms apply",
            ),
        ]
    for url, relative, kind, size, license_note in sources:
        started = time.monotonic()
        result = fetch(url, relative, kind=kind, limit_mb=size, license_note=license_note)
        entries[url] = result
        manifest_path.write_text(
            json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8"
        )
        print(
            result["status"],
            relative,
            result.get("bytes", result.get("error")),
            f"{time.monotonic() - started:.1f}s",
            flush=True,
        )
    if args.ipl_season:
        cards = []
        for page in range(1, 11):
            url = f"https://www.iplt20.com/api/bff/feed/v1/matches/list?status=results&season=2025&page={page}"
            result = fetch(url, f"ipl/results-2025-{page}.json", kind="json")
            entries[url] = result
            if result["status"] == "unavailable":
                break
            payload = json.loads((PACK / result["relative_path"]).read_text("utf-8"))["data"]
            cards.extend(payload["matches"])
            if not payload["meta"]["hasMore"]:
                break
        by_gid = {c["gid"]: c for c in cards}
        (PACK / "official_fixtures.json").write_text(
            json.dumps(list(by_gid.values()), indent=2) + "\n", encoding="utf-8"
        )
        jobs = [
            (
                f"https://www.iplt20.com/api/bff/feed/v1/matches/{gid}/scorecard",
                f"ipl/scorecards/{gid}.json",
            )
            for gid in by_gid
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in pool.map(lambda item: fetch(*item, kind="json"), jobs):
                entries[result["url"]] = result
        print("Official season cards:", len(by_gid), flush=True)
    if args.claims or args.identities:
        config = json.loads((ROOT / "research/prematch-2025/evidence.json").read_text("utf-8"))
        categories = []
        if args.claims:
            categories += ["availability", "nominations", "reviewed_punctuation_nominations"]
        if args.identities:
            categories += ["additional_players"]
        urls = sorted({r["source_url"] for key in categories for r in config.get(key, [])})

        def retain_known_source(url):
            previous = entries.get(url, {})
            relative = previous.get(
                "relative_path",
                "raw/news/" + hashlib.sha256(url.encode()).hexdigest()[:20] + ".html",
            )
            result = fetch(
                url, str(Path(relative).relative_to("raw")), kind=previous.get("kind", "html")
            )
            return previous | result

        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in pool.map(retain_known_source, urls):
                entries[result["url"]] = result
    if args.discover_news:
        result = fetch("https://indianexpress.com/sitemap.xml", "news/sitemap.xml", kind="xml")
        entries[result["url"]] = result
    manifest_path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
    if any(r["status"] == "unavailable" for r in entries.values()):
        print("Some sources are unavailable; gaps remain explicit, not inferred.", flush=True)


if __name__ == "__main__":
    main()
