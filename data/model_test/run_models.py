# -*- coding: utf-8 -*-
"""Run the two pretrained apple/plant-disease models on the photo test set and write a review report.

  python run_models.py --dry-run          check files, labels, packages and internet; run nothing
  python run_models.py --limit 3          quick smoke test on 3 photos
  python run_models.py                    full run on the whole test set (leaf_test + fruit_info)
  python run_models.py --selftest         exercise the scoring/report code with FAKE probabilities (no packages needed)

NO TRAINING happens here. Models are only loaded and run. Nothing is uploaded: photos stay on this machine
(model files are downloaded from huggingface.co on the first run, then cached).
"""
import argparse, collections, csv, datetime, json, os, pathlib, platform, random, sys, time, traceback

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent
IMG = DATA / "images"

# ---------------------------------------------------------------------------------------------- models
MODEL_A = dict(key="A", title="A  On-device candidate: neghani/plantvillage-mobilenetv2 (38 PlantVillage classes)",
               repo="neghani/plantvillage-mobilenetv2", revision="d33601185b32cf05b3942661b8d84ffb86dc48ec",
               temperature=0.8845188130635788, published_threshold=0.5)
MODEL_B = dict(key="B", title="B  Server apple model: ixrbhii/apple-disease-convnext (8 apple classes)",
               repo="ixrbhii/apple-disease-convnext", expected_sha="8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a")
B_MAP = {"Apple Scab": "Apple___Apple_scab", "Apple Scab & Rust": "Apple___Apple_scab_rust", "Gray Spot": "Apple___Gray_spot",
         "Brown Spot": "Apple___Brown_spot", "Alternaria Leaf Spot": "Apple___Alternaria_leaf_spot", "Healthy": "Apple___healthy",
         "Marssonina Blotch": "Apple___Marssonina_blotch", "Root Rot / Collar Rot": "Apple___Root_rot_collar_rot"}
VARIANTS = ["default", "squash224"]   # default = each model's own recommended preprocessing (centre crop); squash224 = resize whole photo to 224x224
THRESHOLDS = [0.3, 0.45, 0.5, 0.65, 0.8, 0.9]


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


CATALOGUE = read_csv(DATA / "reference" / "disease_catalogue.csv")
ALIAS = {r["disease_id"]: r["treat_as"] for r in CATALOGUE if r["treat_as"]}       # e.g. Brown_spot -> Marssonina, scab_rust -> scab
A_LABELS = [r["disease_id"] for r in CATALOGUE if "ondevice_pv" in r["detectable_by"]]
RULES = json.loads((DATA / "reference" / "rules_config.json").read_text(encoding="utf-8"))
SHOW_T = RULES["confidence_policy"]["min_confidence_to_show_result"]
ADVICE_T = RULES["confidence_policy"]["min_confidence_for_auto_advice"]
lenient = lambda label: ALIAS.get(label, label)


def load_rows(limit=None):
    rows = [r for r in read_csv(IMG / "labels.csv") if r["set"] in ("leaf_test", "fruit_info")]
    return rows[:limit] if limit else rows


# ---------------------------------------------------------------------------------------------- inference
def load_model_a(device):
    import torch
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    proc = AutoImageProcessor.from_pretrained(MODEL_A["repo"], revision=MODEL_A["revision"])
    model = AutoModelForImageClassification.from_pretrained(MODEL_A["repo"], revision=MODEL_A["revision"]).to(device).eval()
    id2label = {int(k): v for k, v in model.config.id2label.items()}
    labels = [id2label[i] for i in range(len(id2label))]
    T = MODEL_A["temperature"]

    def predict(img, variant):
        from PIL import Image
        if variant == "squash224":
            inputs = proc(images=img.resize((224, 224), Image.BILINEAR), do_resize=False, do_center_crop=False, return_tensors="pt")
        else:
            inputs = proc(images=img, return_tensors="pt")
        with torch.no_grad():
            logits = model(**{k: v.to(device) for k, v in inputs.items()}).logits[0].float().cpu()
        return labels, torch.softmax(logits / T, -1).tolist(), labels
    return predict, dict(revision=MODEL_A["revision"], labels=len(labels))


