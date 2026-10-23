# ChatGPT photo analysis report

Run: 2026-10-19 16:16 | model: **gpt-4o-mini** | image detail: high | photos: 2 leaf + 0 fruit

## Read this first

- **Same caveats as the vision test:** web images, labels not agronomist-confirmed, tiny n (one photo moves a disease by 9 to 25 points), so this is directional only.
- **Answers from a language model vary from run to run.** One run is one sample; repeat before drawing conclusions.
- **The true label was never sent.** The `closed` variant gives it the project's own symptom descriptions (like RAG); `open` gives nothing; `hybrid` adds the vision model's top 3.
- **The model's stated probability is its own claim, not a measured accuracy.**

## Variant: closed

| True disease | n | Top-1 correct | In its top 3 | Mean stated probability |
|---|---|---|---|---|
| Alternaria_leaf_spot | 2 | 1/2 = 50% | 2/2 = 100% | 0.55 |
| **all leaf photos** | 2 | 1/2 = 50% | 2/2 = 100% | 0.55 |
| **reliable labels only** | 2 | 1/2 = 50% | 2/2 = 100% | 0.55 |

**What it answers for each true disease:**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x1; Alternaria_leaf_spot x1 |

**Does its stated probability separate right from wrong?** Mean when right 0.60 (n=1), when wrong 0.50 (n=1); chance that a right answer is more confident than a wrong one: 1.00 (0.50 = tells nothing).

**Confidently wrong (stated probability >= 0.45 and wrong): 1 of 2**

**Asked for an expert / said unclear:** 0 of 2 photos; among those, it would have been wrong anyway on 0. Among the 2 it answered without flagging, 1 were right.

**Every leaf photo:**

| Photo | True | Doubt | Subject it saw | 1st (p) | 2nd (p) | 3rd (p) | Right? |
|---|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | single_leaf | scab (0.50) | marssonina_blotch (0.30) | alternaria_leaf_spot (0.20) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | single_leaf | alternaria_leaf_spot (0.60) | marssonina_blotch (0.30) | other_or_unclear (0.10) | yes |


## Variant: open

Free-text answers matched to a disease by keyword (the table below shows the raw text so you can judge).

| True disease | n | Named as most likely | Named anywhere in its list |
|---|---|---|---|
| Alternaria_leaf_spot | 2 | 0/2 = 0% | 0/2 = 0% |

| Photo | True | Doubt | Most likely (its words) | Others | Conf. | Right? |
|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal Leaf Spot; Bacterial Leaf Blight; Nutrient Deficiency | 0.70 | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | Apple Scab | Fungal infection; Bacterial infection; Nutrient deficiency | 0.80 | NO |


## Variant: hybrid

| True disease | n | Top-1 correct | In its top 3 | Mean stated probability |
|---|---|---|---|---|
| Alternaria_leaf_spot | 2 | 1/2 = 50% | 1/2 = 50% | 0.65 |
| **all leaf photos** | 2 | 1/2 = 50% | 1/2 = 50% | 0.65 |
| **reliable labels only** | 2 | 1/2 = 50% | 1/2 = 50% | 0.65 |

**What it answers for each true disease:**

| True disease | Answers |
|---|---|
| Alternaria_leaf_spot | Apple_scab x1; Alternaria_leaf_spot x1 |

**Does its stated probability separate right from wrong?** Mean when right 0.60 (n=1), when wrong 0.70 (n=1); chance that a right answer is more confident than a wrong one: 0.00 (0.50 = tells nothing).

**Confidently wrong (stated probability >= 0.45 and wrong): 1 of 2**

**Asked for an expert / said unclear:** 1 of 2 photos; among those, it would have been wrong anyway on 1. Among the 1 it answered without flagging, 1 were right.

**Effect of the vision model's hint:** it agreed with the vision model's first choice on 1 of 2 photos; it fixed 1 photos the vision model got wrong and broke 0 that the vision model got right (lenient scoring for the vision model).

**Every leaf photo:**

| Photo | True | Doubt | Subject it saw | 1st (p) | 2nd (p) | 3rd (p) | Right? |
|---|---|---|---|---|---|---|---|
| ALT_01.jpg | Alternaria_leaf_spot | none | single_leaf | scab (0.70) | marssonina_blotch (0.20) | other_or_unclear (0.10) | NO |
| ALT_02.jpg | Alternaria_leaf_spot | none | leaves_on_branch | alternaria_leaf_spot (0.60) | scab (0.30) | other_or_unclear (0.10) | yes |


## Side by side with the vision model B (same photos)

| True disease | n | Vision B exact | Vision B lenient* | ChatGPT closed | ChatGPT hybrid |
|---|---|---|---|---|---|
| Alternaria_leaf_spot | 2 | 0/2 = 0% | 0/2 = 0% | 1/2 = 50% | 1/2 = 50% |

*lenient counts Brown spot as Marssonina and Scab & Rust as Scab (inferred aliases).

## Cost of this run

6 requests, 71,051 input tokens, 986 output tokens: about $0.011.
