# -*- coding: utf-8 -*-
"""Inspect a folder of collected photos: readability, size, camera metadata, exact and near duplicates.
Usage: python inspect_images.py [folder]   (default: ../images/incoming)"""
import os, sys, glob, hashlib, collections, pathlib
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
folder = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "images" / "incoming"

def ahash(im):
    px = list(im.convert("L").resize((8, 8)).tobytes())
    m = sum(px) / 64
    return "".join("1" if v > m else "0" for v in px)

rows = []
for p in sorted(folder.rglob("*")):
    if not p.is_file() or p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"):
        continue
    rel = p.relative_to(folder).as_posix()
    try:
        im = Image.open(p); im.verify(); im = Image.open(p)
        ex = im.getexif()
        rows.append(dict(rel=rel, w=im.size[0], h=im.size[1], kb=p.stat().st_size / 1024, mode=im.mode,
                         make=ex.get(271), model=ex.get(272), dt=ex.get(306),
                         md5=hashlib.md5(p.read_bytes()).hexdigest()[:10], ah=ahash(im)))
    except Exception as e:
        print("UNREADABLE:", rel, e)

for r in rows:
    print(f"{r['rel']:48s} {r['w']:>5}x{r['h']:<5} {r['kb']:7.1f}KB {r['mode']}  exif={r['make']},{r['model']},{r['dt']}")
c = collections.Counter(r["md5"] for r in rows)
print("\nreadable files:", len(rows))
print("exact duplicate files:", [k for k, v in c.items() if v > 1])
ham = lambda a, b: sum(x != y for x, y in zip(a, b))
near = [(rows[i]["rel"], rows[j]["rel"], ham(rows[i]["ah"], rows[j]["ah"])) for i in range(len(rows)) for j in range(i + 1, len(rows)) if ham(rows[i]["ah"], rows[j]["ah"]) <= 4]
print("near-duplicate pairs (average-hash distance <= 4):", len(near))
for n in near: print("  ", n)
ws = sorted(r["w"] for r in rows); hs = sorted(r["h"] for r in rows)
print("width  min/median/max:", ws[0], ws[len(ws) // 2], ws[-1], "| height:", hs[0], hs[len(hs) // 2], hs[-1])
print("photos with camera EXIF (make/model):", sum(1 for r in rows if r["make"] or r["model"]), "of", len(rows))
