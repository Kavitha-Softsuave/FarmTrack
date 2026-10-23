# ChatGPT photo analysis report

Run: 2026-10-19 16:24 | model: **gpt-4o-mini** | image detail: high | photos: 23 leaf + 5 fruit

## Read this first

- **Same caveats as the vision test:** web images, labels not agronomist-confirmed, tiny n (one photo moves a disease by 9 to 25 points), so this is directional only.
- **Answers from a language model vary from run to run.** One run is one sample; repeat before drawing conclusions.
- **The true label was never sent.** The `closed` variant gives it the project's own symptom descriptions (like RAG); `open` gives nothing; `hybrid` adds the vision model's top 3.
- **The model's stated probability is its own claim, not a measured accuracy.**

## Variant: closed

| True disease | n | Top-1 correct | In its top 3 | Mean stated probability |
|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 2/8 = 25% | 7/8 = 88% | 0.55 |
| Apple_scab | 4 | 0/4 = 0% | 3/4 = 75% | 0.60 |
| Marssonina_blotch | 11 | 11/11 = 100% | 11/11 = 100% | 0.52 |
| **all leaf photos** | 23 | 13/23 = 57% | 21/23 = 91% | 0.54 |
| **reliable labels only** | 19 | 13/19 = 68% | 17/19 = 89% | 0.53 |

**What it answers for each true disease:**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Marssonina_blotch x3; Alternaria_leaf_spot x2; Cedar_apple_rust x2; Apple_scab x1 |
| Apple_scab | Alternaria_leaf_spot x3; Marssonina_blotch x1 |
| Marssonina_blotch | Marssonina_blotch x11 |

**Does its stated probability separate right from wrong?** Mean when right 0.52 (n=13), when wrong 0.57 (n=10); chance that a right answer is more confident than a wrong one: 0.27 (0.50 = tells nothing).

**Confidently wrong (stated probability >= 0.45 and wrong): 10 of 23**

**Asked for an expert / said unclear:** 7 of 23 photos; among those, it would have been wrong anyway on 2. Among the 16 it answered without flagging, 8 were right.

**Every leaf photo:**

| Photo | True | Doubt | Subject it saw | 1st (p) | 2nd (p) | 3rd (p) | Right? |
|---|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | single_leaf | scab (0.60) | marssonina_blotch (0.30) | other_or_unclear (0.10) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | yes |
| ALT_03.jpg | Alternaria_leaf_spot | none | single_leaf | alternaria_leaf_spot (0.50) | marssonina_blotch (0.30) | scab (0.20) | yes |
| ALT_04.jpg | Alternaria_leaf_spot | high | single_leaf | rust (0.60) | alternaria_leaf_spot (0.30) | other_or_unclear (0.10) | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | leaves_on_branch | rust (0.60) | alternaria_leaf_spot (0.30) | other_or_unclear (0.10) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | other_or_unclear (0.20) | NO |
| MAR_01.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| MAR_02.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | other_or_unclear (0.10) | yes |
| MAR_03.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | other_or_unclear (0.20) | yes |
| MAR_04a.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| MAR_04b.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | other_or_unclear (0.20) | yes |
| MAR_05.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| MAR_06.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | other_or_unclear (0.10) | yes |
| MAR_07.jpg | Marssonina_blotch | none | leaves_on_branch | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| MAR_08.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| MAR_09.jpg | Marssonina_blotch | none | leaves_on_branch | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | other_or_unclear (0.20) | yes |
| MAR_10.jpg | Marssonina_blotch | low | leaves_on_branch | marssonina_blotch (0.50) | alternaria_leaf_spot (0.30) | scab (0.20) | yes |
| SCB_05l.jpg | Apple_scab | medium | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | NO |
| SCB_05r.jpg | Apple_scab | medium | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | NO |
| SCB_06.jpg | Apple_scab | medium | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | NO |
| SCB_09.jpg | Apple_scab | none | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | other_or_unclear (0.10) | NO |

**Fruit photos (true disease: scab):** it called 0 of 5 scab; subject recognised as fruit in 3.


## Variant: open

Free-text answers matched to a disease by keyword (the table below shows the raw text so you can judge).

| True disease | n | Named as most likely | Named anywhere in its list |
|---|---|---|---|
| Alternaria_leaf_spot | 8 | 0/8 = 0% | 0/8 = 0% |
| Apple_scab | 4 | 4/4 = 100% | 4/4 = 100% |
| Marssonina_blotch | 11 | 0/11 = 0% | 0/11 = 0% |

