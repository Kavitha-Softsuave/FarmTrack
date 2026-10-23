# -*- coding: utf-8 -*-
"""Advisory knowledge base for the RAG engine: reference/advisory_notes.jsonl

A: one note per recommendable product row (generated from the product master, EN + HI template)
B: hand-written rule / policy / safety notes (EN + HI)  - from the HP 2026 schedule text, FRAC guidance, NIPHM, Nauni advisory
C: one note per disease/pest class (EN generated from the catalogue; HI written by hand for the main in-demo classes)

Hindi is a DRAFT and needs native-speaker agronomy review (hi_status field).
"""
import json, pathlib
import pandas as pd
import ref_data as R

ROOT = pathlib.Path(__file__).resolve().parents[1]
prod = pd.read_csv(ROOT / "reference" / "product_master.csv")
dis = pd.read_csv(ROOT / "reference" / "disease_catalogue.csv")
DN = dict(zip(dis.disease_id, dis.name_en))
DH = R.DISEASE_HI
UNIT_HI = {"g/200L": "ग्राम प्रति 200 लीटर पानी", "ml/200L": "मि.ली. प्रति 200 लीटर पानी", "L/200L": "लीटर प्रति 200 लीटर पानी",
           "g/L": "ग्राम प्रति लीटर पानी", "ml/L": "मि.ली. प्रति लीटर पानी", "percent": "% घोल", "percent_drench": "% घोल (जड़ों के पास डालें)"}
HP26 = "HP Horticulture Dept + UHF Nauni, Spray Schedule 2026 (Apple)"
notes = []
def add(topic, crop, disease_id, stage, en, hi, src, conf, tags=""):
    notes.append(dict(note_id=f"N{len(notes) + 1:03d}", topic=topic, crop=crop, disease_id=disease_id or "", stage=stage or "",
                      text_en=en, text_hi=hi or "", hi_status="draft_needs_native_review" if hi else "missing", source_ref=src, confidence=conf, tags=tags))

def num(x):
    return f"{x:g}"
# ----------------------------------------------------------------------------------------------- A: products
for _, p in prod[prod.usable_for_recommendation == True].iterrows():
    targets = [t for t in str(p.targets).split(";") if t]
    tn = ", ".join(DN.get(t, t) for t in targets)
    th = ", ".join(DH.get(t, DN.get(t, t)) for t in targets)
    dose = num(p.dose_min) if p.dose_min == p.dose_max else f"{num(p.dose_min)}-{num(p.dose_max)}"
    brand = f" ({p.brand_example})" if isinstance(p.brand_example, str) and p.brand_example else ""
    form = f" {p.formulation}" if isinstance(p.formulation, str) and p.formulation else ""
    wp_en = f"Waiting period before harvest: {int(p.waiting_period_days)} days." if pd.notna(p.waiting_period_days) else "Waiting period before harvest: not stated in the source - ask an expert if harvest is within 30 days."
    wp_hi = f"कटाई से पहले प्रतीक्षा अवधि: {int(p.waiting_period_days)} दिन।" if pd.notna(p.waiting_period_days) else "कटाई से पहले प्रतीक्षा अवधि स्रोत में नहीं दी गई - कटाई 30 दिन के भीतर हो तो विशेषज्ञ से पूछें।"
    stage = p.stage
    stage_en = R.STAGE_EN.get(stage, stage)
    stage_hi = R.STAGE_HI.get(stage, stage)
    flags_en, flags_hi = "", ""
    if p.ban_status == "proposed_ban_2020_draft_still_registered":
        flags_en = " Warning: marked 'proposed to be banned' (2020 draft) in the HP 2026 schedule, but still registered today."
        flags_hi = " चेतावनी: सारणी 2026 में इसे 'प्रतिबंधित किए जाने का प्रस्ताव' (2020 मसौदा) बताया गया है, पर अभी पंजीकृत है।"
    when_en = f"at {stage_en.lower()} stage" if stage != "any" else "at any stage"
    when_hi = f"{stage_hi} पर" if stage != "any" else "किसी भी अवस्था में"
    uh = UNIT_HI.get(p.dose_unit, p.dose_unit)
    code_txt = p.frac_irac_code if isinstance(p.frac_irac_code, str) and p.frac_irac_code else 'not listed'
    hb = p.hp_evaluated_brands if isinstance(p.hp_evaluated_brands, str) and p.hp_evaluated_brands else ""
    brands_en = f" Brands evaluated in the HP 2026 schedule: {hb}." if hb else ""
    brands_hi = f" एच.पी. सारणी 2026 में मूल्यांकित ब्रांड: {hb}।" if hb else ""
    en = (f"{p.crop}: for {tn}, {when_en}, the source recommends {p.active_ingredient}{form}{brand} at {dose} {p.dose_unit}. "
          f"Group {code_txt} ({p.behaviour if p.behaviour != 'not_applicable' else p.category}). {wp_en}{flags_en}{brands_en}"
          f"{(' Note: ' + p.note) if isinstance(p.note, str) and p.note else ''}")
    hi = (f"{R.CROP_HI.get(p.crop, p.crop)}: {th} के लिए {when_hi} {p.active_ingredient_hi}{brand} {dose} {uh} की सिफारिश है। "
          f"समूह: {code_txt}। {wp_hi}{flags_hi}{brands_hi}")
    add("product_use", p.crop, targets[0] if targets else "", stage, en, hi, f"{p.source_ref}", p.confidence, tags=f"{p.product_id};{p.active_ingredient}")

# ----------------------------------------------------------------------------------------------- B: rules and policy
def rule(en, hi, src, conf, topic="rule", crop="Apple", disease="", stage="", tags=""):
    add(topic, crop, disease, stage, en, hi, src, conf, tags)

