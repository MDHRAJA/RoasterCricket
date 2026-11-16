"""Retain older public liveblog updates exposed by the publisher's load-more UI."""

import json
import re
from concurrent.futures import ThreadPoolExecutor

from collect_prematch_sources import PACK, fetch
from discover_matchday_reports import LiveBlogMicrodata


def collect(record):
    html = (PACK / record["relative_path"]).read_text("utf-8")
    parser = LiveBlogMicrodata()
    parser.feed(html)
    settings = re.search(r"var live_blogs_data = (\{[^;]+\});", html)
    if len(parser.objects) < 60 or settings is None:
        return []
    config = json.loads(settings[1])
    # This public client identifier and read-only route come from the retained
    # article and publisher script. No accounts or authoring endpoints are used.
    size = int(config["live_blogs_ajaxcall_one_call_load"])
    start = int(config["start_cmnt_live"])
    post_id = config["post_id_live"]
    if size != 60 or start != 60 or not str(post_id).isdigit():
        raise ValueError("Unrecognized public pagination configuration")
    results = []
    for offset in (60, 120, 180):
        url = (
            "https://commenting.jansatta.com/getlivecommenthlgt/"
            + config["api_key_live"]
            + f"/post/{post_id}/{offset}/{size}/?callbackcom=iplResearch"
        )
        page = fetch(url, f"news/pagination/{post_id}-{offset}.jsonp", kind="jsonp", limit_mb=4)
        page["article_url"] = record["url"]
        page["discovered_via"] = "public_article_load_more_control"
        results.append(page)
        if page["status"] == "unavailable":
            break
        raw = (PACK / page["relative_path"]).read_text("utf-8")
        if not raw.lstrip().startswith("iplResearch("):
            raise ValueError("Unexpected public pagination response")
        payload = json.loads(raw[raw.index("(") + 1 : raw.rfind(")")])
        # Some older archives return a public "no comments" fragment instead
        # of pagination metadata. Retain it, but do not invent more pages.
        if "blog_content_total_count" not in payload:
            page["pagination_status"] = "no_further_page_metadata"
            break
        total = int(payload["blog_content_total_count"])
        if total <= offset + size or not payload.get("comments"):
            break
    return results


def main():
    path = PACK / "source_manifest.json"
    entries = {r["url"]: r for r in json.loads(path.read_text("utf-8"))}
    jobs = [
        r
        for r in entries.values()
        if "indianexpress.com/article/sports/" in r["url"]
        and r.get("kind") == "html"
        and r["status"] != "unavailable"
    ]
    count = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for pages in pool.map(collect, jobs):
            for page in pages:
                entries[page["url"]] = page
                count += 1
            path.write_text(json.dumps(list(entries.values()), indent=2) + "\n", encoding="utf-8")
    print("Retained public older-update pages:", count, flush=True)


if __name__ == "__main__":
    main()
