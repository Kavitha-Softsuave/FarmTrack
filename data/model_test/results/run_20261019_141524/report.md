# Model test report: apple leaf diseases

Run: 2026-10-19 14:15 | device: cpu | python 3.13.15 | photos: 23 leaf + 5 fruit

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
| Alternaria_leaf_spot | 8 | 0/8 = 0% | 0/8 = 0% | 0/8 = 0% | 0.00 | 0.70 |
| Apple_scab | 4 | 0/4 = 0% | 0/4 = 0% | 1/4 = 25% | 0.03 | 0.92 |
| Marssonina_blotch | 11 | 0/11 = 0% | 0/11 = 0% | 0/11 = 0% | 0.00 | 0.60 |
| **all leaf photos** | 23 | 0/23 = 0% | 0/23 = 0% | 1/23 = 4% | 0.01 | 0.69 |
| **reliable labels only** | 19 | 0/19 = 0% | 0/19 = 0% | 1/19 = 5% | 0.01 | 0.64 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Grape___Black_rot x3; Peach___Bacterial_spot x2; Grape___Esca_(Black_Measles) x1; Pepper,_bell___Bacterial_spot x1; Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot x1 |
| Apple_scab | Potato___Early_blight x2; Grape___Esca_(Black_Measles) x1; Grape___Black_rot x1 |
| Marssonina_blotch | Strawberry___Leaf_scorch x3; Potato___Early_blight x2; Apple_scab x1; Tomato___Early_blight x1; Tomato___Septoria_leaf_spot x1; Grape___Black_rot x1; Grape___Esca_(Black_Measles) x1; Tomato___healthy x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 20/23 = 87% | 0/20 = 0% |
| 0.45 | 17/23 = 74% | 0/17 = 0% |
| 0.50 | 16/23 = 70% | 0/16 = 0% |
| 0.65 | 13/23 = 57% | 0/13 = 0% |
| 0.80 | 12/23 = 52% | 0/12 = 0% |
| 0.90 | 7/23 = 30% | 0/7 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 17 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot | 0.51 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.94 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Grape___Black_rot | 0.89 |
| ALT_07.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot | 0.53 |
| ALT_08.jpg | Alternaria_leaf_spot | low | Pepper,_bell___Bacterial_spot | 0.49 |
| ALT_09.jpg | Alternaria_leaf_spot | none | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot | 0.83 |
| ALT_10.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 1.00 |
| MAR_02.jpg | Marssonina_blotch | none | Potato___Early_blight | 0.95 |
| MAR_04a.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch | 1.00 |
| MAR_05.jpg | Marssonina_blotch | none | Potato___Early_blight | 1.00 |
| MAR_06.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch | 0.70 |
| MAR_07.jpg | Marssonina_blotch | none | Grape___Black_rot | 0.60 |
| MAR_08.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch | 0.88 |
| SCB_05l.jpg | Apple_scab | medium | Potato___Early_blight | 1.00 |
| SCB_05r.jpg | Apple_scab | medium | Potato___Early_blight | 0.88 |
| SCB_06.jpg | Apple_scab | medium | Grape___Esca_(Black_Measles) | 0.92 |
| SCB_09.jpg | Apple_scab | none | Grape___Black_rot | 0.87 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot (0.51) | Grape___Black_rot (0.47) | Apple_scab (0.01) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Grape___Esca_(Black_Measles) (0.44) | Squash___Powdery_mildew (0.42) | Tomato___healthy (0.09) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.94) | Apple_scab (0.05) | Peach___Bacterial_spot (0.00) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Grape___Black_rot (0.89) | Black_rot (0.09) | Grape___Esca_(Black_Measles) (0.02) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot (0.53) | Grape___Black_rot (0.43) | Grape___Esca_(Black_Measles) (0.03) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Pepper,_bell___Bacterial_spot (0.49) | Potato___Early_blight (0.35) | Tomato___Early_blight (0.16) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.83) | Grape___Esca_(Black_Measles) (0.10) | Corn_(maize)___Northern_Leaf_Blight (0.02) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (1.00) | Grape___Esca_(Black_Measles) (0.00) | Peach___Bacterial_spot (0.00) | NO |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab (0.28) | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.13) | Corn_(maize)___Common_rust_ (0.12) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Potato___Early_blight (0.95) | Grape___Leaf_blight_(Isariopsis_Leaf_Spot) (0.03) | Tomato___Septoria_leaf_spot (0.01) | NO |
| MAR_03.jpg | Marssonina_blotch | none | Tomato___Early_blight (0.37) | Potato___Early_blight (0.27) | Strawberry___Leaf_scorch (0.13) | NO |
| MAR_04a.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch (1.00) | Apple_scab (0.00) | Raspberry___healthy (0.00) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Tomato___Septoria_leaf_spot (0.33) | Tomato___Bacterial_spot (0.33) | Tomato___Early_blight (0.21) | NO |
| MAR_05.jpg | Marssonina_blotch | none | Potato___Early_blight (1.00) | Tomato___Early_blight (0.00) | Pepper,_bell___Bacterial_spot (0.00) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch (0.70) | Pepper,_bell___Bacterial_spot (0.16) | Peach___Bacterial_spot (0.09) | NO |
| MAR_07.jpg | Marssonina_blotch | none | Grape___Black_rot (0.60) | Grape___Esca_(Black_Measles) (0.35) | Strawberry___Leaf_scorch (0.02) | NO |
| MAR_08.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch (0.88) | Grape___Esca_(Black_Measles) (0.06) | Apple_scab (0.02) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Grape___Esca_(Black_Measles) (0.26) | Grape___Black_rot (0.25) | Strawberry___Leaf_scorch (0.18) | NO |
| MAR_10.jpg | Marssonina_blotch | low | Tomato___healthy (0.22) | Corn_(maize)___Common_rust_ (0.20) | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.15) | NO |
| SCB_05l.jpg | Apple_scab | medium | Potato___Early_blight (1.00) | Grape___Leaf_blight_(Isariopsis_Leaf_Spot) (0.00) | Potato___Late_blight (0.00) | NO |
| SCB_05r.jpg | Apple_scab | medium | Potato___Early_blight (0.88) | Tomato___Late_blight (0.03) | Grape___Leaf_blight_(Isariopsis_Leaf_Spot) (0.02) | NO |
| SCB_06.jpg | Apple_scab | medium | Grape___Esca_(Black_Measles) (0.92) | Cedar_apple_rust (0.07) | Potato___Late_blight (0.01) | NO |
| SCB_09.jpg | Apple_scab | none | Grape___Black_rot (0.87) | Apple_scab (0.13) | Grape___Leaf_blight_(Isariopsis_Leaf_Spot) (0.00) | NO |

