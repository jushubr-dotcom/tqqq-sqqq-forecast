"""Scrape YouTube search results for 'boring' / 'unsexy' and passive side hustles.

Uses YouTube's public InnerTube API (youtubei.googleapis.com), so no API key or
browser is needed. For every search query it pages through results, then pulls
each video's full description and chapter markers (which usually name the
individual side hustles covered). Transcripts are not fetched.

Output: side_hustles/data/videos.json
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://youtubei.googleapis.com/youtubei/v1/"
CONTEXT = {"client": {"clientName": "WEB", "clientVersion": "2.20250101.00.00", "hl": "en", "gl": "US"}}
OUT = Path(__file__).parent / "data" / "videos.json"

# Two query families: "unattractive" (boring/dirty/unsexy) and "passive".
QUERIES = {
    "unattractive": [
        "boring side hustles",
        "boring businesses that make money",
        "unsexy side hustles",
        "unsexy businesses",
        "ugly side hustles nobody wants",
        "dirty jobs side hustle",
        "gross side hustles that pay well",
        "boring businesses nobody wants to start",
        "unglamorous side hustles",
        "side hustles nobody talks about",
        "blue collar side hustles",
        "boring passive income businesses",
    ],
    "passive": [
        "most passive side hustles",
        "truly passive income ideas",
        "passive income ideas that actually work",
        "hands off side hustles",
        "passive side hustles with little work",
        "lazy side hustles",
        "set and forget side hustle",
        "passive income businesses you can automate",
        "boring passive income",
        "passive income for introverts",
    ],
}
PAGES_PER_QUERY = 3


def post(endpoint, payload, retries=3):
    for i in range(retries):
        try:
            r = requests.post(API + endpoint + "?prettyPrint=false",
                              json={"context": CONTEXT, **payload}, timeout=30)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    return {}


def walk(obj, key):
    """Yield every value stored under `key` anywhere in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, key)


def text(node):
    if not node:
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    return "".join(r.get("text", "") for r in node.get("runs", []))


def parse_views(s):
    m = re.search(r"([\d,.]+)\s*([KMB]?)", s or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])


def search(query):
    videos, data = [], post("search", {"query": query})
    for _ in range(PAGES_PER_QUERY):
        for v in walk(data, "videoRenderer"):
            videos.append({
                "video_id": v["videoId"],
                "title": text(v.get("title")),
                "channel": text(v.get("ownerText")),
                "views": parse_views(text(v.get("viewCountText"))),
                "published": text(v.get("publishedTimeText")),
                "length": text(v.get("lengthText")),
            })
        tokens = [c["continuationCommand"]["token"] for c in walk(data, "continuationEndpoint")
                  if "continuationCommand" in c]
        if not tokens:
            break
        data = post("search", {"continuation": tokens[0]})
    return videos


def details(video_id):
    """Full description + chapter titles from the watch-page (`next`) endpoint.

    (`player` is bot-gated for anonymous clients, `next` is not.)
    """
    data = post("next", {"videoId": video_id})
    desc = next((d.get("content", "") for d in walk(data, "attributedDescription")), "")
    chapters = []
    for m in walk(data, "macroMarkersListItemRenderer"):
        t = text(m.get("title"))
        if t and t not in chapters:
            chapters.append(t)
    for c in walk(data, "chapterRenderer"):
        t = text(c.get("title"))
        if t and t not in chapters:
            chapters.append(t)
    return {"description": desc, "chapters": chapters}


def main():
    videos = {}
    for family, queries in QUERIES.items():
        for q in queries:
            found = search(q)
            print(f"[{family}] {q!r}: {len(found)} videos", file=sys.stderr)
            for v in found:
                rec = videos.setdefault(v["video_id"], {**v, "queries": [], "families": []})
                rec["queries"].append(q)
                if family not in rec["families"]:
                    rec["families"].append(family)

    ids = list(videos)
    with ThreadPoolExecutor(8) as ex:
        for vid, d in zip(ids, ex.map(details, ids)):
            videos[vid].update(d)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(list(videos.values()), indent=1, ensure_ascii=False))
    print(f"Saved {len(videos)} unique videos -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
