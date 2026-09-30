"""Rank side hustles scraped from YouTube by how unattractive and how passive they are.

Reads side_hustles/data/videos.json (from scrape_youtube.py) and writes:
  side_hustles/data/hustle_rankings.csv
  side_hustles/REPORT.md

Scoring (all derived from video titles, descriptions and chapter lists):
  - mentions / reach: how many videos name the hustle and their combined views.
  - unattractive score: share of mentioning videos that frame it as
    boring/dirty/unsexy (title/description/query), plus "ugly" words within the
    same line as the mention.
  - passive score: same idea for passive / hands-off / automated language,
    then adjusted by an "effort penalty" for mentions near words like
    "physical", "labor", "customers", "daily".
"""
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data" / "videos.json"

# hustle -> regex of aliases (matched case-insensitively on word boundaries)
HUSTLES = {
    "Vending machines": r"vending machines?|vending (route|business)",
    "Claw / arcade machines": r"claw machines?|arcade machines?|crane machines?",
    "Laundromat": r"laundromats?|coin laundry|laundry mats?",
    "Car wash": r"car ?wash(es)?",
    "Self-storage units": r"self[- ]storage|storage units?|storage facilit(y|ies)",
    "Parking lot rental": r"parking (lots?|spaces?|spots?)",
    "ATM machines": r"\batms?\b|atm machines?",
    "Trash can cleaning": r"(trash|garbage|bin) (can )?cleaning|bin washing",
    "Pressure washing": r"pressure washing|power washing|soft washing",
    "Dumpster rental": r"dumpster (rental|business)|roll[- ]off",
    "Junk removal": r"junk removal|junk hauling",
    "Pet waste removal": r"(dog|pet) (poop|waste)|pooper scooper|poop scoop",
    "Portable toilet rental": r"porta(ble)?[- ]?(potty|potties|toilets?|john)",
    "Septic / grease trap cleaning": r"septic|grease trap",
    "Gutter cleaning": r"gutter cleaning",
    "Window cleaning": r"window cleaning",
    "Carpet cleaning": r"carpet cleaning|upholstery cleaning",
    "Crime scene / biohazard cleanup": r"crime scene|biohazard|trauma clean",
    "Commercial cleaning / janitorial": r"commercial cleaning|janitorial|office cleaning",
    "Airbnb cleaning / turnover": r"airbnb clean|turnover clean",
    "Mobile car detailing": r"detailing",
    "Lawn care / landscaping": r"lawn (care|mowing)|landscaping|mowing",
    "Snow removal": r"snow (removal|plowing|shoveling)",
    "Holiday light installation": r"(christmas|holiday) lights?",
    "Line striping (parking lots)": r"line striping|parking lot striping",
    "Mobile tire / oil change": r"mobile (tire|oil)",
    "Moving / hauling help": r"moving (help|company|labor)|hauling",
    "Furniture flipping": r"furniture flip|flipping furniture",
    "Reselling / thrift flipping": r"reselling|thrift flip|flipping (items|thrift)|retail arbitrage|resell",
    "Storage unit auctions": r"storage (unit )?auctions?",
    "Scrap metal recycling": r"scrap metal|scrapping",
    "Pallet flipping": r"pallets?",
    "Bottle / can recycling": r"can recycling|bottle recycling",
    "Billboard rental": r"billboards?",
    "Renting out equipment/tools": r"(equipment|tool) rental|rent(ing)? out (your )?(tools|equipment|camera|gear)",
    "Renting out your car": r"turo|rent(ing)? (out )?your car",
    "Renting out a room / space": r"rent(ing)? out (a|your) (room|space|garage|driveway|basement)|neighbor\b|peerspace",
    "Short-term rentals (Airbnb)": r"airbnb|short[- ]term rental|vacation rental",
    "Rental property / real estate": r"rental propert(y|ies)|real estate|landlord|duplex|house hacking",
    "RV / boat / campsite rental": r"\brv\b|rv rental|boat rental|campsite|hipcamp",
    "Mobile home parks": r"mobile home parks?|trailer parks?",
    "Land flipping / leasing": r"land flipping|raw land|land (leasing|investing)",
    "Farmland / solar land lease": r"solar (farm|land|lease)|farmland",
    "Car charging stations": r"(ev|car) charging",
    "Laundry pickup & delivery": r"laundry (pickup|delivery|service)|wash and fold",
    "Dividend stocks": r"dividend",
    "Index funds / ETFs": r"index funds?|etfs?\b|s&p ?500",
    "High-yield savings / bonds / CDs": r"high[- ]yield savings|treasury bills?|t-bills?|\bcds?\b|certificates? of deposit|\bbonds?\b",
    "Peer-to-peer lending": r"peer[- ]to[- ]peer|p2p lending|lending club",
    "REITs / crowdfunded real estate": r"reits?\b|fundrise|crowdfund",
    "Buying a small business": r"buy(ing)? a (small |boring )?business|acquire a business|business acquisition",
    "Print on demand": r"print[- ]on[- ]demand|\bpod\b|redbubble|merch by amazon|teespring",
    "Digital products / templates": r"digital products?|templates?|printables?|planners?",
    "Etsy shop": r"etsy",
    "Stock photos / footage": r"stock (photo|photography|footage|video|images?)|shutterstock|adobe stock",
    "Selling ebooks / KDP": r"e-?books?|kdp|kindle|low[- ]content books?|amazon publishing|self[- ]publish",
    "Online courses": r"online courses?|udemy|skillshare|teachable",
    "Affiliate marketing": r"affiliate marketing|affiliate (program|site|niche|income)s?|amazon associates",
    "Faceless YouTube channel": r"faceless|youtube automation|cash cow",
    "Blogging / niche websites": r"blog(ging)?|niche (site|website)s?",
    "Newsletter": r"newsletters?",
    "Selling apps / SaaS / plugins": r"(build|create|sell)(ing)? (an? )?(mobile )?apps?|micro[- ]saas|\bsaas\b|chrome extensions?|wordpress plugins?",
    "Music / sound licensing": r"royalt(y|ies)|music licensing|beats|sound effects",
    "Selling Lightroom presets / fonts": r"presets?|fonts?",
    "Dropshipping": r"drop[- ]?shipping",
    "Amazon FBA": r"\bfba\b|amazon fba",
    "Domain flipping": r"domain (names?|flipping)",
    "Website flipping / buying sites": r"website flipping|flip(ping)? websites|buy(ing)? websites",
    "Sell your data / cashback apps": r"cash ?back|honeygain|sell your data|survey",
    "Bandwidth / storage sharing": r"bandwidth|storj|honeygain|packetstream",
    "Car advertising wraps": r"car (wrap|advertis)|wrapify|carvertise",
    "Photo booth rental": r"photo booths?",
    "Bounce house / party rentals": r"bounce house|party rentals?|event rental",
    "Kiosks / massage chairs / gumball": r"massage chairs?|gumball|kiosks?|bulk vending",
    "Coin-op air / water machines": r"air machines?|water (vending|machines?)|ice (vending|machines?)",
}

