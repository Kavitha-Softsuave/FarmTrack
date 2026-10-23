"""Run the vision module over the photo test set (data/images/testset_v1) and print tables.

  python scripts/evaluate_vision.py                 quality table (needs only the backend environment)
  python scripts/evaluate_vision.py --degrade       + artificially blurred / darkened / brightened copies (threshold calibration)
  python scripts/evaluate_vision.py --models        + crop identification and disease classification with the real models
                                                      (needs the ml extra: torch, timm, transformers; downloads about 400 MB once);
                                                      --crop-model / --disease-model run only one of the two

Test-set labels are web images with unconfirmed labels: the model numbers are a smoke test, not accuracy figures.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))   # run without installing the package

from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from app.config import REPO_ROOT, Settings  # noqa: E402
from app.vision.quality import PillowQualityChecker  # noqa: E402

IMAGES = REPO_ROOT / "data" / "images"
CATALOGUE = REPO_ROOT / "data" / "reference" / "disease_catalogue.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def load_photos(limit: int | None) -> list[dict[str, str]]:
    rows = [r for r in read_csv(IMAGES / "labels.csv") if r["set"] in ("leaf_test", "fruit_info")]
    return rows[:limit] if limit else rows


def table(headers: list[str], rows: list[list[object]]) -> None:
    cells = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) if cells else len(h) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)))
    print("  ".join("-" * w for w in widths))
    for r in cells:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
    print()


def quality_section(photos: list[dict[str, str]]) -> None:
    qc = PillowQualityChecker()
    rows, usable_leaf, leaf_n = [], 0, 0
    for p in photos:
        data = (IMAGES / p["filename"]).read_bytes()
        m, res = qc.measure(data), qc.check(data)
        rows.append([p["filename"].split("/")[-1], p["set"], f"{m.width}x{m.height}", f"{m.brightness:.0f}", f"{m.blur_score:.0f}",
                     f"{100 * m.vegetation_fraction:.0f}%", "yes" if res.usable else "NO", ",".join(i.value for i in res.issues)])
        if p["set"] == "leaf_test":
            leaf_n += 1
            usable_leaf += res.usable
    print(f"== Photo quality (thresholds: blur >= {qc.blur_below:.0f}, brightness {qc.dark_below:.0f}..{qc.bright_above:.0f}, "
          f"short side >= {qc.min_short_side}, vegetation >= {100 * qc.vegetation_min_fraction:.0f}%)\n")
    table(["photo", "set", "size", "bright", "blur", "veg", "usable", "issues"], rows)
    print(f"Leaf photos usable: {usable_leaf}/{leaf_n} (all must be usable)\n")


def degrade_section(photos: list[dict[str, str]]) -> None:
    qc = PillowQualityChecker()
    variants = {
        "blur sigma 1.0": lambda im: im.filter(ImageFilter.GaussianBlur(1.0)),
        "blur sigma 1.5": lambda im: im.filter(ImageFilter.GaussianBlur(1.5)),
        "blur sigma 2": lambda im: im.filter(ImageFilter.GaussianBlur(2.0)),
        "blur sigma 3": lambda im: im.filter(ImageFilter.GaussianBlur(3.0)),
        "darker x0.3": lambda im: ImageEnhance.Brightness(im).enhance(0.3),
        "darker x0.2": lambda im: ImageEnhance.Brightness(im).enhance(0.2),
        "brighter x2.5": lambda im: ImageEnhance.Brightness(im).enhance(2.5),
        "brighter x3.5": lambda im: ImageEnhance.Brightness(im).enhance(3.5),
    }
    leaf = [p for p in photos if p["set"] == "leaf_test"]
    rows = []
    for name, fn in variants.items():
        counts: Counter[str] = Counter()
        scores = []
        for p in leaf:
            buf = io.BytesIO()
            fn(Image.open(IMAGES / p["filename"]).convert("RGB")).save(buf, "JPEG", quality=90)
            res = qc.check(buf.getvalue())
            counts["usable" if res.usable else "+".join(i.value for i in res.issues)] += 1
            scores.append(res.blur_score or 0.0)
        rows.append([name, f"{min(scores):.0f}..{max(scores):.0f}", ", ".join(f"{k} {v}" for k, v in counts.most_common())])
    print(f"== Degraded copies of the {len(leaf)} leaf photos (what the quality gate says)\n")
    table(["variant", "blur score range", "verdicts"], rows)


def models_section(photos: list[dict[str, str]], storage_dir: Path | None, crop: bool, disease: bool) -> None:
    from app.vision.torch_models import DISEASE_PACKAGES, missing_packages

    missing = missing_packages(DISEASE_PACKAGES)
    if missing:
        print(f"== Models skipped: {missing} not installed (pip install -e '.[ml]')\n")
        return
    settings = Settings(storage_dir=storage_dir) if storage_dir else Settings()
    if crop:
        crop_section(photos, settings)
    if disease:
        disease_section(photos, settings)


def crop_section(photos: list[dict[str, str]], settings: Settings) -> None:
    from app.vision.factory import build_model_crop_identifier

    print("== Crop identification (server detectors); farmer_crops = none / ['Apple'] / ['Tomato']\n")
    identifier = build_model_crop_identifier(settings)
    rows, hits = [], Counter()
    for p in photos:
        data = [(IMAGES / p["filename"]).read_bytes()]
        row = [p["filename"].split("/")[-1]]
        for farmer in ([], ["Apple"], ["Tomato"]):
            r = identifier.identify(data, farmer)
            row.append(f"{r.crop_id} {r.confidence:.2f}{' ?' if r.needs_confirmation else ''}")
            hits[tuple(farmer)] += r.crop_id == "Apple"
        rows.append(row)
    table(["photo", "no profile", "farmer: Apple", "farmer: Tomato"], rows)
    print(f"Apple named: no profile {hits[()]}/{len(photos)}, farmer Apple {hits[('Apple',)]}/{len(photos)}, "
          f"farmer Tomato {hits[('Tomato',)]}/{len(photos)} ('?' = the farmer would be asked)\n")


def disease_section(photos: list[dict[str, str]], settings: Settings) -> None:
    from app.vision.factory import build_model_disease_classifier

    alias = {r["disease_id"]: r["treat_as"] for r in read_csv(CATALOGUE) if r["treat_as"]}

    def lenient(disease_id: str) -> str:
        return alias.get(disease_id, disease_id)

    print("== Disease classification, apple leaf photos: model B + A mixture (confidences are NOT calibrated)\n")
    leaf = [p for p in photos if p["set"] == "leaf_test"]
    classifiers = {w: build_model_disease_classifier(settings, apple_a_weight=w) for w in (0.0, 0.2, 0.5)}
    scores = {w: Counter() for w in classifiers}
    rows = []
    for p in leaf:
        data = [(IMAGES / p["filename"]).read_bytes()]
        row = [p["filename"].split("/")[-1], p["label"].replace("Apple___", "")]
        for w, classifier in classifiers.items():
            r = classifier.classify(data, "Apple")
            top = r.disease_id or "-"
            scores[w]["exact"] += top == p["label"]
            scores[w]["lenient"] += lenient(top) == lenient(p["label"])
            if w == 0.2:
                row.append(", ".join(f"{c.disease_id.replace('Apple___', '')} {c.confidence:.2f}" for c in r.candidates[:3]))
        rows.append(row)
    table(["photo", "label", "top 3 (A weight 0.2)"], rows)
    table(["A weight", "exact", "lenient (Brown spot=Marssonina, Scab&Rust=Scab)"],
          [[w, f"{scores[w]['exact']}/{len(leaf)}", f"{scores[w]['lenient']}/{len(leaf)}"] for w in classifiers])
    pea = classifiers[0.2].classify([(IMAGES / leaf[0]["filename"]).read_bytes()], "Pea")
    print(f"Crop without a photo model (Pea): model_covers_crop={pea.model_covers_crop}, disease_id={pea.disease_id}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--degrade", action="store_true", help="also test artificially degraded copies")
    ap.add_argument("--models", action="store_true", help="also run the real crop and disease models (needs the ml extra)")
    ap.add_argument("--crop-model", action="store_true", help="also run the real crop detectors only")
    ap.add_argument("--disease-model", action="store_true", help="also run the real disease models only")
    ap.add_argument("--limit", type=int, help="only the first N photos")
    ap.add_argument("--storage-dir", type=Path, help="where model weights are cached (default: settings.storage_dir)")
    args = ap.parse_args()
    photos = load_photos(args.limit)
    print(f"{len(photos)} photos from {IMAGES}\n")
    quality_section(photos)
    if args.degrade:
        degrade_section(photos)
    if args.models or args.crop_model or args.disease_model:
        models_section(photos, args.storage_dir, crop=args.models or args.crop_model, disease=args.models or args.disease_model)


if __name__ == "__main__":
    main()
