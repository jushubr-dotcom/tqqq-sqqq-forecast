#!/usr/bin/env python3
"""Regenerate Reel frames through the ChatGPT web app in your own logged-in Chrome.

No OpenAI API key needed: the script drives chatgpt.com in a visible Chrome window
using your ChatGPT session, sends the style setup message, then for each frame
attaches the source image, sends the prompt, waits for the generated image and
saves it.

Two ways to connect (you log in yourself; the script never handles passwords):

  1. Attach to a Chrome you started with remote debugging (recommended):
       google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.chatgpt-chrome"
     Log in to chatgpt.com in that window once, then:
       chatgpt_browser.py prompts.json --out regen/ --cdp http://localhost:9222

  2. Let the script launch Chrome with a dedicated profile folder:
       chatgpt_browser.py prompts.json --out regen/ --profile ~/.chatgpt-chrome
     On first run, log in in the window that opens; the script waits for you.

Requires: pip install playwright  (uses installed Chrome; no browser download needed)
"""
import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regenerate_frames import STYLE_SETUP, load  # noqa: E402

# chatgpt.com selectors. The UI changes often; if a step times out, inspect the page and
# update these (or override the page with --base-url for testing).
PROMPT_BOX = "#prompt-textarea"
FILE_INPUT = "input[type=file]"
SEND_BUTTON = "[data-testid='send-button']"
STOP_BUTTON = "[data-testid='stop-button']"
GENERATED_IMG = "img[alt^='Generated image'], img[alt^='generated image']"

FETCH_AS_B64 = """async (src) => {
  const r = await fetch(src, {credentials: 'include'});
  const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}"""


def image_ext(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def wait_for_login(page, timeout_s):
    try:
        page.wait_for_selector(PROMPT_BOX, timeout=15_000)
        return
    except Exception:
        pass
    print(f"Log in to ChatGPT in the browser window (waiting up to {timeout_s}s)...")
    page.wait_for_selector(PROMPT_BOX, timeout=timeout_s * 1000)


def send(page, text, attachment=None, upload_wait_s=20):
    if attachment:
        page.set_input_files(FILE_INPUT, os.path.abspath(attachment))
    box = page.locator(PROMPT_BOX)
    box.click()
    # insert_text keeps newlines intact without triggering Enter-to-send.
    page.keyboard.insert_text(text)
    send_btn = page.locator(SEND_BUTTON)
    deadline = time.time() + upload_wait_s
    while not send_btn.is_enabled():  # disabled while an attachment uploads
        if time.time() > deadline:
            raise TimeoutError("send button never enabled (upload stuck?)")
        time.sleep(0.5)
    send_btn.click()


def wait_for_reply(page, timeout_s):
    try:
        page.wait_for_selector(STOP_BUTTON, timeout=15_000)
    except Exception:
        pass  # very fast replies may never show the stop button
    page.wait_for_selector(STOP_BUTTON, state="detached", timeout=timeout_s * 1000)


def wait_for_new_image(page, before, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        imgs = page.locator(GENERATED_IMG)
        if imgs.count() > before:
            img = imgs.nth(imgs.count() - 1)
            # Image previews render progressively; wait until the final src is loaded.
            if img.evaluate("i => i.complete && i.naturalWidth > 0") and page.locator(STOP_BUTTON).count() == 0:
                return img
        time.sleep(2)
    raise TimeoutError("no new generated image appeared")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompts")
    ap.add_argument("--out", default="regen")
    conn = ap.add_mutually_exclusive_group(required=True)
    conn.add_argument("--cdp", help="attach to running Chrome, e.g. http://localhost:9222")
    conn.add_argument("--profile", help="launch Chrome with this dedicated user-data dir")
    ap.add_argument("--base-url", default="https://chatgpt.com/", help="chat URL (e.g. a ChatGPT project URL)")
    ap.add_argument("--only", help="comma-separated ids to (re)run")
    ap.add_argument("--no-style-setup", action="store_true", help="skip the initial style message")
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait per image")
    ap.add_argument("--pause", type=float, default=8, help="seconds between frames")
    ap.add_argument("--login-timeout", type=int, default=300)
    args = ap.parse_args()

    items = load(args.prompts)
    if args.only:
        wanted = set(args.only.split(","))
        items = [it for it in items if it["id"] in wanted]
    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        if args.cdp:
            browser = pw.chromium.connect_over_cdp(args.cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            ctx = pw.chromium.launch_persistent_context(
                os.path.expanduser(args.profile), channel="chrome", headless=False,
                accept_downloads=True, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(args.base_url)
        wait_for_login(page, args.login_timeout)

        if not args.no_style_setup:
            send(page, STYLE_SETUP)
            wait_for_reply(page, args.timeout)
        chat_url = page.url
        print(f"Chat: {chat_url}")

        for it in items:
            before = page.locator(GENERATED_IMG).count()
            text = it["prompt"]
            if it["mode"] == "generate":
                text = "Text-only, no reference image for this one. " + text
            try:
                send(page, text, it.get("source_frame") if it["mode"] == "edit" else None)
                wait_for_reply(page, args.timeout)
                img = wait_for_new_image(page, before, args.timeout)
                data = base64.b64decode(page.evaluate(FETCH_AS_B64, img.get_attribute("src")))
            except Exception as e:  # keep going; report per-frame failures
                print(f"FAIL {it['id']}: {e}")
                manifest[it["id"]] = {**it, "error": str(e), "chat_url": chat_url}
                json.dump(manifest, open(manifest_path, "w"), indent=2)
                continue
            dest = os.path.join(args.out, it["id"] + image_ext(data))
            with open(dest, "wb") as f:
                f.write(data)
            manifest[it["id"]] = {**it, "output": dest, "via": "chatgpt-web", "chat_url": chat_url}
            json.dump(manifest, open(manifest_path, "w"), indent=2)
            print(f"ok   {it['id']} -> {dest}")
            time.sleep(args.pause)

        if not args.cdp:
            ctx.close()


if __name__ == "__main__":
    main()
