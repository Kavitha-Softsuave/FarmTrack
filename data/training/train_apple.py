"""Train the FarmTrack apple leaf classifier (4 classes) by transfer learning and export it for backend/app/vision/torch_models.py.

    python train_apple.py                      # full run (about 10-25 min on a CPU)
    python train_apple.py --quick              # smoke test: 20 images per class, 1 augmented view
    python train_apple.py --arch convnext_small.fb_in22k_ft_in1k --views 6

What it does
  1. Reads photos/<class_id>/*, drops unreadable files and exact duplicates, and groups near-duplicates (perceptual hash, also flipped /
     rotated) so that copies of one leaf never land on both sides of a split.
  2. Splits by group: 20 % held-out TEST (never used for any choice), the rest = train/validation. 5-fold stratified group CV on the rest
     gives the cross-validated numbers; the final model is trained on all non-test images.
  3. Frozen ImageNet backbone (no apple/leaf data in its pre-training, so the evaluation is not contaminated). Features are cached for
     N heavily augmented views per image plus one clean view; only the linear head is trained on them (fast on CPU).
  4. Fits a temperature on out-of-fold logits and folds it into the head, so the exported probabilities are calibrated.
  5. Exports output/apple_leaf_v1/{model.safetensors, config.json, metrics.json, model_card.md} in the format TimmClassifier reads.

Labels are folder names, NOT confirmed by an agronomist. Accuracy here is on web / research-dataset images, not field photos.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
CLASSES = ["Apple___Apple_scab", "Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot", "Apple___healthy"]
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CACHE_SHORT = 256            # images are cached with the shorter side at 256 px (decode once; also evens out resolution between sources)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ----------------------------------------------------------------------------- data
def source_of(name: str) -> str:
    return {"al9": "AppleLeaf9", "jk": "J&K-Mendeley", "pd": "PlantDoc"}.get(name.split("_")[0], "other")


def scan(photos: Path, per_class_cap: int | None, seed: int):
    """-> list of (path, class_idx, source). Drops unreadable files and exact duplicates."""
    items, seen, dropped = [], {}, Counter()
    for ci, cid in enumerate(CLASSES):
        files = sorted(p for p in (photos / cid).glob("*") if p.suffix.lower() in EXTS) if (photos / cid).is_dir() else []
        random.Random(seed + ci).shuffle(files)
        kept = 0
        for p in files:
            if per_class_cap and kept >= per_class_cap:
                break
            try:
                with Image.open(p) as im:
                    im.verify()
            except Exception:
                dropped["unreadable"] += 1
                continue
            h = hashlib.md5(p.read_bytes()).hexdigest()
            if h in seen:
                dropped["exact duplicate"] += 1
                continue
            seen[h] = p
            items.append((p, ci, source_of(p.name)))
            kept += 1
    return items, dropped


def load_cached(path: Path) -> Image.Image:
    im = Image.open(path)
    im = im.convert("RGB")
    w, h = im.size
    if path.name.startswith("jk_"):
        # the Kashmir dataset ships pre-augmented images (rotations padded with smeared edge pixels, only in that source): keep the
        # central 70 % so the smear cannot become a shortcut for "not scab / not Marssonina"
        dx, dy = int(w * 0.15), int(h * 0.15)
        im = im.crop((dx, dy, w - dx, h - dy))
        w, h = im.size
    s = CACHE_SHORT / min(w, h)
    if s < 1:
        im = im.resize((max(CACHE_SHORT, round(w * s)), max(CACHE_SHORT, round(h * s))), Image.Resampling.BILINEAR)
    return im


def hash_bits(im: Image.Image) -> np.ndarray:
    """64-bit difference hashes of the image and its flips/rotation (so rotated/flipped copies are found), as bool arrays (4, 64)."""
    base = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    out = []
    for v in (base, base.transpose(Image.Transpose.FLIP_LEFT_RIGHT), base.transpose(Image.Transpose.FLIP_TOP_BOTTOM),
              base.transpose(Image.Transpose.ROTATE_180)):
        a = np.asarray(v, dtype=np.int16)
        out.append((a[:, 1:] > a[:, :-1]).reshape(-1))
    return np.stack(out)


def group_near_duplicates(hashes: list[np.ndarray], thresh: int = 5) -> list[int]:
    n = len(hashes)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    orig = np.stack([h[0] for h in hashes])                      # (n, 64)
    for i in range(n):
        variants = hashes[i]                                       # (4, 64)
        dist = (variants[:, None, :] != orig[None, :, :]).sum(-1).min(0)   # (n,)
        for j in np.nonzero(dist <= thresh)[0]:
            if j != i:
                parent[find(int(j))] = find(i)
    roots = {}
    return [roots.setdefault(find(i), len(roots)) for i in range(n)]


def stratified_group_split(y, groups, n_splits, seed):
    from sklearn.model_selection import StratifiedGroupKFold
    return list(StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(np.zeros(len(y)), y, groups))


# ----------------------------------------------------------------------------- model / features
def eval_transform(img: Image.Image, size: int, mean, std) -> np.ndarray:
    """Same numerics as backend/app/vision/torch_models.py preprocess_timm (shorter side -> size, centre crop, normalise)."""
    w, h = img.size
    short = min(w, h)
    nw, nh = max(size, int(size * w / short)), max(size, int(size * h / short))
    r = img.convert("RGB").resize((nw, nh), Image.Resampling.BILINEAR)
    left, top = int(round((nw - size) / 2.0)), int(round((nh - size) / 2.0))
    px = np.asarray(r.crop((left, top, left + size, top + size)), dtype=np.float32) / np.float32(255.0)
    px = (px - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    return np.ascontiguousarray(px.transpose(2, 0, 1), dtype=np.float32)


def make_aug(size: int, mean, std):
    import torch
    from torchvision.transforms import v2 as T

    tf = T.Compose([
        T.RandomResizedCrop(size, scale=(0.35, 1.0), ratio=(0.75, 1.33), interpolation=T.InterpolationMode.BILINEAR, antialias=True),
        T.RandomHorizontalFlip(), T.RandomVerticalFlip(0.3),
        T.RandomApply([T.RandomRotation(35)], p=0.6),
        T.ColorJitter(brightness=0.35, contrast=0.35, saturation=0.35, hue=0.04),
        T.RandomGrayscale(0.08),
        T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 1.8))], p=0.3),
        T.RandomApply([T.RandomAffine(0, translate=(0.1, 0.1), scale=(0.9, 1.1))], p=0.3),
    ])
    m = torch.tensor(mean).view(3, 1, 1)
    s = torch.tensor(std).view(3, 1, 1)

    def run(img: Image.Image):
        out = tf(img)
        t = torch.from_numpy(np.asarray(out, dtype=np.float32) / 255.0).permute(2, 0, 1)
        return (t - m) / s
    return run


def extract(net, tensors, bs=32):
    import torch
    feats = []
    with torch.inference_mode():
        for i in range(0, len(tensors), bs):
            x = torch.stack(tensors[i:i + bs])
            feats.append(net.forward_head(net.forward_features(x), pre_logits=True).float().cpu())
    return torch.cat(feats).numpy()


def train_head(X, y, n_cls, epochs, seed, weights=None, wd=1e-2, lr=2e-3, ls=0.1):
    import torch
    torch.manual_seed(seed)
    d = X.shape[1]
    fc = torch.nn.Linear(d, n_cls)
    opt = torch.optim.AdamW(fc.parameters(), lr=lr, weight_decay=wd)
    Xt, yt = torch.from_numpy(X), torch.from_numpy(y)
    cw = torch.tensor(weights, dtype=torch.float32) if weights is not None else None
    loss_fn = torch.nn.CrossEntropyLoss(weight=cw, label_smoothing=ls)
    n = len(Xt)
    steps = epochs * ((n + 127) // 128)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, 128):
            idx = perm[i:i + 128]
            opt.zero_grad()
            loss_fn(fc(Xt[idx]), yt[idx]).backward()
            opt.step()
            sched.step()
    return fc


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_temperature(logits, y):
    best, bt = 1e9, 1.0
    for t in np.arange(0.4, 6.0, 0.02):
        p = softmax(logits / t)
        nll = -np.log(p[np.arange(len(y)), y] + 1e-12).mean()
        if nll < best:
            best, bt = nll, float(t)
    return bt


def ece(p, y, bins=10):
    conf, pred = p.max(1), p.argmax(1)
    e = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf > lo) & (conf <= lo + 1 / bins)
        if m.any():
            e += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(e)


def report(y, pred, probs=None, srcs=None):
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
    p, r, f, s = precision_recall_fscore_support(y, pred, labels=range(len(CLASSES)), zero_division=0)
    out = {"n": int(len(y)), "accuracy": float((y == pred).mean()),
           "macro_f1": float(np.mean(f)),
           "per_class": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])} for i, c in enumerate(CLASSES)},
           "confusion_matrix": {"rows_true_cols_pred": CLASSES, "matrix": confusion_matrix(y, pred, labels=range(len(CLASSES))).tolist()}}
    if probs is not None:
        out["mean_confidence_correct"] = float(probs.max(1)[pred == y].mean()) if (pred == y).any() else None
        out["mean_confidence_wrong"] = float(probs.max(1)[pred != y].mean()) if (pred != y).any() else None
        out["ece"] = ece(probs, y)
    if srcs is not None:
        srcs = np.asarray(srcs)
        out["accuracy_by_source"] = {s_: {"n": int((srcs == s_).sum()), "accuracy": float((y[srcs == s_] == pred[srcs == s_]).mean())} for s_ in sorted(set(srcs))}
    return out


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", default=str(HERE / "photos"))
    ap.add_argument("--out", default=str(HERE / "output" / "apple_leaf_v1"))
    ap.add_argument("--arch", default="convnext_tiny.fb_in22k_ft_in1k", help="timm model name (pretrained tag included)")
    ap.add_argument("--views", type=int, default=8, help="augmented views per training image")
    ap.add_argument("--cap", type=int, default=450, help="max images per class (keeps classes comparable)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--eval-dir", action="append", default=[str(HERE.parent / "images" / "testset_v1" / "leaf"), str(HERE / "external_test")],
                    help="extra folder-per-class sets to evaluate (never trained on); skipped if missing")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    if a.quick:
        a.cap, a.views, a.epochs, a.folds = 20, 1, 5, 2

    import timm
    import torch
    torch.set_num_threads(max(1, torch.get_num_threads()))
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)

    items, dropped = scan(Path(a.photos), a.cap, a.seed)
    counts = Counter(CLASSES[c] for _, c, _ in items)
    log("images", dict(counts), "dropped", dict(dropped))
    missing = [c for c in CLASSES if counts[c] < 10]
    if missing:
        sys.exit(f"too few photos for {missing}: see README.md")
    log("loading and caching images")
    imgs = [load_cached(p) for p, _, _ in items]
    y = np.array([c for _, c, _ in items])
    srcs = [str(s) for _, _, s in items]
    groups = np.array(group_near_duplicates([hash_bits(i) for i in imgs]))
    log(f"{len(set(groups))} groups from {len(imgs)} images (near-duplicate clusters merged: {len(imgs) - len(set(groups))})")

    # ---- split: held-out test, then CV on the rest
    outer = stratified_group_split(y, groups, 5, a.seed)
    trainval_idx, test_idx = outer[0]
    log(f"test {len(test_idx)}  train/val {len(trainval_idx)}  (group-disjoint: {not (set(groups[test_idx]) & set(groups[trainval_idx]))})")

    net = timm.create_model(a.arch, pretrained=True, num_classes=0).eval()    # num_classes=0: backbone only
    cfg = net.pretrained_cfg
    size, mean, std = int(cfg["input_size"][1]), list(cfg["mean"]), list(cfg["std"])
    arch_name = a.arch.split(".")[0]
    aug = make_aug(size, mean, std)
    log("arch", arch_name, "input", size, "feature dim", net.num_features)

    t0 = time.time()
    log("clean features")
    clean = extract(net, [torch.from_numpy(eval_transform(i, size, mean, std)) for i in imgs])
    # augmented views only for train/val images (test is evaluated clean, as the app sees it)
    aug_X, aug_y, aug_idx = [], [], []
    for v in range(a.views):
        log(f"augmented view {v + 1}/{a.views}  ({time.time() - t0:.0f}s)")
        aug_X.append(extract(net, [aug(imgs[i]) for i in trainval_idx]))
        aug_y.append(y[trainval_idx]); aug_idx.append(trainval_idx)
    aug_X = np.concatenate(aug_X) if aug_X else np.zeros((0, clean.shape[1]), np.float32)
    aug_y = np.concatenate(aug_y) if aug_y else np.zeros(0, int)
    aug_idx = np.concatenate(aug_idx) if aug_idx else np.zeros(0, int)
    log(f"features done in {time.time() - t0:.0f}s")

    def train_on(idx):
        m = np.isin(aug_idx, idx)
        X = np.concatenate([clean[idx], aug_X[m]]).astype(np.float32)
        yy = np.concatenate([y[idx], aug_y[m]]).astype(np.int64)
        w = len(yy) / (len(CLASSES) * np.maximum(np.bincount(yy, minlength=len(CLASSES)), 1))
        return train_head(X, yy, len(CLASSES), a.epochs, a.seed, weights=w)

    def logits_of(fc, X):
        with torch.inference_mode():
            return fc(torch.from_numpy(X.astype(np.float32))).numpy()

    # ---- cross-validation on train/val (group-disjoint folds)
    folds = stratified_group_split(y[trainval_idx], groups[trainval_idx], a.folds, a.seed + 1)
    oof = np.zeros((len(trainval_idx), len(CLASSES)), dtype=np.float32)
    for k, (tr, va) in enumerate(folds):
        fc = train_on(trainval_idx[tr])
        oof[va] = logits_of(fc, clean[trainval_idx[va]])
        log(f"fold {k + 1}/{len(folds)} accuracy {(oof[va].argmax(1) == y[trainval_idx[va]]).mean():.3f}")
    ytv = y[trainval_idx]
    T = fit_temperature(oof, ytv)
    cv = report(ytv, oof.argmax(1), softmax(oof / T), [srcs[i] for i in trainval_idx])
    cv["temperature"] = T
    cv["ece_uncalibrated"] = ece(softmax(oof), ytv)
    log(f"CV accuracy {cv['accuracy']:.3f} macro-F1 {cv['macro_f1']:.3f}  T={T:.2f}")

    # ---- final model on all train/val, test once
    fc = train_on(trainval_idx)
    lt = logits_of(fc, clean[test_idx])
    test = report(y[test_idx], lt.argmax(1), softmax(lt / T), [srcs[i] for i in test_idx])
    log(f"TEST accuracy {test['accuracy']:.3f} macro-F1 {test['macro_f1']:.3f}")

    # ---- fold temperature into the head, build the full timm model, export
    full = timm.create_model(arch_name, pretrained=False, num_classes=len(CLASSES))
    sd = {k: v for k, v in net.state_dict().items()}
    sd["head.fc.weight"] = fc.weight.detach() / T
    sd["head.fc.bias"] = fc.bias.detach() / T
    full.load_state_dict(sd)
    full.eval()

    # ---- extra sets (never trained on), through the full exported model
    extra = {}
    for d in a.eval_dir:
        dp = Path(d)
        if not dp.is_dir():
            continue
        xs, ys, names = [], [], []
        for ci, cid in enumerate(CLASSES):
            for p in sorted((dp / cid).glob("*")) if (dp / cid).is_dir() else []:
                if p.suffix.lower() in EXTS:
                    xs.append(torch.from_numpy(eval_transform(Image.open(p), size, mean, std))); ys.append(ci); names.append(p.name)
        if not xs:
            continue
        with torch.inference_mode():
            pr = torch.softmax(full(torch.stack(xs)), -1).numpy()
        r = report(np.array(ys), pr.argmax(1), pr)
        r["predictions"] = {n: [CLASSES[int(q.argmax())], round(float(q.max()), 3)] for n, q in zip(names, pr)}
        extra[str(dp.name)] = r
        log("extra set", dp.name, "n", len(ys), "accuracy", round(r["accuracy"], 3))

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from safetensors.torch import save_file
    state = {k: v.detach().half().contiguous() for k, v in full.state_dict().items()}
    save_file(state, str(out / "model.safetensors"))
    (out / "config.json").write_text(json.dumps({
        "architecture": arch_name, "num_classes": len(CLASSES), "label_names": CLASSES,
        "pretrained_cfg": {"input_size": [3, size, size], "mean": mean, "std": std, "crop_pct": 1.0, "interpolation": "bilinear"},
        "label_descriptions": {c: c for c in CLASSES},
        "note": "FarmTrack apple leaf v1: frozen ImageNet backbone + linear head, labels unconfirmed by an agronomist, see model_card.md",
    }, indent=2), encoding="utf-8")
    metrics = {
        "created": time.strftime("%Y-%m-%d %H:%M"), "arch": a.arch, "args": vars(a), "images_per_class": dict(counts), "dropped": dict(dropped),
        "images_per_source": dict(Counter(srcs)), "n_groups": int(len(set(groups))),
        "cross_validation_on_trainval": cv, "held_out_test": test, "extra_sets": extra,
        "caveats": ["Labels = dataset folder names; no agronomist confirmed them (Marssonina = dataset class 'Brown spot', inferred).",
                    "Each class comes mostly from a different source/imaging setup, so part of the accuracy may be source recognition, not disease recognition.",
                    "Research/web images, not field photos from Himachal farmers: field accuracy will be lower. Never quote these numbers as 90-95%.",
                    "Test split is group-disjoint but drawn from the same datasets as training.",
                    "Marssonina photos come from ONE source (AppleLeaf9 'Brown spot'), so its recall is largely source recognition; check external_test/ (independent real photos).",
                    "The Kashmir (J&K) images are pre-augmented by their authors; the central 70 % is used and siblings of one leaf may survive grouping, so J&K accuracy is optimistic."],
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_model_card(out, metrics, Path(a.photos).parent / "sources.csv")
    # sanity: reload with the same code path the backend uses
    from safetensors.torch import load_file
    chk = timm.create_model(arch_name, pretrained=False, num_classes=len(CLASSES))
    chk.load_state_dict({k: v.float() for k, v in load_file(str(out / "model.safetensors")).items()})
    log("exported to", out, f"({(out / 'model.safetensors').stat().st_size / 1e6:.0f} MB)")


def write_model_card(out: Path, m: dict, sources_csv: Path):
    lic = Counter()
    if sources_csv.exists():
        with sources_csv.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lic[(r["licence"], r["author"][:60])] += 1
    cv, te = m["cross_validation_on_trainval"], m["held_out_test"]

    def table(rep):
        rows = ["| class | precision | recall | F1 | n |", "|---|---|---|---|---|"]
        for c, v in rep["per_class"].items():
            rows.append(f"| {c} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} | {v['support']} |")
        return "\n".join(rows)

    def cm(rep):
        c = rep["confusion_matrix"]
        rows = ["| true \\ predicted | " + " | ".join(x.replace("Apple___", "") for x in c["rows_true_cols_pred"]) + " |", "|---|" + "---|" * len(CLASSES)]
        for name, row in zip(c["rows_true_cols_pred"], c["matrix"]):
            rows.append(f"| {name.replace('Apple___', '')} | " + " | ".join(map(str, row)) + " |")
        return "\n".join(rows)

    ex = ""
    for k, r in m["extra_sets"].items():
        ex += f"\n**{k}** ({r['n']} photos, never trained on): accuracy {r['accuracy']:.2f}\n" + "".join(
            f"- {n}: {p[0]} ({p[1]})\n" for n, p in r["predictions"].items())
    (out / "model_card.md").write_text(f"""# FarmTrack apple leaf classifier v1 (internal demo model)

