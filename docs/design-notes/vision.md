# Vision notes (agent VISION, 19 Oct 2026)

Code: `backend/app/vision/` (`quality.py`, `crop.py`, `disease.py`, `labels.py`, `inference.py`, `torch_models.py`, `fallback.py`, `factory.py`), tests `backend/tests/vision/` (297 tests, offline, no torch), script `backend/scripts/evaluate_vision.py`. Checked: pytest 297 passed, ruff clean, mypy clean on `app/vision`.

## 1. Photo quality gate: thresholds and the numbers behind them

Measured on the 23 leaf photos (+5 fruit) of `data/images/testset_v1` with the final code (`python scripts/evaluate_vision.py --degrade`). Blur = variance of a 4-neighbour Laplacian of the grayscale, long side shrunk to 512 px (BOX). Brightness = mean luma 0..255. Vegetation = share of pixels with hue 10-170 deg, saturation >= 0.15, value >= 0.12.

| Measure | Real leaf photos (n=23) | Threshold | Margin |
|---|---|---|---|
| Blur score | 170 (ALT_02) to 2895; median ~700 | blurry if < **60** | lowest real photo is 2.8x above |
| Brightness | 77 to 183 | dark < **45**, bright > **225** | no real photo near either |
| Vegetation share | 40% (MAR_01) to 99% | no_leaf if < **5%** | 8x below the lowest real photo |
| Short side | 240 px (SCB_05r) | too_small if < **200 px** | |

Artificially degraded copies of the 23 leaf photos (JPEG q90), what the gate says:

| Variant | Blur score range | Verdicts |
|---|---|---|
| Gaussian blur sigma 1.0 | 27-410 | 9 blurry, 14 usable (mild blur is NOT flagged on purpose) |
| sigma 1.5 | 12-129 | 22 blurry, 1 usable |
| sigma 2 / sigma 3 | 6-56 / 4-18 | 23 blurry / 23 blurry |
| darker x0.3 | | 21 too_dark, 2 usable |
| darker x0.2 | | 23 too_dark |
| brighter x2.5 / x3.5 | | 9 / 19 too_bright (the rest are still usable) |

Result: **all 23 real leaf photos and all 5 fruit photos are usable**; sigma >= 2 blur and x0.2 darkness are always caught. Thresholds are constructor arguments of `PillowQualityChecker`.

Decisions
- Conservative by design: the thresholds sit far outside the real range, a photo is unusable only when an issue is found.
- On a badly exposed photo blur and colour are **not judged** (they are meaningless there); the farmer retakes it first and the next check covers them. `blur_score` and `brightness` are still reported.
- Several issues: the tip spoken is the most fundamental (unreadable, too_small, too_dark, too_bright, no_leaf, blurry). `unreadable` also speaks `scan_retake_blurry` as specified.
- Images over 100 million pixels are refused as unreadable (decompression bomb guard). JPEGs are decoded at reduced size (PIL `draft`) for speed.
- The vegetation test is wide on purpose (brown and orange-brown count, so a hand, soil or wood also pass). It only catches obviously non-plant pictures (sky, grey concrete, a screen, white paper). The crop model's `unknown` is the second line.

Doubts
- **Calibrated on web images (240-757 px, already compressed), not on phone photos.** Phone photos shrunk to 512 px are probably sharper, so 60 is probably lax; motion blur and focus-on-background cases are untested. Re-tune on the client's field photos (the test pack: `evaluate_vision.py --degrade`).
- Backlit or heavily shaded leaves can read dark; not measured.

## 2. Crop identification

### What the ixrbhii repo contains (checked 19 Oct 2026 through the HF API)
- `ixrbhii/multicrop-disease-models` @ `ac1536cdd3290ba5ab3b6d9c8149638500434e52` (CC-BY-4.0, updated 4 Oct 2026): 42 per-crop disease folders + `detectors/original` (16 crops, 99.8% on 2,621 own-test photos) + `detectors/new` (36 crops, 98.3-98.4% on 6,167) + `index.json` with SHA-256. The collection lists 46 items: the same 44 models as separate repos, the Q&A dataset and the combined repo.
- The standalone detector repos have **identical weights** (same SHA-256 as `detectors/original` and `detectors/new`); I pin these because their `config.json` carries `label_names`:
  - 16-crop: `ixrbhii/leaf-crop-detector-16-convnext` @ `87da121765fcfa7d2d20c1798fb06de495499eed`
  - 36-crop: `ixrbhii/leaf-crop-detector-36-convnext` @ `e2e60f990a4f07e004ce19fe2f146849bd65d1ba`
  - apple model B: `ixrbhii/apple-disease-convnext` @ `8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a` (unchanged); model A: `neghani/plantvillage-mobilenetv2` @ `d33601185b32cf05b3942661b8d84ffb86dc48ec`.