**Fruit photos (information only, not scored; true disease is scab):** answers Strawberry___Leaf_scorch x2; Tomato___Early_blight x2; Tomato___Late_blight x1; mean confidence 0.79

_Speed on this machine: 32 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: default / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 0/8 = 0% | 0/8 = 0% | 0/8 = 0% | 0.00 | 0.80 |
| Apple_scab | 4 | 3/4 = 75% | 3/4 = 75% | 4/4 = 100% | 0.67 | 0.92 |
| Marssonina_blotch | 11 | 0/11 = 0% | 0/11 = 0% | 0/11 = 0% | 0.00 | 0.72 |
| **all leaf photos** | 23 | 3/23 = 13% | 3/23 = 13% | 4/23 = 17% | 0.12 | 0.78 |
| **reliable labels only** | 19 | 1/19 = 5% | 1/19 = 5% | 1/19 = 5% | 0.05 | 0.75 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x3; Black_rot x3; Cedar_apple_rust x2 |
| Apple_scab | Apple_scab x3; Cedar_apple_rust x1 |
| Marssonina_blotch | Apple_scab x6; Black_rot x3; Cedar_apple_rust x2 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 23/23 = 100% | 3/23 = 13% |
| 0.45 | 22/23 = 96% | 3/22 = 14% |
| 0.50 | 21/23 = 91% | 3/21 = 14% |
| 0.65 | 17/23 = 74% | 3/17 = 18% |
| 0.80 | 12/23 = 52% | 2/12 = 17% |
| 0.90 | 8/23 = 35% | 2/8 = 25% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 19 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.86 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust | 0.86 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 1.00 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot | 1.00 |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.64 |
| ALT_09.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust | 0.89 |
| ALT_10.jpg | Alternaria_leaf_spot | none | Black_rot | 0.77 |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab | 0.95 |
| MAR_02.jpg | Marssonina_blotch | none | Apple_scab | 0.69 |
| MAR_03.jpg | Marssonina_blotch | none | Apple_scab | 0.61 |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab | 1.00 |
| MAR_04b.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.49 |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab | 0.65 |
| MAR_06.jpg | Marssonina_blotch | none | Black_rot | 0.90 |
| MAR_07.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.55 |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab | 0.87 |
| MAR_09.jpg | Marssonina_blotch | none | Black_rot | 0.67 |
| MAR_10.jpg | Marssonina_blotch | low | Black_rot | 0.54 |
| SCB_06.jpg | Apple_scab | medium | Cedar_apple_rust | 0.99 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab (0.86) | Cedar_apple_rust (0.10) | Black_rot (0.04) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust (0.86) | Apple_scab (0.14) | Black_rot (0.00) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | Black_rot (0.00) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot (1.00) | Cedar_apple_rust (0.00) | Apple_scab (0.00) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab (0.64) | healthy (0.30) | Cedar_apple_rust (0.05) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Black_rot (0.39) | Apple_scab (0.38) | Cedar_apple_rust (0.23) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust (0.89) | Black_rot (0.05) | healthy (0.04) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Black_rot (0.77) | Apple_scab (0.17) | Cedar_apple_rust (0.06) | NO |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab (0.95) | Cedar_apple_rust (0.04) | healthy (0.01) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Apple_scab (0.69) | Cedar_apple_rust (0.23) | Black_rot (0.06) | NO |
| MAR_03.jpg | Marssonina_blotch | none | Apple_scab (0.61) | Cedar_apple_rust (0.37) | Black_rot (0.01) | NO |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | Black_rot (0.00) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.49) | Apple_scab (0.40) | Black_rot (0.09) | NO |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab (0.65) | Cedar_apple_rust (0.29) | Black_rot (0.05) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Black_rot (0.90) | Cedar_apple_rust (0.07) | Apple_scab (0.02) | NO |
| MAR_07.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.55) | Apple_scab (0.31) | Black_rot (0.14) | NO |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab (0.87) | Cedar_apple_rust (0.12) | Black_rot (0.00) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Black_rot (0.67) | Cedar_apple_rust (0.18) | Apple_scab (0.15) | NO |
| MAR_10.jpg | Marssonina_blotch | low | Black_rot (0.54) | Cedar_apple_rust (0.27) | Apple_scab (0.17) | NO |
| SCB_05l.jpg | Apple_scab | medium | Apple_scab (0.99) | Cedar_apple_rust (0.01) | Black_rot (0.00) | yes |
| SCB_05r.jpg | Apple_scab | medium | Apple_scab (0.70) | Cedar_apple_rust (0.23) | Black_rot (0.04) | yes |
| SCB_06.jpg | Apple_scab | medium | Cedar_apple_rust (0.99) | Apple_scab (0.01) | healthy (0.00) | NO |
| SCB_09.jpg | Apple_scab | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | healthy (0.00) | yes |

