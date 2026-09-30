#!/usr/bin/env python3
"""Extract scene-change keyframes + pacing metadata from Reels, and build contact sheets.

Usage:
  extract_frames.py <video_or_dir> --out frames/ [--scene 0.3] [--max-frames 12]
  extract_frames.py --sheet <dir_of_images>        # contact sheet only
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    if run(["which", "ffprobe"]).returncode != 0:
        # Fallback for static ffmpeg builds without ffprobe: parse `ffmpeg -i` banner.
        err = run(["ffmpeg", "-hide_banner", "-i", path]).stderr
        d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
        v = re.search(r"Video:.*?(\d{2,5})x(\d{2,5}).*?([\d.]+) fps", err)
        return {
            "duration": round(int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]), 2) if d else 0,
            "width": int(v[1]) if v else None,
            "height": int(v[2]) if v else None,
            "fps": float(v[3]) if v else None,
        }
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration", "-of", "json", path])
    info = json.loads(r.stdout or "{}")
    s = (info.get("streams") or [{}])[0]
    num, _, den = s.get("r_frame_rate", "0/1").partition("/")
    return {
        "duration": round(float(info.get("format", {}).get("duration", 0)), 2),
        "width": s.get("width"),
        "height": s.get("height"),
        "fps": round(float(num) / float(den or 1), 2) if float(den or 1) else None,
    }


def scene_times(path, threshold):
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-vf",
             f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"])
    return [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def pick(times, duration, max_frames):
    # Always include the hook (t=0); thin evenly if there are too many cuts.
    times = [0.0] + [t for t in times if t > 0.2]
    if len(times) < 3 and duration:
        times = sorted(set(times + [round(duration * f, 2) for f in (0.25, 0.5, 0.75)]))
    if len(times) > max_frames:
        step = len(times) / max_frames
        times = [times[int(i * step)] for i in range(max_frames)]
    return times


def grab(path, t, dest):
    # Seek slightly past the cut so we don't land on a transition frame.
    run(["ffmpeg", "-hide_banner", "-y", "-ss", str(t + 0.05), "-i", path,
         "-frames:v", "1", "-q:v", "2", dest])
    return os.path.exists(dest)


def contact_sheet(images, dest, cols=4, thumb_w=270):
    from PIL import Image, ImageDraw
    if not images:
        return None
    thumbs = []
    for p in images:
        im = Image.open(p).convert("RGB")
        im.thumbnail((thumb_w, thumb_w * 2))
        thumbs.append((os.path.basename(p), im))
    th = max(im.height for _, im in thumbs) + 20
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * th), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(thumbs):
        x, y = (i % cols) * thumb_w, (i // cols) * th
        sheet.paste(im, (x + (thumb_w - im.width) // 2, y))
        draw.text((x + 4, y + th - 16), name[:40], fill="black")
    sheet.save(dest, quality=88)
    return dest


def process(video, out_root, threshold, max_frames):
    name = os.path.splitext(os.path.basename(video))[0]
    out = os.path.join(out_root, name)
    os.makedirs(out, exist_ok=True)
    meta = probe(video)
    cuts = scene_times(video, threshold)
    shots = [0.0] + [t for t in cuts if t > 0.2]
    bounds = shots + [meta["duration"]]
    lengths = [round(b - a, 2) for a, b in zip(bounds, bounds[1:]) if b > a]
    frames = []
    for i, t in enumerate(pick(cuts, meta["duration"], max_frames), 1):
        dest = os.path.join(out, f"frame_{i:03d}_{t:.2f}s.jpg")
        if grab(video, t, dest):
            frames.append(dest)
    meta.update({
        "source": video,
        "shot_starts": shots,
        "shot_count": len(shots),
        "avg_shot_length": round(sum(lengths) / len(lengths), 2) if lengths else None,
        "cuts_per_second": round(len(cuts) / meta["duration"], 2) if meta["duration"] else None,
        "frames": frames,
        "contact_sheet": contact_sheet(frames, os.path.join(out, "contact_sheet.jpg")),
    })
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"{name}: {meta['duration']}s, {meta['shot_count']} shots, {len(frames)} frames -> {out}")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("--out", default="frames")
    ap.add_argument("--scene", type=float, default=0.30, help="scene-change threshold 0-1 (lower = more cuts)")
    ap.add_argument("--max-frames", type=int, default=12)
    ap.add_argument("--sheet", help="build contact_sheet.jpg for a directory of images and exit")
    args = ap.parse_args()

    if args.sheet:
        imgs = sorted(p for p in glob.glob(os.path.join(args.sheet, "*"))
                      if p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and "contact_sheet" not in p)
        print(contact_sheet(imgs, os.path.join(args.sheet, "contact_sheet.jpg")))
        return
    if not args.src:
        ap.error("src is required unless --sheet is given")
    if run(["which", "ffmpeg"]).returncode != 0:
        sys.exit("ffmpeg not found (apt install ffmpeg / brew install ffmpeg)")

    videos = [args.src] if os.path.isfile(args.src) else sorted(
        p for p in glob.glob(os.path.join(args.src, "*")) if p.lower().endswith(VIDEO_EXT))
    if not videos:
        sys.exit(f"No videos found in {args.src}")
    index = [process(v, args.out, args.scene, args.max_frames) for v in videos]
    with open(os.path.join(args.out, "index.json"), "w") as f:
        json.dump(index, f, indent=2)


if __name__ == "__main__":
    main()