- ConvNeXt-Small, 224x224, ImageNet mean/std, weights stored in half precision (loaded as float32), ~99 MB each. Total download for all four models ~306 MB.
- Labels. 16: Apple, Banana, Brinjal, Cashew, Custard Apple, Cherry, Coconut, Guava, Mango, Mulberry, Papaya, Rose, Strawberry, Watermelon, Okra, Pomegranate. 36: Apple, Apricot, Betel, Bitter Gourd, Black Pepper, Bottle Gourd, Cashew, Cassava, Cherry, Chrysanthemum, Citrus (Orange / Lemon), Coffee, Cucumber, Cucurbit (Pumpkin / Melon), Fig, Grape, Loquat, Maize, Mango, Peach, Pear, Pepper, Potato, Raspberry, Rice, Ridge Gourd, Rose, Snake Gourd, Sorghum, Soybean, Squash, Strawberry, Sugarcane, Tea, Tomato, Walnut. Six crops are in both; **10 are only in the 16-detector, 30 only in the 36-detector.**
- **Not in either detector:** pea, cauliflower, cabbage, wheat, ginger, kiwi, plum, barley, beans (and every crop outside the lists). The detectors are closed-world: the card says unknown crops "can be taken for a known crop".
- The repo's own "photo-first flow": run the 16-detector; the 36-detector overrides it when it names a crop outside {Apple, Mango, Cashew, Cherry, Strawberry, Rose} with >= 80%; refuse the photo when the crop detector is < 60%.

### Mapping to catalogue crop ids (`labels.canonical_crop`)
Title_Case with underscores: Apple, Tomato, Potato, Maize, Grape, Pear, Walnut, Apricot, Peach, Cherry, Pomegranate, Custard_Apple, Bitter_Gourd ...; `Citrus (Orange / Lemon)` -> **Citrus**, `Cucurbit (...)` -> Cucurbit. Aliases accepted everywhere (farmer profile, client guess): Corn -> Maize, Paddy -> Rice, **Capsicum / Bell pepper -> Pepper**, Orange / Lemon -> Citrus, Peas -> Pea. Doubt: the data catalogue says `Pepper` (PlantVillage name) while the plan says "capsicum"; I follow the data. If the rules/product master add capsicum rows they must use `Pepper` or call `canonical_crop`.