rule("If heavy rain falls within 12 hours of a spray, repeat the spray within 7 days (HP 2026, point 2). The schedule does not define 'heavy' in mm; the app uses a configurable default of 10 mm.",
     "यदि छिड़काव के 12 घंटे के भीतर भारी बारिश हो जाए तो 7 दिन के भीतर छिड़काव दोहराएँ (छिड़काव सारणी 2026, बिंदु 2)। सारणी में 'भारी' का मि.मी. नहीं दिया गया; ऐप में डिफ़ॉल्ट 10 मि.मी. रखा गया है।", HP26, "V", tags="rain;respray")
rule("Do not repeat the same chemical in successive sprays (HP 2026, point 3). Alternate between different resistance groups (FRAC codes) to slow resistance.",
     "लगातार छिड़कावों में एक ही रसायन न दोहराएँ (सारणी 2026, बिंदु 3)। प्रतिरोध धीमा करने के लिए अलग-अलग FRAC समूह के रसायन बदल-बदलकर प्रयोग करें।", HP26, "V", tags="rotation")
rule("The schedule is for normal weather. Spray when there are chances of disease (HP 2026, points 1 and 4); in dry spells without infection risk, do not spray just because the calendar says so.",
     "सारणी सामान्य मौसम के लिए है। छिड़काव तभी करें जब रोग लगने की संभावना हो (बिंदु 1 और 4); रोग का ख़तरा न हो तो केवल कैलेंडर देखकर छिड़काव न करें।", HP26, "V", tags="timing")
rule("Dodine: do not mix it with any other pesticide or chemical; do not spray if the temperature is above 30 degrees C and drying is slow; do not mix with hard water (HP 2026, point 5).",
     "डोडीन: इसे किसी अन्य कीटनाशक/रसायन के साथ न मिलाएँ; तापमान 30 °C से अधिक हो और सूखना धीमा हो तो छिड़काव न करें; कठोर पानी में न मिलाएँ (बिंदु 5)।", HP26, "V", disease="Apple___Apple_scab", tags="dodine")
rule("Avoid captan for at least 15 days before and after an oil spray (HP 2026, point 6).",
     "तेल (ऑयल) के छिड़काव से पहले और बाद में कम से कम 15 दिन तक कैप्टान का प्रयोग न करें (बिंदु 6)।", HP26, "V", tags="captan;oil")
rule("Do not mix any other pesticide, chemical, micronutrient, growth regulator or hormone with the recommended pesticides, because this can cause russeting and other disorders. If needed, spray them separately (HP 2026, point 7). Products already co-formulated in one pack are listed as single products in the schedule.",
     "अनुशंसित कीटनाशकों के साथ कोई अन्य कीटनाशक, रसायन, सूक्ष्म पोषक तत्व, वृद्धि नियामक या हार्मोन न मिलाएँ; इससे फल पर रसेटिंग व अन्य विकार हो सकते हैं। ज़रूरत हो तो अलग से छिड़कें (बिंदु 7)।", HP26, "V", tags="mixing;micronutrient")
rule("Collect fallen apple leaves and compost them in a pit, or spray 5% urea on the orchard floor so that infected leaves decompose quickly (HP 2026, point 8).",
     "सेब की गिरी हुई पत्तियाँ इकट्ठा करके खाद गड्ढे में सड़ाएँ, या बाग की ज़मीन पर 5% यूरिया का छिड़काव करें ताकि रोगग्रस्त पत्तियाँ जल्दी सड़ें (बिंदु 8)।", HP26, "V", disease="Apple___Apple_scab", tags="sanitation")
rule("In scab-prone areas, keep a 12-14 day interval between sprays up to the end of the primary scab stage (HP 2026, point 9).",
     "स्कैब-प्रवण क्षेत्रों में प्राथमिक स्कैब की अवस्था तक छिड़कावों के बीच 12-14 दिन का अंतर रखें (बिंदु 9)।", HP26, "V", disease="Apple___Apple_scab", tags="interval")
rule("White root rot: drench the basin 3-4 times with carbendazim 0.1% or aureofungin 0.05% + copper sulphate 0.05% at the onset of the rainy season, to 15-20 cm depth. In winter, expose the roots of infected trees to the sun, remove the infected part and apply Bordeaux paint (HP 2026, point 10). Always route to an agronomist.",
     "सफेद जड़ सड़न: बरसात शुरू होते ही पेड़ के थाले में 3-4 बार कार्बेन्डाज़िम 0.1% या ऑरियोफंगिन 0.05% + कॉपर सल्फेट 0.05% का घोल 15-20 सेमी गहराई तक डालें। सर्दियों में रोगी पेड़ की जड़ें धूप में खुली रखें, रोगी भाग काटकर बोर्डो पेस्ट लगाएँ (बिंदु 10)। विशेषज्ञ से ज़रूर पूछें।", HP26, "V", disease="Apple___Root_rot_collar_rot", tags="drench")
rule("Collar rot: scarify wounds near the collar and apply Bordeaux paint or another copper-based paint in winter. In the rainy season drench the whole tree basin at 30 cm from the trunk with mancozeb 0.3% (HP 2026, point 11). Always route to an agronomist.",
     "कॉलर रॉट: सर्दियों में तने के निचले भाग के घाव खुरचकर बोर्डो पेस्ट या कॉपर आधारित पेंट लगाएँ। बरसात में तने से 30 सेमी दूर पूरे थाले में मैन्कोज़ेब 0.3% का घोल डालें (बिंदु 11)। विशेषज्ञ से ज़रूर पूछें।", HP26, "V", disease="Apple___Root_rot_collar_rot", tags="drench")
