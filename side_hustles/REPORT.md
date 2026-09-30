# YouTube scrape: least attractive and most passive side hustles

**Data:** 478 unique YouTube videos (~156M combined views) from 22 searches, split into two groups: *unattractive* ("boring businesses", "unsexy side hustles", "dirty jobs side hustle", "gross side hustles that pay well", …) and *passive* ("most passive side hustles", "hands off side hustles", "lazy side hustles", "set and forget", …). Each video's title, full description and chapter list (262 videos had chapters) were matched against a lexicon of about 75 side hustles. Full table: [`data/hustle_rankings.csv`](data/hustle_rankings.csv).

**Scores (0–100):**
- **Unattractive**: share of the videos mentioning a hustle that frame it as boring, dirty, gross or unsexy, plus how often those words appear on the same line as the hustle.
- **Passive**: the same measure for passive, hands-off or automated wording, minus a penalty when the mention sits next to effort words (physical, labor, customers, daily, truck…).
- **Combo**: √(unattractive × passive) × (1 + log₁₀ videos), so hustles that are both boring and passive, and that YouTube discusses often, rank highest.

## 🏆 Boring *and* passive (the sweet spot)

| # | Hustle | Videos | Views | Unattractive | Passive | Combo |
|---|---|---|---|---|---|---|
| 1 | **Vending machines** | 58 | 9.7M | 72 | 52 | 168 |
| 2 | **Laundromat** | 47 | 3.5M | 82 | 47 | 166 |
| 3 | **Self-storage units** | 44 | 3.4M | 80 | 48 | 163 |
| 4 | **Car wash** (self-serve/automatic) | 26 | 0.8M | 72 | 60 | 158 |
| 5 | **ATM machines** | 23 | 1.8M | 77 | 55 | 154 |
| 6 | **Parking lot rental** | 25 | 3.9M | 67 | 50 | 139 |
| 7 | Mobile home parks | 4 | <0.1M | 100 | 65 | 129 |
| 8 | Buying an existing "boring" small business | 10 | 1.3M | 66 | 56 | 122 |
| 9 | Commercial cleaning / janitorial (run with staff) | 16 | 0.6M | 70 | 37 | 112 |
| 10 | Billboard rental | 7 | 1.0M | 71 | 46 | 105 |
| 11 | Portable toilet rental | 4 | 0.2M | 90 | 48 | 105 |

**Pattern:** the winners are almost all **coin-op machines or rentable real estate/space**, where you own the asset, customers serve themselves, and the work is restocking, collecting and maintenance. YouTube calls them "boring businesses that make money while you sleep".

## 🤢 Least attractive (highest "ugly" score, ≥5 videos)

| Hustle | Unattractive | Passive | Note |
|---|---|---|---|
| Trash can cleaning | 100 | 20 | Every mention is framed as gross; 7M views |
| Laundromat | 82 | 47 | |
| Self-storage units | 80 | 48 | |
| Moving / hauling help | 78 | 19 | |
| ATM machines | 77 | 55 | |
| Mobile car detailing | 76 | 25 | |
| Pet waste removal (pooper scooper) | 75 | 20 | |
| Pressure washing | 72 | 20 | |
| Vending machines | 72 | 52 | |
| Junk removal / lawn care / septic & grease trap | 67–71 | 12–17 | Unpleasant **and** hands-on |

The "dirty jobs" group (trash cans, dog poop, pressure washing, junk removal, septic) is the least attractive but **scores among the lowest on passivity**. YouTube pitches these as high-paying and low-competition, not hands-off.

## 😴 Most passive (highest "passive" score, ≥5 videos)

| Hustle | Passive | Unattractive |
|---|---|---|
| Faceless YouTube channel | 76 | 9 |
| Dividend stocks | 72 | 22 |
| Index funds / ETFs | 70 | 24 |
| Blogging / niche websites | 69 | 11 |
| Print on demand | 66 | 27 |
| Affiliate marketing | 62 | 19 |
| Car wash | 60 | 72 |
| Online courses | 57 | 18 |
| KDP / ebooks | 57 | 23 |
| Digital products / templates | 57 | 26 |

The most passive ideas are mostly **digital or financial**. They are also the *most attractive*, so they are crowded. Car washes, ATMs and vending machines are the only hustles that score high on both lists.

## Most-watched source videos
- [Passive Income Expert: How To Make $10k Per Month In 90 Days!](https://youtu.be/4QLWlcneJig) (6.0M views, vending)
- [20 BORING BUSINESSES That Make Money While You Sleep](https://youtu.be/oA0Pk1J9_mw) (1.3M)
- [9 DIRTY Side Hustles No One Is Talking About For 2026!](https://youtu.be/8g0EyxXdOt0) (1.0M)
- [6 BORING Businesses That Always Make Millionaires](https://youtu.be/zgv8HhL-7HE) (816K)
- [9 Dirty But High Paying Side Hustles That Never Fail In 2026!](https://youtu.be/s9Hfvh-DFxU) (671K)
- [7 Machines That Help Broke People Make Real Money (No Staff, No Experience)](https://youtu.be/dcbjQOgA754) (591K)

## Caveats
- **No transcripts.** YouTube's caption/transcript endpoints are blocked from this environment, so scores come from titles, descriptions and chapters, not from what is said in the video.
- Scores measure **how YouTube frames** a hustle, not real passivity or profit. "Passive" vending and laundromats still need restocking, repairs and upfront capital, often $5k–$1M+.
- Hustles mentioned in fewer than 5 videos (mobile home parks, porta-potties, RV rental) have unstable scores.
- Keyword matching adds some noise (for example, a GTA "passive safes" video counts toward car wash).

## Reproduce
```bash
python3 side_hustles/scrape_youtube.py   # ~3 min → data/videos.json
python3 side_hustles/analyze.py          # → data/hustle_rankings.csv
```

## Live ledger
`ledger.html` is published as a private claude.ai artifact (“Boring Money Ledger”). It shows every hustle split into **Top** (15+ videos or 5M+ views), **Rising** (little coverage, mostly from the last year) and **Under the radar** (little coverage, mostly older). You can star hustles, set a status, rate them, keep notes and add your own. Scan data lives in the artifact's database. After rerunning the scraper and analyzer, ask Claude to refresh it. Refreshing keeps your statuses and notes and adds a new entry to each hustle's scan history.
