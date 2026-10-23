"""Message catalogue: every farmer-facing string the rules engine produces (English + draft plain spoken Hindi).

Hindi is a DRAFT for native-speaker review: short sentences, no jargon, units written as words so a voice can read them.
Placeholders use str.format names; a param may be a Bilingual(en, hi) so product names render in each language.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple

from app.domain.types import LocalizedText


class Bilingual(NamedTuple):
    en: str
    hi: str


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS_HI = ("जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर")


def format_date(value: date | datetime, lang: str) -> str:
    months = _MONTHS_HI if lang == "hi" else _MONTHS_EN
    return f"{value.day} {months[value.month - 1]}"


def format_number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def _render(value: object, lang: str) -> str:
    if isinstance(value, Bilingual):
        return value.hi if lang == "hi" else value.en
    if isinstance(value, datetime | date):
        return format_date(value, lang)
    if isinstance(value, float):
        return format_number(value)
    if isinstance(value, list | tuple):
        sep = " और " if lang == "hi" else " and "
        parts = [_render(v, lang) for v in value]
        return ", ".join(parts[:-1]) + sep + parts[-1] if len(parts) > 1 else "".join(parts)
    return str(value)


# key -> (English, Hindi)
CATALOGUE: dict[str, tuple[str, str]] = {
    # ------------------------------------------------------------------------------------------ product warnings
    "PROPOSED_BAN": (
        "{name} may be banned in future. It is still allowed today. Use another medicine from the list if you can.",
        "{name} पर आगे रोक लग सकती है। अभी इसकी अनुमति है। हो सके तो सूची की कोई दूसरी दवा लें।",
    ),
    "NO_WAITING_PERIOD": (
        "The waiting period of {name} is not given in the schedule. Ask an expert before you use it near harvest.",
        "{name} के बाद फल तोड़ने से पहले कितने दिन रुकना है, यह सूची में नहीं दिया है। तुड़ाई के पास इसे लेने से पहले खेती के जानकार से पूछें।",
    ),
    "DOSE_PER_200L": (
        "The dose is for 200 litres of water.",
        "यह मात्रा 200 लीटर पानी के लिए है।",
    ),
    "DODINE_RESTRICTIONS": (
        "Do not mix dodine with any other medicine. Do not spray it when the temperature is above 30 degrees. Do not use hard water.",
        "डोडीन को किसी दूसरी दवा के साथ न मिलाएँ। तापमान 30 डिग्री से ऊपर हो तो छिड़काव न करें। कठोर पानी का इस्तेमाल न करें।",
    ),
    "CAPTAN_OIL_INFO": (
        "Keep 15 days between a captan spray and an oil spray.",
        "कैप्टान और तेल वाले छिड़काव के बीच 15 दिन का अंतर रखें।",
    ),
    "SAME_FRAC_NO_ALTERNATIVE": (
        "Your last spray was from the same medicine group ({code}) and no other group is available now. Use it only once, then change the group.",
        "आपका पिछला छिड़काव इसी दवा-समूह ({code}) का था और अभी कोई दूसरा समूह उपलब्ध नहीं है। इसे सिर्फ़ एक बार लें, फिर समूह बदलें।",
    ),
    # ------------------------------------------------------------------------------------------ output warnings
    "NO_TANK_MIX": (
        "Do not mix any other medicine, nutrient or growth spray with this spray. Spray each one separately.",
        "इस छिड़काव में कोई दूसरी दवा, पोषक तत्व या हार्मोन न मिलाएँ। हर एक को अलग से छिड़कें।",
    ),
    "STALE_HISTORY": (
        "We have no spray record after {date}. Please tell us if you sprayed since then, so the advice is correct.",
        "{date} के बाद का कोई छिड़काव दर्ज नहीं है। अगर उसके बाद छिड़काव किया है तो बताइए, ताकि सलाह सही रहे।",
    ),
    "STALE_HISTORY_NONE": (
        "We have no spray record for you. Please tell us what you sprayed this season, so the advice is correct.",
        "आपका कोई छिड़काव दर्ज नहीं है। इस मौसम में क्या छिड़का है, यह बताइए, ताकि सलाह सही रहे।",
    ),
    "OFF_LABEL_HISTORY": (
        "Your records show {products}. This is not approved for apple. We will never advise it. Please ask your expert before you use it again.",
        "आपके रिकॉर्ड में {products} है। यह सेब के लिए मंज़ूर नहीं है। हम इसकी सलाह कभी नहीं देंगे। दोबारा लेने से पहले अपने खेती के जानकार से पूछें।",
    ),
    "TANK_MIX_HISTORY": (
        "On {date} a nutrient was logged on the same day as a fungicide. The Himachal schedule says to spray nutrients separately, not mixed with the recommended medicines.",
        "{date} को फफूंदनाशक वाले दिन ही पोषक तत्व भी दर्ज हैं। हिमाचल की सारणी कहती है कि पोषक तत्व अलग से छिड़कें, सिफ़ारिश की गई दवाओं के साथ न मिलाएँ।",
    ),
    "ROTATION_DMI": (
        "You have used the DMI group (FRAC 3) {count} times this season. The limit is {limit}. Do not use more medicine of this group.",
        "इस मौसम में आप डीएमआई समूह (FRAC 3) की दवा {count} बार ले चुके हैं। सीमा {limit} बार है। इस समूह की और दवा न लें।",
    ),
    "ROTATION_QOI": (
        "You have used the QoI group (FRAC 11) {count} times this season. The limit is {limit}. Do not use more medicine of this group.",
        "इस मौसम में आप क्यूओआई समूह (FRAC 11) की दवा {count} बार ले चुके हैं। सीमा {limit} बार है। इस समूह की और दवा न लें।",
    ),
    "ROTATION_SDHI": (
        "Your last {count} fungicide sprays were from the SDHI group (FRAC 7). Use a different group next.",
        "आपके पिछले {count} फफूंदनाशक छिड़काव एसडीएचआई समूह (FRAC 7) के थे। अगली बार दूसरे समूह की दवा लें।",
    ),
    "ROTATION_QOI_SOLO": (
        "{name} is a QoI medicine used alone. This group must be used only in a mixture with another group.",
        "{name} अकेली क्यूओआई दवा है। इस समूह की दवा सिर्फ़ किसी दूसरे समूह के मिश्रण में ही लें।",
    ),
    "ROTATION_SAME_ACTIVE": (
        "{name} is the same medicine as your last spray. Do not repeat the same medicine.",
        "{name} वही दवा है जो आपने पिछली बार छिड़की थी। वही दवा दोबारा न लें।",
    ),
    "ROTATION_SAME_FRAC": (
        "{name} is from the same medicine group ({code}) as your last spray. Change the group.",
        "{name} आपके पिछले छिड़काव वाले ही दवा-समूह ({code}) की है। समूह बदलें।",
    ),
    "HARVEST_DATE_UNKNOWN": (
        "We do not know your harvest date. Do not harvest before the waiting period of the medicine is over.",
        "आपकी तुड़ाई की तारीख हमें नहीं पता। दवा का इंतज़ार का समय पूरा होने से पहले फल न तोड़ें।",
    ),
    "NEAR_HARVEST": (
        "Harvest is about {days} days away. Check the waiting period before you spray.",
        "तुड़ाई लगभग {days} दिन में है। छिड़काव से पहले इंतज़ार का समय देख लें।",
    ),
    "WAITING_PERIOD_EXCEEDS_HARVEST": (
        "The waiting period of {name} is {wp} days. Harvest is expected in {days} days. Do not harvest before the waiting period is over.",
        "{name} के बाद {wp} दिन रुकना ज़रूरी है। तुड़ाई लगभग {days} दिन में है। यह समय पूरा होने से पहले फल न तोड़ें।",
    ),
    "BANNED_PRODUCT": (
        "{name} is banned. Do not use it again. Please tell your expert.",
        "{name} पर रोक है। इसे दोबारा न लें। अपने खेती के जानकार को बताइए।",
    ),
    "OFF_LABEL_PRODUCT": (
        "{name} is not approved for apple. Please do not use it again.",
        "{name} सेब के लिए मंज़ूर नहीं है। कृपया इसे दोबारा न लें।",
    ),
    "CAPTAN_OIL_GAP": (
        "Captan and an oil spray were used within 15 days of each other. Keep 15 days between them.",
        "कैप्टान और तेल वाला छिड़काव 15 दिन के अंदर किए गए हैं। इनके बीच 15 दिन का अंतर रखें।",
    ),
    # ------------------------------------------------------------------------------------------ timing
    "TIMING_SPRAY_NOW": (
        "No rain is expected in the next 12 hours. You can spray now.",
        "अगले 12 घंटे बारिश की उम्मीद नहीं है। आप अभी छिड़काव कर सकते हैं।",
    ),
    "TIMING_WAIT": (
        "About {rain} millimetres of rain are expected in the next 12 hours. Wait. Spray when the leaves are dry and no rain is expected for {hours} hours.",
        "अगले 12 घंटे में लगभग {rain} मिलीमीटर बारिश की उम्मीद है। रुकें। जब पत्ते सूखे हों और {hours} घंटे बारिश न हो, तब छिड़काव करें।",
    ),
    "TIMING_REPEAT": (
        "Heavy rain fell within 12 hours of your last spray. Spray again within {days} days. Do not use the same medicine.",
        "पिछले छिड़काव के 12 घंटे के अंदर तेज़ बारिश हुई। {days} दिन के अंदर फिर छिड़काव करें। वही दवा दोबारा न लें।",
    ),
    "TIMING_REPEAT_WAIT": (
        "Heavy rain fell within 12 hours of your last spray. Spray again within {days} days with a different medicine. More rain is expected now, so wait until the leaves are dry.",
        "पिछले छिड़काव के 12 घंटे के अंदर तेज़ बारिश हुई। {days} दिन के अंदर दूसरी दवा से फिर छिड़काव करें। अभी और बारिश की उम्मीद है, इसलिए पत्ते सूखने तक रुकें।",
    ),
    "TIMING_UNKNOWN": (
        "We cannot see the weather now. Look at the sky and the forecast before you spray.",
        "अभी मौसम की जानकारी नहीं है। छिड़काव से पहले आसमान और मौसम का अनुमान देख लें।",
    ),
    # ------------------------------------------------------------------------------------------ risks
    "RISK_SCAB_TITLE": ("Apple scab infection risk", "सेब स्कैब (पपड़ी रोग) के संक्रमण का खतरा"),
    "RISK_SCAB_RED": (
        "The leaves stayed wet long enough for scab to infect. Look at your trees and ask for spray advice today.",
        "पत्तियाँ इतनी देर गीली रहीं कि स्कैब का संक्रमण हो सकता है। अपने पेड़ देखें और आज ही छिड़काव की सलाह लें।",
    ),
    "RISK_SCAB_YELLOW": (
        "Wet weather is close to causing a scab infection. Keep watching the weather.",
        "गीला मौसम स्कैब के संक्रमण के करीब है। मौसम पर नज़र रखें।",
    ),
    "RISK_SCAB_GREEN": (
        "There is no scab infection period now.",
        "अभी स्कैब के संक्रमण का खतरा नहीं है।",
    ),
    "RISK_SCAB_OFF_SEASON": (
        "It is not the main scab season for your orchard now.",
        "आपके बाग में अभी स्कैब का मुख्य मौसम नहीं है।",
    ),
    "RISK_LEAFSPOT_TITLE": ("Leaf spot weather (Marssonina, Alternaria)", "पत्ती धब्बा रोग का मौसम (मार्सोनिना, आल्टरनेरिया)"),
    "RISK_LEAFSPOT_RED": (
        "It has been warm and humid for five days or more. Leaf spots can spread fast. Check your leaves and call your expert.",
        "पाँच दिन या उससे ज़्यादा से गर्मी और नमी है। पत्तियों के धब्बे तेज़ी से फैल सकते हैं। पत्तियाँ देखें और अपने खेती के जानकार से बात करें।",
    ),
    "RISK_LEAFSPOT_YELLOW": (
        "It is getting warm and humid. Watch your leaves for brown spots.",
        "गर्मी और नमी बढ़ रही है। पत्तियों पर भूरे धब्बे देखते रहें।",
    ),
    "RISK_LEAFSPOT_GREEN": (
        "The weather is not favourable for leaf spots now.",
        "अभी मौसम पत्ती धब्बे के लिए अनुकूल नहीं है।",
    ),
    "RISK_LEAFSPOT_OFF_SEASON": (
        "The leaf spot season starts on 1 June.",
        "पत्ती धब्बे का मौसम 1 जून से शुरू होता है।",
    ),
    "RISK_BLIGHT_TITLE": ("Late blight risk", "पछेती झुलसा (लेट ब्लाइट) का खतरा"),
    "RISK_BLIGHT_RED": (
        "The last seven days were cool, wet and humid. Late blight can appear within ten days. Check your leaves often and ask for advice.",
        "पिछले सात दिन ठंडे, गीले और नमी वाले रहे। दस दिन के अंदर पछेती झुलसा आ सकता है। पत्तियाँ बार-बार देखें और सलाह लें।",
    ),
    "RISK_BLIGHT_YELLOW": (
        "The weather is getting close to late blight conditions. Check your leaves.",
        "मौसम पछेती झुलसा के हालात के करीब आ रहा है। अपनी पत्तियाँ देखें।",
    ),
    "RISK_BLIGHT_GREEN": (
        "There is no late blight weather now.",
        "अभी पछेती झुलसा वाला मौसम नहीं है।",
    ),
    "RISK_WASHOFF_TITLE": ("Rain after your spray", "छिड़काव के बाद बारिश"),
    "RISK_WASHOFF_RED": (
        "Heavy rain fell soon after your spray, about {rain} millimetres. The spray may be washed off. Spray again within {days} days with a different medicine.",
        "छिड़काव के तुरंत बाद तेज़ बारिश हुई, लगभग {rain} मिलीमीटर। दवा धुल गई हो सकती है। {days} दिन के अंदर दूसरी दवा से फिर छिड़काव करें।",
    ),
    "RISK_WASHOFF_YELLOW": (
        "About {rain} millimetres of rain are expected soon after your spray. It may wash the spray off. Check the weather.",
        "छिड़काव के तुरंत बाद लगभग {rain} मिलीमीटर बारिश की उम्मीद है। दवा धुल सकती है। मौसम देखते रहें।",
    ),
    "RISK_WASHOFF_GREEN": (
        "The rain after your spray was light. The spray should stay on the leaves.",
        "छिड़काव के बाद हल्की बारिश हुई। दवा पत्तियों पर टिकी रहनी चाहिए।",
    ),
    "RISK_NO_DATA": (
        "There is not enough weather data to check this risk.",
        "इस खतरे को जाँचने के लिए मौसम की जानकारी काफ़ी नहीं है।",
    ),
    # ------------------------------------------------------------------------------------------ non-chemical measures
    "NO_CURE": (
        "This problem has no cure. A spray will not make the sick plant well. Remove the sick plants so the disease does not spread, and ask your expert how to protect the other plants.",
        "इस बीमारी का कोई इलाज नहीं है। छिड़काव से बीमार पौधा ठीक नहीं होगा। बीमारी न फैले, इसलिए बीमार पौधे हटा दें और बाकी पौधे बचाने का तरीका अपने खेती के जानकार से पूछें।",
    ),
    "HYGIENE": (
        "Remove badly affected leaves and fallen leaves from the field and put them in a compost pit.",
        "बहुत खराब पत्तियाँ और गिरी हुई पत्तियाँ खेत से हटाकर खाद के गड्ढे में डालें।",
    ),
    # ------------------------------------------------------------------------------------------ rank reasons (plain strings)
    "RANK_SYSTEMIC_INFECTION": (
        "A scab infection period is active, so a medicine that works inside the leaf is preferred.",
        "स्कैब के संक्रमण का समय चल रहा है, इसलिए पत्ती के अंदर काम करने वाली दवा को पहले रखा है।",
    ),
    "RANK_PROTECTANT": (
        "There is no infection period now, so a cover spray that protects the leaf surface is preferred.",
        "अभी संक्रमण का समय नहीं है, इसलिए पत्ती की सतह को बचाने वाली दवा को पहले रखा है।",
    ),
    "RANK_HP_BRAND": (
        "Brands tested by the Himachal department are available.",
        "हिमाचल विभाग द्वारा जाँचे गए ब्रांड उपलब्ध हैं।",
    ),
    "RANK_PROPOSED_BAN": (
        "Ranked lower because it may be banned in future.",
        "आगे रोक लगने की संभावना के कारण इसे नीचे रखा है।",
    ),
    "RANK_WAITING_KNOWN": (
        "The waiting period is known.",
        "इंतज़ार का समय पता है।",
    ),
}

# Hindi for the catalogue's non_chemical text (data/reference/disease_catalogue.csv), keyed by the exact English text.
NON_CHEMICAL_HI: dict[str, str] = {
    "Compost fallen leaf litter or spray 5% urea on the orchard floor (HP 2026 point 8). Keep 12-14 day interval until the end of primary scab in scab-prone areas.":
        "गिरी हुई पत्तियों की खाद बनाएँ, या बाग की ज़मीन पर 5 प्रतिशत यूरिया का छिड़काव करें। स्कैब वाले इलाकों में शुरुआती स्कैब की अवस्था खत्म होने तक छिड़कावों के बीच 12 से 14 दिन का अंतर रखें।",
    "Sanitation: prune and remove cankered wood and mummified fruit":
        "सफ़ाई रखें: रोगी टहनियाँ छाँटकर हटाएँ और सूखे सड़े फल तोड़कर नष्ट करें।",
    "No measures needed unless an expert confirms the disease":
        "जब तक खेती के जानकार रोग की पुष्टि न करे, कोई उपाय ज़रूरी नहीं है।",
    "Better in open, well-pruned orchards; compost leaf litter":
        "खुले और ठीक से छँटाई वाले बाग में रोग कम होता है। गिरी हुई पत्तियों की खाद बनाएँ।",
    "Compost leaf litter; balanced nutrition":
        "गिरी हुई पत्तियों की खाद बनाएँ। संतुलित खाद दें।",
    "Prune out infected terminals":
        "रोगी सिरे वाली टहनियाँ काटकर हटा दें।",
    "Bordeaux paint on collar in winter; improve drainage":
        "सर्दियों में तने के निचले हिस्से पर बोर्डो पेस्ट लगाएँ। पानी की निकासी ठीक करें।",
    "Prune and burn cankered wood":
        "रोगी लकड़ी काटकर जला दें।",
    "Keep insecticide use minimal in April-June to protect natural enemies; spray the basin too":
        "अप्रैल से जून में कीटनाशक कम से कम इस्तेमाल करें, ताकि मित्र कीट बचे रहें। पेड़ के थाले में भी छिड़काव करें।",
    "Disease-free seed/seedlings; avoid overhead irrigation":
        "रोग-मुक्त बीज और पौध लें। ऊपर से पानी न दें।",
    "Crop rotation; remove infected debris":
        "फसल चक्र अपनाएँ। रोगी पौधों के अवशेष हटाएँ।",
    "Resistant varieties; remove infected plants":
        "रोग सहने वाली किस्में लगाएँ। रोगी पौधे हटा दें।",
    "Ventilation; avoid leaf wetness":
        "हवा का आना-जाना बनाए रखें। पत्तियों को गीला न रहने दें।",
    "Rotate crops; remove debris":
        "फसल चक्र अपनाएँ। फसल के अवशेष हटाएँ।",
    "Avoid dust and water stress":
        "धूल और पानी की कमी से बचाएँ।",
    "No cure. Net nursery, roguing, maize barrier rows, 10 yellow traps per acre, resistant varieties (Arka Rakshak, Arka Ananya)":
        "इलाज नहीं है। पौध जाली के अंदर तैयार करें। बीमार पौधे उखाड़ दें। मक्का की बाड़ वाली कतारें लगाएँ। हर एकड़ में 10 पीले चिपचिपे जाल लगाएँ। रोग सहने वाली किस्में (अर्का रक्षक, अर्का अनन्या) लगाएँ।",
    "No chemical control. Roguing, hygiene, disease-free seed, rotation":
        "रासायनिक इलाज नहीं है। बीमार पौधे उखाड़ें, सफ़ाई रखें, रोग-मुक्त बीज लें और फसल चक्र अपनाएँ।",
    "Balanced fertiliser; rotation":
        "संतुलित खाद दें। फसल चक्र अपनाएँ।",
    "Resistant varieties (Kufri Jyoti, Kufri Girdhari)":
        "रोग सहने वाली किस्में (कुफरी ज्योति, कुफरी गिरधारी) लगाएँ।",
    "Rotation; residue management":
        "फसल चक्र अपनाएँ। फसल के अवशेष संभालें।",
    "Resistant hybrids":
        "रोग सहने वाली संकर किस्में लगाएँ।",
    "Resistant hybrids; rotation":
        "रोग सहने वाली संकर किस्में लगाएँ। फसल चक्र अपनाएँ।",
    "Remove mummified fruit":
        "सूखे सड़े फल तोड़कर हटा दें।",
    "Protect pruning wounds; remove infected wood (UC IPM)":
        "छँटाई के घावों को बचाएँ। रोगी लकड़ी हटा दें।",
    "Canopy management":
        "टहनियों की ठीक से छँटाई करें, ताकि पेड़ में हवा और धूप आए।",
}


def text(key: str, **params: object) -> LocalizedText:
    """Localised text for `key`; raises KeyError for an unknown key so typos fail loudly."""
    en, hi = CATALOGUE[key]
    return LocalizedText(
        en=en.format(**{k: _render(v, "en") for k, v in params.items()}),
        hi=hi.format(**{k: _render(v, "hi") for k, v in params.items()}),
    )


def plain(key: str, lang: str, **params: object) -> str:
    return text(key, **params).get(lang)


def non_chemical(english: str) -> LocalizedText:
    """Catalogue non-chemical text with its Hindi draft; a text without a Hindi draft falls back to the hygiene measure."""
    hindi = NON_CHEMICAL_HI.get(english)
    if hindi is None:
        return text("HYGIENE")
    return LocalizedText(en=english, hi=hindi)
