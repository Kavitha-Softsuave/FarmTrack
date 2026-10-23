# Research: pretrained plant/leaf disease models (for the FarmTrack MVP)

**Researched:** 19 Oct 2026.

**Labels:**
- **[V]** the page or Hugging Face API was opened and read
- **[R]** the value comes from a search-result summary only
- **[I]** our inference

Key claims spot-checked again by the main session through the Hugging Face API on 19 Oct 2026: neghani licence and 16% field figure; ixrbhii licence; linkanjarad licence "other"; Kindwise pricing.

## Bottom line
- **No off-the-shelf model reaches 90–95% on field photos.**
  - Multi-crop checkpoints report 95–99.9% on test sets drawn from their own training data, mostly PlantVillage lab images.
  - Field accuracy for PlantVillage-trained models is roughly **15–40%**.
  - Plantix (commercial) advertises about **73–74%** on field images [V].
- **MVP approach:**
  - small on-device model with "not sure"
  - server fallback
  - collect labelled Himachal field photos from day 1 for a phase-2 fine-tune

## Ranked options
1. **Server fallback: Kindwise crop.health API** [V]
   - Covers about 23 crops including apple, and about 288 pests, diseases and deficiencies.
   - Self-serve. €0.05 per call (from 1,000 credits) down to €0.01 (from 1.5M); 100 free credits.
   - Credits bought in purchases of 30,000 or more expire after 3 months.
   - No offline mode. Marssonina and Alternaria coverage is unconfirmed, so test it.
   - Alternative: **Plantix Vision API**. 57 crops, about 970 stressors, about 73–74% on field images. Sales-led, 4–6 weeks onboarding, no public price.
2. **On-device: PlantVillage MobileNetV2 → int8 TFLite**
   - **`neghani/plantvillage-mobilenetv2`**: Apache-2.0, 9.3 MB fp32. 99.17% on the PlantVillage test set but **16% top-1 on 25 cropped PlantDoc images** (16 of 25 answered "not sure"). Updated 12 Oct 2026.
   - `onnx-community/mobilenet_v2_1.0_224-plant-disease-identification-ONNX` has a ready **int8 ONNX (2.7 MB)**, but its licence is "other" with no terms.
3. **Server / teacher: `ixrbhii/multicrop-disease-models`** (CC-BY-4.0)
   - 42 per-crop ConvNeXt-Small models, about 99 MB each; includes apple, apricot, cherry, peach, pear, walnut, tomato and potato.
   - **`ixrbhii/apple-disease-convnext` is the only public model with a Marssonina Blotch class.** It reports 99.2% on its own test set and 98.8% recall on 82 Marssonina images.
   - New (4 Oct 2026), vague data sources, and not field-validated.

**Not recommended:**
- `Arko007/agromind-plant-disease-nfnet`: 519 MB, no accuracy reported.
- `JK-TK/PlantDiseaseDetection`: YOLOv11x trained on PlantWild, which is non-commercial; Ultralytics is AGPL [I].

## Models table
| Model (huggingface.co/…) | Arch | Data | Classes | Reported acc. | Licence | Size / formats |
|---|---|---|---|---|---|---|
| `neghani/plantvillage-mobilenetv2` | MobileNetV2 | PlantVillage + Cropped-PlantDoc (27 of 38 classes) | 38 PV | 99.17% PV; **16% field** | **Apache-2.0** | 9.3 MB safetensors |
| `linkanjarad/mobilenet_v2_1.0_224-plant-disease-identification` | MobileNetV2 | PV | 38 | 95.4% PV | "other" | 9.3 MB |
| `onnx-community/…-ONNX` | same | same | 38 | same | "other" | ONNX int8 2.7 MB, fp16 4.8 MB |
| `Kathir56/plant-disease-tamilnadu` | MobileNetV2 | PV | 38 | 97.3% | Apache-2.0 | 9.3 MB |
| `rodynaemad/plant-disease-dinov2-small` | DINOv2-small + linear head | PV (leaf-grouped split) | 38 | 98.9% | CC-BY-SA-4.0 | ONNX int8 24 MB |
| `animeshakr/plant-disease-efficientnetv2s` | EffNetV2-S | PV | 38 | 99.57% | MIT | TFLite fp16 41.8 MB |
| `ixrbhii/apple-disease-convnext` | ConvNeXt-S | unspecified | 8 apple incl. Marssonina, Alternaria | 99.2% (own test) | CC-BY-4.0 | 99 MB |
| `ixrbhii/multicrop-disease-models` | 42 × ConvNeXt-S + crop detectors | "LeafNet", PV, others | 42 crops | 91–100% per crop | CC-BY-4.0 | ~99 MB / crop |
| `Bazaar/cv_apple_leaf_disease_detection` | ViT-base | AppleLeaf9 labels | 9 apple | 97.6% | **none** | 343 MB |
| `nahuelnb/plant-pathology-efficientnetb2` | EffNet-B2 | Plant Pathology 2020 (field) | 4 | 97.0% | Apache-2.0 | 31 MB |
| `imageomics/bioclip` (zero-shot) | CLIP ViT | TreeOfLife | open | PV 24.4%, PlantDoc 28.4% | MIT | 599 MB |
| `Madras1/plantdoc-rtdetrv2-leaf-disease-detector` | RT-DETRv2 | PlantDoc (field) | 27 | mAP50 33.7% | Apache-2.0 | 80.6 MB |