def load_model_b(device):
    import torch, timm
    from torchvision import transforms
    model = timm.create_model(f"hf-hub:{MODEL_B['repo']}", pretrained=True).to(device).eval()
    raw_names = list(model.pretrained_cfg["label_names"])
    labels = [B_MAP.get(n, n) for n in raw_names]
    cfg = timm.data.resolve_data_config({}, model=model)
    tf_default = timm.data.create_transform(**cfg)
    size = tuple(cfg["input_size"][1:])
    tf_squash = transforms.Compose([transforms.Resize(size), transforms.ToTensor(), transforms.Normalize(cfg["mean"], cfg["std"])])
    sha = None
    try:
        from huggingface_hub import HfApi
        sha = HfApi().model_info(MODEL_B["repo"]).sha
    except Exception:
        pass

    def predict(img, variant):
        x = (tf_squash if variant == "squash224" else tf_default)(img).unsqueeze(0).to(device)
        with torch.no_grad():
            logits = model(x)[0].float().cpu()
        return labels, torch.softmax(logits, -1).tolist(), raw_names
    return predict, dict(revision=sha, expected_revision=MODEL_B["expected_sha"], labels=len(labels), input_size=size, raw_label_names=raw_names)


def run_model(loader, rows, device):
    from PIL import Image
    predict, info = loader(device)
    out = {v: {} for v in VARIANTS}
    for v in VARIANTS:
        for r in rows:
            img = Image.open(IMG / r["filename"]).convert("RGB")
            t0 = time.perf_counter()
            labels, probs, names = predict(img, v)
            out[v][r["filename"]] = dict(labels=labels, probs=probs, names=names, ms=(time.perf_counter() - t0) * 1000)
    return out, info


def fake_run(key, rows, seed=1):
    """FAKE probabilities for --selftest only."""
    rnd = random.Random(seed + (0 if key == "A" else 1))
    labels = A_LABELS if key == "A" else list(B_MAP.values())
    out = {v: {} for v in VARIANTS}
    for v in VARIANTS:
        for r in rows:
            w = [rnd.random() ** 3 for _ in labels]
            if key == "B" and rnd.random() < 0.6:
                w[labels.index(lenient(r["label"])) if lenient(r["label"]) in labels else 0] += 2.0
            s = sum(w)
            out[v][r["filename"]] = dict(labels=labels, probs=[x / s for x in w], names=labels, ms=rnd.uniform(20, 120))
    return out, dict(revision="FAKE", labels=len(labels))


# ---------------------------------------------------------------------------------------------- analysis
def view(pred, mask):
    labels, probs = pred["labels"], pred["probs"]
    if mask == "apple_only":
        idx = [i for i, l in enumerate(labels) if l.startswith("Apple___")]
        s = sum(probs[i] for i in idx) or 1e-12
        return [labels[i] for i in idx], [probs[i] / s for i in idx]
    return labels, probs


def top(labels, probs, k=5):
    order = sorted(range(len(labels)), key=lambda i: -probs[i])[:k]
    return [(labels[i], probs[i]) for i in order]


def score(rows, preds, mask):
    """Per-image results for one (model, variant, mask)."""
    res = []
    for r in rows:
        labels, probs = view(preds[r["filename"]], mask)
        t = top(labels, probs, 5)
        truth = r["label"]
        mass = sum(p for l, p in zip(labels, probs) if lenient(l) == lenient(truth))
        res.append(dict(row=r, top=t, p1=t[0][1], pred=t[0][0], strict=t[0][0] == truth, lenient=lenient(t[0][0]) == lenient(truth),
                        in_top3=any(lenient(l) == lenient(truth) for l, _ in t[:3]), mass=mass))
    return res