UGLY = r"boring|unsexy|ugly|dirty|gross|nasty|unglamorous|nobody wants|no one wants|nobody talks|disgusting|smelly|unpopular|overlooked|poop|trash|garbage|blue collar|mundane|underrated"
PASSIVE = r"passive|hands[- ]off|automat|set (it )?and forget|while (you|u) sleep|semi[- ]passive|little (work|effort)|no work|zero work|lazy|recurring|autopilot|minimal (effort|time|work)|runs itself|mailbox money"
EFFORT = r"physical|labor|labour|hard work|manual|customers?|clients?|daily|every day|hours a (day|week)|trade|license|truck|equipment"

COMPILED = {h: re.compile(rf"\b(?:{p})", re.I) for h, p in HUSTLES.items()}
UGLY_RE, PASSIVE_RE, EFFORT_RE = (re.compile(p, re.I) for p in (UGLY, PASSIVE, EFFORT))
CHAPTER_RE = re.compile(r"^\s*\(?\d{1,2}:\d{2}(?::\d{2})?\)?\s*[-–—:|]?\s*(.+)$")


def is_recent(published):
    """True when YouTube's relative date ("3 weeks ago", "11 months ago") is under a year."""
    return bool(re.search(r"(second|minute|hour|day|week|month)s? ago", published or ""))