**Fruit photos (information only, not scored; true disease is scab):** answers Cedar_apple_rust x3; Apple_scab x1; Black_rot x1; mean confidence 0.71

_Speed on this machine: 32 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: squash224 / all 38 classes

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 0/8 = 0% | 0/8 = 0% | 0/8 = 0% | 0.00 | 0.81 |
| Apple_scab | 4 | 0/4 = 0% | 0/4 = 0% | 3/4 = 75% | 0.01 | 0.92 |
| Marssonina_blotch | 11 | 0/11 = 0% | 0/11 = 0% | 0/11 = 0% | 0.00 | 0.74 |
| **all leaf photos** | 23 | 0/23 = 0% | 0/23 = 0% | 3/23 = 13% | 0.00 | 0.79 |
| **reliable labels only** | 19 | 0/19 = 0% | 0/19 = 0% | 1/19 = 5% | 0.00 | 0.77 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Grape___Black_rot x3; Squash___Powdery_mildew x1; Black_rot x1; Peach___Bacterial_spot x1; Pepper,_bell___Bacterial_spot x1; Grape___Esca_(Black_Measles) x1 |
| Apple_scab | Potato___Early_blight x2; Grape___Esca_(Black_Measles) x1; Grape___Black_rot x1 |
| Marssonina_blotch | Grape___Black_rot x3; Pepper,_bell___Bacterial_spot x2; Strawberry___Leaf_scorch x2; Grape___Esca_(Black_Measles) x1; Tomato___Septoria_leaf_spot x1; Potato___Early_blight x1; Corn_(maize)___Common_rust_ x1 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 23/23 = 100% | 0/23 = 0% |
| 0.45 | 22/23 = 96% | 0/22 = 0% |
| 0.50 | 21/23 = 91% | 0/21 = 0% |
| 0.65 | 18/23 = 78% | 0/18 = 0% |
| 0.80 | 12/23 = 52% | 0/12 = 0% |
| 0.90 | 10/23 = 43% | 0/10 = 0% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 22 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.99 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Squash___Powdery_mildew | 1.00 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.49 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot | 0.94 |
| ALT_07.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot | 0.65 |
| ALT_08.jpg | Alternaria_leaf_spot | low | Pepper,_bell___Bacterial_spot | 1.00 |
| ALT_10.jpg | Alternaria_leaf_spot | none | Grape___Black_rot | 0.98 |
| MAR_01.jpg | Marssonina_blotch | none | Grape___Esca_(Black_Measles) | 0.53 |
| MAR_02.jpg | Marssonina_blotch | none | Grape___Black_rot | 0.55 |
| MAR_03.jpg | Marssonina_blotch | none | Pepper,_bell___Bacterial_spot | 0.89 |
| MAR_04a.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch | 0.66 |
| MAR_04b.jpg | Marssonina_blotch | none | Tomato___Septoria_leaf_spot | 0.50 |
| MAR_05.jpg | Marssonina_blotch | none | Potato___Early_blight | 0.99 |
| MAR_06.jpg | Marssonina_blotch | none | Pepper,_bell___Bacterial_spot | 1.00 |
| MAR_07.jpg | Marssonina_blotch | none | Grape___Black_rot | 0.79 |
| MAR_08.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch | 0.83 |
| MAR_09.jpg | Marssonina_blotch | none | Grape___Black_rot | 0.68 |
| MAR_10.jpg | Marssonina_blotch | low | Corn_(maize)___Common_rust_ | 0.69 |
| SCB_05l.jpg | Apple_scab | medium | Potato___Early_blight | 1.00 |
| SCB_05r.jpg | Apple_scab | medium | Potato___Early_blight | 0.74 |
| SCB_06.jpg | Apple_scab | medium | Grape___Esca_(Black_Measles) | 0.96 |
| SCB_09.jpg | Apple_scab | none | Grape___Black_rot | 1.00 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.99) | Grape___Esca_(Black_Measles) (0.00) | Peach___Bacterial_spot (0.00) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Squash___Powdery_mildew (1.00) | Tomato___healthy (0.00) | Grape___Esca_(Black_Measles) (0.00) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.49) | Apple_scab (0.20) | Peach___Bacterial_spot (0.16) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot (0.94) | Grape___Esca_(Black_Measles) (0.05) | Grape___Black_rot (0.01) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Peach___Bacterial_spot (0.65) | Grape___Black_rot (0.33) | Grape___Esca_(Black_Measles) (0.01) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Pepper,_bell___Bacterial_spot (1.00) | Grape___Esca_(Black_Measles) (0.00) | Grape___Black_rot (0.00) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Grape___Esca_(Black_Measles) (0.39) | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.20) | Tomato___Late_blight (0.15) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Grape___Black_rot (0.98) | Grape___Esca_(Black_Measles) (0.02) | Peach___Bacterial_spot (0.00) | NO |
| MAR_01.jpg | Marssonina_blotch | none | Grape___Esca_(Black_Measles) (0.53) | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.13) | Cedar_apple_rust (0.07) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Grape___Black_rot (0.55) | Strawberry___Leaf_scorch (0.17) | Grape___Leaf_blight_(Isariopsis_Leaf_Spot) (0.08) | NO |
| MAR_03.jpg | Marssonina_blotch | none | Pepper,_bell___Bacterial_spot (0.89) | Tomato___Tomato_Yellow_Leaf_Curl_Virus (0.05) | Strawberry___Leaf_scorch (0.05) | NO |
| MAR_04a.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch (0.66) | Apple_scab (0.34) | Peach___Bacterial_spot (0.00) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Tomato___Septoria_leaf_spot (0.50) | Tomato___Bacterial_spot (0.34) | Strawberry___Leaf_scorch (0.08) | NO |
| MAR_05.jpg | Marssonina_blotch | none | Potato___Early_blight (0.99) | Pepper,_bell___Bacterial_spot (0.00) | Strawberry___Leaf_scorch (0.00) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Pepper,_bell___Bacterial_spot (1.00) | Peach___Bacterial_spot (0.00) | Strawberry___Leaf_scorch (0.00) | NO |
| MAR_07.jpg | Marssonina_blotch | none | Grape___Black_rot (0.79) | Grape___Esca_(Black_Measles) (0.07) | Tomato___Early_blight (0.06) | NO |
| MAR_08.jpg | Marssonina_blotch | none | Strawberry___Leaf_scorch (0.83) | Grape___Esca_(Black_Measles) (0.14) | Cherry_(including_sour)___healthy (0.01) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Grape___Black_rot (0.68) | Grape___Esca_(Black_Measles) (0.30) | Strawberry___Leaf_scorch (0.01) | NO |
| MAR_10.jpg | Marssonina_blotch | low | Corn_(maize)___Common_rust_ (0.69) | Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot (0.18) | Squash___Powdery_mildew (0.04) | NO |
| SCB_05l.jpg | Apple_scab | medium | Potato___Early_blight (1.00) | Apple_scab (0.00) | Potato___Late_blight (0.00) | NO |
| SCB_05r.jpg | Apple_scab | medium | Potato___Early_blight (0.74) | Tomato___Late_blight (0.09) | Apple_scab (0.04) | NO |
| SCB_06.jpg | Apple_scab | medium | Grape___Esca_(Black_Measles) (0.96) | Cedar_apple_rust (0.04) | Strawberry___Leaf_scorch (0.00) | NO |
| SCB_09.jpg | Apple_scab | none | Grape___Black_rot (1.00) | Apple_scab (0.00) | Grape___Esca_(Black_Measles) (0.00) | NO |

