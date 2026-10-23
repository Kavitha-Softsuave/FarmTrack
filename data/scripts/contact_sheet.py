# -*- coding: utf-8 -*-
"""Make a labelled contact sheet (grid of thumbnails) for each sub-folder of a photo folder, to eyeball labels.
Usage: python contact_sheet.py [folder] [out_folder]"""
import sys, pathlib, re
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
folder = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "images" / "incoming"
out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "images" / "_review"
out.mkdir(parents=True, exist_ok=True)

def natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]

TH, COLS, PAD = 280, 5, 6
for sub in sorted(d for d in folder.iterdir() if d.is_dir()):
    files = sorted([f for f in sub.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")], key=natural)
    rows = (len(files) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * (TH + PAD) + PAD, rows * (TH + 22 + PAD) + PAD), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB"); im.thumbnail((TH, TH))
        x = PAD + (i % COLS) * (TH + PAD); y = PAD + (i // COLS) * (TH + 22 + PAD)
        sheet.paste(im, (x + (TH - im.size[0]) // 2, y + (TH - im.size[1]) // 2))
        d.text((x + 4, y + TH + 4), f"{f.stem[-12:]}  {Image.open(f).size[0]}x{Image.open(f).size[1]}", fill=(255, 255, 255))
    name = re.sub(r"\W+", "_", sub.name.strip().lower())
    sheet.save(out / f"sheet_{name}.png")
    print(sub.name, len(files), "->", out / f"sheet_{name}.png", sheet.size)
