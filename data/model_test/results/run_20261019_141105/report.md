# Model test report: apple leaf diseases

Run: 2026-10-19 14:15 | device: cpu | python 3.13.15 | photos: 3 leaf + 0 fruit

- Model A: {"revision": "d33601185b32cf05b3942661b8d84ffb86dc48ec", "labels": 38}
- Model B: {"revision": "8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a", "expected_revision": "8bb9c1ae513fff294eed77bdec53ca6fa3c10e8a", "labels": 8, "input_size": [224, 224]}

## Read this first

- **The photos look like web images, not the client's photos; labels are not agronomist-confirmed; source and licence unknown.** A score here is NOT a field measure.
- **Very few photos per disease** (see n). One wrong answer moves a result by 9 to 25 points. Treat everything as a first look.
- **Model A has no Alternaria or Marssonina class**, so it cannot be right for them. For those, read what it answers and how confident it is.
- Model A's own published figures (model card): 16% top-1 on 25 PlantDoc field/web photos; at its 0.50 cut-off, 71% precision at 58% coverage on its 302-photo PlantDoc validation set.
- Two preprocessing styles are shown. `default` = the model's recommended centre-crop. `squash224` = whole photo squeezed to 224x224 (model B's card says it was trained that way).

## A  On-device candidate: neghani/plantvillage-mobilenetv2 (38 PlantVillage classes)

### A / preprocessing: default / all 38 classes

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.63 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.63 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.63 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Peach___Bacterial_spot x1; Grape___Esca_(Black_Measles) x1; Grape___Black_rot x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 2/3 = 67% | 0/2 = 0% |
| 0.50 | 2/3 = 67% | 0/2 = 0% |
| 0.65 | 1/3 = 33% | 0/1 = 0% |
| 0.80 | 1/3 = 33% | 0/1 = 0% |
| 0.90 | 1/3 = 33% | 0/1 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 2 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot | 0.51 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.94 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot (0.51) | Grape___Black_rot (0.47) | Apple_scab (0.01) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Grape___Esca_(Black_Measles) (0.44) | Squash___Powdery_mildew (0.42) | Tomato___healthy (0.09) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.94) | Apple_scab (0.05) | Peach___Bacterial_spot (0.00) | NO |

_Speed on this machine: 39 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: default / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.91 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.91 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.91 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x2; Cedar_apple_rust x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 3/3 = 100% | 0/3 = 0% |
| 0.50 | 3/3 = 100% | 0/3 = 0% |
| 0.65 | 3/3 = 100% | 0/3 = 0% |
| 0.80 | 3/3 = 100% | 0/3 = 0% |
| 0.90 | 1/3 = 33% | 0/1 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 3 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.86 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust | 0.86 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 1.00 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab (0.86) | Cedar_apple_rust (0.10) | Black_rot (0.04) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust (0.86) | Apple_scab (0.14) | Black_rot (0.00) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | Black_rot (0.00) | NO |

_Speed on this machine: 39 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: squash224 / all 38 classes

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.83 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.83 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.83 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Grape___Black_rot x2; Squash___Powdery_mildew x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 3/3 = 100% | 0/3 = 0% |
| 0.50 | 2/3 = 67% | 0/2 = 0% |
| 0.65 | 2/3 = 67% | 0/2 = 0% |
| 0.80 | 2/3 = 67% | 0/2 = 0% |
| 0.90 | 2/3 = 67% | 0/2 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 3 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.99 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Squash___Powdery_mildew | 1.00 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.49 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.99) | Grape___Esca_(Black_Measles) (0.00) | Peach___Bacterial_spot (0.00) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Squash___Powdery_mildew (1.00) | Tomato___healthy (0.00) | Grape___Esca_(Black_Measles) (0.00) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.49) | Apple_scab (0.20) | Peach___Bacterial_spot (0.16) | NO |

_Speed on this machine: 29 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: squash224 / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.92 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.92 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 0/3 = 0% | 0.00 | 0.92 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x3 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 3/3 = 100% | 0/3 = 0% |
| 0.50 | 3/3 = 100% | 0/3 = 0% |
| 0.65 | 3/3 = 100% | 0/3 = 0% |
| 0.80 | 3/3 = 100% | 0/3 = 0% |
| 0.90 | 2/3 = 67% | 0/2 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 3 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.84 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.96 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.97 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab (0.84) | Cedar_apple_rust (0.13) | Black_rot (0.03) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab (0.96) | Cedar_apple_rust (0.03) | Black_rot (0.01) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.97) | Cedar_apple_rust (0.03) | Black_rot (0.00) | NO |

_Speed on this machine: 29 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

## B  Server apple model: ixrbhii/apple-disease-convnext (8 apple classes)

### B / preprocessing: default / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.02 | 0.89 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.02 | 0.89 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.02 | 0.89 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab_rust x2; Apple_scab x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 3/3 = 100% | 0/3 = 0% |
| 0.50 | 3/3 = 100% | 0/3 = 0% |
| 0.65 | 3/3 = 100% | 0/3 = 0% |
| 0.80 | 3/3 = 100% | 0/3 = 0% |
| 0.90 | 2/3 = 67% | 0/2 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 3 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.84 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.91 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Gray_spot (0.02) | Root_rot_collar_rot (0.02) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.84) | Alternaria_leaf_spot (0.04) | Root_rot_collar_rot (0.03) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.91) | Apple_scab_rust (0.01) | Gray_spot (0.01) | NO |

_Speed on this machine: 134 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### B / preprocessing: squash224 / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.03 | 0.88 |
| **all leaf photos** | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.03 | 0.88 |
| **reliable labels only** | 3 | 0/3 = 0% | 0/3 = 0% | 1/3 = 33% | 0.03 | 0.88 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab_rust x2; Apple_scab x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 3/3 = 100% | 0/3 = 0% |
| 0.45 | 3/3 = 100% | 0/3 = 0% |
| 0.50 | 3/3 = 100% | 0/3 = 0% |
| 0.65 | 3/3 = 100% | 0/3 = 0% |
| 0.80 | 3/3 = 100% | 0/3 = 0% |
| 0.90 | 2/3 = 67% | 0/2 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 3 of 3**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.82 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.92 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Gray_spot (0.02) | Root_rot_collar_rot (0.02) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.82) | Alternaria_leaf_spot (0.05) | Root_rot_collar_rot (0.03) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.92) | Gray_spot (0.01) | Brown_spot (0.01) | NO |

_Speed on this machine: 130 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

## Does the preprocessing matter?

| Model | Classes | default: top-1 lenient | squash224: top-1 lenient |
|---|---|---|---|
| A | all_classes | 0/3 = 0% | 0/3 = 0% |
| A | apple_only | 0/3 = 0% | 0/3 = 0% |
| B | apple_only | 0/3 = 0% | 0/3 = 0% |

## Next

Send this file and `predictions.csv` back for review. Do not train anything yet.