**Fruit photos (information only, not scored; true disease is scab):** answers Tomato___Early_blight x3; Strawberry___Leaf_scorch x1; Tomato___Late_blight x1; mean confidence 0.71

_Speed on this machine: 32 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### A / preprocessing: squash224 / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 0/8 = 0% | 0/8 = 0% | 0/8 = 0% | 0.00 | 0.81 |
| Apple_scab | 4 | 3/4 = 75% | 3/4 = 75% | 4/4 = 100% | 0.71 | 0.96 |
| Marssonina_blotch | 11 | 0/11 = 0% | 0/11 = 0% | 0/11 = 0% | 0.00 | 0.65 |
| **all leaf photos** | 23 | 3/23 = 13% | 3/23 = 13% | 4/23 = 17% | 0.12 | 0.76 |
| **reliable labels only** | 19 | 1/19 = 5% | 1/19 = 5% | 1/19 = 5% | 0.05 | 0.72 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x3; Black_rot x3; healthy x1; Cedar_apple_rust x1 |
| Apple_scab | Apple_scab x3; Cedar_apple_rust x1 |
| Marssonina_blotch | Apple_scab x5; Cedar_apple_rust x4; Black_rot x2 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 23/23 = 100% | 3/23 = 13% |
| 0.45 | 22/23 = 96% | 3/22 = 14% |
| 0.50 | 19/23 = 83% | 3/19 = 16% |
| 0.65 | 15/23 = 65% | 3/15 = 20% |
| 0.80 | 13/23 = 57% | 3/13 = 23% |
| 0.90 | 8/23 = 35% | 2/8 = 25% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 19 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.84 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.96 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.97 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot | 1.00 |
| ALT_08.jpg | Alternaria_leaf_spot | low | Black_rot | 0.49 |
| ALT_09.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust | 0.86 |
| ALT_10.jpg | Alternaria_leaf_spot | none | Black_rot | 0.91 |
| MAR_01.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.51 |
| MAR_02.jpg | Marssonina_blotch | none | Apple_scab | 0.45 |
| MAR_03.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.82 |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab | 1.00 |
| MAR_04b.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.54 |
| MAR_05.jpg | Marssonina_blotch | none | Cedar_apple_rust | 0.51 |
| MAR_06.jpg | Marssonina_blotch | none | Apple_scab | 0.66 |
| MAR_07.jpg | Marssonina_blotch | none | Black_rot | 0.61 |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab | 0.76 |
| MAR_09.jpg | Marssonina_blotch | none | Black_rot | 0.87 |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab | 0.47 |
| SCB_06.jpg | Apple_scab | medium | Cedar_apple_rust | 1.00 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab (0.84) | Cedar_apple_rust (0.13) | Black_rot (0.03) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab (0.96) | Cedar_apple_rust (0.03) | Black_rot (0.01) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.97) | Cedar_apple_rust (0.03) | Black_rot (0.00) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Black_rot (1.00) | Cedar_apple_rust (0.00) | Apple_scab (0.00) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | healthy (0.41) | Apple_scab (0.30) | Cedar_apple_rust (0.26) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Black_rot (0.49) | Cedar_apple_rust (0.37) | Apple_scab (0.14) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Cedar_apple_rust (0.86) | Black_rot (0.07) | healthy (0.04) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Black_rot (0.91) | Cedar_apple_rust (0.05) | Apple_scab (0.03) | NO |
| MAR_01.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.51) | Apple_scab (0.47) | healthy (0.02) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Apple_scab (0.45) | Cedar_apple_rust (0.26) | Black_rot (0.22) | NO |
| MAR_03.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.82) | healthy (0.12) | Black_rot (0.04) | NO |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | Black_rot (0.00) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.54) | Apple_scab (0.28) | Black_rot (0.13) | NO |
| MAR_05.jpg | Marssonina_blotch | none | Cedar_apple_rust (0.51) | Apple_scab (0.39) | Black_rot (0.09) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Apple_scab (0.66) | Cedar_apple_rust (0.23) | Black_rot (0.11) | NO |
| MAR_07.jpg | Marssonina_blotch | none | Black_rot (0.61) | Apple_scab (0.20) | Cedar_apple_rust (0.19) | NO |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab (0.76) | Cedar_apple_rust (0.20) | Black_rot (0.03) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Black_rot (0.87) | Cedar_apple_rust (0.06) | Apple_scab (0.06) | NO |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab (0.47) | Black_rot (0.38) | Cedar_apple_rust (0.14) | NO |
| SCB_05l.jpg | Apple_scab | medium | Apple_scab (0.98) | Cedar_apple_rust (0.02) | healthy (0.00) | yes |
| SCB_05r.jpg | Apple_scab | medium | Apple_scab (0.85) | Cedar_apple_rust (0.08) | healthy (0.06) | yes |
| SCB_06.jpg | Apple_scab | medium | Cedar_apple_rust (1.00) | Black_rot (0.00) | Apple_scab (0.00) | NO |
| SCB_09.jpg | Apple_scab | none | Apple_scab (1.00) | Cedar_apple_rust (0.00) | Black_rot (0.00) | yes |

