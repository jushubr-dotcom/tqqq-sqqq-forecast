"""Renders the dex (all 24 species) to a PNG. Usage: node dump_sprites.js | python3 render_preview.py out.png [shiny]"""
import json
import sys

from PIL import Image, ImageDraw

data = json.load(sys.stdin)
out = sys.argv[1]
key = "shiny" if len(sys.argv) > 2 and sys.argv[2] == "shiny" else "normal"
px, cols = 12, 6
w, h = len(data[0][key][0]), len(data[0][key])
cell_w, cell_h = w * px + 20, h * px + 36
img = Image.new("RGB", (cols * cell_w, ((len(data) + cols - 1) // cols) * cell_h), "white")
draw = ImageDraw.Draw(img)
for i, sp in enumerate(data):
    ox, oy = (i % cols) * cell_w + 10, (i // cols) * cell_h + 6
    for y, row in enumerate(sp[key]):
        for x, c in enumerate(row):
            color = c or ("#bfe8a6" if y == h - 1 else "#eaf4ff")
            draw.rectangle([ox + x * px, oy + y * px, ox + (x + 1) * px - 1, oy + (y + 1) * px - 1], fill=color)
    draw.text((ox, oy + h * px + 6), f"#{i + 1:02d} {sp['name']}", fill="black")
img.save(out)
