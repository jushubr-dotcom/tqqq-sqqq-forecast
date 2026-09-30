#!/usr/bin/env python3
"""Fetch trending Instagram posts via the official Instagram Graph API.

Requires an Instagram Business/Creator account connected to a Facebook app with
the instagram_basic and instagram_manage_insights (hashtag search) permissions.

Env:
  IG_ACCESS_TOKEN  long-lived user access token
  IG_USER_ID       the Instagram Business/Creator account id

Usage:
  fetch_trending.py --hashtags fitness,gymtok --limit 50 --out trending.json
  fetch_trending.py --accounts nike,redbull --out trending.json
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

import requests

GRAPH = "https://graph.facebook.com/v21.0"
HASHTAG_FIELDS = "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count,children{media_type,media_url}"
ACCOUNT_MEDIA_FIELDS = "id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count"
HASHTAG_RE = re.compile(r"#(\w+)", re.UNICODE)


def graph_get(path, params, token):
    params = {**params, "access_token": token}
    r = requests.get(f"{GRAPH}/{path}", params=params, timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{path}: {data['error'].get('message')}")
    return data


def paged(path, params, token, limit):
    out, data = [], graph_get(path, params, token)
    while True:
        out.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if len(out) >= limit or not nxt:
            return out[:limit]
        r = requests.get(nxt, timeout=30)
        data = r.json()
        if "error" in data:
            return out[:limit]


def enrich(post, now):
    likes = post.get("like_count") or 0
    comments = post.get("comments_count") or 0
    ts = post.get("timestamp")
    age_h = None
    if ts:
        posted = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
        age_h = max((now - posted).total_seconds() / 3600, 1.0)
    post["engagement"] = likes + comments
    post["age_hours"] = round(age_h, 1) if age_h else None
    post["velocity_per_hour"] = round(post["engagement"] / age_h, 2) if age_h else None
    post["caption_hashtags"] = [h.lower() for h in HASHTAG_RE.findall(post.get("caption") or "")]
    hook = (post.get("caption") or "").strip().splitlines()
    post["caption_hook"] = hook[0][:140] if hook else ""
    return post


def fetch_hashtag(tag, user_id, token, limit):
    found = graph_get("ig_hashtag_search", {"user_id": user_id, "q": tag}, token)
    if not found.get("data"):
        return []
    hid = found["data"][0]["id"]
    posts = {}
    for edge in ("top_media", "recent_media"):
        try:
            items = paged(f"{hid}/{edge}", {"user_id": user_id, "fields": HASHTAG_FIELDS, "limit": 50}, token, limit)
        except RuntimeError as e:
            print(f"warn: #{tag} {edge}: {e}", file=sys.stderr)
            continue
        for p in items:
            p = posts.setdefault(p["id"], {**p, "source": f"#{tag}", "in_top": False, "in_recent": False})
            p["in_top" if edge == "top_media" else "in_recent"] = True
    return list(posts.values())


def fetch_account(username, user_id, token, limit):
    fields = f"business_discovery.username({username}){{username,followers_count,media.limit({min(limit, 100)}){{{ACCOUNT_MEDIA_FIELDS}}}}}"
    data = graph_get(user_id, {"fields": fields}, token)
    bd = data.get("business_discovery", {})
    followers = bd.get("followers_count")
    posts = bd.get("media", {}).get("data", [])
    for p in posts:
        p["source"] = f"@{username}"
        p["followers"] = followers
        if followers:
            p["engagement_rate"] = round(((p.get("like_count") or 0) + (p.get("comments_count") or 0)) / followers, 5)
    return posts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hashtags", default="", help="comma-separated, without #")
    ap.add_argument("--accounts", default="", help="comma-separated public business/creator usernames")
    ap.add_argument("--limit", type=int, default=50, help="max posts per hashtag edge / account")
    ap.add_argument("--reels-only", action="store_true", help="keep only VIDEO media")
    ap.add_argument("--out", default="trending.json")
    args = ap.parse_args()

    token, user_id = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
    if not token or not user_id:
        sys.exit("Set IG_ACCESS_TOKEN and IG_USER_ID (Instagram Graph API). See SKILL.md Stage 1 fallback.")

    tags = [t.strip().lstrip("#").lower() for t in args.hashtags.split(",") if t.strip()]
    accounts = [a.strip().lstrip("@") for a in args.accounts.split(",") if a.strip()]
    if not tags and not accounts:
        sys.exit("Pass --hashtags and/or --accounts")

    now = dt.datetime.now(dt.timezone.utc)
    posts = []
    for t in tags:
        posts += fetch_hashtag(t, user_id, token, args.limit)
    for a in accounts:
        try:
            posts += fetch_account(a, user_id, token, args.limit)
        except RuntimeError as e:
            print(f"warn: @{a}: {e}", file=sys.stderr)

    posts = [enrich(p, now) for p in posts]
    if args.reels_only:
        posts = [p for p in posts if p.get("media_type") == "VIDEO"]
    posts.sort(key=lambda p: p.get("velocity_per_hour") or 0, reverse=True)

    searched = set(tags)
    cooc = collections.Counter(h for p in posts for h in set(p["caption_hashtags"]) if h not in searched)
    hooks = collections.Counter(
        re.sub(r"\d+", "#", " ".join(p["caption_hook"].lower().split()[:3])) for p in posts if p["caption_hook"]
    )
    summary = {
        "fetched_at": now.isoformat(),
        "hashtags": tags,
        "accounts": accounts,
        "post_count": len(posts),
        "media_mix": dict(collections.Counter(p.get("media_type") for p in posts)),
        "hashtag_cooccurrence": cooc.most_common(30),
        "common_hook_openers": [h for h in hooks.most_common(15) if h[1] > 1],
        "rising_candidates": [p["id"] for p in posts if p.get("in_recent") and not p.get("in_top")][:15],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "posts": posts}, f, indent=2, ensure_ascii=False)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(posts)} posts to {args.out}")


if __name__ == "__main__":
    main()
