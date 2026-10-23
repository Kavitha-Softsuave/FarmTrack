"""Label sets, crop ids and the crop -> label masks used by the vision models. Pure data and tiny helpers: no torch, no I/O.

Crop ids follow the data catalogue ('Apple', 'Tomato', 'Maize', 'Pepper', ...); disease ids follow
data/reference/disease_catalogue.csv ('Apple___Apple_scab', ...).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

# ---------------------------------------------------------------------------------------------- crop ids
DEMO_CROPS: tuple[str, ...] = ("Apple", "Tomato", "Potato", "Maize", "Grape")   # crops with approved-list data in the MVP

# Crops of the Himachal crop list that NO photo model covers (plan section 4.8): crop identification cannot name them
# (the detectors do not know them either) and the disease classifier reports model_covers_crop=False.
NO_PHOTO_MODEL_CROPS: frozenset[str] = frozenset(
    {"Pea", "Cauliflower", "Cabbage", "Wheat", "Ginger", "Kiwi", "Plum", "Barley", "Beans"})

_CROP_ALIASES: dict[str, str] = {
    "corn": "Maize", "paddy": "Rice", "capsicum": "Pepper", "bell_pepper": "Pepper", "pepper_bell": "Pepper",
    "peas": "Pea", "bean": "Beans", "kiwifruit": "Kiwi", "orange": "Citrus", "lemon": "Citrus", "malta": "Citrus",
    "citrus_(orange_/_lemon)": "Citrus", "cucurbit_(pumpkin_/_melon)": "Cucurbit",
}


def canonical_crop(name: str) -> str:
    """Normalise a crop name to the catalogue style: 'apple' -> 'Apple', 'custard apple' -> 'Custard_Apple', 'Corn' -> 'Maize'.

    Unknown names are title-cased, never rejected (the farmer's profile may list a crop no model knows).
    """
    key = re.sub(r"[\s\-]+", "_", name.strip().lower())
    if key in _CROP_ALIASES:
        return _CROP_ALIASES[key]
    return "_".join(part[:1].upper() + part[1:] for part in key.split("_") if part)


def canonical_crops(names: Iterable[str]) -> list[str]:
    """Canonical, de-duplicated, order-preserving; blanks dropped."""
    out: list[str] = []
    for n in names:
        if n and n.strip():
            c = canonical_crop(n)
            if c and c not in out:
                out.append(c)
    return out


# ---------------------------------------------------------------------------------------------- model A (PlantVillage, 38 classes)
# Exactly the label names of neghani/plantvillage-mobilenetv2 (id2label order) = the catalogue ids with detectable_by 'ondevice_pv'.
PV_LABELS: tuple[str, ...] = (
    "Apple___Apple_scab", "Apple___Black_rot", "Apple___Cedar_apple_rust", "Apple___healthy", "Blueberry___healthy",
    "Cherry_(including_sour)___Powdery_mildew", "Cherry_(including_sour)___healthy",
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "Corn_(maize)___Common_rust_", "Corn_(maize)___Northern_Leaf_Blight",
    "Corn_(maize)___healthy", "Grape___Black_rot", "Grape___Esca_(Black_Measles)", "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)",
    "Grape___healthy", "Orange___Haunglongbing_(Citrus_greening)", "Peach___Bacterial_spot", "Peach___healthy",
    "Pepper,_bell___Bacterial_spot", "Pepper,_bell___healthy", "Potato___Early_blight", "Potato___Late_blight", "Potato___healthy",
    "Raspberry___healthy", "Soybean___healthy", "Squash___Powdery_mildew", "Strawberry___Leaf_scorch", "Strawberry___healthy",
    "Tomato___Bacterial_spot", "Tomato___Early_blight", "Tomato___Late_blight", "Tomato___Leaf_Mold", "Tomato___Septoria_leaf_spot",
    "Tomato___Spider_mites Two-spotted_spider_mite", "Tomato___Target_Spot", "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato___Tomato_mosaic_virus", "Tomato___healthy",
)

# crop id -> the PlantVillage label prefix of that crop
PV_CROP_PREFIX: dict[str, str] = {
    "Apple": "Apple___", "Blueberry": "Blueberry___", "Cherry": "Cherry_(including_sour)___", "Maize": "Corn_(maize)___",
    "Grape": "Grape___", "Citrus": "Orange___", "Peach": "Peach___", "Pepper": "Pepper,_bell___", "Potato": "Potato___",
    "Raspberry": "Raspberry___", "Soybean": "Soybean___", "Squash": "Squash___", "Strawberry": "Strawberry___", "Tomato": "Tomato___",
}


def pv_labels_for(crop_id: str, labels: Sequence[str] = PV_LABELS) -> list[str]:
    """The model-A classes of one crop (the crop mask). Empty when model A has no class for the crop."""
    prefix = PV_CROP_PREFIX.get(canonical_crop(crop_id))
    return [lab for lab in labels if prefix and lab.startswith(prefix)]


# A one-class mask (Blueberry/Raspberry/Soybean healthy, Orange HLB, Squash mildew) always renormalises to confidence 1.0, which
# says nothing about the leaf: those crops are NOT treated as covered even though PlantVillage has a class for them.
A_COVERED_CROPS: frozenset[str] = frozenset(c for c in PV_CROP_PREFIX if len(pv_labels_for(c)) >= 2)

# ---------------------------------------------------------------------------------------------- model B (apple, 8 classes)
# raw label names of ixrbhii/apple-disease-convnext -> catalogue disease ids
B_MAP: dict[str, str] = {
    "Apple Scab": "Apple___Apple_scab", "Apple Scab & Rust": "Apple___Apple_scab_rust", "Gray Spot": "Apple___Gray_spot",
    "Brown Spot": "Apple___Brown_spot", "Alternaria Leaf Spot": "Apple___Alternaria_leaf_spot", "Healthy": "Apple___healthy",
    "Marssonina Blotch": "Apple___Marssonina_blotch", "Root Rot / Collar Rot": "Apple___Root_rot_collar_rot",
}
B_COVERED_CROPS: frozenset[str] = frozenset({"Apple"})

# ---------------------------------------------------------------------------------------------- crop detectors
# label_names of the two detectors (pinned revisions, see inference.py). The detectors are closed-world: a crop they do not know is
# taken for a known one, so the farmer's own crops must be used as a prior (see crop.py).
DETECTOR_16_LABELS: tuple[str, ...] = (
    "Apple", "Banana", "Brinjal", "Cashew", "Custard Apple", "Cherry", "Coconut", "Guava", "Mango", "Mulberry", "Papaya", "Rose",
    "Strawberry", "Watermelon", "Okra", "Pomegranate",
)
DETECTOR_36_LABELS: tuple[str, ...] = (
    "Apple", "Apricot", "Betel", "Bitter Gourd", "Black Pepper", "Bottle Gourd", "Cashew", "Cassava", "Cherry", "Chrysanthemum",
    "Citrus (Orange / Lemon)", "Coffee", "Cucumber", "Cucurbit (Pumpkin / Melon)", "Fig", "Grape", "Loquat", "Maize", "Mango", "Peach",
    "Pear", "Pepper", "Potato", "Raspberry", "Rice", "Ridge Gourd", "Rose", "Snake Gourd", "Sorghum", "Soybean", "Squash",
    "Strawberry", "Sugarcane", "Tea", "Tomato", "Walnut",
)


def detector_label_to_crop(label: str) -> str:
    """Detector label name -> catalogue crop id ('Custard Apple' -> 'Custard_Apple', 'Citrus (Orange / Lemon)' -> 'Citrus')."""
    return canonical_crop(label)
