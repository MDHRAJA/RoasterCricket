"""Follow public archive pagination links for the explicitly selected TOI reports."""

import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

from collect_prematch_sources import PACK, fetch


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("a", "link") and "curpg=" in attrs.get("href", ""):
            self.urls.append(attrs["href"])


def archive_links(html, article_url):
    parser = PageLinks()
    parser.feed(html)
    post_id = article_url.split(".cms")[0].rsplit("/", 1)[-1]
    urls = set()
    for href in parser.urls:
        url = urljoin(article_url, href)
        parsed = urlparse(url)
        page = parse_qs(parsed.query).get("curpg", [""])[0]
        if (
            parsed.scheme == "https"
            and parsed.netloc == "timesofindia.indiatimes.com"
            and re.search(r"/(?:amp_)?liveblog/" + re.escape(post_id) + r"\.cms$", parsed.path)
            and page.isdigit()
            and 1 <= int(page) <= 12
        ):
            urls.add(url)
    return sorted(urls)


def main():
    path = PACK / "source_manifest.json"
    entries = {r["url"]: r for r in json.loads(path.read_text("utf-8"))}
    roots = [
        r
        for r in entries.values()
        if r.get("use_for_nomination_discovery")
        and "timesofindia.indiatimes.com" in r["url"]
        and not r.get("article_url")
        and r["status"] != "unavailable"
    ]
    count = 0
    for root in roots:
        article_url = root["url"]
        queue = archive_links((PACK / root["relative_path"]).read_text("utf-8"), article_url)
        seen = {article_url}
        post_id = article_url.split(".cms")[0].rsplit("/", 1)[-1]
        while queue:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if len(seen) > 14:
                raise ValueError("Archive pagination exceeded the declared bound")
            page = parse_qs(urlparse(url).query)["curpg"][0]
            record = fetch(url, f"news/pagination/toi-{post_id}-{page}.html", limit_mb=4)
            record["article_url"] = article_url
            record["use_for_nomination_discovery"] = True
            entries[url] = record
            count += 1
            if record["status"] != "unavailable":
                html = (PACK / record["relative_path"]).read_text("utf-8")
                queue.extend(u for u in archive_links(html, article_url) if u not in seen)
            path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
        print("Reviewed public archive pages:", post_id, len(seen) - 1, flush=True)
    print("Retained pagination pages:", count, flush=True)


if __name__ == "__main__":
    main()