def tier(r):
    """Top = YouTube already talks about it a lot; Rising = small but mostly recent coverage;
    Under the radar = small and older/sparse coverage."""
    if r["videos"] >= 15 or r["total_views"] >= 5e6:
        return "Top"
    if r["recent_share"] >= 50:
        return "Rising"
    return "Under the radar"


def main():
    videos = json.loads(DATA.read_text())
    stats = defaultdict(lambda: {"videos": set(), "views": 0, "chapter_videos": set(), "ugly": 0,
                                 "passive": 0, "effort": 0, "local_ugly": 0, "local_passive": 0,
                                 "recent": 0, "top": []})
    for v in videos:
        desc = v.get("description", "")
        title = v["title"]
        # Ignore link/social/sponsor boilerplate lines in descriptions.
        lines = [l for l in desc.splitlines() if l.strip() and not re.search(r"https?://|@|#\w+\s+#|subscribe|instagram|tiktok|twitter|sponsor|discount|promo code|affiliate link|commission|may earn|disclaimer|not financial advice|links? below|download (the|my)", l, re.I)]
        chapters = v.get("chapters", []) + [m.group(1) for l in lines if (m := CHAPTER_RE.match(l))]
        v_ugly = bool(UGLY_RE.search(title + " " + desc[:400])) or "unattractive" in v["families"]
        v_passive = bool(PASSIVE_RE.search(title + " " + desc[:400])) or "passive" in v["families"]
        units = [title] + lines + v.get("chapters", [])
        for h, rx in COMPILED.items():
            hit_lines = [u for u in units if rx.search(u)]
            if not hit_lines:
                continue
            s = stats[h]
            s["videos"].add(v["video_id"])
            s["views"] += v["views"]
            if any(rx.search(c) for c in chapters) or rx.search(title):
                s["chapter_videos"].add(v["video_id"])
            s["ugly"] += v_ugly
            s["passive"] += v_passive
            s["local_ugly"] += any(UGLY_RE.search(u) for u in hit_lines)
            s["local_passive"] += any(PASSIVE_RE.search(u) for u in hit_lines)
            s["effort"] += any(EFFORT_RE.search(u) for u in hit_lines)
            s["recent"] += is_recent(v.get("published", ""))
            s["top"].append((v["views"], title, v["video_id"]))

    rows = []
    for h, s in stats.items():
        n = len(s["videos"])
        if n < 1:
            continue
        ugly = 0.6 * s["ugly"] / n + 0.4 * s["local_ugly"] / n
        passive = 0.6 * s["passive"] / n + 0.4 * s["local_passive"] / n - 0.3 * s["effort"] / n
        top = sorted(s["top"], reverse=True)[:3]
        rows.append({
            "hustle": h, "videos": n, "featured_in_chapters": len(s["chapter_videos"]),
            "total_views": s["views"],
            "unattractive_score": round(100 * ugly, 1),
            "passive_score": round(100 * max(passive, 0), 1),
            "popularity": round(math.log10(1 + s["views"]) * math.sqrt(n), 1),
            "recent_share": round(100 * s["recent"] / n),
            "top_videos": " | ".join(f"{t} (https://youtu.be/{i}, {vw:,} views)" for vw, t, i in top),
        })
    # Combined: sweet spot of boring AND passive, weighted by how much YouTube talks about it.
    for r in rows:
        r["boring_passive_score"] = round(
            (r["unattractive_score"] * r["passive_score"]) ** 0.5 * (1 + math.log10(r["videos"])), 1)
        # Opportunity ignores reach: how boring+passive it is, discounted when the niche is crowded.
        r["opportunity_score"] = round(
            (r["unattractive_score"] * r["passive_score"]) ** 0.5 / (1 + 0.15 * math.log10(1 + r["total_views"] / 1e5)), 1)
        r["tier"] = tier(r)
    rows.sort(key=lambda r: r["boring_passive_score"], reverse=True)

    out = HERE / "data" / "hustle_rankings.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(videos)} videos analysed, {len(rows)} hustles ranked -> {out}")
    for r in rows[:40]:
        print(f"{r['hustle'][:32]:32} vids={r['videos']:3} ch={r['featured_in_chapters']:3} "
              f"views={r['total_views']/1e6:7.1f}M ugly={r['unattractive_score']:5} "
              f"passive={r['passive_score']:5} combo={r['boring_passive_score']}")


if __name__ == "__main__":
    main()