| Photo | True | Doubt | Most likely (its words) | Others | Conf. | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Blight; Nutrient Deficiency | 0.70 | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Spot; Nutrient Deficiency | 0.80 | NO |
| ALT_03.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Spot; Nutrient Deficiency | 0.70 | NO |
| ALT_04.jpg | Alternaria_leaf_spot | high | Apple scab | Fungal leaf spot; Rust disease; Bacterial infection | 0.80 | NO |
| ALT_07.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Blight; Nutrient Deficiency | 0.70 | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Blight; Nutrient Deficiency | 0.70 | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | Apple scab | Powdery mildew; Rust; Fungal infection | 0.80 | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Spot; Nutrient Deficiency | 0.80 | NO |
| MAR_01.jpg | Marssonina_blotch | none | Apple Scab | Fungal infection; Nutrient deficiency; Bacterial disease | 0.70 | NO |
| MAR_02.jpg | Marssonina_blotch | none | Apple scab | Fungal infection; Nutrient deficiency; Bacterial infection | 0.80 | NO |
| MAR_03.jpg | Marssonina_blotch | none | Apple scab | Fungal infection; Nutrient deficiency; Bacterial infection | 0.70 | NO |
| MAR_04a.jpg | Marssonina_blotch | none | Apple Scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.70 | NO |
| MAR_04b.jpg | Marssonina_blotch | none | Apple mosaic virus | Nutrient deficiency (e.g., nitrogen or magnesium); Fungal infection; E | 0.70 | NO |
| MAR_05.jpg | Marssonina_blotch | none | Apple Scab | Fungal Leaf Spot; Bacterial Blight; Nutrient Deficiency | 0.80 | NO |
| MAR_06.jpg | Marssonina_blotch | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Spot; Nutrient Deficiency | 0.70 | NO |
| MAR_07.jpg | Marssonina_blotch | none | Apple Scab | Fungal Leaf Spot; Powdery Mildew; Nutrient Deficiency | 0.80 | NO |
| MAR_08.jpg | Marssonina_blotch | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Spot; Nutrient Deficiency | 0.80 | NO |
| MAR_09.jpg | Marssonina_blotch | none | apple scab | powdery mildew; leaf spot disease; nutrient deficiency | 0.80 | NO |
| MAR_10.jpg | Marssonina_blotch | low | Apple Scab | Powdery Mildew; Fungal Leaf Spot; Nutrient Deficiency | 0.70 | NO |
| SCB_05l.jpg | Apple_scab | medium | Apple scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.80 | yes |
| SCB_05r.jpg | Apple_scab | medium | Apple scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.80 | yes |
| SCB_06.jpg | Apple_scab | medium | Apple Scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.80 | yes |
| SCB_09.jpg | Apple_scab | none | Apple scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.80 | yes |


## Variant: hybrid

| True disease | n | Top-1 correct | In its top 3 | Mean stated probability |
|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 4/8 = 50% | 6/8 = 75% | 0.64 |
| Apple_scab | 4 | 3/4 = 75% | 4/4 = 100% | 0.75 |
| Marssonina_blotch | 11 | 6/11 = 55% | 11/11 = 100% | 0.64 |
| **all leaf photos** | 23 | 13/23 = 57% | 21/23 = 91% | 0.66 |
| **reliable labels only** | 19 | 10/19 = 53% | 17/19 = 89% | 0.65 |

**What it answers for each true disease:**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Alternaria_leaf_spot x4; Marssonina_blotch x2; Apple_scab x1; Cedar_apple_rust x1 |
| Apple_scab | Apple_scab x3; Alternaria_leaf_spot x1 |
| Marssonina_blotch | Marssonina_blotch x6; Alternaria_leaf_spot x3; Apple_scab x2 |

**Does its stated probability separate right from wrong?** Mean when right 0.66 (n=13), when wrong 0.66 (n=10); chance that a right answer is more confident than a wrong one: 0.49 (0.50 = tells nothing).

**Confidently wrong (stated probability >= 0.45 and wrong): 10 of 23**

**Asked for an expert / said unclear:** 3 of 23 photos; among those, it would have been wrong anyway on 1. Among the 20 it answered without flagging, 11 were right.