rule("When spraying for mites, also spray the tree basin to get good control (HP 2026, point 12). Keep insecticide use minimal in April-June to protect natural enemies.",
     "माइट के लिए छिड़काव करते समय पेड़ के नीचे का थाला भी भिगोएँ (बिंदु 12)। अप्रैल-जून में कीटनाशकों का प्रयोग कम से कम रखें ताकि मित्र कीट बचे रहें।", HP26, "V", disease="PEST_apple_mites", tags="mites")
rule("After harvest, drench the basin against woolly apple aphid and root borer: chlorpyriphos 20 EC at 4 ml per litre (400 ml per 200 L) per the HP 2026 insecticide table. The schedule marks chlorpyriphos with '*' (proposed to be banned); show the warning.",
     "तुड़ाई के बाद वूली एफिड व जड़ छेदक के लिए थाले में क्लोरपायरीफॉस 20 ईसी 4 मि.ली. प्रति लीटर (400 मि.ली. प्रति 200 लीटर) का घोल डालें। सारणी में इसे '*' (प्रतिबंध प्रस्तावित) चिह्नित किया गया है; चेतावनी दिखाएँ।", HP26, "V", disease="PEST_apple_woolly_aphid", stage="post_harvest", tags="post_harvest")
rule("Hail damage (HP 2026): immediately spray carbendazim 100 g or mancozeb 600 g per 200 L; within 3-4 days boric acid 200 g + zinc sulphate 500 g + quicklime 250 g per 200 L; after 10-12 days micronutrients 400-600 g plus urea 1 kg per 200 L.",
     "ओलावृष्टि के बाद (सारणी 2026): तुरंत कार्बेन्डाज़िम 100 ग्राम या मैन्कोज़ेब 600 ग्राम प्रति 200 लीटर; 3-4 दिन में बोरिक एसिड 200 ग्राम + ज़िंक सल्फेट 500 ग्राम + बुझा हुआ चूना 250 ग्राम; 10-12 दिन बाद सूक्ष्म पोषक तत्व 400-600 ग्राम और यूरिया 1 किलो प्रति 200 लीटर।", HP26, "V", tags="hail")
rule("Resistance limits for apple (FRAC pome-fruit guidance): DMI fungicides (group 3) at most 4 sprays per season, alone or in mixture; QoI (group 11) only in mixture and at most 3 sprays per season (4 if the season has 12 or more sprays); SDHI (group 7) at most 2 consecutive applications. After the limit is reached, choose products from other groups.",
     "सेब में प्रतिरोध की सीमा (FRAC मार्गदर्शन): DMI (समूह 3) एक मौसम में अधिकतम 4 छिड़काव (अकेले या मिश्रण में); QoI (समूह 11) केवल मिश्रण में, अधिकतम 3 छिड़काव (12 या अधिक छिड़काव वाले मौसम में 4); SDHI (समूह 7) लगातार अधिकतम 2 बार। सीमा पूरी होने पर दूसरे समूह के उत्पाद चुनें।", "FRAC recommendations for SBI fungicides (frac.info); FRAC QoI WG minutes 2025; FRAC SDHI minutes 2024", "V", tags="rotation;DMI;QoI;SDHI")
rule("Apple scab infection needs a minimum number of leaf-wetness hours that depends on temperature (revised Mills table): e.g. 41 h at 1 C, 21 h at 5 C, 11 h at 10 C, 8 h at 12-13 C, 7 h at 14-15 C, 6 h at 16-24 C, 8 h at 25 C. Join wet periods separated by less than 8 hours. Lesions appear 9-17 days after infection. Primary infection runs from green tip to about 3 weeks after petal fall.",
     "सेब स्कैब का संक्रमण होने के लिए पत्तियों का एक न्यूनतम घंटे तक गीला रहना ज़रूरी है जो तापमान पर निर्भर है (संशोधित मिल्स सारणी): जैसे 1 °C पर 41 घंटे, 5 °C पर 21, 10 °C पर 11, 12-13 °C पर 8, 14-15 °C पर 7, 16-24 °C पर 6 घंटे। 8 घंटे से कम अंतर वाले गीले दौर जोड़ लें। धब्बे संक्रमण के 9-17 दिन बाद दिखते हैं। प्राथमिक संक्रमण हरी नोक से पंखुड़ी झड़ने के लगभग 3 सप्ताह बाद तक रहता है।", "Penn State Extension (MacHardy & Gadoury 1989 revised Mills table)", "V", disease="Apple___Apple_scab", tags="mills;weather")
rule("Marssonina blotch and Alternaria leaf blotch (premature leaf fall) become likely from June when the average temperature is above 20 C and relative humidity stays around 70% or higher for 5-6 days; infection needs at least 6 hours of leaf wetness. This is an indicative rule from ICAR abstracts, not a validated Himachal model. High orchards (above about 2500 m) rarely reach these temperatures.",
     "मार्सोनिना और आल्टरनेरिया पत्ती धब्बा (समय से पहले पत्ते झड़ना) की संभावना जून से तब बढ़ती है जब औसत तापमान 20 °C से ऊपर और नमी 5-6 दिन तक लगभग 70% या अधिक रहे; संक्रमण के लिए कम से कम 6 घंटे पत्ती गीली रहनी चाहिए। यह ICAR सारांशों पर आधारित संकेतात्मक नियम है, हिमाचल के लिए प्रमाणित मॉडल नहीं। ऊँचे बाग (लगभग 2500 मी. से ऊपर) में तापमान प्रायः इतना नहीं पहुँचता।", "ICAR Indian Phytopathology abstracts (Thakur & Sharma 2010 and others)", "V-s", disease="Apple___Marssonina_blotch", tags="marssonina;weather")