## Datasets
| Dataset | Classes (apple) | Images | Field/lab | Licence |
|---|---|---|---|---|
| PlantVillage | 38 classes / 14 crops; apple: scab, black rot, cedar rust, healthy | 54,306 | Lab | **Ambiguous**: CC-BY-SA-3.0 on HF `mohanty/PlantVillage`; CC0 claimed elsewhere; none on GitHub |
| PlantDoc | 27 classes / 13 species; apple: scab, leaf, rust | 2,598 (9,216 cropped) | Field/web | CC-BY-4.0 ✔ (github.com/pratikkayal/PlantDoc-Dataset) |
| Plant Pathology 2020 / 2021 (FGVC) | scab, rust, frog-eye, powdery mildew, complex | 3,651 / ~18.6k | Field (US) | Kaggle terms unverified; HF mirror says Apache-2.0 |
| AppleLeaf9 | 9 apple classes incl. Alternaria, mosaic | 14,582 | Mostly field | CC-BY-4.0, but it merges other sets |
| **Indigenous Apple Leaf Dataset (J&K)** | healthy, Alternaria, mosaic | 7,569 | **Field, Indian** | CC-BY-4.0 ✔ (data.mendeley.com/datasets/9m2dcb5mmr/3) |
| PlantWild | 89/115 classes | 18.5k / 11.5k | Web | **CC-BY-NC-ND**: avoid |
| Khan et al. 2020 (Kashmir) | incl. **Marssonina** (1,312) | ~8,400 | Field | not public |

**No public Himachal dataset exists.**

## Evidence of domain shift
- **Mohanty 2016:** 99.35% on PlantVillage → 31.4% / 31.7% on web images.
- **PlantDoc paper:** PlantVillage-trained → cropped PlantDoc 19.7–39.9%; fine-tuning on PlantDoc → 60–70%. On uncropped images: 15.1%.
- **PlantVillage background bias:** 8 background pixels alone give 49% accuracy (arXiv 2206.04374).

## Himachal coverage gaps
| Disease | Public model | Public dataset |
|---|---|---|
| Scab | many | many |
| **Marssonina blotch** | only `ixrbhii` apple (server) | none downloadable |
| Alternaria | ixrbhii, Bazaar (no licence) | AppleLeaf9, J&K Indigenous |
| Powdery mildew, mosaic | Bazaar / Plant Pathology 2021 | yes |
| Mites, woolly aphid, San Jose scale on apple | **none** | **none** |
| Cedar apple rust | PlantVillage has it | **does not occur on apple in India**, so treat as a low-prior class |

## On-device facts
- **MobileNetV3 paper (Pixel 1, TFLite, single core):**
  - V3-Large: 51 ms float / 44 ms quantised
  - V3-Small: about 15.5 ms
  - V2: 64 / 52 ms
- **Expect** about 50–200 ms on budget Android phones from 2020 onward [I].
- **Flutter packages:**
  - `flutter_litert` 3.9.4: released 12 Oct 2026, active
  - `tflite_flutter` 0.12.1: last released 28 Oct 2025
  - `flutter_onnxruntime` 1.9.0
  - `executorch_flutter` 0.8.0
- **Conversion:** PyTorch → TFLite via `ai-edge-torch` (or ONNX) → int8 quantisation.

## PlantVillage 38 classes (the on-device label set)
| Crop | Classes |
|---|---|
| Apple | Scab, Black rot, Cedar apple rust, healthy |
| Blueberry | healthy |
| Cherry | Powdery mildew, healthy |
| Corn | Cercospora/Gray leaf spot, Common rust, Northern leaf blight, healthy |
| Grape | Black rot, Esca, Leaf blight (Isariopsis), healthy |
| Orange | Huanglongbing |
| Peach | Bacterial spot, healthy |
| Pepper (bell) | Bacterial spot, healthy |
| Potato | Early blight, Late blight, healthy |
| Raspberry | healthy |
| Soybean | healthy |
| Squash | Powdery mildew |
| Strawberry | Leaf scorch, healthy |
| Tomato | Bacterial spot, Early blight, Late blight, Leaf mold, Septoria, Spider mites, Target spot, Yellow leaf curl virus, Mosaic virus, healthy |

## Key URLs
- huggingface.co/neghani/plantvillage-mobilenetv2
- huggingface.co/ixrbhii/apple-disease-convnext
- huggingface.co/ixrbhii/multicrop-disease-models
- huggingface.co/onnx-community/mobilenet_v2_1.0_224-plant-disease-identification-ONNX
- github.com/pratikkayal/PlantDoc-Dataset
- data.mendeley.com/datasets/9m2dcb5mmr/3
- kindwise.com/crop-health
- kindwise.com/pricing
- plantix.net/en/business/plantix-vision-api
- arxiv.org/pdf/1911.10317
- arxiv.org/abs/2206.04374
- pub.dev/packages/flutter_litert
