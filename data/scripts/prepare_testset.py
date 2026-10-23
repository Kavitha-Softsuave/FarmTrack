# -*- coding: utf-8 -*-
"""Prepare test set v1 from the 30 photos the user collected (images/incoming). Originals are never modified.

Outputs (under data/images/):
  testset_v1/leaf/<disease_id>/<CODE>_<nn>.jpg        PRIMARY accuracy set: single-leaf photos
  testset_v1/fruit_info/<disease_id>/<CODE>_<nn>.jpg  fruit photos: run for information only (models read leaves)
  labels.csv                                          one row per original/derived photo, with the review decisions
  testset_v1_manifest.json                            counts and caveats

The review decisions below are the assistant's VISUAL judgement. They are NOT agronomist-confirmed.
"""
import csv, hashlib, json, re, shutil, pathlib
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG = ROOT / "images"
SRC = IMG / "incoming"
OUT = IMG / "testset_v1"
if OUT.exists():
    shutil.rmtree(OUT)

CLASSES = {"alt": ("Alternaria", "ALT", "Apple___Alternaria_leaf_spot"),
           "mar": ("Marssonina", "MAR", "Apple___Marssonina_blotch"),
           "scab": ("scab", "SCB", "Apple___Apple_scab")}
# (class key, number) -> decision
# subject: leaf | fruit | fruit_panels | two_panels | two_leaves ; doubt: none | low | medium | high
R = {
 ("alt", 1): dict(subject="leaf", doubt="none", note="Brown lesions at the leaf edge"),
 ("alt", 2): dict(subject="leaf", doubt="none", note="Small brown spots"),
 ("alt", 3): dict(subject="leaf", doubt="none", note="Purple-brown spots"),
 ("alt", 4): dict(subject="leaf", doubt="high", note="Round ORANGE spots with dark rims look like rust (e.g. cedar apple rust), not Alternaria; agronomist to confirm"),
 ("alt", 5): dict(subject="fruit_panels", doubt="none", note="Three-panel figure (a, b, c) of FRUIT: not a leaf photo", exclude="not a leaf photo (fruit panels)"),
 ("alt", 6): dict(subject="fruit_panels", doubt="none", note="Exact duplicate of Alternaria 5", dup_of=("alt", 5)),
 ("alt", 7): dict(subject="leaf", doubt="none", note="Brown lesion on the leaf edge"),
 ("alt", 8): dict(subject="leaf", doubt="low", note="Yellowing leaf with brown spots; could also be other blotch diseases"),
 ("alt", 9): dict(subject="leaf", doubt="none", note="Branch with several spotted leaves"),
 ("alt", 10): dict(subject="leaf", doubt="none", note="Round brown spots with halos"),
 ("mar", 1): dict(subject="leaf", doubt="none", note="Purple-brown dots on a green leaf"),
 ("mar", 2): dict(subject="leaf", doubt="none", note="Yellow leaf with dark green islands and brown blotches"),
 ("mar", 3): dict(subject="leaf", doubt="none", note="Leaf held in hand"),
 ("mar", 4): dict(subject="two_panels", doubt="none", note="Two-panel figure (a, b) of two different leaves: split into 4a and 4b",
                  split=[("a", (0, 0, 435, 350)), ("b", (0, 352, 435, 705))]),
 ("mar", 5): dict(subject="leaf", doubt="none", note="Large yellow-green leaf with dark patches"),
 ("mar", 6): dict(subject="leaf", doubt="none", note="Leaf held in hand"),
 ("mar", 7): dict(subject="leaf", doubt="none", note="Two leaves, the upper one yellowing with dark patches"),
 ("mar", 8): dict(subject="leaf", doubt="none", note="Purple spots on a blue-green leaf"),
 ("mar", 9): dict(subject="leaf", doubt="none", note="Branch with yellowing, blotched leaves"),
 ("mar", 10): dict(subject="leaf", doubt="low", note="Branch with dark purple-brown leaves; may be advanced blotch"),
 ("scab", 1): dict(subject="fruit", doubt="none", note="Small apples with scab lesions, leaves in the background"),
 ("scab", 2): dict(subject="fruit", doubt="none", note="Apple with scab lesions"),
 ("scab", 3): dict(subject="fruit", doubt="none", note="Red apple with scab lesions"),
 ("scab", 4): dict(subject="fruit", doubt="none", note="Yellow apple with black scab spots"),
 ("scab", 5): dict(subject="two_leaves", doubt="medium", note="Two leaves side by side (slide photo): split into left and right. The right leaf has ring-like lesions with pale centres that look like frogeye leaf spot; agronomist to confirm",
                   split=[("L", (0, 0, 272, 337)), ("R", (275, 0, 515, 337))]),
 ("scab", 6): dict(subject="leaf", doubt="medium", note="Reddish-brown round blotches; scab is usually olive-brown and velvety; agronomist to confirm"),
 ("scab", 7): dict(subject="fruit", doubt="none", note="Cluster of cracked, scabbed apples"),
 ("scab", 8): dict(subject="fruit", doubt="none", note="Exact duplicate of scab 2", dup_of=("scab", 2)),
 ("scab", 9): dict(subject="leaf", doubt="none", note="Dark circular scab lesions on a leaf"),
 ("scab", 10): dict(subject="leaf", doubt="none", note="Exact duplicate of scab 9", dup_of=("scab", 9)),
}

