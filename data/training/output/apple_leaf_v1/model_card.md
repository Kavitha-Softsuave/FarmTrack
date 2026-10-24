# FarmTrack apple leaf classifier v1 (internal demo model)

Created 2026-10-24 15:37 by `data/training/train_apple.py`. Classes: Apple___Apple_scab, Apple___Marssonina_blotch, Apple___Alternaria_leaf_spot, Apple___healthy.
Architecture `convnext_tiny.fb_in22k_ft_in1k` (timm), ImageNet-pretrained backbone frozen, linear head trained, temperature folded into the head. fp16 weights.

## Status: NOT validated for farmers
Labels are dataset folder names, **not confirmed by an agronomist**. The Marssonina class is the datasets' "Brown spot" (inferred to be
*Diplocarpon mali*). Accuracy below is on research/web images and does not describe field photos from Himachal. Do not quote 90-95 %.

## Data (photos are not redistributed; provenance per file in `data/training/sources.csv`)
Images per class used: {'Apple___Apple_scab': 400, 'Apple___Marssonina_blotch': 372, 'Apple___Alternaria_leaf_spot': 450, 'Apple___healthy': 450}. Images per source: {'AppleLeaf9': 1362, 'J&K-Mendeley': 310}. Image groups after merging near-duplicates: 1662.
Licences recorded in sources.csv (rows): {'CC-BY-4.0 / Yang, Duan & Wang (AppleLeaf9 compilers); images originate f': 1572, 'CC-BY-4.0 / Arshad Yatoo and Amit Sharma (Lovely Professional University': 400}.
All sources are CC BY 4.0 (attribution required: AppleLeaf9 compilers Yang, Duan and Wang, Agronomy 2022, 12(11), 2784; Yatoo and Sharma, Mendeley Data, DOI 10.17632/9m2dcb5mmr.3).

## Cross-validation (5-fold, group-disjoint, on train/val): accuracy 0.969, macro-F1 0.970
| class | precision | recall | F1 | n |
|---|---|---|---|---|
| Apple___Apple_scab | 0.96 | 0.97 | 0.96 | 320 |
| Apple___Marssonina_blotch | 0.98 | 1.00 | 0.99 | 298 |
| Apple___Alternaria_leaf_spot | 0.97 | 0.95 | 0.96 | 360 |
| Apple___healthy | 0.96 | 0.97 | 0.96 | 360 |

| true \ predicted | Apple_scab | Marssonina_blotch | Alternaria_leaf_spot | healthy |
|---|---|---|---|---|
| Apple_scab | 309 | 0 | 4 | 7 |
| Marssonina_blotch | 0 | 297 | 1 | 0 |
| Alternaria_leaf_spot | 5 | 5 | 343 | 7 |
| healthy | 8 | 0 | 4 | 348 |

## Held-out test (group-disjoint, 334 photos): accuracy 0.979, macro-F1 0.979
| class | precision | recall | F1 | n |
|---|---|---|---|---|
| Apple___Apple_scab | 0.96 | 0.97 | 0.97 | 80 |
| Apple___Marssonina_blotch | 0.99 | 0.99 | 0.99 | 74 |
| Apple___Alternaria_leaf_spot | 0.99 | 0.99 | 0.99 | 90 |
| Apple___healthy | 0.98 | 0.97 | 0.97 | 90 |

| true \ predicted | Apple_scab | Marssonina_blotch | Alternaria_leaf_spot | healthy |
|---|---|---|---|---|
| Apple_scab | 78 | 0 | 0 | 2 |
| Marssonina_blotch | 0 | 73 | 1 | 0 |
| Alternaria_leaf_spot | 0 | 1 | 89 | 0 |
| healthy | 3 | 0 | 0 | 87 |

Calibration: temperature 0.42; ECE 0.103 before, 0.005 after (out-of-fold).
Accuracy by source (test): {'AppleLeaf9': {'n': 274, 'accuracy': 0.9744525547445255}, 'J&K-Mendeley': {'n': 60, 'accuracy': 1.0}}

## Other sets

**external_test** (2 photos, never trained on): accuracy 0.50
- wm_blattsymptome.jpg: Apple___Apple_scab (0.772)
- wm_rome_leaf.jpg: Apple___Marssonina_blotch (0.565)


## Limits
- Labels = dataset folder names; no agronomist confirmed them (Marssonina = dataset class 'Brown spot', inferred).
- Each class comes mostly from a different source/imaging setup, so part of the accuracy may be source recognition, not disease recognition.
- Research/web images, not field photos from Himachal farmers: field accuracy will be lower. Never quote these numbers as 90-95%.
- Test split is group-disjoint but drawn from the same datasets as training.
- Marssonina photos come from ONE source (AppleLeaf9 'Brown spot': yellowing leaves with dark blotches, mostly on a white background), so its 99 % recall is largely source recognition. The only independent real Marssonina photo (Wikimedia, CC0) was called Marssonina at just 0.57, and the other Commons photo was called scab.
- The Kashmir (J&K) images are pre-augmented by their authors (rotations with smeared edges); the central 70 % is used and siblings of one leaf may survive grouping, so J&K accuracy is optimistic.
