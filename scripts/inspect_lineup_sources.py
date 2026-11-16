"""Inspect only public IPL page/script references; no private feed credentials."""

import json
import re
import urllib.parse
import urllib.request

URL = "https://www.iplt20.com/matches/21da6f47-8d35-4afa-ac54-0a950de18ec4/kolkata-knight-riders-vs-royal-challengers-bengaluru/squads"


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "IPLResearchDataset/0.2"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def main():
    html = get(URL)
    scripts = re.findall(r'<script[^>]*src="([^"]+)', html)
    print("Public page scripts:", scripts)
    for src in scripts:
        text = get(urllib.parse.urljoin(URL, src))
        patterns = re.findall(
            r".{0,80}(?:api/bff|/feed/|/squads|playingXI|playingXi|playing_xi).{0,130}", text
        )
        for pattern in patterns[:30]:
            print(src, pattern)
    docs = get("https://bff.bcci.tv/scalar")
    start = docs.index('"content":') + len('"content":')
    spec, _ = json.JSONDecoder().raw_decode(docs[start:].lstrip())
    for path, methods in spec["paths"].items():
        if "/feed/" in path and any(word in path for word in ("match", "competition")):
            print(
                "FEED PATH",
                path,
                json.dumps(
                    {
                        method: {
                            "description": d.get("description"),
                            "parameters": d.get("parameters"),
                        }
                        for method, d in methods.items()
                    }
                )[:3000],
            )


if __name__ == "__main__":
    main()
