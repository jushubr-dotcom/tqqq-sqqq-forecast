#!/usr/bin/env bash
# Download Reels the user has rights to analyze.
# Usage: download_reels.sh <out_dir> <urls.txt>   (one URL per line, # for comments)
set -euo pipefail

out_dir=${1:?out_dir required}
urls=${2:?urls file required}

if ! command -v yt-dlp >/dev/null; then
  echo "yt-dlp not found: pip install yt-dlp (or have the user provide .mp4 files)" >&2
  exit 1
fi

mkdir -p "$out_dir"
yt-dlp \
  --batch-file "$urls" \
  --format "mp4/best" \
  --output "$out_dir/%(uploader_id)s_%(id)s.%(ext)s" \
  --write-info-json \
  --sleep-interval 3 --max-sleep-interval 8 \
  --no-overwrites --ignore-errors

echo "Saved to $out_dir"