def pct(a, b):
    return "n/a" if b == 0 else f"{a}/{b} = {100 * a / b:.0f}%"


def md(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def short(label):
    return label.replace("Apple___", "")


def section(title, key, variant, mask, preds, rows, ms):
    leaf = [r for r in rows if r["set"] == "leaf_test"]
    fruit = [r for r in rows if r["set"] == "fruit_info"]
    sc = score(leaf, preds, mask)
    reliable = [s for s in sc if s["row"]["label_doubt"] in ("none", "low")]
    L = [f"### {title}", ""]
    classes = sorted({r["label"] for r in leaf})
    tab = []
    for c in classes:
        s = [x for x in sc if x["row"]["label"] == c]
        tab.append([short(c), len(s), pct(sum(x["strict"] for x in s), len(s)), pct(sum(x["lenient"] for x in s), len(s)), pct(sum(x["in_top3"] for x in s), len(s)),
                    f"{sum(x['mass'] for x in s) / max(len(s), 1):.2f}", f"{sum(x['p1'] for x in s) / max(len(s), 1):.2f}"])
    tab.append(["**all leaf photos**", len(sc), pct(sum(x["strict"] for x in sc), len(sc)), pct(sum(x["lenient"] for x in sc), len(sc)), pct(sum(x["in_top3"] for x in sc), len(sc)),
                f"{sum(x['mass'] for x in sc) / max(len(sc), 1):.2f}", f"{sum(x['p1'] for x in sc) / max(len(sc), 1):.2f}"])
    tab.append(["**reliable labels only**", len(reliable), pct(sum(x["strict"] for x in reliable), len(reliable)), pct(sum(x["lenient"] for x in reliable), len(reliable)),
                pct(sum(x["in_top3"] for x in reliable), len(reliable)), f"{sum(x['mass'] for x in reliable) / max(len(reliable), 1):.2f}",
                f"{sum(x['p1'] for x in reliable) / max(len(reliable), 1):.2f}"])
    L += [md(["True disease", "n", "Top-1 exact", "Top-1 lenient*", "Top-3 lenient*", "Mean prob. on true class", "Mean top-1 confidence"], tab), "",
          "*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.", ""]
    # what does the model say, per true disease
    L.append("**What the model answers for each true disease (top-1 counts):**\n")
    dist = []
    for c in classes:
        cnt = collections.Counter(short(x["pred"]) for x in sc if x["row"]["label"] == c)
        dist.append([short(c), "; ".join(f"{k} x{v}" for k, v in cnt.most_common())])
    L += [md(["True disease", "Answers"], dist), ""]
    # confidence thresholds
    thr = []
    for t in THRESHOLDS:
        ans = [x for x in sc if x["p1"] >= t]
        thr.append([f"{t:.2f}", pct(len(ans), len(sc)), pct(sum(x["lenient"] for x in ans), len(ans))])
    L += ["**Confidence cut-offs (leaf photos).** Our design uses show >= %.2f and auto-advice >= %.2f; model A's authors chose 0.50.\n" % (SHOW_T, ADVICE_T),
          md(["Cut-off", "Answered (coverage)", "Correct among answered (lenient)"], thr), ""]
    cw = [x for x in sc if (not x["lenient"]) and x["p1"] >= SHOW_T]
    L.append(f"**Confidently wrong (top-1 confidence >= {SHOW_T:.2f} and not the true disease): {len(cw)} of {len(sc)}**\n")
    if cw:
        L += [md(["Photo", "True", "Doubt", "Model said", "Confidence"], [[x["row"]["filename"].split("/")[-1], short(x["row"]["label"]), x["row"]["label_doubt"], short(x["pred"]), f"{x['p1']:.2f}"] for x in cw]), ""]
    # per-image table
    L.append("**Every leaf photo:**\n")
    L += [md(["Photo", "True", "Doubt", "1st answer (conf.)", "2nd", "3rd", "Right?"],
             [[x["row"]["filename"].split("/")[-1], short(x["row"]["label"]), x["row"]["label_doubt"], f"{short(x['top'][0][0])} ({x['top'][0][1]:.2f})",
               f"{short(x['top'][1][0])} ({x['top'][1][1]:.2f})", f"{short(x['top'][2][0])} ({x['top'][2][1]:.2f})", "yes" if x["lenient"] else "NO"] for x in sc]), ""]
    # fruit
    if fruit:
        fs = score(fruit, preds, mask)
        cnt = collections.Counter(short(x["pred"]) for x in fs)
        L.append(f"**Fruit photos (information only, not scored; true disease is scab):** answers {'; '.join(f'{k} x{v}' for k, v in cnt.most_common())}; mean confidence {sum(x['p1'] for x in fs) / len(fs):.2f}\n")
    allp = [v["ms"] for v in preds.values()]
    L.append(f"_Speed on this machine: {sum(allp) / len(allp):.0f} ms per photo on average (CPU, includes preprocessing). Not a phone speed._\n")
    return "\n".join(L)


def build_report(rows, results, infos, args, device, fake):
    leaf = [r for r in rows if r["set"] == "leaf_test"]
    L = []
    if fake:
        L += ["# SELFTEST: FAKE DATA. THESE NUMBERS MEAN NOTHING.", "", "This report was produced with random probabilities only to test the scoring code.", ""]
    L += ["# Model test report: apple leaf diseases", "",
          f"Run: {datetime.datetime.now():%Y-%m-%d %H:%M} | device: {device} | python {platform.python_version()} | photos: {len(leaf)} leaf + {len(rows) - len(leaf)} fruit", ""]
    for k, v in infos.items():
        L.append(f"- Model {k}: {json.dumps({a: b for a, b in v.items() if a != 'raw_label_names'})}")
    if "B" in infos and infos["B"].get("revision") and infos["B"].get("expected_revision") and infos["B"]["revision"] != infos["B"]["expected_revision"]:
        L.append("- **WARNING: model B has changed since this project pinned it (19 Oct 2026). Results may differ from earlier runs.**")
    L += ["", "## Read this first", "",
          "- **The photos look like web images, not the client's photos; labels are not agronomist-confirmed; source and licence unknown.** A score here is NOT a field measure.",
          "- **Very few photos per disease** (see n). One wrong answer moves a result by 9 to 25 points. Treat everything as a first look.",
          "- **Model A has no Alternaria or Marssonina class**, so it cannot be right for them. For those, read what it answers and how confident it is.",
          "- Model A's own published figures (model card): 16% top-1 on 25 PlantDoc field/web photos; at its 0.50 cut-off, 71% precision at 58% coverage on its 302-photo PlantDoc validation set.",
          "- Two preprocessing styles are shown. `default` = the model's recommended centre-crop. `squash224` = whole photo squeezed to 224x224 (model B's card says it was trained that way).", ""]
    for key, title in (("A", MODEL_A["title"]), ("B", MODEL_B["title"])):
        if key not in results:
            L += [f"## {title}", "", "**This model did not run (see the console error).**", ""]
            continue
        L += [f"## {title}", ""]
        masks = ["all_classes", "apple_only"] if key == "A" else ["apple_only"]
        for v in VARIANTS:
            for m in masks:
                label = {"all_classes": "all 38 classes", "apple_only": "apple classes only (crop picked first)"}[m]
                L.append(section(f"{key} / preprocessing: {v} / {label}", key, v, m, results[key][v], rows, None))
    # compare preprocessing
    L += ["## Does the preprocessing matter?", ""]
    comp = []
    for key in results:
        for m in (["all_classes", "apple_only"] if key == "A" else ["apple_only"]):
            row = [key, m]
            for v in VARIANTS:
                sc = score(leaf, results[key][v], m)
                row.append(pct(sum(x["lenient"] for x in sc), len(sc)))
            comp.append(row)
    L += [md(["Model", "Classes", "default: top-1 lenient", "squash224: top-1 lenient"], comp), "",
          "## Next", "", "Send this file and `predictions.csv` back for review. Do not train anything yet.", ""]
    return "\n".join(L)


def write_predictions(path, rows, results):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "preprocessing", "classes", "photo", "set", "true_label", "label_doubt", "top1", "p1", "top2", "p2", "top3", "p3", "exact", "lenient", "true_class_prob", "ms"])
        for key, byv in results.items():
            for v, preds in byv.items():
                for m in (["all_classes", "apple_only"] if key == "A" else ["apple_only"]):
                    for s in score(rows, preds, m):
                        t = s["top"]
                        w.writerow([key, v, m, s["row"]["filename"], s["row"]["set"], s["row"]["label"], s["row"]["label_doubt"], t[0][0], f"{t[0][1]:.4f}",
                                    t[1][0], f"{t[1][1]:.4f}", t[2][0], f"{t[2][1]:.4f}", int(s["strict"]), int(s["lenient"]), f"{s['mass']:.4f}", f"{preds[s['row']['filename']]['ms']:.0f}"])