rule("Nauni rainy-season advisory (July 2026): use metiram 600 g per 200 L as a protectant against Alternaria and Marssonina; in severe cases Lustre 160 ml, Cabrio Top 200 g, Shamir 500 ml, Luna Experience 126 ml or Avtaar 500 g per 200 L. Spray Cuprofix Disperss 1200 g per 200 L within 24 hours after harvest.",
     "नौणी विश्वविद्यालय की बरसात की सलाह (जुलाई 2026): आल्टरनेरिया व मार्सोनिना के लिए रोकथाम हेतु मेटिराम 600 ग्राम प्रति 200 लीटर; गंभीर स्थिति में लस्टर 160 मि.ली., कैब्रियो टॉप 200 ग्राम, शमीर 500 मि.ली., लूना एक्सपीरियंस 126 मि.ली. या अवतार 500 ग्राम प्रति 200 लीटर। तुड़ाई के 24 घंटे के भीतर क्यूप्रोफिक्स डिस्परस 1200 ग्राम प्रति 200 लीटर छिड़कें।", "Nauni advisory July 2026 (news report: thenewshimachal.com/2026/07/...)", "V-s", disease="Apple___Marssonina_blotch", tags="advisory;monsoon")
rule("Late blight on potato and tomato: if, over the last 7 days, hours between 7.2 and 26.6 C total at least 115 AND hours with relative humidity above 85% total at least 90, late blight is expected within 10 days (NIPHM rule). Start or tighten protectant sprays and look at the crop daily.",
     "आलू-टमाटर का पछेती झुलसा: पिछले 7 दिनों में 7.2 से 26.6 °C के बीच कुल कम से कम 115 घंटे और 85% से अधिक नमी के कम से कम 90 घंटे हों तो 10 दिन के भीतर पछेती झुलसा आने की संभावना है (NIPHM नियम)। रोकथाम के छिड़काव शुरू/तेज़ करें और फसल रोज़ देखें।", "NIPHM AESA Potato package p.17", "V", crop="Potato", disease="Potato___Late_blight", tags="late_blight;weather")
rule("Potato late blight management: protectant mancozeb 0.2% (2 kg per ha in 1000 L) about every 10 days; after symptoms appear, cymoxanil + mancozeb 3 kg per ha in 1000 L, or dimethomorph + mancozeb. Use resistant varieties such as Kufri Jyoti and Kufri Girdhari.",
     "आलू के पछेती झुलसा का प्रबंधन: रोकथाम के लिए मैन्कोज़ेब 0.2% (2 किलो प्रति हेक्टेयर, 1000 लीटर पानी) लगभग हर 10 दिन; लक्षण दिखने पर साइमोक्सानिल + मैन्कोज़ेब 3 किलो प्रति हेक्टेयर (1000 लीटर पानी) या डाइमेथोमॉर्फ + मैन्कोज़ेब। कुफ़री ज्योति, कुफ़री गिरधारी जैसी प्रतिरोधी किस्में लगाएँ।", "CIB&RC Major Uses; CPRI advisory 2024; NIPHM", "V", crop="Potato", disease="Potato___Late_blight", tags="late_blight")
rule("Tomato yellow leaf curl virus has no cure. Do not recommend a fungicide. Control the whitefly vector (imidacloprid 17.8 SL 150-175 ml per ha, waiting period 3 days, or cyantraniliprole 10.26 OD 900 ml per ha), remove infected plants, use a net nursery, 10 yellow sticky traps per acre and maize barrier rows; prefer resistant varieties (Arka Rakshak, Arka Ananya).",
     "टमाटर के पत्ती मरोड़ (येलो लीफ कर्ल) वायरस का कोई इलाज नहीं है। फफूंदनाशक की सलाह न दें। वाहक सफेद मक्खी की रोकथाम करें (इमिडाक्लोप्रिड 17.8 एसएल 150-175 मि.ली. प्रति हेक्टेयर, प्रतीक्षा अवधि 3 दिन, या साइएंट्रानिलिप्रोल 10.26 ओडी 900 मि.ली. प्रति हेक्टेयर), रोगी पौधे उखाड़ें, नेट नर्सरी, प्रति एकड़ 10 पीले चिपचिपे जाल और मक्का की बाड़ पंक्तियाँ लगाएँ; प्रतिरोधी किस्में (अर्का रक्षक, अर्का अनन्या) चुनें।", "NIPHM AESA Tomato; CIB&RC Major Uses", "V", crop="Tomato", disease="Tomato___Tomato_Yellow_Leaf_Curl_Virus", tags="virus;vector")
rule("Tomato mosaic virus has no chemical control. Remove infected plants, keep hands and tools clean, use disease-free seed and rotate crops.",
     "टमाटर के मोज़ेक वायरस का रसायन से नियंत्रण नहीं होता। रोगी पौधे हटाएँ, हाथ और औज़ार साफ़ रखें, रोगमुक्त बीज प्रयोग करें और फसल चक्र अपनाएँ।", "NIPHM AESA Tomato; TNAU Agritech", "V", crop="Tomato", disease="Tomato___Tomato_mosaic_virus", tags="virus")
rule("Rain-fastness (guidance): contact fungicides need roughly 8-24 hours without rain after spraying, systemic ones about 1-2 hours; mancozeb needs at least about 4 hours. Do not respray immediately after rain; shorten the next interval instead. The mm thresholds used by the app are configurable defaults, not label values.",
     "वर्षा-सहनशीलता (मार्गदर्शन): संपर्क फफूंदनाशकों को छिड़काव के बाद लगभग 8-24 घंटे बारिश से बचाव चाहिए, अंतर्प्रवाही को लगभग 1-2 घंटे; मैन्कोज़ेब को कम से कम लगभग 4 घंटे। बारिश के तुरंत बाद दोबारा छिड़काव न करें; अगला अंतराल छोटा करें। ऐप में दिए मि.मी. मान समायोज्य डिफ़ॉल्ट हैं, लेबल के मान नहीं।", "Purdue Vegetable Crops Hotline 2021; NC State Apple Alert 2018", "V", tags="rainfast")