def key_of(folder, fname):
    k = "alt" if folder.lower().startswith("altern") else "mar" if folder.lower().startswith("marss") else "scab"
    return k, int(re.search(r"(\d+)\.jpg$", fname, re.I).group(1))

PROV = "Web image: no camera metadata, thumbnail-style size, source and licence unknown"
RESTRICT = "Internal testing only. Do not redistribute, train on, or show as client data until the licence is known."
rows, counts = [], {"leaf_test": {}, "fruit_info": {}, "excluded": 0, "duplicates": 0}
for sub in sorted(d for d in SRC.iterdir() if d.is_dir()):
    for f in sorted(sub.iterdir(), key=lambda p: key_of(sub.name, p.name)[1]):
        ck, n = key_of(sub.name, f.name)
        _, code, did = CLASSES[ck]
        r = R[(ck, n)]
        md5 = hashlib.md5(f.read_bytes()).hexdigest()
        im = Image.open(f).convert("RGB")
        base = dict(crop="Apple", label=did, label_source="folder name chosen by the person who collected the photos",
                    confirmed_by="NOT confirmed by an agronomist", provenance=PROV, use_restriction=RESTRICT,
                    original_file=f.relative_to(IMG).as_posix(), md5=md5[:12], subject=r["subject"], label_doubt=r["doubt"], review_note=r["note"])
        if r.get("dup_of"):
            dk = r["dup_of"]
            rows.append(dict(base, filename="", leaf_id="", set="excluded", duplicate_of=f"{CLASSES[dk[0]][1]}_{dk[1]:02d}", derived_from="", width=im.size[0], height=im.size[1], exclusion_reason="exact duplicate"))
            counts["duplicates"] += 1
            continue
        if r.get("exclude"):
            rows.append(dict(base, filename="", leaf_id="", set="excluded", duplicate_of="", derived_from="", width=im.size[0], height=im.size[1], exclusion_reason=r["exclude"]))
            counts["excluded"] += 1
            continue
        is_leaf = r["subject"] in ("leaf", "two_panels", "two_leaves")
        setname = "leaf" if is_leaf else "fruit_info"
        dest_dir = OUT / setname / did
        dest_dir.mkdir(parents=True, exist_ok=True)
        pieces = []
        if r.get("split"):
            for tag, box in r["split"]:
                crop = im.crop(box)
                name = f"{code}_{n:02d}{tag.lower()}.jpg"
                crop.save(dest_dir / name, quality=95)
                pieces.append((name, f"{code}-{n:02d}{tag}", f.name, crop.size))
        else:
            name = f"{code}_{n:02d}.jpg"
            shutil.copy2(f, dest_dir / name)
            pieces.append((name, f"{code}-{n:02d}", "", im.size))
        for name, leaf_id, derived, size in pieces:
            tag = "leaf_test" if is_leaf else "fruit_info"
            rows.append(dict(base, filename=f"testset_v1/{setname}/{did}/{name}", leaf_id=leaf_id, set=tag, duplicate_of="",
                             derived_from=("crop of " + derived) if derived else "", width=size[0], height=size[1], exclusion_reason=""))
            counts[tag][did] = counts[tag].get(did, 0) + 1

fields = ["filename", "crop", "label", "label_source", "confirmed_by", "leaf_id", "set", "subject", "label_doubt", "review_note",
          "duplicate_of", "derived_from", "exclusion_reason", "original_file", "md5", "width", "height", "provenance", "use_restriction"]
with open(IMG / "labels.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})

leaf_rows = [r for r in rows if r["set"] == "leaf_test"]
manifest = dict(
    prepared="19 Oct 2026", source_folder="images/incoming (30 originals, 10 per folder)", originals=30,
    leaf_test=counts["leaf_test"], leaf_test_total=len(leaf_rows),
    leaf_test_reliable_labels={d: sum(1 for r in leaf_rows if r["label"] == d and r["label_doubt"] in ("none", "low")) for d in counts["leaf_test"]},
    fruit_info=counts["fruit_info"], fruit_info_total=sum(counts["fruit_info"].values()),
    excluded_not_a_leaf=counts["excluded"], excluded_exact_duplicates=counts["duplicates"],
    caveats=["Labels come from the folder names chosen by the collector; not confirmed by an agronomist.",
             "Photos look like web images (no camera EXIF, thumbnail sizes), not photos taken by the client; accuracy on them is NOT a field measure.",
             "Source and licence unknown: internal testing only.",
             "Counts per disease are tiny; a single wrong answer moves a class result by 9 to 25 points."])
(IMG / "testset_v1_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))