**Effect of the vision model's hint:** it agreed with the vision model's first choice on 14 of 23 photos; it fixed 3 photos the vision model got wrong and broke 1 that the vision model got right (lenient scoring for the vision model).

**Every leaf photo:**

| Photo | True | Doubt | Subject it saw | 1st (p) | 2nd (p) | 3rd (p) | Right? |
|---|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | single_leaf | scab (0.70) | marssonina_blotch (0.20) | other_or_unclear (0.10) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | leaves_on_branch | alternaria_leaf_spot (0.60) | scab (0.30) | other_or_unclear (0.10) | yes |
| ALT_03.jpg | Alternaria_leaf_spot | none | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | yes |
| ALT_04.jpg | Alternaria_leaf_spot | high | single_leaf | alternaria_leaf_spot (0.60) | rust (0.30) | scab (0.10) | yes |
| ALT_07.jpg | Alternaria_leaf_spot | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | NO |
| ALT_08.jpg | Alternaria_leaf_spot | low | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | NO |
| ALT_09.jpg | Alternaria_leaf_spot | none | leaves_on_branch | rust (0.70) | scab (0.20) | other_or_unclear (0.10) | NO |
| ALT_10.jpg | Alternaria_leaf_spot | none | leaves_on_branch | alternaria_leaf_spot (0.70) | marssonina_blotch (0.20) | scab (0.10) | yes |
| MAR_01.jpg | Marssonina_blotch | none | single_leaf | scab (0.70) | marssonina_blotch (0.20) | other_or_unclear (0.10) | NO |
| MAR_02.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | other_or_unclear (0.10) | yes |
| MAR_03.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | yes |
| MAR_04a.jpg | Marssonina_blotch | none | single_leaf | alternaria_leaf_spot (0.70) | marssonina_blotch (0.20) | scab (0.10) | NO |
| MAR_04b.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.70) | alternaria_leaf_spot (0.20) | scab (0.10) | yes |
| MAR_05.jpg | Marssonina_blotch | none | single_leaf | alternaria_leaf_spot (0.50) | marssonina_blotch (0.30) | scab (0.20) | NO |
| MAR_06.jpg | Marssonina_blotch | none | single_leaf | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | yes |
| MAR_07.jpg | Marssonina_blotch | none | leaves_on_branch | marssonina_blotch (0.60) | scab (0.25) | other_or_unclear (0.15) | yes |
| MAR_08.jpg | Marssonina_blotch | none | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | NO |
| MAR_09.jpg | Marssonina_blotch | none | leaves_on_branch | marssonina_blotch (0.60) | alternaria_leaf_spot (0.30) | scab (0.10) | yes |
| MAR_10.jpg | Marssonina_blotch | low | leaves_on_branch | scab (0.85) | marssonina_blotch (0.10) | other_or_unclear (0.05) | NO |
| SCB_05l.jpg | Apple_scab | medium | single_leaf | scab (0.85) | alternaria_leaf_spot (0.10) | other_or_unclear (0.05) | yes |
| SCB_05r.jpg | Apple_scab | medium | single_leaf | scab (0.70) | marssonina_blotch (0.20) | other_or_unclear (0.10) | yes |
| SCB_06.jpg | Apple_scab | medium | leaves_on_branch | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | scab (0.10) | NO |
| SCB_09.jpg | Apple_scab | none | single_leaf | scab (0.85) | marssonina_blotch (0.10) | other_or_unclear (0.05) | yes |

**Fruit photos (true disease: scab):** it called 2 of 5 scab; subject recognised as fruit in 4.


## Side by side with the vision model B (same photos)

| True disease | n | Vision B exact | Vision B lenient* | ChatGPT closed | ChatGPT hybrid |
|---|---|---|---|---|---|
| Alternaria_leaf_spot | 8 | 1/8 = 12% | 1/8 = 12% | 2/8 = 25% | 4/8 = 50% |
| Apple_scab | 4 | 3/4 = 75% | 4/4 = 100% | 0/4 = 0% | 3/4 = 75% |
| Marssonina_blotch | 11 | 2/11 = 18% | 6/11 = 55% | 11/11 = 100% | 6/11 = 55% |

*lenient counts Brown spot as Marssonina and Scab & Rust as Scab (inferred aliases).

## Cost of this run

84 requests, 1,079,670 input tokens, 13,717 output tokens: about $0.170.