rule("Never recommend a product that has no label claim for the crop. Example: Miravis Duo (pydiflumetofen + difenoconazole) is approved for tomato, chilli, groundnut and grape in India, not apple; fenpropathrin 30% EC has no apple label claim; thiamethoxam 30% FS is a seed treatment, not a foliar spray. If a farmer's history contains such a product, flag it gently and recommend only products from the approved list.",
     "जिस फसल के लिए उत्पाद का लेबल दावा न हो, उसकी सलाह कभी न दें। उदाहरण: मिरावीस ड्यूओ (पाइडिफ्लुमेटोफेन + डिफेनोकोनाज़ोल) भारत में टमाटर, मिर्च, मूँगफली व अंगूर के लिए स्वीकृत है, सेब के लिए नहीं; फेनप्रोपेथ्रिन 30% ईसी का सेब पर लेबल दावा नहीं है; थायामेथोक्साम 30% एफएस बीज उपचार है, पत्तियों पर छिड़काव के लिए नहीं। किसान के इतिहास में ऐसा उत्पाद मिले तो नरमी से चेताएँ और केवल अनुमोदित सूची के उत्पाद सुझाएँ।", "CIB&RC Major Uses (30.09.2026); Syngenta India launch release 5 Aug 2024; HP 2026 schedule", "V", tags="offlabel;policy")
rule("Banned or restricted: dicofol, dinocap and methomyl are banned; malathion is banned on apple, tomato and grape among others; dimethoate is banned on fruits and vegetables eaten raw; monocrotophos 36% SL is discontinued. Never recommend these.",
     "प्रतिबंधित/सीमित: डाइकोफोल, डाइनोकैप और मेथोमिल प्रतिबंधित हैं; मैलाथियान सेब, टमाटर, अंगूर आदि पर प्रतिबंधित है; डाइमेथोएट कच्चे खाए जाने वाले फलों-सब्ज़ियों पर प्रतिबंधित है; मोनोक्रोटोफॉस 36% एसएल बंद है। इनकी सलाह कभी न दें।", "CIB&RC banned/restricted list (31.07.2026); S.O. 4294(E) 2023", "V", tags="banned;policy")
rule("Products marked with an asterisk in the HP 2026 schedule (captan, ziram, zineb, mancozeb, carbendazim, thiophanate-methyl, chlorpyriphos) are among the pesticides 'proposed to be banned' by the Government of India under Gazette Notification No. CG-DL-E-18052020-219423 (18 May 2020 draft; the same note also lists dimethoate, malathion and monocrotophos). They are still registered today. The app may recommend the asterisked ones but shows a warning that rules may change; the admin can disable any of them.",
     "सारणी 2026 में तारांकित (*) उत्पाद (कैप्टान, ज़ीरम, ज़िनेब, मैन्कोज़ेब, कार्बेन्डाज़िम, थायोफैनेट-मिथाइल, क्लोरपायरीफॉस) भारत सरकार की गजट अधिसूचना सं. CG-DL-E-18052020-219423 (18 मई 2020 का मसौदा) के अंतर्गत 'प्रतिबंध प्रस्तावित' कीटनाशकों में हैं (उसी नोट में डाइमेथोएट, मैलाथियान व मोनोक्रोटोफॉस भी हैं)। ये अभी पंजीकृत हैं। ऐप तारांकित उत्पाद सुझा सकता है पर चेतावनी दिखाता है कि नियम बदल सकते हैं; एडमिन इन्हें बंद कर सकता है।", "HP 2026 schedule (note on proposed bans); CIB&RC list", "V", tags="proposed_ban;policy")
rule("Brands: recommend by active ingredient first. The HP 2026 schedule lists the brands it 'recommended and evaluated' for each active ingredient (reference/brand_master.csv, with manufacturer where printed). Show those brands as examples. A brand missing from that table is not necessarily unapproved - it may simply not have been evaluated - so say 'not in the HP evaluated list' instead of 'not approved', and let the farmer check the label.",
     "ब्रांड: पहले सक्रिय तत्व के आधार पर सलाह दें। हि.प्र. सारणी 2026 में हर सक्रिय तत्व के लिए 'अनुशंसित व मूल्यांकित' ब्रांड दिए गए हैं (reference/brand_master.csv, जहाँ छपा है वहाँ निर्माता सहित)। उन्हें उदाहरण के रूप में दिखाएँ। इस सूची में न दिखने वाला ब्रांड अनिवार्य रूप से अस्वीकृत नहीं है - हो सकता है उसका मूल्यांकन ही न हुआ हो - इसलिए 'अस्वीकृत' नहीं, 'एच.पी. मूल्यांकित सूची में नहीं' कहें और किसान से लेबल जाँचने को कहें।", HP26 + " (evaluated-brand table, PDF pp. 8-11)", "V", crop="", tags="brands;policy")
rule("Preventive measures for foliar diseases (HP 2026): the pathogens overwinter on fallen leaves, so remove weeds and bushes and the fallen leaf litter from the orchard floor, and prune trees for good air circulation so foliage dries quickly and secondary lesions do not develop.",
     "पत्तियों के रोगों से बचाव (सारणी 2026): रोगाणु गिरी हुई पत्तियों पर सर्दियाँ काटते हैं, इसलिए बाग से खरपतवार, झाड़ियाँ और गिरी पत्तियाँ हटाएँ और छँटाई करें ताकि हवा का आवागमन रहे, पत्तियाँ जल्दी सूखें और द्वितीयक धब्बे न बनें।", HP26 + " (Preventive measures b)", "V", disease="Apple___Apple_scab", tags="sanitation;pruning")
