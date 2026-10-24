"""Download a sample of AppleLeaf9 (GitHub JasonYangCode/AppleLeaf9, CC BY 4.0) into photos/<class_id>/ and log each file in sources.csv.

Usage: python fetch_appleleaf9.py [--per-class N] [--seed 7]
Mapping (dataset folder -> our class id):
  Scab -> Apple___Apple_scab ; Health -> Apple___healthy ; Alternaria leaf spot -> Apple___Alternaria_leaf_spot
  Brown spot -> Apple___Marssonina_blotch  (INFERRED: Chinese 'apple brown spot' is Diplocarpon mali = Marssonina; not agronomist-confirmed)
"""
import argparse, csv, json, random, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
REPO = "JasonYangCode/AppleLeaf9"
MAP = {"Scab": "Apple___Apple_scab", "Health": "Apple___healthy",
       "Alternaria leaf spot": "Apple___Alternaria_leaf_spot", "Brown spot": "Apple___Marssonina_blotch"}
AUTHOR = "Yang, Duan & Wang (AppleLeaf9 compilers); images originate from PlantVillage, Apple Tree Leaf Disease Segmentation Dataset, Plant Pathology 2020/2021"
FIELDS = ["file", "class", "source_url", "licence", "author", "note"]


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tree", help="saved git tree json (optional)")
    a = ap.parse_args()
    tree = json.loads(Path(a.tree).read_text()) if a.tree else json.loads(get(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1"))
    rnd = random.Random(a.seed)
    jobs = []
    for folder, cid in MAP.items():
        paths = sorted(t["path"] for t in tree["tree"] if t["type"] == "blob" and t["path"].startswith(folder + "/"))
        rnd.shuffle(paths)
        for p in paths[: a.per_class]:
            jobs.append((p, cid))
    rows = []

    def work(job):
        p, cid = job
        name = "al9_" + Path(p).stem.replace(" ", "").replace("(", "_").replace(")", "") + Path(p).suffix.lower()
        dest = HERE / "photos" / cid / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/{REPO}/main/{urllib.parse.quote(p)}"
        if not dest.exists():
            try:
                dest.write_bytes(get(url))
            except Exception as e:
                print("FAIL", p, e, file=sys.stderr)
                return None
        note = "label inferred: dataset 'Brown spot' = Marssonina; unconfirmed" if cid.endswith("Marssonina_blotch") else "dataset label; unconfirmed"
        return [f"{cid}/{name}", cid, f"https://github.com/{REPO}/blob/main/{urllib.parse.quote(p)}", "CC-BY-4.0", AUTHOR, note]

    with ThreadPoolExecutor(8) as ex:
        rows = [r for r in ex.map(work, jobs) if r]
    sp = HERE / "sources.csv"
    new = not sp.exists()
    with sp.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(FIELDS)
        w.writerows(rows)
    print(len(rows), "files")


if __name__ == "__main__":
    main()
