"""Farmer-facing text written by the platform layer (everything else comes from rules, advice, voice prompts or the KB).

Plain spoken Hindi, short sentences, no digits (numbers are words), no first-person verbs. ALL HINDI HERE IS A DRAFT for native review.
Fixed prompts live in voice/prompts.json; these are the sentences that are specific to an API response.
"""
from __future__ import annotations

from app.domain.types import LocalizedText

L = LocalizedText

HISTORY_UNAVAILABLE = L(
    en="We could not read your spray record. Please check what you sprayed recently before you spray again.",
    hi="आपके छिड़काव का रिकॉर्ड नहीं मिल सका। दोबारा छिड़काव से पहले देख लीजिए कि हाल में क्या छिड़का था।")

# --- advice written by the platform only when the composer itself fails (never the normal path)
SAFE_ADVICE_HEADLINE = L(en="Advice for your plant", hi="आपके पौधे के लिए सलाह")
SAFE_ADVICE_SUMMARY = L(
    en="Please read the medicine and the amount on this card carefully. If you are not sure, ask a farm expert.",
    hi="इस कार्ड में दवा और उसकी मात्रा ध्यान से पढ़िए। पक्का न हो तो खेती के जानकार से पूछिए।")
SAFE_ADVICE_SAFETY = L(
    en="Wear gloves and a mask when you spray. Keep children and animals away.",
    hi="छिड़काव करते समय दस्ताने और मास्क पहनिए। बच्चों और जानवरों को दूर रखिए।")
SAFE_EXPERT_HEADLINE = L(en="Not sure yet: do not spray any medicine now", hi="अभी पक्का नहीं है: अभी कोई दवा मत छिड़किए")
SAFE_EXPERT_SUMMARY = L(
    en="Do not spray any medicine until you know what is wrong with the plant. Take another clear photo, or show it to a local agriculture expert.",
    hi="जब तक पक्का न पता चले कि पौधे को क्या हुआ है, कोई दवा मत छिड़किए। दूसरी साफ़ फ़ोटो लीजिए, या पौधा स्थानीय खेती के जानकार को दिखाइए।")

# --- spray diary
DIARY_WARNING_LEAD_FALLBACK = L(en="Please listen carefully.", hi="ध्यान से सुनिए।")
DIARY_SAVED_FALLBACK = L(en="Done. It is saved in your diary.", hi="हो गया। आपकी डायरी में लिख लिया गया है।")
PRODUCT_NOT_RECOGNISED = L(
    en="This medicine is not in our list, so we could not check it. Please ask a farm expert before you spray it again.",
    hi="यह दवा हमारी सूची में नहीं मिली, इसलिए इसकी जाँच नहीं हो सकी। दोबारा छिड़कने से पहले खेती के जानकार से पूछ लीजिए।")

# --- field page
FIELD_NO_DATA_FALLBACK = L(en="There is no information for your field yet.", hi="आपके खेत की जानकारी अभी नहीं है।")
FIELD_STALE_FALLBACK = L(en="This information is old. Turn on the internet to see new information.",
                         hi="यह जानकारी पुरानी है। नई जानकारी के लिए इंटरनेट चालू कीजिए।")
FIELD_TEMPERATURE = {
    "cold": L(en="It is cold in your field now.", hi="आपके खेत में अभी ठंड है।"),
    "cool": L(en="It is cool in your field now.", hi="आपके खेत में अभी मौसम ठंडा है।"),
    "mild": L(en="The weather in your field is pleasant now.", hi="आपके खेत में अभी मौसम अच्छा है।"),
    "warm": L(en="It is warm in your field now.", hi="आपके खेत में अभी गर्मी है।"),
    "hot": L(en="It is very hot in your field now.", hi="आपके खेत में अभी बहुत गर्मी है।"),
}
FIELD_RAIN = {
    "none": L(en="No rain is expected in the next two days.", hi="अगले दो दिन बारिश की उम्मीद नहीं है।"),
    "light": L(en="Some light rain is expected in the next two days.", hi="अगले दो दिन में हल्की बारिश हो सकती है।"),
    "heavy": L(en="Heavy rain is expected in the next two days.", hi="अगले दो दिन में तेज़ बारिश हो सकती है।"),
}
FIELD_NO_RISK = L(en="There is no weather danger for your crops now.", hi="अभी आपकी फसल को मौसम से कोई खतरा नहीं है।")
FIELD_RISK_LEAD = L(en="Please note.", hi="ध्यान दीजिए।")

# --- scan result
CROP_CONFIRM_FALLBACK = L(en="Is this the right crop?", hi="क्या यह सही फसल है?")
CROP_IS_FALLBACK = L(en="This looks like {crop}.", hi="यह {crop} की फसल लगती है।")
CROP_UNKNOWN_FALLBACK = L(en="I could not tell the crop.", hi="फसल पहचान में नहीं आई।")
RESULT_EXPERT_FALLBACK = L(en="A farm expert needs to see this. Your photos are being sent to the expert.",
                           hi="इसे खेती के जानकार को दिखाना ज़रूरी है। आपकी फोटो उनके पास भेजी जा रही हैं।")
RETAKE_FALLBACK = L(en="The photo is not clear. Please take it again.", hi="फोटो साफ़ नहीं आई। कृपया दोबारा खींचिए।")