rule("Preventive measures (HP 2026): powdery mildew - prune off the silvery terminals and destroy them; collar rot / crown gall - avoid injury to the collar region and rogue out and destroy infected plants; canker - remove and destroy infected parts, mummified fruit, dead twigs and pruned branches, and avoid mechanical injuries.",
     "बचाव के उपाय (सारणी 2026): चूर्णिल आसिता - चाँदी जैसे सिरे काटकर नष्ट करें; कॉलर रॉट/क्राउन गॉल - तने के निचले भाग को चोट से बचाएँ और रोगी पौधे उखाड़कर नष्ट करें; कैंकर - रोगग्रस्त भाग, सूखे फल, मरी टहनियाँ व छँटाई की टहनियाँ हटाकर नष्ट करें और यांत्रिक चोट से बचें।", HP26 + " (Preventive measures a, c, d)", "V", disease="Apple___Powdery_mildew", tags="sanitation;prevention")
rule("Tree health (HP 2026): apply balanced fertilisers based on leaf and soil analysis, irrigate properly during hot dry periods to avoid tree stress, protect plants from high and low temperature injury, and control insect pests and diseases effectively.",
     "पेड़ का स्वास्थ्य (सारणी 2026): पत्ती व मिट्टी की जाँच के आधार पर संतुलित खाद दें, गर्म-शुष्क दिनों में उचित सिंचाई करें ताकि पेड़ पर तनाव न पड़े, अधिक/कम तापमान की चोट से पौधों को बचाएँ और कीट-रोगों का प्रभावी नियंत्रण करें।", HP26 + " (Preventive measures e)", "V", tags="nutrition;prevention")
rule("Fruit size (HP 2026): gibberellic acid (GA4+7) 1.8% + benzyladenine 1.8% at 25-30 ppm (277-333 ml per 200 L) can be applied at 80-90% king-flower bloom to improve fruit size (L:D ratio). This is a growth regulator, not a pesticide: spray it separately and never mix it with pesticides.",
     "फल का आकार (सारणी 2026): फल का आकार (L:D अनुपात) सुधारने के लिए 80-90% किंग फ्लावर खिलने पर जिबरेलिक एसिड (GA4+7) 1.8% + बेंज़ाइलएडेनीन 1.8% 25-30 पीपीएम (277-333 मि.ली. प्रति 200 लीटर) छिड़का जा सकता है। यह वृद्धि नियामक है, कीटनाशक नहीं: इसे अलग से छिड़कें, कीटनाशकों के साथ कभी न मिलाएँ।", HP26 + " (Enhancement of fruit size)", "V", tags="pgr;orchard_practice")
rule("Streptomycin + tetracycline sprays are excluded from the app: a ban was proposed in December 2021 and no final order was found. Do not recommend antibiotic sprays.",
     "स्ट्रेप्टोमाइसिन + टेट्रासाइक्लिन के छिड़काव ऐप से बाहर हैं: दिसंबर 2021 में प्रतिबंध प्रस्तावित हुआ था और अंतिम आदेश नहीं मिला। एंटीबायोटिक छिड़काव की सलाह न दें।", "docs/research/agronomy-data.md sec. 4", "V-s", tags="policy;antibiotic")
rule("Safe use (HP 2026): keep children, pets and unfamiliar people away while mixing and spraying; wear long sleeves, long trousers, closed shoes, gloves and goggles; mix outdoors or in a well-ventilated place; mix only what is advised; wash hands before eating; dispose of empty containers properly.",
     "सुरक्षित प्रयोग (सारणी 2026): मिलाते और छिड़कते समय बच्चों, पालतू पशुओं और अनजान लोगों को दूर रखें; पूरी बाँह की कमीज़, लंबी पैंट, बंद जूते, दस्ताने और चश्मा पहनें; खुले में या हवादार जगह पर मिलाएँ; उतना ही मिलाएँ जितना बताया गया है; खाने से पहले हाथ धोएँ; खाली डिब्बे/थैले सही तरीक़े से नष्ट करें।", HP26 + " (Ensure safe use of pesticides)", "V", crop="", tags="safety")
rule("First aid and spills: read the first-aid instructions on the label before use. Note: the HP 2026 sheet prints a Poison Control number (1-800-222-1222) that looks like a US number and should not be shown to Indian farmers; the client must supply the correct Indian poison-helpline number.",
     "प्राथमिक उपचार व रिसाव: उपयोग से पहले लेबल पर दिए प्राथमिक उपचार निर्देश पढ़ें। ध्यान दें: सारणी 2026 में छपा पॉइज़न कंट्रोल नंबर (1-800-222-1222) अमेरिकी नंबर जैसा लगता है और भारतीय किसानों को नहीं दिखाना चाहिए; क्लाइंट सही भारतीय पॉइज़न हेल्पलाइन नंबर दे।", HP26 + " (Ensure safe use of pesticides)", "I", crop="", tags="safety;gap")
rule("Always keep the minimum waiting period between the last spray and harvest so that fruit is free of harmful residues (HP 2026). If a product's waiting period is longer than the days left to harvest, do not recommend it. If the source gives no waiting period, ask an expert when harvest is within 30 days.",
     "अंतिम छिड़काव और तुड़ाई के बीच न्यूनतम प्रतीक्षा अवधि हमेशा रखें ताकि फल में हानिकारक अवशेष न रहें (सारणी 2026)। यदि उत्पाद की प्रतीक्षा अवधि तुड़ाई में बचे दिनों से अधिक हो तो उसकी सलाह न दें। स्रोत में प्रतीक्षा अवधि न हो और तुड़ाई 30 दिन के भीतर हो तो विशेषज्ञ से पूछें।", HP26, "V", crop="", tags="waiting_period")
