# Real leaf photos: drop folder

## Test set v1 (prepared 19 Oct 2026)

Built from the 30 photos collected in `incoming/` (10 each of Scab, Alternaria, Marssonina). **Originals were not modified.** Rebuild: `python scripts/prepare_testset.py`, check: `python scripts/validate_testset.py`.

| Set | Folder | Photos | Use |
|---|---|---|---|
| **Leaf test (primary)** | `testset_v1/leaf/<disease_id>/` | **23**: Alternaria 8, Marssonina 11, Scab 4 | Accuracy test: single-leaf photos |
| Fruit (information only) | `testset_v1/fruit_info/` | 5 (all scab) | Run for information; the models read leaves, so fruit is not scored |
| Excluded | listed in `labels.csv` | 4 | 3 exact duplicates (Alternaria 6, scab 8, scab 10) and 1 three-panel figure of fruit (Alternaria 5) |

`labels.csv` has one row per photo with the decision, the reason, the doubt level and the provenance. Two figures were split into separate leaves (Marssonina 4 into a and b, scab 5 into left and right); these are marked `derived_from`.

**Read this before trusting any result from this set:**
- **These look like web images, not the client's photos:** no camera metadata, thumbnail-style sizes (299 to 757 px wide), and some are publication figures. Accuracy here is **not** a field measure.
- **Source and licence are unknown.** Use for internal testing only. Do not redistribute, train on, or show them as client data.
- **Labels are the folder names you chose. No agronomist has confirmed them.** My visual review flagged doubts:
  - **Alternaria 4 (high):** round orange spots look like rust.
  - **Scab 5 and 6 (medium):** scab 5's right leaf looks like frogeye; scab 6 has reddish-brown blotches where scab is normally olive-brown and velvety.
  - Alternaria 8 and Marssonina 10 (low).
- **Scab has only 1 clearly reliable leaf photo** (SCB_09). Half of the scab folder was fruit.
- **Class sizes are tiny.** One wrong answer moves a disease's score by 9 to 25 points.
- **The on-device model has no Alternaria or Marssonina class.** For those two diseases the test shows what it says instead, and how confident it is, not accuracy.

`_review/` holds contact sheets for eyeballing the labels.

---

Put the client's real photos here. They are used **only to test** the pretrained vision models (no training). Nothing is uploaded anywhere: the models run on this machine.

## How to add photos

1. Copy the photo files into `incoming/` (any sub-folders are fine, any names are fine).
2. Copy `labels_template.csv` to `labels.csv` and add **one row per photo**.

## Columns in labels.csv

| Column | What to write | Required |
|---|---|---|
| `filename` | Exact file name (with sub-folder if any), e.g. `incoming/IMG_0012.jpg` | yes |
| `crop` | Apple, Tomato, Potato, Maize, Grape, or other | yes |
| `label` | The disease or pest **as the client names it**, or `healthy`. Examples: Scab, Marssonina, Alternaria, Powdery mildew, Mites, Early blight | yes |
| `confirmed_by` | Who confirmed the label: agronomist name, or `farmer` / `unknown` | yes |
| `leaf_id` | A code for the **physical leaf** (all photos of the same leaf share one code), e.g. `L01` | yes |
| `plant_id` | A code for the tree/plant, if known | no |
| `photo_date` | `YYYY-MM-DD`, if known | no |
| `location` | Village or orchard, if known | no |
| `source` | Phone camera, WhatsApp, lab, etc. | no |
| `notes` | Anything unusual (hazy, two leaves, fruit in frame, etc.) | no |

## Tips for a useful test

- **Include healthy leaves** (at least a few per crop).
- **Include the hard photos too**: bad light, shadows, several leaves, a hand in the frame. Farmers will take those.
- **Marssonina and Alternaria photos are the most valuable**: no open dataset exists for them.
- Keep the **original file** if possible. WhatsApp-compressed photos are fine as a second set (that is what farmers will actually send).
- If one leaf was photographed several times, give those photos the **same `leaf_id`**. This stops the test from looking better than it is.
- 50 photos is enough for a first look, but the accuracy figure will be rough (one wrong photo moves it by 2 points or more).

## What I will do with them

1. Check the files and labels, and map your label names to our disease classes.
2. Run the on-device model and the server apple model on every photo.
3. Report top-1 and top-3 accuracy, per-disease results, which diseases the models cannot name at all, and the confidence scores.
4. Suggest the confidence thresholds for "show result", "give advice" and "ask an expert".
