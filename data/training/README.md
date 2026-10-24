# Apple leaf training kit (internal demo model)

Added 24 Oct 2026 on the owner's request (this reverses the earlier "no model training now" decision, see `docs/open-questions.md`).
It trains a small 4-class apple leaf classifier and exports a folder the backend can load:

| Class id (as in `data/reference/disease_catalogue.csv`) | Meaning |
|---|---|
| `Apple___Apple_scab` | scab |
| `Apple___Marssonina_blotch` | Marssonina blotch (Himachal's top-3 diseases are scab, Marssonina, Alternaria) |
| `Apple___Alternaria_leaf_spot` | Alternaria leaf spot |
| `Apple___healthy` | healthy leaf (stops false disease calls) |

**Status:** the labels are the folder names of the source datasets. **No agronomist has confirmed them**; Marssonina = the Chinese datasets'
"Brown spot" (inferred). Accuracy is measured on research/web images, not on farmers' field photos. Never quote 90-95 %.

## Folder layout

```
data/training/
  photos/<class_id>/*.jpg        training photos (NOT committed: third-party licences; rebuilt by the fetch scripts)
  external_test/<class_id>/*.jpg extra real photos used only to check, never trained on (NOT committed)
  sources.csv                    provenance of every training photo: file, class, source_url, licence, author, note   (committed)
  external_test/sources.csv      same for the external check photos                                                      (committed)
  fetch_appleleaf9.py            downloads a sample of AppleLeaf9 (CC BY 4.0)
  fetch_jk_apple.py              downloads a sample of the Kashmir apple dataset (CC BY 4.0, via HTTP range reads of the zip)
  train_apple.py                 train + evaluate + export
  output/apple_leaf_v1/          model.safetensors (not committed), config.json, metrics.json, model_card.md
  .venv/                         own Python 3.13 environment (not committed)
```

## Adding photos

1. Copy the photo into `photos/<class_id>/` (one leaf per photo; any file name; JPEG/PNG).
2. Add **one row to `sources.csv`**: `file` (relative to `photos/`, e.g. `Apple___Apple_scab/my_leaf.jpg`), `class`, `source_url`, `licence`, `author`, `note`.
3. Licence rule: only CC0, public domain or CC BY / CC BY-SA photos with the author recorded, **or the client's own photos with written
   permission** (licence `client-owned`). Web photos of unknown licence may only be used for an internal demo model and must be marked
   `internal-only/unknown licence` in `licence`; they cannot then also be the test set. Never add generated images.
4. Keep photos single-leaf, in focus, the disease visible; no fruit, no diagrams, no several-leaf collages. Remove a wrong or doubtful one
   rather than relabel it.
5. Photos of the **same leaf** are grouped automatically (perceptual hash) so they stay on one side of the train/test split. Still keep
   the number of photos per leaf low.

The client's confirmed field photos (with an agronomist's label) are by far the most valuable addition: they are the only way to measure
real accuracy (`data/images/README.md` has the label format used for the test set).

## Install (once)

```powershell
cd data\training
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r requirements.txt
```

If `import torch` fails with "c10.dll or one of its dependencies" the machine lacks the Microsoft Visual C++ Redistributable: install it
(https://aka.ms/vs/17/release/vc_redist.x64.exe) or run `pip install msvc-runtime` and copy `.venv\*.dll` into `.venv\Lib\site-packages\torch\lib`.

## Get the photos (reproduces the committed `sources.csv`)

```powershell
.venv\Scripts\python fetch_appleleaf9.py --per-class 400      # scab, healthy, Alternaria, "Brown spot" (= Marssonina)
.venv\Scripts\python fetch_jk_apple.py --per-class 200 --only healthy
.venv\Scripts\python fetch_jk_apple.py --per-class 200 --only alternaria   # then append sources_*.part.csv to sources.csv
```

## Train

```powershell
.venv\Scripts\python train_apple.py --quick     # 1-minute smoke test (writes to output/apple_leaf_v1: rerun the full run afterwards)
.venv\Scripts\python train_apple.py             # full run, about 10-25 minutes on 12 CPU cores
```

What it does: drops unreadable files and exact duplicates, groups near-duplicates, holds out 20 % of the groups as a test set, runs 5-fold
group-disjoint cross-validation on the rest, trains on a frozen ImageNet ConvNeXt-Tiny backbone with 8 heavily augmented views per image
(only the linear head is trained, so CPU is enough), fits a temperature on out-of-fold logits and folds it into the head, evaluates the
test split, `external_test/` and `data/images/testset_v1/leaf` (if present; never trained on), and exports the folder. The backbone is
ImageNet-only on purpose: starting from the downloaded `ixrbhii/apple-disease-convnext` would be stronger but it was trained on the same
public datasets, which would make every number here too optimistic.

## Use it in the backend

```
DISEASE_PROVIDER=model
DISEASE_MODEL_DIR=D:\FarmTrack\data\training\output\apple_leaf_v1
```

(needs `pip install -e ".[ml]"`). Apple photos are then answered by this model alone; other crops still use the downloaded models.
The model only knows these 4 classes: any other apple problem (rust, powdery mildew, ...) will be forced into one of them, so keep the
expert-review guards on.

## Read before trusting a number

`output/apple_leaf_v1/model_card.md` has the data, licences, metrics and limits. In short: tiny and curated data; each class comes largely
from a different imaging source (so the model may partly learn the source, not the disease); field accuracy is unknown and lower.
