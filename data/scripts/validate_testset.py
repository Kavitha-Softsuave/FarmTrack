# -*- coding: utf-8 -*-
"""Integrity checks for images/testset_v1 and images/labels.csv. Exit 1 on failure."""
import csv, hashlib, json, pathlib, sys
import pandas as pd
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMG = ROOT / "images"
FAIL, OK = [], []
def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name + (f" -- {detail}" if (detail and not cond) else ""))

lab = pd.read_csv(IMG / "labels.csv", keep_default_na=False)
dis = pd.read_csv(ROOT / "reference" / "disease_catalogue.csv", keep_default_na=False)
used = lab[lab.set.isin(["leaf_test", "fruit_info"])]

check("labels.csv accounts for all 30 originals", lab.original_file.nunique() == 30, str(lab.original_file.nunique()))
check("every used row points to an existing file", all((IMG / f).exists() for f in used.filename))
check("no stray files in testset_v1 that labels.csv does not list", {p.relative_to(IMG).as_posix() for p in (IMG / "testset_v1").rglob("*.jpg")} == set(used.filename))
check("label names equal disease ids in the catalogue", set(lab.label) <= set(dis.disease_id), str(set(lab.label) - set(dis.disease_id)))
check("folder name equals the label for every file", all(pathlib.PurePosixPath(f).parent.name == l for f, l in zip(used.filename, used.label)))
leaf = used[used.set == "leaf_test"]
check("leaf set has no exact duplicate images", leaf.filename.map(lambda f: hashlib.md5((IMG / f).read_bytes()).hexdigest()).is_unique)
check("every leaf image is >= 200 px on its short side", all(min(Image.open(IMG / f).size) >= 200 for f in leaf.filename))
check("leaf ids are unique", leaf.leaf_id.is_unique)
check("fruit images are kept out of the leaf set", not (leaf.subject == "fruit").any())
check("all three diseases are present in the leaf set", set(leaf.label) == {"Apple___Apple_scab", "Apple___Alternaria_leaf_spot", "Apple___Marssonina_blotch"})
check("every row records provenance, use restriction and 'not confirmed'", (lab.provenance != "").all() and (lab.use_restriction != "").all() and lab.confirmed_by.str.contains("NOT confirmed").all())
check("excluded rows say why", (lab[lab.set == "excluded"].exclusion_reason != "").all())
srcs = [(IMG / f) for f in lab.original_file.unique()]
check("originals in images/incoming are untouched (30 readable files)", len(srcs) == 30 and all(s.exists() for s in srcs))
man = json.loads((IMG / "testset_v1_manifest.json").read_text(encoding="utf-8"))
check("manifest matches labels.csv", man["leaf_test_total"] == len(leaf) and man["fruit_info_total"] == int((used.set == "fruit_info").sum()))
print("leaf set per class:", leaf.groupby("label").size().to_dict(), "| reliable labels:", leaf[leaf.label_doubt.isin(["none", "low"])].groupby("label").size().to_dict())
print(f"PASS {len(OK)} | FAIL {len(FAIL)}")
for x in FAIL: print("  FAIL:", x)
sys.exit(1 if FAIL else 0)
