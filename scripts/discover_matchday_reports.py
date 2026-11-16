"""Discover publicly indexed 2025 IPL liveblogs; extract dated claim candidates.

Extracted candidates are NOT silently promoted to reviewed nominations.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_prematch_sources import PACK, fetch  # noqa: E402


class StructuredScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.inside = False
        self.buffer = []
        self.objects = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").startswith("application/ld+json"):
            self.inside = True
            self.buffer = []

    def handle_data(self, data):
        if self.inside:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.inside:
            self.inside = False
            try:
                self.objects.append(json.loads("".join(self.buffer)))
            except ValueError as exc:
                self.errors.append(
                    {
                        "message": str(exc),
                        "sample": "".join(self.buffer)[
                            max(0, getattr(exc, "pos", 0) - 100) : getattr(exc, "pos", 0) + 200
                        ],
                    }
                )


class LiveBlogMicrodata(HTMLParser):
    VOID = {
        "meta",
        "link",
        "img",
        "br",
        "hr",
        "input",
        "source",
        "wbr",
        "area",
        "base",
        "embed",
        "param",
        "track",
        "col",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.current = None
        self.root_depth = None
        self.capture = {}
        self.objects = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("itemprop") == "liveBlogUpdate":
            self.current = {"headline": [], "articleBody": []}
            self.root_depth = len(self.stack)
            self.capture = {}
        if tag not in self.VOID:
            self.stack.append(tag)
        if self.current is not None:
            prop = attrs.get("itemprop")
            if prop in ("datePublished", "dateModified"):
                self.current[prop] = attrs.get("datetime") or attrs.get("content")
            if prop in ("headline", "articleBody"):
                if tag == "meta":
                    self.current[prop] = [attrs.get("content", "")]
                else:
                    self.capture[prop] = len(self.stack)
            if tag in ("p", "br", "div") and "articleBody" in self.capture:
                self.current["articleBody"].append("\n")

    def handle_endtag(self, tag):
        if tag in self.VOID or tag not in self.stack:
            return
        depth = len(self.stack) - self.stack[::-1].index(tag)
        if self.current is not None:
            for key, capture_depth in list(self.capture.items()):
                if depth <= capture_depth:
                    self.capture.pop(key)
            if depth - 1 == self.root_depth:
                obj = dict(self.current)
                obj["headline"] = " ".join(obj["headline"])
                obj["articleBody"] = " ".join(obj["articleBody"])
                self.objects.append(obj)
                self.current = None
        del self.stack[depth - 1 :]

    def handle_data(self, text):
        if self.current is not None and not any(t in ("script", "style") for t in self.stack[-2:]):
            for key in self.capture:
                if key == "headline" and "articleBody" in self.capture:
                    continue
                self.current[key].append(text)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def clean(value):
    if not isinstance(value, str):
        return ""
    return unescape(re.sub(r"<[^>]*>", " ", value or "")).strip()


def public_next_payloads(html):
    """Decode literal public page data, without executing JavaScript."""
    decoder = json.JSONDecoder()
    for marker in re.finditer(r"self\.__next_f\.push\(", html):
        try:
            args, _ = decoder.raw_decode(html, marker.end())
        except ValueError:
            continue
        if not isinstance(args, list) or len(args) < 2 or not isinstance(args[1], str):
            continue
        payload = args[1]
        for line in payload.splitlines():
            prefix, separator, value = line.partition(":")
            if separator and re.fullmatch(r"[a-fA-F0-9]+", prefix):
                try:
                    yield json.loads(value)
                except ValueError:
                    continue


def cricbuzz_candidates(html, url):
    match_id = int(re.search(r"/live-cricket-full-commentary/(\d+)/", url)[1])
    records = []
    for payload in public_next_payloads(html):
        for obj in walk(payload):
            preview = obj.get("matchPreviewFullComm", {})
            if not isinstance(preview, dict) or preview.get("matchId") != match_id:
                continue
            for innings in preview.get("commentary", []):
                if innings.get("inningsId") != 0:
                    continue
                for entry in innings.get("commentaryList", []):
                    body = entry.get("commText", "")
                    if not isinstance(body, str) or not isinstance(entry.get("timestamp"), int):
                        continue
                    for format in entry.get("commentaryFormats", {}).values():
                        for key, value in zip(
                            format.get("formatId", []), format.get("formatValue", []), strict=True
                        ):
                            body = body.replace(key, value)
                    body = clean(body)
                    if not re.search(r"playing\s*xi|impact\s*subs|nominated\s+subs", body, re.I):
                        continue
                    records.append(
                        {
                            "source_url": url,
                            "entry_id": str(entry["timestamp"]),
                            "title": "Publisher prematch commentary: nominated lineups",
                            "published_at": datetime.fromtimestamp(
                                entry["timestamp"] / 1000, timezone.utc
                            ).isoformat(),
                            "modified_at": None,
                            "text": body,
                            "timestamp_basis": "publisher_comment_timestamp_not_immutable_publication_proof",
                            "modification_timestamp_available": False,
                            "status": "timestamped_report_candidate_needs_identity_and_content_review",
                        }
                    )
    return records


def candidates_from_html(html, url):
    if re.match(r"https://www\.cricbuzz\.com/live-cricket-full-commentary/\d+/", url):
        return cricbuzz_candidates(html, url)
    # Public "load more" responses wrap the same entry microdata in JSONP.
    # Parse data only; never execute a publisher callback or JavaScript.
    if html.lstrip().startswith("iplResearch("):
        payload = json.loads(html[html.index("(") + 1 : html.rfind(")")])
        html = payload.get("comments", "")
        if not isinstance(html, str):
            raise ValueError("Unexpected public liveblog pagination payload")
    parser = StructuredScripts()
    parser.feed(html)
    microdata = LiveBlogMicrodata()
    microdata.feed(html)
    records = []
    for obj in parser.objects + microdata.objects:
        for entry in walk(obj):
            title = clean(entry.get("headline") or entry.get("name") or "")
            body = clean(entry.get("articleBody") or entry.get("text") or "")
            if not entry.get("datePublished") or not (
                re.search(
                    r"playing\s*xi|playing\s*11|impact\s*(?:sub|player)|substitutes|\bsubs\b|\bXIs?\b|\bteams\b|lineups?",
                    title,
                    re.I,
                )
                or re.search(
                    r"playing\s*xis?|playing\s*11|impact\s*(?:subs|players)|\bXI\s*:", body, re.I
                )
            ):
                continue
            if re.search(r"predict|probable|dream11", title, re.I):
                continue
            records.append(
                {
                    "source_url": url,
                    "entry_id": entry.get("@id"),
                    "title": title,
                    "published_at": entry["datePublished"],
                    "modified_at": entry.get("dateModified"),
                    "text": body,
                    "status": "timestamped_report_candidate_needs_identity_and_content_review",
                }
            )
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-only", action="store_true")
    args = parser.parse_args()
    manifest_path = PACK / "source_manifest.json"
    entries = {r["url"]: r for r in json.loads(manifest_path.read_text("utf-8"))}
    if args.cached_only:
        extracted = []
        for url, record in entries.items():
            if (
                (
                    "indianexpress.com/article/sports/" in url
                    or record.get("article_url")
                    or record.get("use_for_nomination_discovery")
                )
                and record["status"] != "unavailable"
                and record.get("kind") in ("html", "jsonp")
            ):
                extracted.extend(
                    candidates_from_html((PACK / record["relative_path"]).read_text("utf-8"), url)
                )
        (PACK / "lineup_source_candidates.json").write_text(
            json.dumps(extracted, indent=2) + "\n", encoding="utf-8"
        )
        print("Reparsed cached dated candidates:", len(extracted), flush=True)
        return
    fixtures = json.loads((PACK / "official_fixtures.json").read_text("utf-8"))
    days = sorted({c["startDateTimeUtc"][:10] for c in fixtures})
    jobs = []
    for day in days:
        year, month, day_number = day.split("-")
        url = "https://indianexpress.com/sitemap.xml?" + urllib.parse.urlencode(
            {"yyyy": year, "mm": month, "dd": day_number}
        )
        jobs.append((url, f"news/sitemaps/{day}.xml"))
    urls = set()
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(lambda item: fetch(*item, kind="xml"), jobs):
            entries[result["url"]] = result
            if result["status"] == "unavailable":
                continue
            try:
                root = ET.fromstring((PACK / result["relative_path"]).read_bytes())
            except ET.ParseError:
                continue
            for location in root.findall(".//{*}loc"):
                url = location.text or ""
                slug = url.rstrip("/").rsplit("/", 1)[-1]
                if "/article/sports/" in url and "live" in slug and "ipl" in slug:
                    urls.add(url)
    if len(urls) > 240:
        raise ValueError("Discovery exceeded the declared 240-article research bound")
    print("Dated sitemaps:", len(days), "candidate liveblogs:", len(urls), flush=True)
    candidates = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index, result in enumerate(
            pool.map(
                lambda url: fetch(
                    url, f"news/{hashlib.sha256(url.encode()).hexdigest()[:20]}.html", limit_mb=4
                ),
                sorted(urls),
            ),
            1,
        ):
            entries[result["url"]] = result
            if result["status"] != "unavailable":
                candidates.extend(
                    candidates_from_html(
                        (PACK / result["relative_path"]).read_text("utf-8"), result["url"]
                    )
                )
            if index % 20 == 0:
                print(
                    "Read",
                    index,
                    "articles; extracted",
                    len(candidates),
                    "dated candidates",
                    flush=True,
                )
    manifest_path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
    (PACK / "lineup_source_candidates.json").write_text(
        json.dumps(candidates, indent=2) + "\n", encoding="utf-8"
    )
    print("Dated nomination candidates:", len(candidates), flush=True)


if __name__ == "__main__":
    main()
