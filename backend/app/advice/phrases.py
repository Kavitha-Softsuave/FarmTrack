"""Fixed farmer-facing sentences (English + Hindi) used by the template drafts and the spoken text.

All Hindi here is a DRAFT for native-speaker review (see docs/design-notes/advice.md). Rules for every sentence: plain words, short,
no medicine unless the rule output lists it, and every sentence that mentions spraying also says 'not', 'wait', 'before' or
'ask' where the situation calls for it (the validator relies on that).
"""
from __future__ import annotations

from app.domain.types import LocalizedText


def loc(en: str, hi: str) -> LocalizedText:
    return LocalizedText(en=en, hi=hi)


# ---------------------------------------------------------------- shared
SEVERITY_SENTENCE = {
    "green": loc("This is not urgent, but treat it so that it does not spread.",
                 "यह जल्दी का मामला नहीं है, पर फैलने से रोकने के लिए इलाज कर लें।"),
    "yellow": loc("This needs attention soon.", "इस पर जल्दी ध्यान देना ज़रूरी है।"),
    "red": loc("This is serious. Please act quickly.", "यह गंभीर है। कृपया जल्दी कदम उठाएँ।"),
}
SEVERITY_CLAUSE = {                       # for the one-sentence spoken diagnosis
    "green": loc("", ""),
    "yellow": loc(", and it needs attention soon", ", और इस पर जल्दी ध्यान देना ज़रूरी है"),
    "red": loc(", and it is serious", ", और यह गंभीर है"),
}

EXPERT_CONFIRM = loc("Please confirm with your agriculture expert before you spray.",
                     "छिड़काव से पहले अपने खेती के जानकार से पक्का कर लें।")
EXPERT_WILL_CONFIRM = loc("If the problem grows, show the plant to a local agriculture expert.",
                          "अगर दिक्कत बढ़े तो पौधा अपने स्थानीय खेती के जानकार को दिखाएँ।")
MIXING = loc("Do not mix any other pesticide, nutrient or growth regulator with the spray.",
             "छिड़काव की दवा में कोई और दवा, पोषक तत्व या वृद्धि नियामक न मिलाएँ।")
PPE_SPOKEN = loc("Wear gloves, goggles and full clothes while you spray, and keep children and animals away.",
                 "छिड़काव करते समय दस्ताने, चश्मा और पूरे कपड़े पहनें, और बच्चों और पशुओं को दूर रखें।")
CHOOSE_ONE = loc("Choose one of the medicines below for each spray.",
                 "हर छिड़काव के लिए नीचे दी गई दवाओं में से एक चुनें।")

TIMING_ACTION = {
    "spray_now": loc("You can spray now.", "आप अभी छिड़काव कर सकते हैं।"),
    "wait": loc("Do not spray now. Wait until it is safe to spray.", "अभी छिड़काव न करें। छिड़काव का सही समय आने तक रुकें।"),
    "not_needed": loc("Spraying is not needed now.", "अभी छिड़काव की ज़रूरत नहीं है।"),
    "unknown": loc("Ask your expert for the best time to spray.", "छिड़काव का सही समय खेती के जानकार से पूछें।"),
}


def repeat_sentence(days: int | None) -> LocalizedText:
    if days is None:
        return loc("You will need to spray again. Ask your expert when.", "दोबारा छिड़काव करना होगा। कब करना है, यह खेती के जानकार से पूछें।")
    return loc(f"Spray again within {days} days.", f"{days} दिन के अंदर दोबारा छिड़काव करें।")


def timing_sentence(action: str, repeat_days: int | None) -> LocalizedText:
    return repeat_sentence(repeat_days) if action == "repeat_within_days" else TIMING_ACTION.get(action, TIMING_ACTION["unknown"])


def waiting_sentence(days: int | None) -> LocalizedText:
    if days is None:
        return loc("No waiting period is listed for this medicine, so ask your expert if harvest is near.",
                   "इस दवा के लिए तुड़ाई से पहले रुकने के दिन नहीं लिखे हैं, इसलिए तुड़ाई पास हो तो खेती के जानकार से पूछें।")
    return loc(f"Do not harvest for at least {days} days after you spray.", f"छिड़काव के बाद कम से कम {days} दिन तक तुड़ाई न करें।")