rule("SKUAST-Kashmir 2026 guidance (second source): keep 3-4 days between an insecticide and a fungicide spray; stop sprays 3-4 weeks before harvest. At green tip and tight cluster, protectant sprays are needed only if a full day of rain is forecast; skip them if 7 dry days are forecast.",
     "शेर-ए-कश्मीर कृषि विश्वविद्यालय (SKUAST-K) 2026 मार्गदर्शन (दूसरा स्रोत): कीटनाशक और फफूंदनाशक के छिड़काव में 3-4 दिन का अंतर रखें; तुड़ाई से 3-4 सप्ताह पहले छिड़काव बंद करें। हरी नोक व टाइट क्लस्टर पर रोकथाम का छिड़काव तभी करें जब पूरे दिन बारिश का पूर्वानुमान हो; 7 दिन सूखे का पूर्वानुमान हो तो न करें।", "SKUAST-K Apple Spray Schedule 2026 (Scribd copy)", "V-s", tags="timing;second_source")
rule("Photo guidance: one leaf filling most of the frame, in daylight and in focus. If the model's confidence is below about 45%, ask for a better photo; below the auto-advice threshold, say 'not sure' and send the case to an agronomist.",
     "फ़ोटो सलाह: एक पत्ती जो फ़्रेम का अधिकांश भाग भरे, दिन की रोशनी में और साफ़ फ़ोकस में। मॉडल का भरोसा लगभग 45% से कम हो तो बेहतर फ़ोटो माँगें; स्वचालित सलाह की सीमा से नीचे 'पक्का नहीं' कहें और मामला कृषि विशेषज्ञ को भेजें।", "ixrbhii apple model card; rules_config.json", "V", crop="", tags="photo;confidence")
rule("Low-prior classes: cedar apple rust is not recorded on apple in India and the server label 'Apple Scab & Rust' mixes scab and rust, so treat both as possible mis-classifications: show the scab advice only with an expert-review flag.",
     "कम संभावना वाले वर्ग: सेब का सीडर रस्ट भारत में दर्ज नहीं है और सर्वर मॉडल का 'Apple Scab & Rust' लेबल स्कैब व रस्ट को मिलाता है, इसलिए दोनों को ग़लत वर्गीकरण की संभावना मानें: स्कैब की सलाह केवल विशेषज्ञ-जाँच चिह्न के साथ दिखाएँ।", "JoTT 2019 HP rust checklist; model card", "I", disease="Apple___Cedar_apple_rust", tags="policy;lowprior")
rule("When a disease has no Indian label recommendation in our sources (e.g. tomato leaf mold and target spot, maize gray leaf spot, grape black rot and esca, strawberry leaf scorch), say so plainly, give only cultural measures, and refer the farmer to an expert. Do not borrow foreign recommendations.",
     "जिस रोग के लिए हमारे स्रोतों में भारतीय लेबल सिफारिश नहीं है (जैसे टमाटर का लीफ मोल्ड व टार्गेट स्पॉट, मक्का का ग्रे लीफ स्पॉट, अंगूर का ब्लैक रॉट व एस्का, स्ट्रॉबेरी का लीफ स्कॉर्च), वहाँ यह साफ़ बताएँ, केवल कृषि-क्रियात्मक उपाय दें और किसान को विशेषज्ञ के पास भेजें। विदेशी सिफारिशें उधार न लें।", "docs/research/agronomy-data.md sec. 7", "V", crop="", tags="policy;expert_referral")
rule("Bacterial spot of tomato: copper oxychloride 50 WP 1000 g per acre in 300-400 L is a protectant only (it prevents spread, it does not cure). Use disease-free seedlings and avoid overhead irrigation. Antibiotic sprays are excluded from this app.",
     "टमाटर का जीवाणु धब्बा: कॉपर ऑक्सीक्लोराइड 50 डब्ल्यूपी 1000 ग्राम प्रति एकड़ (300-400 लीटर पानी) केवल रोकथाम के लिए है (फैलाव रोकता है, इलाज नहीं करता)। रोगमुक्त पौध लगाएँ और ऊपर से सिंचाई से बचें। एंटीबायोटिक छिड़काव इस ऐप में शामिल नहीं हैं।", "NIPHM AESA Tomato", "V", crop="Tomato", disease="Tomato___Bacterial_spot", tags="bacterial")
rule("Every recommendation must cite its source (e.g. 'HP Horticulture Dept / UHF Nauni Spray Schedule 2026'). If retrieval finds no supporting note, answer 'I do not have approved advice for this; please talk to an expert' instead of guessing.",
     "हर सिफारिश के साथ उसका स्रोत बताएँ (जैसे 'हि.प्र. बागवानी विभाग / नौणी छिड़काव सारणी 2026')। यदि कोई समर्थन करने वाला नोट न मिले तो अनुमान न लगाएँ; कहें 'इसके लिए मेरे पास अनुमोदित सलाह नहीं है, कृपया विशेषज्ञ से बात करें।'", "design policy (docs/mvp-plan.md sec. 6)", "V", crop="", tags="policy;grounding")

