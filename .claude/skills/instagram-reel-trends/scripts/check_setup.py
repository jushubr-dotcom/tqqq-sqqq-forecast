#!/usr/bin/env python3
"""Report which tools, packages and env vars the instagram-reel-trends skill can use."""
import importlib.util
import os
import shutil

CHECKS = [
    ("binary", "ffmpeg", "frame extraction (apt install ffmpeg / brew install ffmpeg)"),
    ("binary", "ffprobe", "video metadata (ships with ffmpeg)"),
    ("binary", "yt-dlp", "optional: download Reels (pip install yt-dlp)"),
    ("binary", "google-chrome", "ChatGPT-in-Chrome route (or Chrome.app on macOS)"),
    ("module", "playwright", "ChatGPT-in-Chrome route (pip install playwright)"),
    ("module", "requests", "API calls (pip install requests)"),
    ("module", "PIL", "contact sheets (pip install Pillow)"),
    ("env", "IG_ACCESS_TOKEN", "Stage 1 discovery via Instagram Graph API"),
    ("env", "IG_USER_ID", "Stage 1: your IG Business/Creator account id"),
    ("env", "OPENAI_API_KEY", "optional: Stage 4 API route (not needed for ChatGPT in Chrome)"),
]


def main():
    for kind, name, why in CHECKS:
        if kind == "binary":
            ok = shutil.which(name) is not None
        elif kind == "module":
            ok = importlib.util.find_spec(name) is not None
        else:
            ok = bool(os.environ.get(name))
        print(f"[{'ok' if ok else '--'}] {kind:6} {name:16} {why}")


if __name__ == "__main__":
    main()
