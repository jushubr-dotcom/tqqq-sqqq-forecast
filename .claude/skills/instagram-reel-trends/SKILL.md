---
name: instagram-reel-trends
description: Analyze trending Instagram posts and Reels, spot emerging trends, break Reels down into keyframes, and regenerate those frames as new images with ChatGPT / OpenAI image models. Use when the user asks to find what's trending on Instagram, analyze a Reel or a set of Reels, reverse-engineer a Reel's visual style, build a shot list from a trend, or recreate / remix Reel frames in ChatGPT.
---

# Instagram Reel Trends → ChatGPT Frame Regeneration

End-to-end workflow in four stages. Each stage writes to a run folder
(`ig_runs/<YYYY-MM-DD>_<slug>/` by default) so later stages can reuse earlier output.

```
1. Discover  → trending.json          (scripts/fetch_trending.py)
2. Collect   → reels/*.mp4            (user files, or scripts/download_reels.sh)
3. Analyze   → frames/, analysis.md   (scripts/extract_frames.py + your vision)
4. Regenerate→ prompts.json, regen/   (scripts/regenerate_frames.py, or ChatGPT by hand)
```

Ask the user only for what's missing: hashtags/niche, the Reels (URLs or files),
and whether they want API regeneration or copy-paste prompts for the ChatGPT app.

## Ground rules

- **Use official or user-supplied sources.** Discovery uses the Instagram Graph API
  (requires a Business/Creator account). Don't write scrapers that log in, bypass
  rate limits, or evade Instagram's anti-bot measures.
- **Download only what the user may use** — their own Reels, licensed content, or
  public Reels for private analysis. Say so once if the user is unclear.
- **Regenerate, don't replicate.** Frames are references for composition, lighting,
  pacing and style. Prompts must describe *new* subjects; never reproduce a real
  person's face/likeness, logos, watermarks, or a creator's distinctive
  copyrighted character. Strip usernames from prompts.
- Never print or commit API tokens. Read them from env vars only.

## Setup check

Run once and install whatever is missing:

```bash
python3 .claude/skills/instagram-reel-trends/scripts/check_setup.py
```

Needs: `ffmpeg`/`ffprobe` (frame extraction), Python `requests` and `Pillow`,
optionally `yt-dlp` (downloads). Env vars: `IG_ACCESS_TOKEN`, `IG_USER_ID`
(discovery), `OPENAI_API_KEY` (API regeneration).

## Stage 1 — Discover trending posts

```bash
python3 .claude/skills/instagram-reel-trends/scripts/fetch_trending.py \
  --hashtags fitness,gymtok,morningroutine --limit 50 --out ig_runs/<run>/trending.json
# optional: benchmark specific public business/creator accounts
  --accounts nike,redbull
```

The script pulls `top_media` and `recent_media` per hashtag (Graph API
hashtag search allows 30 unique hashtags per 7 days — reuse them) and, for
`--accounts`, recent media via Business Discovery. It computes per post:
engagement (`likes + comments`), engagement velocity (per hour since posting),
and flags `in_top` / `in_recent`.

If the user has no Graph API access, ask them to paste Reel URLs or captions,
or export from Instagram's own Insights / Trending audio page, and continue from
Stage 2 with that list.

### Spotting a *new* trend

Read `trending.json` and report, in a short table:

1. **Rising formats** — posts with high velocity that appear in `recent_media`
   but not yet in `top_media` are early signals; formats in both are established.
2. **Co-occurring hashtags** — hashtags repeated across top posts that the user
   didn't search for (the script outputs `hashtag_cooccurrence`). New entrants
   there are candidate trends.