# ----------------------------------------------------------------------------------------------- C: disease info
HI_DIS = {
 "Apple___Apple_scab": "सेब का स्कैब (वेंचुरिया इनएक्वालिस): पत्तियों पर जैतूनी-भूरे मखमली धब्बे, फल पर खुरदरे फटे धब्बे। प्राथमिक संक्रमण हरी नोक से पंखुड़ी झड़ने के लगभग 3 सप्ताह बाद तक; पत्तियों के गीले रहने के घंटे तापमान पर निर्भर।",
 "Apple___Marssonina_blotch": "मार्सोनिना पत्ती धब्बा: जून के दूसरे सप्ताह से पत्तियों की ऊपरी सतह पर गहरे भूरे धब्बे; पत्ते पीले होकर जुलाई-अगस्त में समय से पहले झड़ते हैं। औसत तापमान 20 °C से ऊपर और नमी लगभग 70% रहने पर ख़तरा बढ़ता है।",
 "Apple___Alternaria_leaf_spot": "आल्टरनेरिया पत्ती धब्बा: बरसात (जून-अगस्त) में छल्लेदार गोल भूरे धब्बे, समय से पहले पत्ते झड़ना; मार्सोनिना जैसा ही गर्म-नम मौसम अनुकूल।",
 "Apple___Powdery_mildew": "चूर्णिल आसिता (पाउडरी मिल्ड्यू): कली फूटने पर टहनियों के सिरों पर सफ़ेद-स्लेटी चूर्ण जैसी परत; ग्रैनी स्मिथ, गोल्डन डिलीशियस और गाला अधिक संवेदनशील।",
 "PEST_apple_mites": "माइट: पत्तियाँ कांस्य रंग की और धब्बेदार; गर्म-शुष्क मौसम में जुलाई में प्रकोप बढ़ता है। छिड़काव में थाला भी भिगोएँ।",
 "Tomato___Early_blight": "टमाटर का अगेती झुलसा: पुरानी पत्तियों पर गोल छल्लेदार भूरे धब्बे; 24-29 °C और नम/बरसाती मौसम में बढ़ता है।",
 "Tomato___Late_blight": "टमाटर का पछेती झुलसा: पत्तियों पर पानी जैसे बड़े धब्बे जो भूरे-काले हो जाते हैं; ठंडा, बादलों वाला, नम मौसम अनुकूल।",
 "Potato___Early_blight": "आलू का अगेती झुलसा: पुरानी पत्तियों पर छल्लेदार भूरे धब्बे; 25-30 °C, बीच-बीच में बारिश वाला गर्म मौसम अनुकूल।",
 "Potato___Late_blight": "आलू का पछेती झुलसा: पानी जैसे धब्बे जो भूरे-काले हो जाते हैं, नीचे सफ़ेद फफूंद; 10-25 °C, 90% से अधिक नमी, बादल/बारिश अनुकूल।",
 "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "टमाटर का पत्ती मरोड़ वायरस: पत्तियाँ ऊपर मुड़कर पीली, पौधा बौना; सफेद मक्खी से फैलता है। कोई इलाज नहीं।",
 "Tomato___Tomato_mosaic_virus": "टमाटर का मोज़ेक वायरस: पत्तियों पर हल्के-गहरे हरे धब्बे और विकृति; रसायन से नियंत्रण नहीं।",
 "Corn_(maize)___Northern_Leaf_Blight": "मक्का का उत्तरी पत्ती झुलसा: लंबे सिगार जैसे धूसर-हरे धब्बे; 18-27 °C और 6 घंटे से अधिक पत्ती गीली रहने पर।",
 "Corn_(maize)___Common_rust_": "मक्का का सामान्य रस्ट: दोनों सतहों पर ईंट जैसे लाल दाने; 15-25 °C और अधिक नमी।",
 "Tomato___Bacterial_spot": "टमाटर का जीवाणु धब्बा: पत्तियों व फलों पर छोटे गहरे जल-भरे धब्बे; गर्म नम मौसम और बारिश की छींटों से फैलता है।",
 "Tomato___Septoria_leaf_spot": "टमाटर का सेप्टोरिया पत्ती धब्बा: छोटे गोल धब्बे जिनका केंद्र धूसर; लगभग 25 °C और अधिक नमी/ओस।",
}
for _, d in dis.iterrows():
    if d.kind == "healthy":
        add("disease_info", d.crop, d.disease_id, "", f"{d['name_en']}: no treatment needed.", "स्वस्थ पत्ती: उपचार की आवश्यकता नहीं।" if d.in_demo_scope else "", "n/a", "V", tags="healthy")
        continue
    parts = [f"{d.name_en} ({d.pathogen_or_pest})." if isinstance(d.pathogen_or_pest, str) and d.pathogen_or_pest else f"{d.name_en}."]
    for label, col in (("Season", "season"), ("Symptoms", "symptoms"), ("Favourable weather", "favourable_weather"), ("Non-chemical measures", "non_chemical"), ("Note", "note")):
        v = d[col]
        if isinstance(v, str) and v.strip(): parts.append(f"{label}: {v}")
    cc = {"yes": "Chemical control is available (see product notes).", "no": "No chemical control for the disease itself.",
          "expert_referral": "No approved recommendation in our sources: refer to an expert."}[d.chemical_control]
    parts.append(cc)
    add("disease_info", d.crop, d.disease_id, "", " ".join(parts), HI_DIS.get(d.disease_id, ""), d.source_ref if isinstance(d.source_ref, str) else "", d.confidence, tags="disease" + (";out_of_demo_scope" if not d.in_demo_scope else ""))

with open(ROOT / "reference" / "advisory_notes.jsonl", "w", encoding="utf-8") as f:
    for n in notes:
        f.write(json.dumps(n, ensure_ascii=False) + "\n")
by = pd.DataFrame(notes)
print("notes:", len(notes)); print(by.topic.value_counts().to_dict()); print("with Hindi:", int((by.text_hi != "").sum()), "| missing Hindi:", int((by.text_hi == "").sum()))
