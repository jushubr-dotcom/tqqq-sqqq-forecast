#!/usr/bin/env python3
"""Regenerate Reel keyframes with OpenAI image models, or build a ChatGPT copy-paste pack.

prompts.json: list of {id, prompt, source_frame?, mode: "edit"|"generate", size?}

Usage:
  regenerate_frames.py prompts.json --out regen/ [--model gpt-image-1] [--quality medium]
  regenerate_frames.py prompts.json --out regen/ --dry-run
  regenerate_frames.py prompts.json --out regen/ --chatgpt-pack
"""
import argparse
import base64
import json
import os
import sys

API = "https://api.openai.com/v1/images"
SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


def load(path):
    with open(path) as f:
        items = json.load(f)
    errors = []
    for i, it in enumerate(items):
        if not it.get("id") or not it.get("prompt"):
            errors.append(f"#{i}: needs id and prompt")
        mode = it.setdefault("mode", "edit" if it.get("source_frame") else "generate")
        if mode == "edit" and not os.path.exists(it.get("source_frame", "")):
            errors.append(f"{it.get('id')}: source_frame not found: {it.get('source_frame')}")
        if it.setdefault("size", "1024x1536") not in SIZES:
            errors.append(f"{it.get('id')}: size must be one of {sorted(SIZES)}")
    if errors:
        sys.exit("prompts.json invalid:\n  " + "\n  ".join(errors))
    return items


def call(item, model, quality, key):
    import requests
    headers = {"Authorization": f"Bearer {key}"}
    data = {"model": model, "prompt": item["prompt"], "size": item["size"], "quality": quality, "n": 1}
    if item["mode"] == "edit":
        with open(item["source_frame"], "rb") as f:
            files = {"image[]": (os.path.basename(item["source_frame"]), f, "image/jpeg")}
            r = requests.post(f"{API}/edits", headers=headers, data=data, files=files, timeout=300)
    else:
        r = requests.post(f"{API}/generations", headers=headers, json=data, timeout=300)
    body = r.json()
    if r.status_code != 200:
        raise RuntimeError(body.get("error", {}).get("message", r.text[:300]))
    return base64.b64decode(body["data"][0]["b64_json"])


def chatgpt_pack(items, out):
    lines = [
        "# ChatGPT frame regeneration pack",
        "",
        "Open a new ChatGPT chat (image generation enabled). Send message 0 first,",
        "then each numbered message, attaching the listed frame where shown.",
        "",
        "## 0. Style setup",
        "```",
        "I'm going to send you reference frames from a vertical short-form video. For each one,",
        "create a NEW 9:16 image that keeps the composition, camera angle, lighting and color mood",
        "of the reference, but uses the subject I describe. Don't copy any people, faces, logos,",
        "text or watermarks from the reference. Keep all images visually consistent as one sequence.",
        "```",
        "",
    ]
    for n, it in enumerate(items, 1):
        lines.append(f"## {n}. {it['id']}")
        if it["mode"] == "edit":
            lines.append(f"Attach: `{it['source_frame']}`")
        else:
            lines.append("No attachment (text-only).")
        lines += ["```", it["prompt"], "```", ""]
    path = os.path.join(out, "chatgpt_pack.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompts")
    ap.add_argument("--out", default="regen")
    ap.add_argument("--model", default="gpt-image-1")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high", "auto"])
    ap.add_argument("--only", help="comma-separated ids to (re)run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chatgpt-pack", action="store_true", help="write copy-paste pack for the ChatGPT app instead of calling the API")
    args = ap.parse_args()

    items = load(args.prompts)
    if args.only:
        wanted = set(args.only.split(","))
        items = [it for it in items if it["id"] in wanted]
    os.makedirs(args.out, exist_ok=True)

    if args.chatgpt_pack:
        print(f"Wrote {chatgpt_pack(items, args.out)} ({len(items)} frames)")
        return
    edits = sum(it["mode"] == "edit" for it in items)
    print(f"{len(items)} images ({edits} edit, {len(items) - edits} generate), model={args.model}, quality={args.quality}")
    if args.dry_run:
        return

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("Set OPENAI_API_KEY, or use --chatgpt-pack for the manual ChatGPT flow.")

    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    for it in items:
        dest = os.path.join(args.out, f"{it['id']}.png")
        try:
            png = call(it, args.model, args.quality, key)
        except Exception as e:  # keep going; report per-frame failures
            print(f"FAIL {it['id']}: {e}")
            manifest[it["id"]] = {**it, "error": str(e)}
            continue
        with open(dest, "wb") as f:
            f.write(png)
        manifest[it["id"]] = {**it, "output": dest, "model": args.model, "quality": args.quality}
        print(f"ok   {it['id']} -> {dest}")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    main()