Created {m['created']} by `data/training/train_apple.py`. Classes: {', '.join(CLASSES)}.
Architecture `{m['arch']}` (timm), ImageNet-pretrained backbone frozen, linear head trained, temperature folded into the head. fp16 weights.

## Status: NOT validated for farmers
Labels are dataset folder names, **not confirmed by an agronomist**. The Marssonina class is the datasets' "Brown spot" (inferred to be
*Diplocarpon mali*). Accuracy below is on research/web images and does not describe field photos from Himachal. Do not quote 90-95 %.

## Data (photos are not redistributed; provenance per file in `data/training/sources.csv`)
Images per class used: {m['images_per_class']}. Images per source: {m['images_per_source']}. Image groups after merging near-duplicates: {m['n_groups']}.
Licences recorded in sources.csv (rows): {dict((f'{a} / {b}', n) for (a, b), n in lic.items())}.
All sources are CC BY 4.0 (attribution required: AppleLeaf9 compilers Yang, Duan and Wang, Agronomy 2022, 12(11), 2784; Yatoo and Sharma, Mendeley Data, DOI 10.17632/9m2dcb5mmr.3).

## Cross-validation ({m['args']['folds']}-fold, group-disjoint, on train/val): accuracy {cv['accuracy']:.3f}, macro-F1 {cv['macro_f1']:.3f}
{table(cv)}

{cm(cv)}

## Held-out test (group-disjoint, {te['n']} photos): accuracy {te['accuracy']:.3f}, macro-F1 {te['macro_f1']:.3f}
{table(te)}

{cm(te)}

Calibration: temperature {cv['temperature']:.2f}; ECE {cv['ece_uncalibrated']:.3f} before, {cv.get('ece', float('nan')):.3f} after (out-of-fold).
Accuracy by source (test): {te.get('accuracy_by_source')}

## Other sets
{ex or 'none found'}

## Limits
""" + "\n".join(f"- {c}" for c in m["caveats"]) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