### Combination rule (ModelCropIdentifier)
- I did **not** copy the vendor's override rule (it hands the win to the 36-detector whenever it is >= 80%, even when it is the one that does not know the crop). Instead: per detector average the probabilities over the photos; **evidence of a crop = max over the two detectors**, renormalise. If the detectors confidently name different crops the margin collapses and the farmer is asked, which is the safe outcome.
- Farmer crops no detector knows (pea, wheat, kiwi ...) get the detectors' leftover doubt (1 - best probability) as evidence so a confused detector can still land on the farmer's own crop.
- posterior = evidence x prior (1.0 for the farmer's crops, **0.15** for others, so a new crop can still win), renormalised.
- `needs_confirmation` when: winner not in the farmer's crops (profile known), margin to the runner-up < 0.25, the detectors' own probability for the winner < 0.6 (the repo card's refusal level), or the prior changed the detectors' favourite. An empty profile is "no information" and does not force a question by itself.
- `unknown` (crop_id None) when the winner's posterior < 0.30 (flat detector output). All constants are constructor arguments. **Heuristic; confidences are not calibrated.**
- The on-device guess is ignored by the server model (the on-device model was confidently wrong in the field test). `ProfileCropIdentifier` (stub/fallback) uses it; its decision table is in its docstring, every branch has a test.

### Smoke run with the real detectors (28 test photos, all apple; web images, so directional only)
| Farmer crops given | Apple named | Farmer asked ("?") |
|---|---|---|
| none | **22/28** (others: Rose, Cherry x3, Soybean, Peach) | 11/28 |
| ['Apple'] | **28/28** | 6/28 (exactly the six where the prior overrode the detectors) |
| ['Tomato'] (wrong profile) | 22/28 (the profile does not force a wrong answer) | **28/28** |

So without the farmer prior the detectors named a wrong crop for 21% of these apple photos: the prior and the confirmation rule matter. Never read as a field accuracy.

## 3. Disease classifier

- Faithful port of `data/model_test/run_models.py`: **parity check against `results/run_20261019_141524/predictions.csv`** (model B default preprocessing, model A apple-only): max |p1 difference| 0.0001 (B) and 0.0000 (A), **0 top-1 mismatches** on the 23 leaves. Smoke output of the integrated classifier: B alone **6/23 exact, 11/23 lenient** (same as the review).
- Model A: softmax(logits / 0.8845) over 38 classes, then the crop mask (restrict to the crop's classes, renormalise, identical to a softmax over that subset). Per photo, then averaged over photos.
- Covered crops (A): Apple, Cherry, Maize, Grape, Peach, Pepper, Potato, Strawberry, Tomato. **Crops with a single PlantVillage class (Blueberry, Raspberry, Soybean, Citrus/Orange, Squash) are NOT covered**: a one-class mask is always 1.0 and says nothing about the leaf. Pepper is covered with 2 classes (bacterial spot, healthy) although the plan says "no model for capsicum"; no approved data exists for it anyway.
- Apple adds model B (8 classes, `B_MAP` -> catalogue ids; Brown spot and Scab & Rust keep their own ids, the rules apply `treat_as`). Merge: B carries the answer; A contributes only where B has the same class (scab, healthy): `p = (1-w) B + w A`, w = 0.2, renormalised; A's black rot and cedar rust mass is dropped (B never says them, A's apple answers were unreliable, cedar rust does not occur on apple in India). My first version injected those two classes; they appeared as noisy 2nd candidates (up to 0.20) and w = 0.5 cost 2 lenient hits, so I restricted the merge. With the final merge **w = 0, 0.2 and 0.5 all give 6/23 exact and 11/23 lenient**: A adds nothing measurable; 0.2 is kept because the brief asks for the merge.
- **Confidence values are not calibrated and did not separate right from wrong in the field test** (documented in the module docstring). Rules must not rely on them.
- Label tables are checked against `data/reference/disease_catalogue.csv`: the 38 PlantVillage labels are exactly the catalogue's `ondevice_pv` ids, the 8 B labels map to 8 distinct `server_apple` ids.
- Not wired (phase 2 / later): the per-crop ixrbhii disease models (pear, walnut, apricot, peach, cherry, pomegranate, citrus, mango, strawberry, cucumber, grape, maize, potato, tomato ...). They would need label-to-catalogue mappings and agronomy rows; today crops without A/B report `model_covers_crop=False`.
- `StubDiseaseClassifier`: covers the 5 demo crops with `disease_id None` unless `hints={'Apple': 'Apple___Apple_scab'}` (value or `(id, confidence)`) is passed; `build_disease_classifier(settings, stub_hints=...)` forwards it so a demo can force a result.
- Candidate confidences are truncated (not rounded) to 4 decimals so they never add up to more than 1.

## 4. Models, caching, fallback, performance

- Real loading is lazy and optional: `torch`, `timm`, `transformers`, `huggingface_hub`, `safetensors` are imported only inside functions of `torch_models.py` (a test proves `import app.vision.factory` imports none of them). `provider='model'` without them logs one warning and returns the stub/profile implementation.
- Weights are cached under `settings.storage_dir/models` (HF cache layout). Pinned commits are immutable, so the cache is tried first (`local_files_only`), the network only when files are missing. `warm_up_models(settings)` downloads and loads everything (use it at deploy / image build; the first request otherwise waits 10-15 s plus the download, which took 3-5 min per 100 MB model on this connection).
- A failed load is remembered for 300 s (no retry storm, no slow request), then retried. `SafeCropIdentifier` / `SafeDiseaseClassifier` catch any model error, answer with `ProfileCropIdentifier` / `StubDiseaseClassifier`, and log once per failure kind (no farmer data in the message).
- CPU timings (this laptop, torch 2.14.1+cpu): crop detectors 15 s first load, then 1.7 s for 3 photos (both detectors); disease 9 s first load, then 0.9 s for 3 photos. Inference is blocking CPU work: call it from a threadpool, not from the event loop.
- Smoke run (optional, not part of the tests): `data/model_test/.venv` has torch 2.14.1+cpu, timm 1.0.30, transformers 5.20.1, huggingface_hub 2.2.0 but not pydantic, so run with the backend site-packages on the path:
  `PYTHONPATH="backend/.venv/Lib/site-packages" data/model_test/.venv/Scripts/python.exe backend/scripts/evaluate_vision.py --models --storage-dir <cache dir>` (`--crop-model` / `--disease-model` run one half). It also ran end to end through `build_crop_identifier` / `build_disease_classifier` with `provider='model'`: Apple identified at 0.98 (`server_model`, no confirmation), five other covered crops (Tomato, Potato, Maize, Grape, Pepper) classified through the mask, Pea reported as `model_covers_crop=False`.

## 5. Contract requests and integration notes

- No change to frozen files is required. Optional: a setting for the stub disease hint (today `build_disease_classifier(settings, stub_hints=...)`).
- `pyproject.toml` `ml` extra lists `torchvision`, which the code does not need, and no versions; pin `torch`, `timm`, `transformers`, `huggingface_hub` after the first real deployment (tested with the versions above).
- Platform wiring: container calls `build_quality_checker(settings)`, `build_crop_identifier(settings)`, `build_disease_classifier(settings)`. Flow per scan: quality check every photo (unusable -> speak `tip_prompt_id`), crop identification (pass `farmer.crops`, the on-device guess and its confidence), ask the farmer when `needs_confirmation` or `unknown`, then classify with the confirmed crop id. Crop ids returned are canonical (`Apple`, `Pepper` ...); farmer-confirmed ids from the app should go through `app.vision.labels.canonical_crop` before use.
- `ProfileCropIdentifier` returns `source='stub'` only for "no information"; with a profile or a guess it returns `farmer_profile` or `on_device`.