**Fruit photos (information only, not scored; true disease is scab):** answers Cedar_apple_rust x3; Apple_scab x1; Black_rot x1; mean confidence 0.67

_Speed on this machine: 32 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

## B  Server apple model: ixrbhii/apple-disease-convnext (8 apple classes)

### B / preprocessing: default / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 1/8 = 12% | 1/8 = 12% | 4/8 = 50% | 0.12 | 0.89 |
| Apple_scab | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.90 | 0.87 |
| Marssonina_blotch | 11 | 2/11 = 18% | 6/11 = 55% | 7/11 = 64% | 0.52 | 0.83 |
| **all leaf photos** | 23 | 6/23 = 26% | 11/23 = 48% | 15/23 = 65% | 0.45 | 0.86 |
| **reliable labels only** | 19 | 4/19 = 21% | 8/19 = 42% | 11/19 = 58% | 0.40 | 0.85 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab_rust x4; Apple_scab x1; Root_rot_collar_rot x1; Brown_spot x1; Alternaria_leaf_spot x1 |
| Apple_scab | Apple_scab x3; Apple_scab_rust x1 |
| Marssonina_blotch | Apple_scab x5; Brown_spot x4; Marssonina_blotch x2 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 23/23 = 100% | 11/23 = 48% |
| 0.45 | 23/23 = 100% | 11/23 = 48% |
| 0.50 | 22/23 = 96% | 11/22 = 50% |
| 0.65 | 22/23 = 96% | 11/22 = 50% |
| 0.80 | 20/23 = 87% | 9/20 = 45% |
| 0.90 | 12/23 = 52% | 4/12 = 33% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 12 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.84 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.91 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Root_rot_collar_rot | 0.89 |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.92 |
| ALT_08.jpg | Alternaria_leaf_spot | low | Brown_spot | 0.86 |
| ALT_09.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab | 0.91 |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab | 0.92 |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab | 0.48 |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab | 0.90 |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab | 0.92 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Gray_spot (0.02) | Root_rot_collar_rot (0.02) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.84) | Alternaria_leaf_spot (0.04) | Root_rot_collar_rot (0.03) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.91) | Apple_scab_rust (0.01) | Gray_spot (0.01) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Root_rot_collar_rot (0.89) | Alternaria_leaf_spot (0.03) | Apple_scab_rust (0.01) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.92) | Alternaria_leaf_spot (0.02) | Root_rot_collar_rot (0.01) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Brown_spot (0.86) | Apple_scab_rust (0.06) | Apple_scab (0.02) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Apple_scab (0.02) | Root_rot_collar_rot (0.01) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Alternaria_leaf_spot (0.85) | Gray_spot (0.06) | Root_rot_collar_rot (0.02) | yes |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab (0.91) | Root_rot_collar_rot (0.01) | healthy (0.01) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Brown_spot (0.91) | Apple_scab (0.02) | Apple_scab_rust (0.01) | yes |
| MAR_03.jpg | Marssonina_blotch | none | Brown_spot (0.80) | Apple_scab (0.14) | Apple_scab_rust (0.01) | yes |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab (0.92) | Apple_scab_rust (0.01) | Root_rot_collar_rot (0.01) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Marssonina_blotch (0.81) | Brown_spot (0.10) | Apple_scab (0.02) | yes |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab (0.48) | Brown_spot (0.41) | Marssonina_blotch (0.03) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Brown_spot (0.88) | Apple_scab (0.04) | Apple_scab_rust (0.02) | yes |
| MAR_07.jpg | Marssonina_blotch | none | Marssonina_blotch (0.67) | Apple_scab (0.18) | Brown_spot (0.03) | yes |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab (0.90) | Apple_scab_rust (0.02) | Root_rot_collar_rot (0.02) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Brown_spot (0.90) | Marssonina_blotch (0.03) | Apple_scab_rust (0.01) | yes |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab (0.92) | Root_rot_collar_rot (0.01) | Gray_spot (0.01) | NO |
| SCB_05l.jpg | Apple_scab | medium | Apple_scab (0.92) | Apple_scab_rust (0.01) | Alternaria_leaf_spot (0.01) | yes |
| SCB_05r.jpg | Apple_scab | medium | Apple_scab (0.82) | Root_rot_collar_rot (0.11) | Apple_scab_rust (0.02) | yes |
| SCB_06.jpg | Apple_scab | medium | Apple_scab_rust (0.83) | Apple_scab (0.09) | Root_rot_collar_rot (0.02) | yes |
| SCB_09.jpg | Apple_scab | none | Apple_scab (0.92) | Apple_scab_rust (0.01) | Gray_spot (0.01) | yes |

