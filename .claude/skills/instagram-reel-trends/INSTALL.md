# Install on your computer

This installs the skill as a **personal** Claude Code skill (`~/.claude/skills/`),
so it works in every project and can drive your own Chrome.

## 1. Copy the skill

macOS / Linux:

```bash
git clone --depth 1 -b claude/exciting-goodall-810v9g \
  https://github.com/jushubr-dotcom/tqqq-sqqq-forecast.git /tmp/ig-skill
mkdir -p ~/.claude/skills
cp -R /tmp/ig-skill/.claude/skills/instagram-reel-trends ~/.claude/skills/
rm -rf /tmp/ig-skill
```

Windows (PowerShell):

```powershell
git clone --depth 1 -b claude/exciting-goodall-810v9g `
  https://github.com/jushubr-dotcom/tqqq-sqqq-forecast.git $env:TEMP\ig-skill
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse "$env:TEMP\ig-skill\.claude\skills\instagram-reel-trends" "$HOME\.claude\skills\"
Remove-Item -Recurse -Force "$env:TEMP\ig-skill"
```

(After the branch is merged, use `-b main` instead.)

## 2. Install the tools

```bash
# macOS
brew install ffmpeg
# Windows: winget install Gyan.FFmpeg     Linux: sudo apt install ffmpeg
pip install requests Pillow playwright yt-dlp
```

Check: `python3 ~/.claude/skills/instagram-reel-trends/scripts/check_setup.py`

## 3. Run Claude Code with Chrome

1. Install Claude Code: https://code.claude.com/docs
2. Install the Claude in Chrome extension: https://claude.ai/chrome
3. In any folder: `claude --chrome`
4. Ask: *"find trending reels for #fitness and recreate the frames in ChatGPT"*.

Claude can then browse Instagram and type into ChatGPT in your Chrome, where
you're already logged in.

## Optional: Instagram Graph API

For API-based trend data, set these in your shell profile (never paste them into a chat):

```bash
export IG_ACCESS_TOKEN=...   # long-lived token from Graph API Explorer
export IG_USER_ID=...        # instagram_business_account id
```