# ---------------------------------------------------------------------------------------------- main
def check_env():
    ok = True
    for mod in ("PIL", "torch", "torchvision", "transformers", "timm", "huggingface_hub", "safetensors", "numpy"):
        try:
            m = __import__(mod)
            print(f"  ok       {mod:16s} {getattr(m, '__version__', '')}")
        except Exception as e:
            ok = False
            print(f"  MISSING  {mod:16s} ({type(e).__name__}: {e})")
    try:
        import urllib.request
        urllib.request.urlopen("https://huggingface.co", timeout=10)
        print("  ok       internet to huggingface.co")
    except Exception as e:
        print(f"  PROBLEM  cannot reach huggingface.co ({e}); the first run needs it to download the models")
        ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--models", default="AB")
    args = ap.parse_args()
    rows = load_rows(args.limit)
    leaf = [r for r in rows if r["set"] == "leaf_test"]
    missing = [r["filename"] for r in rows if not (IMG / r["filename"]).exists()]
    print(f"photos: {len(rows)} ({len(leaf)} leaf, {len(rows) - len(leaf)} fruit); missing files: {len(missing)}")
    for c, n in sorted(collections.Counter(r["label"] for r in leaf).items()):
        print(f"   leaf  {c:34s} {n}")
    if missing:
        sys.exit("Missing photo files: " + ", ".join(missing[:5]))
    if args.dry_run:
        print("\nchecking packages and internet:")
        ok = check_env()
        print("\nREADY to run." if ok else "\nNOT ready: fix the items marked MISSING / PROBLEM, then run --dry-run again.")
        sys.exit(0 if ok else 1)

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HERE / "results" / (("selftest_" if args.selftest else "run_") + stamp)
    out.mkdir(parents=True, exist_ok=True)
    results, infos = {}, {}
    for key, loader in (("A", load_model_a), ("B", load_model_b)):
        if key not in args.models:
            continue
        print(f"\n=== model {key} ===")
        try:
            if args.selftest:
                results[key], infos[key] = fake_run(key, rows)
            else:
                results[key], infos[key] = run_model(loader, rows, args.device)
            print("done:", infos[key])
        except Exception:
            print(f"MODEL {key} FAILED. Copy everything below and send it to me:\n")
            traceback.print_exc()
    if not results:
        sys.exit("No model ran.")
    (out / "report.md").write_text(build_report(rows, results, infos, args, args.device, args.selftest), encoding="utf-8")
    write_predictions(out / "predictions.csv", rows, results)
    (out / "run_info.json").write_text(json.dumps(dict(infos=infos, python=platform.python_version(), args=vars(args), fake=args.selftest), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out / 'report.md'}\n      {out / 'predictions.csv'}")


if __name__ == "__main__":
    main()