**Fruit photos (information only, not scored; true disease is scab):** answers Apple_scab x5; mean confidence 0.92

_Speed on this machine: 150 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

### B / preprocessing: squash224 / apple classes only (crop picked first)

| True disease | n | Top-1 exact | Top-1 lenient* | Top-3 lenient* | Mean prob. on true class | Mean top-1 confidence |
|---|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 1/8 = 12% | 1/8 = 12% | 3/8 = 38% | 0.12 | 0.88 |
| Apple_scab | 4 | 3/4 = 75% | 4/4 = 100% | 4/4 = 100% | 0.92 | 0.87 |
| Marssonina_blotch | 11 | 2/11 = 18% | 5/11 = 45% | 7/11 = 64% | 0.43 | 0.88 |
| **all leaf photos** | 23 | 6/23 = 26% | 10/23 = 43% | 14/23 = 61% | 0.41 | 0.88 |
| **reliable labels only** | 19 | 4/19 = 21% | 7/19 = 37% | 10/19 = 53% | 0.35 | 0.88 |

*lenient = counts the dataset aliases (Brown spot = Marssonina, Scab & Rust = Scab) as the same disease. 'Mean prob. on true class' is 0 where the model has no such class.

**What the model answers for each true disease (top-1 counts):**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab_rust x4; Apple_scab x1; Root_rot_collar_rot x1; Brown_spot x1; Alternaria_leaf_spot x1 |
| Apple_scab | Apple_scab x3; Apple_scab_rust x1 |
| Marssonina_blotch | Apple_scab x6; Brown_spot x3; Marssonina_blotch x2 |