3. **Caption hooks** — recurring opening lines/templates ("POV:", "Things I
   wish…", "Day X of…"), CTA patterns, emoji usage.
4. **Media mix** — share of `VIDEO` (Reels) vs `CAROUSEL_ALBUM` vs `IMAGE`.

Label each trend **Emerging / Peaking / Saturated** with the evidence behind it.
Don't overclaim from small samples; state the sample size.

## Stage 2 — Collect Reels

Preferred: the user drops `.mp4` files into `ig_runs/<run>/reels/`.
Otherwise, for URLs the user has rights to analyze:

```bash
bash .claude/skills/instagram-reel-trends/scripts/download_reels.sh ig_runs/<run>/reels urls.txt
```

(If Instagram requires login, ask the user to supply the files instead —
don't handle their Instagram password.)

## Stage 3 — Analyze Reels

```bash
python3 .claude/skills/instagram-reel-trends/scripts/extract_frames.py \
  ig_runs/<run>/reels --out ig_runs/<run>/frames --scene 0.30 --max-frames 12
```

Per Reel this writes scene-change keyframes (`frame_###_<t>s.jpg`), a
`contact_sheet.jpg`, and `meta.json` (duration, fps, resolution, shot
timestamps, average shot length, cuts per second).

Then **look at the contact sheet and keyframes** (Read the images) and write
`ig_runs/<run>/analysis.md` with, per Reel:

| Field | What to capture |
|---|---|
| Hook (0–3 s) | What happens in the first shot and why it stops the scroll |
| Structure | Beat list with timestamps from `meta.json` |
| Pacing | Avg shot length, cuts/sec, where the pace changes |
| Camera | Framing (ECU/CU/MS/WS), angle, movement (handheld, whip pan, locked-off) |
| Lighting & color | Key light direction, hard/soft, palette (3–5 hex), grade (teal-orange, faded film…) |
| Subject & set | Who/what, wardrobe, props, location — generically, no identities |
| On-screen text | Font style, placement, captions/subtitles style |
| Audio cue | Trending sound / voiceover / beat-sync (from caption or user) |
| Why it works | 1–2 sentences tying the above to the trend |

Finish with a **Trend recipe**: the reusable formula (hook + structure + look)
the user can shoot or generate.

## Stage 4 — Regenerate frames with ChatGPT

First write `ig_runs/<run>/prompts.json` — one entry per keyframe to regenerate:

```json
[
  {
    "id": "reel1_f003",
    "source_frame": "ig_runs/<run>/frames/reel1/frame_003_2.40s.jpg",
    "mode": "edit",
    "prompt": "Vertical 9:16 photo, medium close-up of a woman in her 30s in a sunlit minimalist kitchen pouring iced matcha into a glass, soft window light from camera left, warm neutral palette (#F2E8DA, #8FAF6B, #3B3B3B), shallow depth of field, handheld phone-camera look, slight motion blur on the pour, empty space in the top third for caption text. No text, no logos, no watermark.",
    "size": "1024x1536"
  }
]
```

Prompt-writing rules:
- Lead with format (`Vertical 9:16`), then shot size + subject + action, setting,
  lighting, palette (hex), lens/camera feel, mood, then negatives
  (`No text, no logos, no watermark`).
- Swap in the **user's** subject/brand/product; keep the source's composition,
  lighting and energy.
- Keep a shared "style block" across all frames of one Reel so the set is
  visually consistent; only vary subject/action/framing.
- `mode: "edit"` passes the original frame as a reference image (composition
  transfer). `mode: "generate"` is text-only — use it when the frame contains a
  recognizable person or brand you must not carry over.

Then pick a path:

**A. API (automated)** — requires `OPENAI_API_KEY`:

```bash
python3 .claude/skills/instagram-reel-trends/scripts/regenerate_frames.py \
  ig_runs/<run>/prompts.json --out ig_runs/<run>/regen --model gpt-image-1 --quality medium
```

Add `--dry-run` first to validate the file and estimate the image count.
Outputs `regen/<id>.png` plus `regen/manifest.json`.

**B. ChatGPT app (manual)** — run the same script with `--chatgpt-pack`. It writes
`regen/chatgpt_pack.md`: numbered, copy-paste-ready messages, each naming the
frame file to attach. Tell the user to open a new ChatGPT chat, send the style
block message first, then each frame message with its image attached.

After regeneration, Read a few outputs, compare against the source frames, and
report: which frames matched the intended composition, what drifted, and a
revised prompt for any frame worth re-running. Optionally stitch outputs into a
storyboard:

```bash
python3 .claude/skills/instagram-reel-trends/scripts/extract_frames.py --sheet ig_runs/<run>/regen
```

## Deliverables to hand back

1. Trend summary table (Stage 1) with Emerging/Peaking/Saturated labels.
2. `analysis.md` with per-Reel breakdowns and the Trend recipe.
3. `prompts.json` + regenerated frames (or `chatgpt_pack.md`).
4. A short shot list for recreating the Reel with the user's own subject.