# ---------------------------------------------------------------- names in sentences
def crop_phrase(crop: LocalizedText) -> LocalizedText:
    return loc(f"{crop.en} crop", f"{crop.hi} की फसल")


# ---------------------------------------------------------------- statuses that carry no medicine
GENERIC_MEASURES = (
    loc("Remove fallen leaves and badly spotted leaves from around the plants.",
        "पौधों के आसपास गिरी हुई और बहुत धब्बे वाली पत्तियाँ हटा दें।"),
    loc("Watch the plants. If the spots spread quickly, take another clear photo.",
        "पौधों पर नज़र रखें। धब्बे तेज़ी से फैलें तो दूसरी साफ़ फ़ोटो लें।"),
)
NO_SPRAY_UNTIL_EXPERT = loc("Do not spray any medicine until you know what is wrong.",
                            "जब तक पक्का न पता चले कि क्या दिक्कत है, कोई भी दवा न छिड़कें।")

EXPERT_HEADLINE = loc("Not sure yet: do not spray any medicine now", "अभी पक्का नहीं है: अभी कोई दवा न छिड़कें")
NO_DATA_HEADLINE = loc("No approved medicine advice for this crop yet", "इस फसल के लिए अभी मंज़ूर दवा की सलाह उपलब्ध नहीं है")
NOT_DISEASE_HEADLINE = loc("No disease seen in this photo", "इस फ़ोटो में कोई रोग नहीं दिखा")
MORE_INFO_HEADLINE = loc("One more clear photo please", "कृपया एक और साफ़ फ़ोटो लें")

MORE_INFO_SUMMARY = loc("The app needs one more clear photo before it can help. There is no medicine advice yet.",
                        "मदद करने से पहले ऐप को एक और साफ़ फ़ोटो चाहिए। अभी दवा की कोई सलाह नहीं है।")
MORE_INFO_STEPS = (
    loc("Take a close photo of one leaf in daylight.", "दिन की रोशनी में एक पत्ती की पास से फ़ोटो लें।"),
    loc("Hold the phone steady and fill the screen with the leaf.", "फ़ोन को सीधा पकड़ें और पूरी स्क्रीन पर पत्ती दिखाएँ।"),
    loc("Send the new photo.", "नई फ़ोटो भेजें।"),
)
MORE_INFO_SPOKEN = loc("I need one more clear photo. Take a close photo of one leaf in daylight. Hold the phone steady. "
                       "Then send the new photo.",
                       "मुझे एक और साफ़ फ़ोटो चाहिए। दिन की रोशनी में एक पत्ती की पास से फ़ोटो लें। फ़ोन को सीधा पकड़ें। "
                       "फिर नई फ़ोटो भेजें।")


def expert_summary(crop: LocalizedText) -> LocalizedText:
    c = crop_phrase(crop)
    return loc(f"The app is not sure what is wrong with your {c.en}. Please do not spray any medicine yet. "
               "Take another clear photo of one leaf, or show the plant to a local agriculture expert.",
               f"ऐप को पक्का नहीं पता कि आपकी {c.hi} में क्या दिक्कत है। अभी कोई दवा न छिड़कें। "
               "एक पत्ती की दूसरी साफ़ फ़ोटो लें, या पौधा अपने स्थानीय खेती के जानकार को दिखाएँ।")


def no_data_summary(crop: LocalizedText) -> LocalizedText:
    c = crop_phrase(crop)
    return loc(f"The app does not have approved medicine advice for your {c.en} yet. "
               "Please ask a local agriculture expert before you use any medicine.",
               f"आपकी {c.hi} के लिए ऐप के पास अभी मंज़ूर दवा की सलाह नहीं है। "
               "कोई भी दवा इस्तेमाल करने से पहले अपने स्थानीय खेती के जानकार से पूछें।")


def not_disease_summary(crop: LocalizedText) -> LocalizedText:
    return loc(f"The app does not see a disease on this {crop.en} leaf. No medicine is needed now. "
               "If you still see spots or damage, take another clear photo or ask an expert.",
               f"ऐप को इस {crop.hi} की पत्ती में कोई रोग नहीं दिखा। अभी किसी दवा की ज़रूरत नहीं है। "
               "फिर भी धब्बे या नुकसान दिखें तो दूसरी साफ़ फ़ोटो लें या खेती के जानकार से पूछें।")


