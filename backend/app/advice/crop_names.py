"""Hindi display names of crops (DRAFT for the native-speaker review, like all Hindi in this project).

One table for every place that builds a crop name: the scan card (`services/catalogue.py`), the advice text (`advice/refdata.py`).
Sources: data/reference/hindi_glossary.json (the five demo crops), voice/prompts.json `crop_is_*`, mobile/assets/l10n/strings.json,
plus everyday names of the crops the detectors can name. A crop missing here keeps its English name (never an empty field).
"""
from __future__ import annotations

# key: lower case, spaces and punctuation as '_' (see `crop_key`)
CROP_HI: dict[str, str] = {
    # the five crops with approved-list data
    "apple": "सेब", "tomato": "टमाटर", "potato": "आलू", "maize": "मक्का", "grape": "अंगूर",
    # the Himachal crop list (voice/prompts.json crop_is_*)
    "pear": "नाशपाती", "plum": "आलूबुखारा", "peach": "आड़ू", "apricot": "खुबानी", "cherry": "चेरी", "walnut": "अखरोट",
    "pomegranate": "अनार", "kiwi": "कीवी", "strawberry": "स्ट्रॉबेरी", "pea": "मटर", "cauliflower": "फूलगोभी",
    "cabbage": "पत्तागोभी", "capsicum": "शिमला मिर्च", "pepper": "शिमला मिर्च", "beans": "बीन्स", "wheat": "गेहूँ",
    "paddy": "धान", "rice": "धान", "barley": "जौ", "ginger": "अदरक", "cucumber": "खीरा", "mango": "आम", "citrus": "नींबू",
    "orange": "संतरा", "litchi": "लीची", "soybean": "सोयाबीन", "blueberry": "ब्लूबेरी", "raspberry": "रास्पबेरी",
    # other crops a detector or the PlantVillage classes can name
    "squash": "कद्दू", "cucurbit": "कद्दू", "banana": "केला", "brinjal": "बैंगन", "cashew": "काजू", "custard_apple": "शरीफा",
    "coconut": "नारियल", "guava": "अमरूद", "mulberry": "शहतूत", "papaya": "पपीता", "rose": "गुलाब", "watermelon": "तरबूज",
    "okra": "भिंडी", "betel": "पान", "bitter_gourd": "करेला", "black_pepper": "काली मिर्च", "bottle_gourd": "लौकी",
    "cassava": "कसावा", "chrysanthemum": "गुलदाउदी", "coffee": "कॉफ़ी", "fig": "अंजीर", "loquat": "लोकाट",
    "ridge_gourd": "तोरी", "snake_gourd": "चिचिंडा", "sorghum": "ज्वार", "sugarcane": "गन्ना", "tea": "चाय",
}


def crop_key(crop_id: str) -> str:
    return "_".join(part for part in "".join(c if c.isalnum() else " " for c in crop_id.lower()).split())


def crop_hi(crop_id: str) -> str | None:
    """The Hindi name of a crop id in any spelling ('Apple', 'custard apple', 'Custard_Apple'); None when there is none."""
    return CROP_HI.get(crop_key(crop_id))