**Confidence cut-offs (leaf photos).** Our design uses show >= 0.45 and auto-advice >= 0.65; model A's authors chose 0.50.

| Cut-off | Answered (coverage) | Correct among answered (lenient) |
|---|---|---|
| 0.30 | 23/23 = 100% | 10/23 = 43% |
| 0.45 | 23/23 = 100% | 10/23 = 43% |
| 0.50 | 23/23 = 100% | 10/23 = 43% |
| 0.65 | 23/23 = 100% | 10/23 = 43% |
| 0.80 | 21/23 = 91% | 8/21 = 38% |
| 0.90 | 12/23 = 52% | 3/12 = 25% |

**Confidently wrong (top-1 confidence >= 0.45 and not the true disease): 13 of 23**

| Photo | True | Doubt | Model said | Confidence |
|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.82 |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab | 0.92 |
| ALT_04.jpg | Alternaria_leaf_spot | high | Root_rot_collar_rot | 0.90 |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.83 |
| ALT_08.jpg | Alternaria_leaf_spot | low | Brown_spot | 0.87 |
| ALT_09.jpg | Alternaria_leaf_spot | none | Apple_scab_rust | 0.91 |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab | 0.91 |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab | 0.92 |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab | 0.84 |
| MAR_06.jpg | Marssonina_blotch | none | Apple_scab | 0.92 |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab | 0.90 |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab | 0.92 |