def _generic_spoken() -> LocalizedText:
    """The general protective measures, always as whole sentences (the rules' own measures are bullet fragments: screen only)."""
    return loc(" ".join(m.en for m in GENERIC_MEASURES), " ".join(m.hi for m in GENERIC_MEASURES))


def expert_spoken(crop: LocalizedText) -> LocalizedText:
    c, general = crop_phrase(crop), _generic_spoken()
    return loc(f"I am not sure what is wrong with your {c.en}. Please do not spray any medicine now. {general.en} "
               "You can also show the plant to a local agriculture expert.",
               f"मुझे पक्का नहीं पता कि आपकी {c.hi} में क्या दिक्कत है। अभी कोई भी दवा न छिड़कें। {general.hi} "
               "आप पौधा अपने स्थानीय खेती के जानकार को भी दिखा सकते हैं।")


def no_data_spoken(crop: LocalizedText) -> LocalizedText:
    c, general = crop_phrase(crop), _generic_spoken()
    return loc(f"I do not have approved medicine advice for your {c.en} yet. "
               f"Please ask a local agriculture expert before you use any medicine. {general.en}",
               f"आपकी {c.hi} के लिए मेरे पास अभी मंज़ूर दवा की सलाह नहीं है। "
               f"कोई भी दवा इस्तेमाल करने से पहले अपने स्थानीय खेती के जानकार से पूछें। {general.hi}")


def not_disease_spoken(crop: LocalizedText) -> LocalizedText:
    return loc(f"I do not see a disease on this {crop.en} leaf. No medicine is needed now. "
               "If you still see spots, take another clear photo or ask an expert.",
               f"मुझे इस {crop.hi} की पत्ती में कोई रोग नहीं दिखा। अभी किसी दवा की ज़रूरत नहीं है। "
               "फिर भी धब्बे दिखें तो दूसरी साफ़ फ़ोटो लें या खेती के जानकार से पूछें।")


def diagnosis_summary(disease: LocalizedText | None, crop: LocalizedText, severity: str) -> LocalizedText:
    c = crop_phrase(crop)
    sev = SEVERITY_SENTENCE.get(severity, SEVERITY_SENTENCE["green"])
    what_en = disease.en if disease else "a plant problem"
    what_hi = disease.hi if disease else "पौधे की एक समस्या"
    return loc(f"The photo looks like {what_en} on your {c.en}. {sev.en} Medicines from the approved list are given below.",
               f"फ़ोटो में आपकी {c.hi} पर {what_hi} दिख रहा है। {sev.hi} नीचे मंज़ूर सूची की दवाएँ दी गई हैं।")


def diagnosis_spoken(disease_hi_short: str, disease_en: str | None, crop: LocalizedText, severity: str) -> LocalizedText:
    c = crop_phrase(crop)
    clause = SEVERITY_CLAUSE.get(severity, SEVERITY_CLAUSE["green"])
    what_en = disease_en or "a plant problem"
    what_hi = disease_hi_short or "पौधे की एक समस्या"
    return loc(f"This looks like {what_en} on your {c.en}{clause.en}.", f"आपकी {c.hi} में {what_hi} लग रहा है{clause.hi}।")


def advice_headline(disease: LocalizedText | None, crop: LocalizedText) -> LocalizedText:
    if disease:
        return loc(f"{disease.en}: what to do", f"{disease.hi}: क्या करें")
    return loc(f"Advice for your {crop.en}", f"आपकी {crop.hi} के लिए सलाह")


def product_step(ingredient: LocalizedText, brand: str, dose: LocalizedText, waiting: LocalizedText) -> LocalizedText:
    e_brand = f" (for example {brand})" if brand else ""
    h_brand = f" (जैसे {brand})" if brand else ""
    return loc(f"{ingredient.en}{e_brand}: {dose.en}. {waiting.en}", f"{ingredient.hi}{h_brand}: {dose.hi}। {waiting.hi}")


def product_spoken(ingredient: LocalizedText, brand: str, dose: LocalizedText) -> LocalizedText:
    e_brand = f", for example {brand}," if brand else ","
    return loc(f"Use {ingredient.en}{e_brand} {dose.en}.", f"{ingredient.hi} का इस्तेमाल करें, {dose.hi}।")