**Every leaf photo:**

| Photo | True | Doubt | 1st answer (conf.) | 2nd | 3rd | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Gray_spot (0.02) | Root_rot_collar_rot (0.02) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.82) | Alternaria_leaf_spot (0.05) | Root_rot_collar_rot (0.03) | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple_scab (0.92) | Gray_spot (0.01) | Brown_spot (0.01) | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Root_rot_collar_rot (0.90) | Alternaria_leaf_spot (0.02) | Apple_scab_rust (0.02) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.83) | Root_rot_collar_rot (0.10) | Apple_scab (0.02) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Brown_spot (0.87) | Apple_scab_rust (0.05) | Apple_scab (0.02) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Apple_scab_rust (0.91) | Apple_scab (0.01) | Root_rot_collar_rot (0.01) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Alternaria_leaf_spot (0.83) | Gray_spot (0.08) | Root_rot_collar_rot (0.02) | yes |
| MAR_01.jpg | Marssonina_blotch | none | Apple_scab (0.91) | Root_rot_collar_rot (0.01) | Apple_scab_rust (0.01) | NO |
| MAR_02.jpg | Marssonina_blotch | none | Brown_spot (0.88) | Apple_scab (0.06) | Apple_scab_rust (0.01) | yes |
| MAR_03.jpg | Marssonina_blotch | none | Brown_spot (0.89) | Apple_scab (0.04) | Apple_scab_rust (0.01) | yes |
| MAR_04a.jpg | Marssonina_blotch | none | Apple_scab (0.92) | Apple_scab_rust (0.01) | Root_rot_collar_rot (0.01) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Marssonina_blotch (0.87) | Brown_spot (0.06) | Apple_scab (0.02) | yes |
| MAR_05.jpg | Marssonina_blotch | none | Apple_scab (0.84) | Brown_spot (0.05) | Marssonina_blotch (0.04) | NO |
| MAR_06.jpg | Marssonina_blotch | none | Apple_scab (0.92) | Apple_scab_rust (0.01) | Brown_spot (0.01) | NO |
| MAR_07.jpg | Marssonina_blotch | none | Marssonina_blotch (0.88) | Brown_spot (0.03) | Gray_spot (0.02) | yes |
| MAR_08.jpg | Marssonina_blotch | none | Apple_scab (0.90) | Apple_scab_rust (0.02) | Root_rot_collar_rot (0.02) | NO |
| MAR_09.jpg | Marssonina_blotch | none | Brown_spot (0.80) | Marssonina_blotch (0.11) | Apple_scab (0.02) | yes |
| MAR_10.jpg | Marssonina_blotch | low | Apple_scab (0.92) | Root_rot_collar_rot (0.01) | Apple_scab_rust (0.01) | NO |
| SCB_05l.jpg | Apple_scab | medium | Apple_scab (0.92) | Apple_scab_rust (0.01) | Alternaria_leaf_spot (0.01) | yes |
| SCB_05r.jpg | Apple_scab | medium | Apple_scab (0.92) | Apple_scab_rust (0.02) | Root_rot_collar_rot (0.01) | yes |
| SCB_06.jpg | Apple_scab | medium | Apple_scab_rust (0.74) | Apple_scab (0.16) | Root_rot_collar_rot (0.02) | yes |
| SCB_09.jpg | Apple_scab | none | Apple_scab (0.92) | Apple_scab_rust (0.01) | Gray_spot (0.01) | yes |

**Fruit photos (information only, not scored; true disease is scab):** answers Apple_scab x5; mean confidence 0.92

_Speed on this machine: 154 ms per photo on average (CPU, includes preprocessing). Not a phone speed._

## Does the preprocessing matter?

| Model | Classes | default: top-1 lenient | squash224: top-1 lenient |
|---|---|---|---|
| A | all_classes | 0/23 = 0% | 0/23 = 0% |
| A | apple_only | 3/23 = 13% | 3/23 = 13% |
| B | apple_only | 11/23 = 48% | 10/23 = 43% |

## Next

Send this file and `predictions.csv` back for review. Do not train anything yet.
