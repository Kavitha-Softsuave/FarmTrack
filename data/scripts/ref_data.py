# -*- coding: utf-8 -*-
"""Source tables for the FarmTrack MVP reference data.

Every value traces to docs/research/agronomy-data.md (and its cited sources) or docs/research/cv-models.md.
Confidence tags: V = verified in source, V-s = secondary / snippet, I = inferred (flagged in notes).
"""

DEMO_CROPS = ["Apple", "Tomato", "Potato", "Maize", "Grape"]

# ----------------------------------------------------------------------------------------------
# Glossary (Hindi is a DRAFT written by the assistant - needs native-speaker agronomy review)
# ----------------------------------------------------------------------------------------------
CROP_HI = {"Apple": "सेब", "Tomato": "टमाटर", "Potato": "आलू", "Maize": "मक्का", "Grape": "अंगूर"}

STAGES = [  # id, name_en, name_hi
    ("dormant", "Dormant", "सुप्तावस्था"),
    ("silver_tip", "Silver tip", "सिल्वर टिप"),
    ("green_tip", "Green tip", "ग्रीन टिप (कली फूटना)"),
    ("half_inch_green_tip", "Half-inch green tip", "आधा इंच हरी नोक"),
    ("tight_cluster", "Tight cluster", "टाइट क्लस्टर (कलियों का गुच्छा)"),
    ("pink_bud", "Pink bud", "पिंक बड (गुलाबी कली)"),
    ("full_bloom", "Full bloom", "पूर्ण फूल"),
    ("petal_fall", "Petal fall / pea size", "पंखुड़ी झड़ना / मटर के आकार का फल"),
    ("fruit_set", "Fruit set", "फल बनना"),
    ("walnut_size", "Fruit development (walnut size)", "फल विकास (अखरोट के आकार का)"),
    ("walnut_plus_20d", "Fruit development (20 days after walnut size)", "फल विकास (अखरोट आकार के 20 दिन बाद)"),
    ("walnut_plus_40d", "Fruit development (20 days after the walnut+20d mite spray)", "फल विकास (पिछले माइट छिड़काव के 20 दिन बाद)"),
    ("pre_harvest", "Pre-harvest (20-25 days before harvest)", "तुड़ाई से 20-25 दिन पहले"),
    ("harvest", "Harvest", "तुड़ाई"),
    ("post_harvest", "After harvest", "तुड़ाई के बाद"),
    ("any", "Any stage", "किसी भी अवस्था में"),
]
STAGE_HI = {s[0]: s[2] for s in STAGES}
STAGE_EN = {s[0]: s[1] for s in STAGES}

AI_HI = {  # active ingredient -> Hindi (transliterated)
    "Captan": "कैप्टान", "Dodine": "डोडीन", "Ziram": "ज़ीरम", "Mancozeb": "मैन्कोज़ेब",
    "Propineb": "प्रोपीनेब", "Difenoconazole": "डिफेनोकोनाज़ोल", "Hexaconazole": "हेक्साकोनाज़ोल",
    "Zineb": "ज़िनेब", "Carbendazim": "कार्बेन्डाज़िम", "Thiophanate-methyl": "थायोफैनेट-मिथाइल",
    "Myclobutanil": "मायक्लोब्यूटानिल", "Flusilazole": "फ्लुसिलाज़ोल", "Pyraclostrobin": "पायराक्लोस्ट्रोबिन",
    "Tebuconazole": "टेबुकोनाज़ोल", "Trifloxystrobin": "ट्राइफ्लॉक्सीस्ट्रोबिन", "Boscalid": "बोस्कैलिड",
    "Metrafenone": "मेट्राफेनोन", "Chlorothalonil": "क्लोरोथैलोनिल", "Metiram": "मेटिराम",
    "Fluxapyroxad": "फ्लक्सापाइरोक्साड", "Fluopyram": "फ्लुओपाइराम", "Copper sulphate": "कॉपर सल्फेट",
    "Copper oxychloride": "कॉपर ऑक्सीक्लोराइड", "Sulphur": "गंधक (सल्फर)", "Aureofungin": "ऑरियोफंगिन",
    "Horticultural mineral oil": "बागवानी खनिज तेल", "Thiacloprid": "थायाक्लोप्रिड",
    "Spiromesifen": "स्पाइरोमेसिफेन", "Etoxazole": "एटोक्साज़ोल", "Hexythiazox": "हेक्सीथियाज़ॉक्स",
    "Oxydemeton-methyl": "ऑक्सीडेमेटॉन-मिथाइल", "Cyenopyrafen": "साइनोपायरेफेन", "Fenazaquin": "फेनाज़ाक्विन",
    "Propargite": "प्रोपार्गाइट", "Chlorpyriphos": "क्लोरपायरीफॉस", "Azoxystrobin": "एज़ॉक्सीस्ट्रोबिन",
    "Cymoxanil": "साइमोक्सानिल", "Cyazofamid": "साइज़ोफामिड", "Dimethomorph": "डाइमेथोमॉर्फ",
    "Imidacloprid": "इमिडाक्लोप्रिड", "Cyantraniliprole": "साइएंट्रानिलिप्रोल", "Propiconazole": "प्रोपिकोनाज़ोल",
    "Kresoxim-methyl": "क्रेसोक्सिम-मिथाइल", "Hexaconazole + Zineb": "हेक्साकोनाज़ोल + ज़िनेब",
}

DISEASE_HI = {
    "Apple___Apple_scab": "सेब का स्कैब (पपड़ी रोग)",
    "Apple___Apple_scab_rust": "सेब स्कैब/रस्ट (मिश्रित - विशेषज्ञ जाँच)",
    "Apple___Black_rot": "सेब का ब्लैक रॉट",
    "Apple___Cedar_apple_rust": "सेब का सीडर रस्ट (भारत में दुर्लभ)",
    "Apple___healthy": "स्वस्थ सेब की पत्ती",
    "Apple___Marssonina_blotch": "मार्सोनिना पत्ती धब्बा (समय से पहले पत्ते झड़ना)",
    "Apple___Alternaria_leaf_spot": "आल्टरनेरिया पत्ती धब्बा",
    "Apple___Brown_spot": "सेब का भूरा धब्बा",
    "Apple___Gray_spot": "सेब का स्लेटी धब्बा",
    "Apple___Powdery_mildew": "सेब का चूर्णिल आसिता (पाउडरी मिल्ड्यू)",
    "Apple___Root_rot_collar_rot": "जड़ सड़न / कॉलर रॉट",
    "Apple___Canker": "सेब का कैंकर (तने का रोग)",
    "PEST_apple_mites": "सेब में माइट (लाल मकड़ी)",
    "PEST_apple_san_jose_scale": "सेब में सैन जोज़ स्केल",
    "PEST_apple_thrips": "सेब में थ्रिप्स",
    "PEST_apple_woolly_aphid": "सेब का वूली एफिड (सफेद रूई जैसा कीट)",
    "Tomato___Bacterial_spot": "टमाटर का जीवाणु धब्बा",
    "Tomato___Early_blight": "टमाटर का अगेती झुलसा",
    "Tomato___Late_blight": "टमाटर का पछेती झुलसा",
    "Tomato___Leaf_Mold": "टमाटर का लीफ मोल्ड",
    "Tomato___Septoria_leaf_spot": "टमाटर का सेप्टोरिया पत्ती धब्बा",
    "Tomato___Spider_mites Two-spotted_spider_mite": "टमाटर में लाल मकड़ी (माइट)",
    "Tomato___Target_Spot": "टमाटर का टार्गेट स्पॉट",
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "टमाटर का पत्ती मरोड़ (येलो लीफ कर्ल) वायरस",
    "Tomato___Tomato_mosaic_virus": "टमाटर का मोज़ेक वायरस",
    "Tomato___healthy": "स्वस्थ टमाटर की पत्ती",
    "Potato___Early_blight": "आलू का अगेती झुलसा",
    "Potato___Late_blight": "आलू का पछेती झुलसा",
    "Potato___healthy": "स्वस्थ आलू की पत्ती",
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": "मक्का का ग्रे लीफ स्पॉट",
    "Corn_(maize)___Common_rust_": "मक्का का सामान्य रस्ट (गेरुआ)",
    "Corn_(maize)___Northern_Leaf_Blight": "मक्का का उत्तरी पत्ती झुलसा",
    "Corn_(maize)___healthy": "स्वस्थ मक्का की पत्ती",
    "Grape___Black_rot": "अंगूर का ब्लैक रॉट",
    "Grape___Esca_(Black_Measles)": "अंगूर का एस्का (ब्लैक मीज़ल्स)",
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": "अंगूर का पत्ती झुलसा (इज़ारियोप्सिस)",
    "Grape___healthy": "स्वस्थ अंगूर की पत्ती",
}

# ----------------------------------------------------------------------------------------------
# Disease catalogue
# columns: disease_id, kind, crop, name_en, pathogen_or_pest, in_demo_scope, detectable_by,
#          chemical_control, treat_as, requires_expert_review, season, symptoms, favourable_weather,
#          non_chemical, note, source_ref, confidence
# ----------------------------------------------------------------------------------------------
HP26 = "HP Dept of Horticulture + UHF Nauni, Spray Schedule 2026 (Apple), eudyan.hp.gov.in/cms/media/fd3dr2c5/1699-horti-2026-eng.pdf"
NIPHM = "NIPHM AESA IPM packages, niphm.gov.in/IPMPackages"
TNAU = "TNAU Agritech portal, agritech.tnau.ac.in/crop_protection"

D = []  # appended below

def dis(disease_id, kind, crop, name_en, pathogen, scope, detect, chem, treat_as, expert, season, symptoms,
        weather, nonchem, note, src, conf):
    D.append(dict(disease_id=disease_id, kind=kind, crop=crop, name_en=name_en, pathogen_or_pest=pathogen,
                  in_demo_scope=scope, detectable_by=detect, chemical_control=chem, treat_as=treat_as,
                  requires_expert_review=expert, season=season, symptoms=symptoms, favourable_weather=weather,
                  non_chemical=nonchem, note=note, source_ref=src, confidence=conf))

# ---- Apple (deep) ----
dis("Apple___Apple_scab", "disease", "Apple", "Apple scab", "Venturia inaequalis", "true", "ondevice_pv;server_apple", "yes", "", "false",
    "Primary infection green tip to ~3 weeks after petal fall; secondary through summer",
    "Olive-brown velvety spots on leaves; scabby, cracked fruit",
    "Leaf wetness hours needed for infection depend on temperature (revised Mills table, see rules_config.json). Infection is rare above ~26 C.",
    "Compost fallen leaf litter or spray 5% urea on the orchard floor (HP 2026 point 8). Keep 12-14 day interval until the end of primary scab in scab-prone areas.",
    "Do not repeat the same chemical. Dodine: do not tank-mix, do not spray above 30 C.",
    HP26 + "; Penn State Extension apple scab review", "V")
dis("Apple___Apple_scab_rust", "disease", "Apple", "Apple scab & rust (combined model label)", "Venturia inaequalis / rust", "true", "server_apple", "yes", "Apple___Apple_scab", "true",
    "See scab", "Combined class of the server model (ixrbhii apple ConvNeXt); rust is not recorded on apple in India (JoTT 2019 HP rust checklist)",
    "See scab", "See scab", "Treat as scab but ALWAYS route to agronomist review because the rust half of the label is unlikely in Himachal.",
    "ixrbhii/apple-disease-convnext model card; docs/research/agronomy-data.md", "I")
dis("Apple___Black_rot", "disease", "Apple", "Black rot / frogeye leaf spot", "Botryosphaeria / Diplodia", "true", "ondevice_pv", "yes", "", "true",
    "Warm wet weather, mostly late season", "Frogeye leaf spot (purple-bordered brown spots); fruit rot",
    "About 20-27 C with 4.5-13 h wetness (netreefruit.org)", "Sanitation: prune and remove cankered wood and mummified fruit",
    "Present in Kashmir (Bhat et al., Sci Rep 2023); minor in Himachal (inferred). Zineb row in the HP 2026 schedule lists 'scab and black rot'.",
    HP26 + "; Bhat et al. 2023", "V-s")
dis("Apple___Cedar_apple_rust", "disease", "Apple", "Cedar apple rust", "Gymnosporangium juniperi-virginianae", "true", "ondevice_pv", "expert_referral", "", "true",
    "n/a for Himachal", "Bright yellow-orange spots on leaves (North American disease)",
    "10-24 C, 4-6 h wetness (Illinois Extension)", "No measures needed unless an expert confirms the disease",
    "Not recorded on apple in India (JoTT 2019). Treat as a LOW-PRIOR prediction: probably a mis-classification (e.g. of scab or Alternaria). Always ask for a better photo and expert review.",
    "docs/research/agronomy-data.md sec. 7; Illinois Extension", "V")
dis("Apple___healthy", "healthy", "Apple", "Healthy apple leaf", "", "true", "ondevice_pv;server_apple", "no", "", "false", "", "", "", "", "No treatment needed.", "", "V")
dis("Apple___Marssonina_blotch", "disease", "Apple", "Marssonina blotch / premature leaf fall", "Diplocarpon mali (Marssonina coronaria)", "true", "server_apple", "yes", "", "false",
    "From 2nd week of June; defoliation July-August (monsoon)",
    "Dark brown blotches on the upper leaf surface, yellowing and early leaf drop",
    "Mean temperature above 20 C with RH ~70% for 5-6 days (Thakur & Sharma 2010, V-s); infection needs >=6 h wetness, ~20 C optimum; >=40 h wetness for an epidemic. No validated Himachal forecasting model.",
    "Better in open, well-pruned orchards; compost leaf litter",
    "ONLY the server apple model (ixrbhii) has this class; no on-device model does. No dataset validated on Himachal field photos.",
    HP26 + "; Nauni advisory July 2026; ICAR Indian Phytopathology abstracts", "V-s")
dis("Apple___Alternaria_leaf_spot", "disease", "Apple", "Alternaria leaf blotch / leaf spot", "Alternaria spp.", "true", "server_apple", "yes", "", "false",
    "Monsoon (June-August); part of the premature leaf fall complex",
    "Round brown spots with darker rings; premature yellowing and leaf drop",
    "Same humid >20 C trigger as Marssonina (V-s)", "Compost leaf litter; balanced nutrition",
    "On-device model does not have this class.", HP26 + "; Nauni advisory July 2026", "V-s")
dis("Apple___Brown_spot", "disease", "Apple", "Brown spot (dataset label)", "Probably Marssonina complex (inferred)", "true", "server_apple", "yes", "Apple___Marssonina_blotch", "true",
    "See Marssonina", "Brown leaf spots (label from Chinese apple datasets)", "See Marssonina", "See Marssonina",
    "INFERRED: in Chinese datasets 'brown spot' is typically the Marssonina leaf-blotch complex. Treat as Marssonina but send to agronomist.",
    "ixrbhii model card (label); research inference", "I")
dis("Apple___Gray_spot", "disease", "Apple", "Gray spot (dataset label)", "Not identified", "true", "server_apple", "expert_referral", "", "true",
    "Unknown", "Grey leaf spots (label from datasets)", "Unknown", "",
    "No entry in the HP 2026 schedule -> no recommendation; refer to expert.", "ixrbhii model card", "I")
dis("Apple___Powdery_mildew", "disease", "Apple", "Powdery mildew", "Podosphaera leucotricha", "true", "none", "yes", "", "false",
    "Silvery terminals at bud break; spring-early summer", "White-grey powdery coating on shoot tips and young leaves",
    "Not quantified in HP sources. Granny Smith, Golden Delicious and Gala highly susceptible; Delicious types less (Kinnaur survey, V-s).",
    "Prune out infected terminals", "No model in our stack recognises it from a photo; shown for weather/stage advisories and manual selection.", HP26, "V")
dis("Apple___Root_rot_collar_rot", "disease", "Apple", "White root rot / collar rot", "Dematophora / Phytophthora", "true", "server_apple", "yes", "", "true",
    "Rainy season (July-September)", "Yellowing, wilting and early leaf fall; basal bark lesions",
    "Onset of rains; waterlogging", "Bordeaux paint on collar in winter; improve drainage",
    "Not reliably diagnosable from a leaf photo (inferred) -> always expert review. Drench rules from HP 2026 points 10-11.", HP26, "V")
dis("Apple___Canker", "disease", "Apple", "Canker (post-harvest spray target)", "Various", "true", "none", "yes", "", "false",
    "After harvest / leaf fall", "Sunken bark lesions on branches", "Wet autumn", "Prune and burn cankered wood",
    "Not leaf-detectable. Post-harvest copper + mancozeb spray in HP 2026.", HP26, "V")
dis("PEST_apple_mites", "pest", "Apple", "Mites (European red mite, two-spotted mite)", "Panonychus ulmi / Tetranychus urticae", "true", "none", "yes", "", "false",
    "Build-up in July (HP)", "Bronzed, stippled leaves", "Hot, dry weather favours; cool wet weather suppresses (10-18 day generations)",
    "Keep insecticide use minimal in April-June to protect natural enemies; spray the basin too", "Calendar/threshold advisories only; not image-detected.", HP26 + "; Penn State", "V")
dis("PEST_apple_san_jose_scale", "pest", "Apple", "San Jose scale", "Quadraspidiotus perniciosus", "true", "none", "yes", "", "false",
    "Dormant to green tip; pre-harvest", "Grey scale crusts on bark, red halos on fruit", "", "Horticultural mineral oil at half-inch green tip", "", HP26, "V")
dis("PEST_apple_thrips", "pest", "Apple", "Thrips", "Thrips spp.", "true", "none", "yes", "", "false",
    "Pink bud", "Silvery scars on fruit and leaves", "", "", "", HP26, "V")
dis("PEST_apple_woolly_aphid", "pest", "Apple", "Woolly apple aphid", "Eriosoma lanigerum", "true", "none", "yes", "", "false",
    "After harvest (root drench); summer colonies", "White cottony masses on bark and roots", "", "", "", HP26, "V")

# ---- Tomato (light) ----
dis("Tomato___Bacterial_spot", "disease", "Tomato", "Bacterial spot", "Xanthomonas spp.", "true", "ondevice_pv", "yes", "", "false",
    "Warm humid weather with splashing rain", "Small dark water-soaked spots on leaves and fruit", "Moderate temperature, high RH, splashing rain (NIPHM)",
    "Disease-free seed/seedlings; avoid overhead irrigation", "Copper is a protectant only (antibiotic sprays excluded from MVP).", NIPHM, "V")
dis("Tomato___Early_blight", "disease", "Tomato", "Early blight", "Alternaria solani", "true", "ondevice_pv", "yes", "", "false",
    "Warm humid or rainy periods", "Brown concentric-ring spots on older leaves", "24-29 C, humid/rainy (TNAU)", "Crop rotation; remove infected debris", "", NIPHM + "; " + TNAU, "V")
dis("Tomato___Late_blight", "disease", "Tomato", "Late blight", "Phytophthora infestans", "true", "ondevice_pv", "yes", "", "false",
    "Cool, wet, cloudy weather", "Large water-soaked greasy lesions; white mould under leaves in humid weather",
    "NIPHM forecast rule: in 7 days, >=115 h at 7.2-26.6 C AND >=90 h with RH >85% -> blight expected within 10 days",
    "Resistant varieties; remove infected plants", "", NIPHM, "V")
dis("Tomato___Leaf_Mold", "disease", "Tomato", "Leaf mold", "Passalora fulva", "true", "ondevice_pv", "expert_referral", "", "false",
    "Humid, protected cultivation", "Yellow patches on top, olive mould below", ">21 C and RH >85% (UKY, non-Indian)", "Ventilation; avoid leaf wetness",
    "No Indian label claim found -> refer to expert.", "docs/research/agronomy-data.md sec. 7", "I")
dis("Tomato___Septoria_leaf_spot", "disease", "Tomato", "Septoria leaf spot", "Septoria lycopersici", "true", "ondevice_pv", "yes", "", "false",
    "Humid weather, dew", "Many small round spots with grey centres", "~25 C with high humidity or dew (NIPHM)", "Rotate crops; remove debris", "", NIPHM + "; " + TNAU, "V")
dis("Tomato___Spider_mites Two-spotted_spider_mite", "pest", "Tomato", "Two-spotted spider mite", "Tetranychus urticae", "true", "ondevice_pv", "yes", "", "false",
    "Hot, dry spells", "Stippled, bronzed leaves with fine webbing", "Hot and dry", "Avoid dust and water stress", "", NIPHM + "; " + TNAU, "V")
dis("Tomato___Target_Spot", "disease", "Tomato", "Target spot", "Corynespora cassiicola", "true", "ondevice_pv", "expert_referral", "", "false",
    "Warm humid weather", "Brown spots with concentric rings", "28-32 C, 16-44 h leaf wetness (UF/IFAS, non-Indian)", "", "No Indian label claim found -> refer to expert.", "docs/research/agronomy-data.md sec. 7", "I")
dis("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "disease", "Tomato", "Tomato yellow leaf curl virus", "TYLCV (whitefly-borne)", "true", "ondevice_pv", "no", "", "false",
    "Hot, low-rain periods with whitefly build-up", "Upward leaf curling, yellowing, stunting", "Whitefly vector favoured by 28-36 C, RH 62-92%, scanty rain (NIPHM)",
    "No cure. Net nursery, roguing, maize barrier rows, 10 yellow traps per acre, resistant varieties (Arka Rakshak, Arka Ananya)",
    "Chemical control targets only the whitefly vector (see product master, use_note=vector_control).", NIPHM, "V")
dis("Tomato___Tomato_mosaic_virus", "disease", "Tomato", "Tomato mosaic virus", "ToMV", "true", "ondevice_pv", "no", "", "false",
    "Any", "Mottled light/dark green leaves, distortion", "Contact spread", "No chemical control. Roguing, hygiene, disease-free seed, rotation", "", NIPHM + "; " + TNAU, "V")
dis("Tomato___healthy", "healthy", "Tomato", "Healthy tomato leaf", "", "true", "ondevice_pv", "no", "", "false", "", "", "", "", "No treatment needed.", "", "V")

# ---- Potato (light) ----
dis("Potato___Early_blight", "disease", "Potato", "Early blight", "Alternaria solani", "true", "ondevice_pv", "yes", "", "false",
    "Dry warm weather with intermittent rain", "Concentric-ring brown spots on older leaves", "25-30 C, dry warm with intermittent rain (TNAU)", "Balanced fertiliser; rotation", "", TNAU, "V")
dis("Potato___Late_blight", "disease", "Potato", "Late blight", "Phytophthora infestans", "true", "ondevice_pv", "yes", "", "false",
    "Cool, wet, cloudy weather", "Water-soaked lesions turning brown-black; white growth under leaves",
    "10-25 C, RH >90%, cloudy/rain; NIPHM 7-day forecast rule (see rules_config.json)", "Resistant varieties (Kufri Jyoti, Kufri Girdhari)", "", NIPHM + "; CPRI advisory", "V")
dis("Potato___healthy", "healthy", "Potato", "Healthy potato leaf", "", "true", "ondevice_pv", "no", "", "false", "", "", "", "", "No treatment needed.", "", "V")

# ---- Maize (light) ----
dis("Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot", "disease", "Maize", "Gray leaf spot", "Cercospora zeae-maydis", "true", "ondevice_pv", "expert_referral", "", "false",
    "Humid warm weather", "Rectangular grey-tan lesions", "~27-32 C, RH >90% for >=12 h (Crop Protection Network)", "Rotation; residue management",
    "No Indian source found for chemical control -> refer to expert.", "docs/research/agronomy-data.md sec. 7", "I")
dis("Corn_(maize)___Common_rust_", "disease", "Maize", "Common rust", "Puccinia sorghi", "true", "ondevice_pv", "yes", "", "false",
    "Cool humid weather", "Small brick-red pustules on both leaf surfaces", "15-25 C, high humidity (TNAU)", "Resistant hybrids", "", TNAU + "; ICAR-IIMR", "V")
dis("Corn_(maize)___Northern_Leaf_Blight", "disease", "Maize", "Northern leaf blight", "Exserohilum turcicum", "true", "ondevice_pv", "yes", "", "false",
    "Moderate temperature with long leaf wetness", "Long cigar-shaped grey-green lesions", "18-27 C, >6 h leaf wetness (CPN)", "Resistant hybrids; rotation", "", TNAU + "; ICAR-IIMR", "V")
dis("Corn_(maize)___healthy", "healthy", "Maize", "Healthy maize leaf", "", "true", "ondevice_pv", "no", "", "false", "", "", "", "", "No treatment needed.", "", "V")

# ---- Grape (light) ----
dis("Grape___Black_rot", "disease", "Grape", "Black rot", "Guignardia bidwellii", "true", "ondevice_pv", "expert_referral", "", "false",
    "Warm wet weather", "Brown circular leaf spots with black dots; fruit mummies", "Needs ~24 h wetness at 10 C (Wikipedia, secondary)", "Remove mummified fruit",
    "Not a recorded problem in Indian viticulture (NRCG list has no black rot) -> refer to expert.", "docs/research/agronomy-data.md sec. 7", "I")
dis("Grape___Esca_(Black_Measles)", "disease", "Grape", "Esca (black measles)", "Wood-decay fungi complex", "true", "ondevice_pv", "expert_referral", "", "false",
    "Any", "Tiger-striped leaves, berry spotting, vine decline", "", "Protect pruning wounds; remove infected wood (UC IPM)", "No Indian chemical recommendation -> refer to expert.", "UC IPM esca page", "I")
dis("Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", "disease", "Grape", "Leaf blight (Isariopsis leaf spot)", "Pseudocercospora vitis", "true", "ondevice_pv", "yes", "", "true",
    "Humid weather", "Angular dark spots on leaves", "Humid", "Canopy management",
    "Product rows are mapped from the NIPHM anthracnose/leaf-blight row (mapping is inferred) -> expert review.", NIPHM + " (Grapes)", "I")
dis("Grape___healthy", "healthy", "Grape", "Healthy grape leaf", "", "true", "ondevice_pv", "no", "", "false", "", "", "", "", "No treatment needed.", "", "V")

# ---- Other PlantVillage classes: kept because the on-device model outputs them; OUT of demo scope ----
OTHER = [
    ("Blueberry___healthy", "healthy", "Blueberry", "Healthy blueberry leaf"),
    ("Cherry_(including_sour)___Powdery_mildew", "disease", "Cherry", "Cherry powdery mildew"),
    ("Cherry_(including_sour)___healthy", "healthy", "Cherry", "Healthy cherry leaf"),
    ("Orange___Haunglongbing_(Citrus_greening)", "disease", "Orange", "Citrus greening (Huanglongbing)"),
    ("Peach___Bacterial_spot", "disease", "Peach", "Peach bacterial spot"),
    ("Peach___healthy", "healthy", "Peach", "Healthy peach leaf"),
    ("Pepper,_bell___Bacterial_spot", "disease", "Pepper", "Bell pepper bacterial spot"),
    ("Pepper,_bell___healthy", "healthy", "Pepper", "Healthy bell pepper leaf"),
    ("Raspberry___healthy", "healthy", "Raspberry", "Healthy raspberry leaf"),
    ("Soybean___healthy", "healthy", "Soybean", "Healthy soybean leaf"),
    ("Squash___Powdery_mildew", "disease", "Squash", "Squash powdery mildew"),
    ("Strawberry___Leaf_scorch", "disease", "Strawberry", "Strawberry leaf scorch"),
    ("Strawberry___healthy", "healthy", "Strawberry", "Healthy strawberry leaf"),
]
for did, kind, crop, name in OTHER:
    dis(did, kind, crop, name, "", "false", "ondevice_pv", "no" if kind == "healthy" else "expert_referral", "", "false", "", "", "", "",
        "Outside the MVP demo crops. Researched advice exists in docs/research/agronomy-data.md sec. 7 and can be added later; for now the app says 'consult your expert'.",
        "docs/research/agronomy-data.md sec. 7", "V" if kind == "healthy" else "I")

# ----------------------------------------------------------------------------------------------
# Product master. Doses: apple rows are per 200 L water exactly as printed in the HP 2026 schedule.
# columns: crop, active_ingredient, formulation, brand_example, category, code, targets(list), stage,
#          dose_min, dose_max, dose_unit, wp_days, ban_status, use_note, source_ref, confidence, note
# ----------------------------------------------------------------------------------------------
REG = "registered"
PROPOSED = "proposed_ban_2020_draft_still_registered"
SC = "Scab"
SCAB = ["Apple___Apple_scab"]
PM = ["Apple___Powdery_mildew"]
ALT = ["Apple___Alternaria_leaf_spot"]
PLF = ["Apple___Marssonina_blotch", "Apple___Alternaria_leaf_spot"]   # "premature leaf fall" complex

P = []
def prod(crop, ai, form, brand, cat, code, targets, stage, dmin, dmax, unit, wp, ban, use, src, conf, note=""):
    P.append(dict(crop=crop, active_ingredient=ai, formulation=form, brand_example=brand, category=cat, frac_irac_code=code,
                  targets=";".join(targets), stage=stage, dose_min=dmin, dose_max=dmax, dose_unit=unit,
                  waiting_period_days=wp, ban_status=ban, use_note=use, source_ref=src, confidence=conf, note=note))

A = "Apple"
F = "fungicide"
cur = "curative_or_protectant"
# ----- Apple fungicides: HP 2026 schedule (V) -----
prod(A, "Captan", "50 WP", "Captaf", F, "M04", SCAB, "green_tip", 600, 600, "g/200L", None, PROPOSED, cur, HP26, "V", "Brand shown in the client's Zoho rows (partly cut off: '...taf').")
prod(A, "Dodine", "65 WP", "", F, "U12", SCAB, "green_tip", 200, 200, "g/200L", 21, REG, cur, HP26, "V", "Do not tank-mix; do not spray above 30 C; do not use hard water.")
prod(A, "Ziram", "27% SC", "", F, "M03", SCAB, "green_tip", 600, 600, "ml/200L", None, PROPOSED, cur, HP26, "V", "Schedule prints '600 ml/g'.")
prod(A, "Fluxapyroxad + Difenoconazole", "75 g/l + 50 g/l SC", "Sercadis Plus", F, "7+3", SCAB + PM, "green_tip", 60, 60, "ml/200L", 33, REG, cur, HP26, "V")
prod(A, "Mancozeb", "75 WP", "Dithane M-45 / Indofil M-45", F, "M03", SCAB, "pink_bud", 600, 600, "g/200L", None, PROPOSED, cur, HP26, "V", "Brands verified in the HP 2026 evaluated-brand table.")
prod(A, "Propineb", "70 WP", "", F, "M03", SCAB, "pink_bud", 600, 600, "g/200L", 30, REG, cur, HP26, "V")
prod(A, "Difenoconazole", "25 EC", "Score", F, "3", SCAB, "pink_bud", 30, 30, "ml/200L", 14, REG, cur, HP26, "V", "Brand verified in the HP 2026 evaluated-brand table (Syngenta India).")
prod(A, "Hexaconazole + Zineb", "4% + 68% WP", "Avtaar", F, "3+M03", SCAB + PM, "pink_bud", 500, 500, "g/200L", 30, REG, cur, HP26, "V", "Schedule also lists core rot.")
prod(A, "Carbendazim", "50 WP", "Bavistin", F, "1", SCAB, "petal_fall", 100, 100, "g/200L", None, PROPOSED, cur, HP26, "V", "Appears in the client's Zoho history.")
prod(A, "Thiophanate-methyl", "70 WP", "", F, "1", SCAB, "petal_fall", 100, 100, "g/200L", 3, PROPOSED, cur, HP26, "V")
prod(A, "Hexaconazole", "5 EC", "", F, "3", SCAB, "petal_fall", 100, 100, "ml/200L", 30, REG, cur, HP26, "V")
prod(A, "Myclobutanil", "10 WP", "Systhane", F, "3", SCAB, "petal_fall", 80, 80, "g/200L", 21, REG, cur, HP26, "V", "Appears in the client's Zoho history.")
prod(A, "Flusilazole", "40% EC", "", F, "3", SCAB, "petal_fall", 50, 50, "ml/200L", None, REG, cur, HP26, "V")
prod(A, "Mancozeb + Pyraclostrobin", "60% + 5% WG", "Laurel", F, "M03+11", SCAB, "petal_fall", 700, 700, "g/200L", None, PROPOSED, cur, HP26, "V")
prod(A, "Tebuconazole + Trifloxystrobin", "50% + 25% WG", "Nativo", F, "3+11", PM, "petal_fall", 80, 80, "g/200L", None, REG, cur, HP26, "V")
prod(A, "Tebuconazole + Captan", "8% + 32% SC", "Shamir", F, "3+M04", PM, "petal_fall", 500, 500, "ml/200L", 10, PROPOSED, cur, HP26, "V")
prod(A, "Boscalid + Pyraclostrobin", "25.2% + 12.8% WG", "Signum", F, "7+11", PM, "petal_fall", 50, 50, "g/200L", 41, REG, cur, HP26, "V")
prod(A, "Metrafenone", "500 g/l SC", "Acrisio", F, "50", PM, "petal_fall", 20, 20, "ml/200L", 42, REG, cur, HP26, "V")
prod(A, "Chlorothalonil + Difenoconazole", "40% + 4% SC", "Kavach Flo", F, "M05+3", [], "petal_fall", 160, 160, "ml/200L", 24, REG, cur, HP26, "V", "Target cell is BLANK in the schedule at this stage -> not recommended for a specific disease here.")
prod(A, "Carbendazim + Mancozeb", "12% + 63% WP", "SAAF / Companion", F, "1+M03", SCAB + PM, "petal_fall", 500, 500, "g/200L", 20, PROPOSED, cur, HP26, "V", "Appears in the client's Zoho history (SAAF).")
prod(A, "Carbendazim + Flusilazole", "25% + 12.5% SE", "Lustre", F, "1+3", ALT, "petal_fall", 160, 160, "ml/200L", 9, PROPOSED, cur, HP26, "V")
prod(A, "Metiram", "70% WG", "Polyram", F, "M03", ALT + SCAB, "petal_fall", 600, 600, "g/200L", 21, REG, cur, HP26, "V", "Client Zoho shows '...ram (BASF) M3', consistent with Polyram.")
# walnut size
prod(A, "Mancozeb", "75 WP", "Dithane M-45 / Indofil M-45", F, "M03", SCAB, "walnut_size", 600, 600, "g/200L", None, PROPOSED, cur, HP26, "V")
prod(A, "Propineb", "70 WP", "", F, "M03", SCAB, "walnut_size", 600, 600, "g/200L", 30, REG, cur, HP26, "V")
prod(A, "Dodine", "65 WP", "", F, "U12", SCAB, "walnut_size", 150, 150, "g/200L", 21, REG, cur, HP26, "V", "Dodine 65 WP at this stage is 150 g in the schedule (200 g at green tip).")
prod(A, "Metiram + Pyraclostrobin", "55% + 5% WG", "Cabrio Top", F, "M03+11", ALT + ["Apple___Marssonina_blotch"], "walnut_size", 200, 200, "g/200L", 12, REG, cur, HP26 + "; Nauni advisory Jul 2026", "V")
prod(A, "Tebuconazole + Captan", "8% + 32% SC", "Shamir", F, "3+M04", PLF, "walnut_size", 500, 500, "ml/200L", 10, PROPOSED, cur, HP26 + "; Nauni advisory Jul 2026", "V")
prod(A, "Tebuconazole + Captan", "6.7% + 26.9% SC", "Kohicap Plus", F, "3+M04", ALT, "walnut_size", 600, 600, "ml/200L", 10, PROPOSED, cur, HP26, "V")
prod(A, "Fluxapyroxad + Pyraclostrobin", "250 + 250 g/l SC", "Merivon", F, "7+11", PLF, "walnut_size", 50, 50, "ml/200L", 29, REG, cur, HP26, "V")
prod(A, "Fluopyram + Tebuconazole", "17.7% + 17.7% SC", "Luna Experience", F, "7+3", PLF, "walnut_size", 126, 126, "ml/200L", 30, REG, cur, HP26 + "; Nauni advisory Jul 2026", "V")
prod(A, "Dodine", "40% SC", "", F, "U12", PLF, "walnut_size", 150, 150, "ml/200L", 21, REG, cur, HP26, "V")
prod(A, "Hexaconazole + Zineb", "4% + 68% WP", "Avtaar", F, "3+M03", PLF + SCAB, "walnut_size", 500, 500, "g/200L", 30, REG, cur, HP26 + "; Nauni advisory Jul 2026", "V")
prod(A, "Metiram", "70% WG", "Polyram", F, "M03", PLF, "walnut_size", 600, 600, "g/200L", 21, REG, "protectant", "Nauni advisory Jul 2026, thenewshimachal.com/2026/07/...", "V-s", "600 g/200 L protectant for Alternaria and Marssonina (news report of the Nauni advisory).")
# walnut + 20 d
prod(A, "Tebuconazole + Trifloxystrobin", "50% + 25% WG", "Nativo", F, "3+11", PLF, "walnut_plus_20d", 80, 80, "g/200L", None, REG, cur, HP26, "V")
prod(A, "Chlorothalonil + Difenoconazole", "40% + 4% SC", "Kavach Flo", F, "M05+3", PLF, "walnut_plus_20d", 160, 160, "ml/200L", 24, REG, cur, HP26, "V")
prod(A, "Propineb", "70 WP", "", F, "M03", SCAB, "walnut_plus_20d", 600, 600, "g/200L", 30, REG, cur, HP26, "V")
prod(A, "Zineb", "75 WP", "", F, "M03", SCAB + ["Apple___Black_rot"], "walnut_plus_20d", 600, 600, "g/200L", None, PROPOSED, cur, HP26, "V")
prod(A, "Carbendazim + Flusilazole", "25% + 12.5% SE", "Lustre", F, "1+3", PLF, "walnut_plus_20d", 160, 160, "ml/200L", 9, PROPOSED, cur, HP26, "V")
prod(A, "Mancozeb + Pyraclostrobin", "60% + 5% WG", "Laurel", F, "M03+11", PLF + SCAB, "walnut_plus_20d", 700, 700, "g/200L", None, PROPOSED, cur, HP26, "V")
prod(A, "Metiram", "70% WG", "Polyram", F, "M03", PLF + SCAB, "walnut_plus_20d", 600, 600, "g/200L", 21, REG, cur, HP26, "V")
# pre-harvest
prod(A, "Captan", "50 WP", "Captaf", F, "M04", SCAB, "pre_harvest", 600, 600, "g/200L", None, PROPOSED, cur, HP26, "V", "Schedule target: scab, fly speck, bitter rot.")
prod(A, "Ziram", "27% SC", "", F, "M03", SCAB, "pre_harvest", 600, 600, "ml/200L", None, PROPOSED, cur, HP26, "V")
prod(A, "Ziram", "80% WP", "", F, "M03", PLF, "pre_harvest", 500, 500, "g/200L", 21, PROPOSED, cur, HP26, "V", "Schedule target: Alternaria, premature leaf fall, fly speck.")
prod(A, "Metiram + Pyraclostrobin", "55% + 5% WG", "Cabrio Top", F, "M03+11", ALT + ["Apple___Marssonina_blotch"], "pre_harvest", 200, 200, "g/200L", 12, REG, cur, HP26, "V")
prod(A, "Fluopyram + Tebuconazole", "SC", "Luna Experience", F, "7+3", PLF, "pre_harvest", 126, 126, "ml/200L", 30, REG, cur, HP26, "V")
prod(A, "Hexaconazole + Zineb", "4% + 68% WP", "Avtaar", F, "3+M03", PLF + SCAB, "pre_harvest", 500, 500, "g/200L", 30, REG, cur, HP26, "V")
# post-harvest
prod(A, "Copper sulphate + Mancozeb", "47.15% + 30% WG", "Cuprofix Disperss", F, "M01+M03", ["Apple___Canker"], "post_harvest", 1200, 1200, "g/200L", 184, PROPOSED, cur, HP26 + "; Nauni advisory Jul 2026", "V", "Apply within 24 h after harvest (Nauni advisory).")
# root / collar drenches (HP 2026 points 10-11) -- percent solutions
prod(A, "Carbendazim", "drench 0.1%", "Bavistin", F, "1", ["Apple___Root_rot_collar_rot"], "any", 0.1, 0.1, "percent_drench", None, PROPOSED, "drench_3_to_4_times_to_15_20cm_at_onset_of_rains", HP26 + " (point 10)", "V", "White root rot. Always agronomist-reviewed.")
prod(A, "Aureofungin + Copper sulphate", "0.05% + 0.05%", "", F, "", ["Apple___Root_rot_collar_rot"], "any", 0.05, 0.05, "percent_drench", None, REG, "drench_alternative_for_white_root_rot", HP26 + " (point 10)", "V", "Codes not listed in the FRAC list read for this project (blank).")
prod(A, "Mancozeb", "drench 0.3%", "Dithane M-45 / Indofil M-45", F, "M03", ["Apple___Root_rot_collar_rot"], "any", 0.3, 0.3, "percent_drench", None, PROPOSED, "drench_within_30cm_of_trunk_in_rainy_season", HP26 + " (point 11)", "V", "Collar rot.")

# ----- Apple insecticides / acaricides: HP 2026 (V), per 200 L -----
I_ = "insecticide"
K = "acaricide"
MITE = ["PEST_apple_mites"]
prod(A, "Horticultural mineral oil", "", "", "oil", "UNM", ["PEST_apple_san_jose_scale"] + MITE, "half_inch_green_tip", 4, 4, "L/200L", None, REG, "preventive", HP26, "V", "Avoid captan for 15 days before/after an oil spray.")
prod(A, "Thiacloprid", "21.7% (EC in the dose table, SC in the brand table)", "Alanto", I_, "4A", ["PEST_apple_thrips"], "pink_bud", 100, 100, "ml/200L", 30, REG, "preventive", HP26, "V")
prod(A, "Spiromesifen", "22.9 SC", "", K, "23", MITE, "petal_fall", 60, 60, "ml/200L", 30, REG, "preventive", HP26, "V")
prod(A, "Etoxazole", "10 SC", "", K, "10B", MITE, "petal_fall", 80, 80, "ml/200L", 43, REG, "preventive", HP26, "V")
prod(A, "Hexythiazox", "5.45 EC", "", K, "10A", MITE, "petal_fall", 200, 200, "ml/200L", 15, REG, "preventive", HP26, "V")
prod(A, "Oxydemeton-methyl", "25 EC", "", I_, "1B", ["PEST_apple_san_jose_scale"], "petal_fall", 200, 200, "ml/200L", None, REG, "preventive", HP26, "V")
prod(A, "Horticultural mineral oil", "", "", "oil", "UNM", MITE, "walnut_size", 2, 2, "L/200L", None, REG, "preventive", HP26, "V")
prod(A, "Cyenopyrafen", "30 SC", "", K, "25A", MITE, "walnut_size", 50, 50, "ml/200L", 15, REG, "preventive", HP26, "V")
prod(A, "Fenazaquin", "10 EC", "", K, "21A", MITE, "walnut_size", 50, 50, "ml/200L", 30, REG, "preventive", HP26, "V")
prod(A, "Propargite", "57 EC", "", K, "12C", MITE, "walnut_size", 200, 200, "ml/200L", 9, REG, "preventive", HP26, "V")
prod(A, "Hexythiazox", "5.45 EC", "", K, "10A", MITE, "walnut_plus_20d", 200, 200, "ml/200L", 15, REG, "preventive", HP26, "V")
prod(A, "Spiromesifen", "22.9 SC", "", K, "23", MITE, "walnut_plus_20d", 60, 60, "ml/200L", 30, REG, "preventive", HP26, "V")
prod(A, "Propargite + Hexythiazox", "42% + 2% EC", "", K, "12C+10A", MITE, "walnut_plus_20d", 200, 200, "ml/200L", 15, REG, "preventive", HP26, "V")
prod(A, "Fenazaquin", "10 EC", "", K, "21A", MITE, "walnut_plus_40d", 50, 50, "ml/200L", 30, REG, "preventive", HP26, "V", "Third mite spray: 20 days after the walnut+20d spray (schedule row 6).")
prod(A, "Propargite", "57 EC", "", K, "12C", MITE, "walnut_plus_40d", 200, 200, "ml/200L", 9, REG, "preventive", HP26, "V", "Third mite spray (schedule row 6).")
prod(A, "Cyenopyrafen", "30 SC", "", K, "25A", MITE, "walnut_plus_40d", 50, 50, "ml/200L", 15, REG, "preventive", HP26, "V", "Third mite spray (schedule row 6).")
prod(A, "Oxydemeton-methyl", "25 EC", "", I_, "1B", ["PEST_apple_san_jose_scale"], "pre_harvest", 200, 200, "ml/200L", None, REG, "preventive", HP26, "V")
prod(A, "Chlorpyriphos", "20 EC", "", I_, "1B", ["PEST_apple_woolly_aphid"], "post_harvest", 400, 400, "ml/200L", None, PROPOSED, "basin_drench_4_ml_per_litre", HP26, "V", "Marked '*' (proposed to be banned) in the schedule.")

# ----- Tomato (light; CIB&RC / NIPHM / TNAU) -----
T = "Tomato"
prod(T, "Copper oxychloride", "50 WP", "", F, "M01", ["Tomato___Bacterial_spot"], "any", 1000, 1000, "g/acre in 300-400 L", None, REG, "protectant", NIPHM + " (Tomato)", "V", "Dose is verified; applying it to bacterial spot is inferred.")
prod(T, "Mancozeb", "75 WP", "", F, "M03", ["Tomato___Early_blight"], "any", 1.5, 2, "kg/ha in 750 L", None, REG, "protectant", "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(T, "Azoxystrobin", "23 SC", "", F, "11", ["Tomato___Early_blight"], "any", 500, 500, "ml/ha", 3, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(T, "Metiram + Pyraclostrobin", "WG", "", F, "M03+11", ["Tomato___Early_blight"], "any", 1500, 1750, "g/ha", 5, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(T, "Cymoxanil + Mancozeb", "8% + 64% WP", "", F, "27+M03", ["Tomato___Late_blight"], "any", 1500, 1500, "g/ha", None, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(T, "Cyazofamid", "34.5 SC", "", F, "21", ["Tomato___Late_blight"], "any", 200, 200, "ml/ha", 5, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V", "Waiting period listed as 3-5 days; the larger value is stored.")
prod(T, "Fluxapyroxad + Pyraclostrobin", "SC", "", F, "7+11", ["Tomato___Septoria_leaf_spot"], "any", 200, 250, "ml/ha", 10, REG, cur, "CIB&RC Major Uses; " + TNAU, "V")
prod(T, "Azoxystrobin + Boscalid", "WG", "", F, "11+7", ["Tomato___Septoria_leaf_spot"], "any", 500, 500, "g/ha", None, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(T, "Fenazaquin", "10 EC", "", K, "21A", ["Tomato___Spider_mites Two-spotted_spider_mite"], "any", 1250, 1250, "ml/ha", 7, REG, cur, "CIB&RC Major Uses (insecticides, 30.09.2026)", "V")
prod(T, "Spiromesifen", "22.9 SC", "", K, "23", ["Tomato___Spider_mites Two-spotted_spider_mite"], "any", 625, 625, "ml/ha", 3, REG, cur, "CIB&RC Major Uses (insecticides, 30.09.2026)", "V")
prod(T, "Sulphur", "wettable", "", K, "M02", ["Tomato___Spider_mites Two-spotted_spider_mite"], "any", 2, 2, "g/L", None, REG, cur, TNAU, "V")
prod(T, "Imidacloprid", "17.8 SL", "", I_, "4A", ["Tomato___Tomato_Yellow_Leaf_Curl_Virus"], "any", 150, 175, "ml/ha", 3, REG, "vector_control", "CIB&RC Major Uses (insecticides, 30.09.2026)", "V", "Controls the WHITEFLY vector only. No cure for the virus.")
prod(T, "Cyantraniliprole", "10.26 OD", "", I_, "28", ["Tomato___Tomato_Yellow_Leaf_Curl_Virus"], "any", 900, 900, "ml/ha", None, REG, "vector_control", "CIB&RC Major Uses (insecticides, 30.09.2026)", "V", "Controls the WHITEFLY vector only.")

# ----- Potato -----
PO = "Potato"
prod(PO, "Mancozeb", "75 WP", "", F, "M03", ["Potato___Early_blight"], "any", 2, 2, "g/L", None, REG, "protectant_at_45_60_75_days_after_planting", TNAU + " (potato)", "V")
prod(PO, "Chlorothalonil", "75 WP", "", F, "M05", ["Potato___Early_blight"], "any", 0.875, 1.25, "kg/ha", 14, REG, "protectant", "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")
prod(PO, "Mancozeb", "75 WP", "", F, "M03", ["Potato___Late_blight"], "any", 2, 2, "kg/ha in 1000 L", None, REG, "protectant_every_10_days", "CIB&RC Major Uses; CPRI advisory 2024", "V")
prod(PO, "Cymoxanil + Mancozeb", "WP", "", F, "27+M03", ["Potato___Late_blight"], "any", 3, 3, "kg/ha in 1000 L", None, REG, "after_symptoms", "CPRI advisory 2024 (indianpotato.com)", "V-s")
prod(PO, "Dimethomorph + Mancozeb", "50 WP + mancozeb", "", F, "40+M03", ["Potato___Late_blight"], "any", 1, 1, "kg dimethomorph + 2 kg mancozeb per ha", None, REG, cur, "CPRI; CIB&RC Major Uses", "V")
prod(PO, "Cyazofamid", "34.5 SC", "", F, "21", ["Potato___Late_blight"], "any", 200, 200, "ml/ha", 27, REG, cur, "CIB&RC Major Uses (fungicides, 30.09.2026)", "V")

# ----- Maize -----
M = "Maize"
prod(M, "Mancozeb", "75 WP", "", F, "M03", ["Corn_(maize)___Northern_Leaf_Blight"], "any", 2.5, 2.5, "g/L", None, REG, "repeat_after_15_days", "ICAR-IIMR (2022 archive copy)", "V")
prod(M, "Hexaconazole", "5 EC", "", F, "3", ["Corn_(maize)___Northern_Leaf_Blight"], "any", 1, 1, "ml/L", None, REG, cur, "ICAR-IIMR (2022 archive copy)", "V")
prod(M, "Propiconazole", "25 EC", "", F, "3", ["Corn_(maize)___Northern_Leaf_Blight"], "any", 1, 1, "ml/L", None, REG, cur, TNAU + " (maize)", "V")
prod(M, "Azoxystrobin + Difenoconazole", "SC", "", F, "11+3", ["Corn_(maize)___Northern_Leaf_Blight"], "any", 1, 1, "ml/L", None, REG, cur, "ICAR-IIMR (2022 archive copy)", "V")
prod(M, "Mancozeb", "75 WP", "", F, "M03", ["Corn_(maize)___Common_rust_"], "any", 2.5, 4, "g/L", None, REG, "protectant", "ICAR-IIMR (2022 archive copy)", "V")
prod(M, "Kresoxim-methyl", "44.3 SC", "", F, "11", ["Corn_(maize)___Common_rust_"], "any", 1, 1, "ml/L", None, REG, "at_35_and_50_days_after_sowing", TNAU + " (maize)", "V")
prod(M, "Tebuconazole", "EC", "", F, "3", ["Corn_(maize)___Common_rust_"], "any", 1, 1, "ml/L", None, REG, "at_35_and_50_days_after_sowing", TNAU + " (maize)", "V")

# ----- Grape (mapping inferred) -----
G = "Grape"
LB = ["Grape___Leaf_blight_(Isariopsis_Leaf_Spot)"]
prod(G, "Mancozeb", "75 WP", "", F, "M03", LB, "any", 0.6, 0.8, "kg/acre in 300 L", None, REG, "protectant", NIPHM + " (Grapes, anthracnose/leaf-blight row)", "V", "Mapping this row to Isariopsis leaf blight is INFERRED -> expert review.")
prod(G, "Carbendazim", "50 WP", "", F, "1", LB, "any", 120, 120, "g/acre in 240 L", None, PROPOSED, cur, NIPHM + " (Grapes, anthracnose/leaf-blight row)", "V", "Mapping is INFERRED -> expert review.")
prod(G, "Chlorothalonil", "75 WP", "", F, "M05", LB, "any", 0.2, 0.2, "percent", None, REG, "protectant", NIPHM + " (Grapes, anthracnose/leaf-blight row)", "V", "Mapping is INFERRED -> expert review.")

# ----------------------------------------------------------------------------------------------
# Products that appear in the client's real Zoho rows but are NOT approved for apple
# (kept separately: the app must FLAG these, never recommend them)
# ----------------------------------------------------------------------------------------------
OFFLABEL = [
    dict(trade_name="Syngenta Miravis Duo", active_ingredient="Pydiflumetofen + Difenoconazole", frac_irac_code="7+3", formulation="SC",
         approved_crops="Tomato; Chilli; Groundnut; Grape", apple_status="not_approved_for_apple",
         evidence="Syngenta India launch release, 5 Aug 2024: approved for tomato, chilli, groundnut and grape; no pydiflumetofen entry for apple in the CIB&RC fungicide list (30.09.2026); not in HP 2026 apple schedule.",
         source_ref="global-agriculture.com/crop-protection/syngenta-india-launches-new-fungicides-miravis-duo-and-reflect-top-in-india/; CIB&RC MUP", confidence="V"),
    dict(trade_name="Meothrin", active_ingredient="Fenpropathrin", frac_irac_code="3A", formulation="30% EC",
         approved_crops="(no apple row in CIB&RC insecticide list)", apple_status="no_apple_label_claim",
         evidence="No apple row in the CIB&RC insecticide Major Uses list (30.09.2026, text search) and not in the HP 2026 schedule.",
         source_ref="CIB&RC MUP (insecticides, 30.09.2026); HP 2026", confidence="V"),
    dict(trade_name="Trot (Thiamethoxam 30% FS)", active_ingredient="Thiamethoxam", frac_irac_code="4A", formulation="30% FS",
         approved_crops="(seed treatment)", apple_status="seed_treatment_not_foliar_spray",
         evidence="'FS' is a flowable concentrate for SEED treatment, so it is not an apple foliar spray (inferred from the formulation type); no apple row in the CIB&RC list.",
         source_ref="CIB&RC MUP (insecticides, 30.09.2026)", confidence="V/I"),
]

BANNED = [  # active ingredient / scope, status, source
    ("Dicofol", "banned_all_uses", "CIB&RC banned list 31.07.2026; S.O. 4294(E) 2023"),
    ("Dinocap", "banned_all_uses", "CIB&RC banned list 31.07.2026; S.O. 4294(E) 2023"),
    ("Methomyl", "banned_all_uses", "CIB&RC banned list 31.07.2026; S.O. 4294(E) 2023"),
    ("Monocrotophos", "36% SL discontinued", "CIB&RC banned/restricted list"),
    ("Malathion", "banned_on_apple_tomato_grape_mango_and_others", "CIB&RC banned/restricted list"),
    ("Dimethoate", "banned_on_fruits_and_vegetables_eaten_raw", "CIB&RC banned/restricted list; HP 2026 omits it for apple"),
    ("Streptomycin + Tetracycline", "ban_proposed_Dec_2021_final_order_not_found", "excluded from the MVP product master"),
]


# ----------------------------------------------------------------------------------------------
# HP 2026 "Pesticides formulations recommended and evaluated" table (PDF pages 8-11), read from the rendered pages on 19 Oct 2026.
# (group as printed, kind, match_ai, match_form substring of the product-master formulation or "", waiting_period_days or None for '-', [(brand, company or "")])
# ----------------------------------------------------------------------------------------------
BRANDS = [
 ("Carbendazim 50 WP*", "fungicide", "Carbendazim", "50 WP", None, [("Bavistin", ""), ("Benfil", "Indofil Industries Ltd."), ("Carbestin", "BR Agrotech Ltd."), ("Derosal", "Bayer Crop Science Ltd."), ("Dhanustin", "Dhanuka Agritech Ltd."), ("Gilzim", "Gujarat Insecticides Ltd."), ("Goldstin", "Crop Chemicals Ltd."), ("Mavistin", "Pioneer Pesticides Pvt. Ltd.")]),
 ("Captan 50 WP*", "fungicide", "Captan", "50 WP", None, [("Capgold", "Crop Chemicals Ltd."), ("Captaf", "Rallis India Ltd"), ("Captax", "India Pesticides Limited"), ("Dhanutan", "Dhanuka Agritech Ltd"), ("Kohicap", "FIL Industries Pvt. Ltd."), ("Masstan", "Pioneer Pesticides Pvt. Ltd")]),
 ("Dodine 65 WP", "fungicide", "Dodine", "65 WP", 21, [("Himdin", ""), ("Noor", "Indofil Industries Ltd."), ("Superstar", "FIL Industries Pvt. Ltd."), ("Syllit", "UPL Sustainable Agro Solution"), ("Tohfa", "Krishi Rasayan Pvt. Ltd.")]),
 ("Dodine 40% SC", "fungicide", "Dodine", "40% SC", 21, [("Dodin O FIL", "FIL Industries Pvt. Ltd")]),
 ("Difenoconazole 25 EC", "fungicide", "Difenoconazole", "25 EC", 14, [("Dizole", "Crop Chemicals Ltd"), ("Karara", "Krishi Rasayan Pvt. Ltd."), ("Rubigan D", "FIL Industries Pvt. Ltd"), ("Scale", ""), ("Score", "Syngenta India Ltd.")]),
 ("Flusilazole 40% EC", "fungicide", "Flusilazole", "40% EC", None, [("Cursor 40% EC", "Dhanuka Agritech Limited."), ("Governor 40% EC", "FIL Industries Pvt. Ltd")]),
 ("Hexaconazole 5 EC", "fungicide", "Hexaconazole", "5 EC", 30, [("Contaf", "Rallis India Ltd."), ("Envil", "FIL Industries Pvt. Ltd."), ("Glow", "Pioneer Pesticides Pvt. Ltd"), ("Hexcon", "Crop Chemicals Ltd"), ("Hexzol", "Sumitomo Chemical India Ltd."), ("Krizole", "Krishi Rasayan Group"), ("Sitara", "Indofil Industries Limited."), ("Titan", "Sudarshan Farm Chemicals India Pvt. Ltd.")]),
 ("Mancozeb 75 WP*", "fungicide", "Mancozeb", "75 WP", None, [("Abic M-45", "Syngenta India Ltd."), ("Dithane M-45", ""), ("Dhanuka M-45", "Dhanuka Agritech Ltd"), ("Emthane M-45", ""), ("Gold M-45", "Crop Chemicals Ltd."), ("Hindustan M-45", "HPM Chemicals & Fertilizers Ltd."), ("Indofil M-45", "Indofil Industries Ltd."), ("Kohinoor M-45", "FIL Industries Pvt. Ltd."), ("Marlett M-45", "Coromandel International Ltd"), ("Mass M-45", "Pioneer Pesticides Pvt. Ltd"), ("Uthane M-45", "UPL Sustainable Agro Solution")]),
 ("Metiram 70% WG", "fungicide", "Metiram", "70% WG", 21, [("Polyram", "BASF India Ltd.")]),
 ("Metrafenone 500 g/l SC", "fungicide", "Metrafenone", "", 42, [("Acrisio 50 SC", "BASF India Ltd.")]),
 ("Myclobutanil 10 WP", "fungicide", "Myclobutanil", "", 21, [("Boon", "Indofil Industries Ltd"), ("Grapple", "FIL Industries Pvt. Ltd"), ("Index", "Nagarjuna NACL Industries Limited"), ("Systhane", "Corteva Agriscience")]),
 ("Propineb 70 WP", "fungicide", "Propineb", "", 30, [("Aaroosh", "Coromandel International Ltd"), ("Antracol", "Bayer Crop Science Ltd."), ("Scale 70% WP", "Krishi Rasayan Exports Pvt. Ltd.")]),
 ("Thiophanate methyl 70 WP*", "fungicide", "Thiophanate-methyl", "", 3, [("Alert", ""), ("Key", "Krishi Rasayan Ltd"), ("Roko", "Biostadt India Ltd."), ("Topsin-M", "Moti Pesticides"), ("Trust", "Crop Chemicals Ltd"), ("Stop", "Pioneer Pesticides Pvt. Ltd")]),
 ("Zineb 75 WP*", "fungicide", "Zineb", "", None, [("FIL Kanji", "FIL Industries Pvt. Ltd"), ("Indofil Z-78", "Indofil Industries Ltd")]),
 ("Ziram 27% SC*", "fungicide", "Ziram", "27%", None, [("Cuman L", "Syngenta India Ltd")]),
 ("Ziram 80% WP*", "fungicide", "Ziram", "80%", 21, [("IPL Ziram-80", "India Pesticides Ltd"), ("ZED-78", "FIL Industries Pvt. Ltd.")]),
 ("Boscalid 25.2% + Pyraclostrobin 12.8% w/w WG", "fungicide", "Boscalid + Pyraclostrobin", "", 41, [("Signum 38% WG", "BASF India Ltd.")]),
 ("Carbendazim 25% + Flusilazole 12.5% SE", "fungicide", "Carbendazim + Flusilazole", "", 9, [("Lustre 37.5% SE", "Dhanuka Agritech Ltd")]),
 ("Carbendazim 12% + Mancozeb 63% WP", "fungicide", "Carbendazim + Mancozeb", "", 20, [("Companion", "Indofil Industries Ltd"), ("SAAF", "UPL Sustainable Agro Solution")]),
 ("Chlorothalonil 40% + Difenoconazole 4% (44 SC)", "fungicide", "Chlorothalonil + Difenoconazole", "", 24, [("Kavach Flo", "Syngenta India Private Limited")]),
 ("Copper Sulphate 47.15% + Mancozeb 30% WG", "fungicide", "Copper sulphate + Mancozeb", "", 184, [("Cuprofix Disperss", "UPL Sustainable Agri Solutions Limited")]),
 ("Fluopyram 17.7% w/w + Tebuconazole 17.7% w/w SC", "fungicide", "Fluopyram + Tebuconazole", "", 30, [("Luna Experience", "Bayer Crop Science Ltd")]),
 ("Fluxapyroxad 75 g/l + Difenoconazole 50 g/l SC", "fungicide", "Fluxapyroxad + Difenoconazole", "", 33, [("Sercadis Plus 12.5 SC", "BASF India Ltd.")]),
 ("Fluxapyroxad 250 g/l + Pyraclostrobin 250 g/l 500 SC", "fungicide", "Fluxapyroxad + Pyraclostrobin", "", 29, [("Merivon 50 SC", "BASF India Ltd.")]),
 ("Hexaconazole 4% + Zineb 68% WP", "fungicide", "Hexaconazole + Zineb", "", 30, [("Avtaar", "Indofil Industries Ltd")]),
 ("Mancozeb 60% + Pyraclostrobin 5% w/w WG", "fungicide", "Mancozeb + Pyraclostrobin", "", None, [("Laurel", "UPL Limited")]),
 ("Metiram 55% + Pyraclostrobin 5% WG", "fungicide", "Metiram + Pyraclostrobin", "", 12, [("Cabrio Top 60 WG", "BASF India Ltd.")]),
 ("Tebuconazole 8% + Captan 32% SC or Tebuconazole 6.7% + Captan 26.9% SC", "fungicide", "Tebuconazole + Captan", "", 10, [("Shamir", "Adama India Pvt. Ltd"), ("Kohicap Plus", "FIL Industries Pvt. Ltd.")]),
 ("Tebuconazole 50% + Trifloxystrobin 25% WG", "fungicide", "Tebuconazole + Trifloxystrobin", "", None, [("Nativo 75 WG", "Bayer Crop Science Ltd")]),
 ("Chlorpyriphos 20 EC*", "insecticide", "Chlorpyriphos", "", None, [("Danusban", "Dhanuka Agritech Ltd"), ("Durmet", "FMC India Ltd."), ("Dursban", "Dow Agroscience India Pvt. Ltd"), ("Force", "Nagarjuna Pesticides"), ("Goldban", "Crop Chemicals Ltd"), ("Massban", "Pioneer Pesticides Pvt. Ltd."), ("Navigator", "Gharda Chemicals Pvt. Ltd."), ("Tricel", "Sumitomo Chemical India Ltd.")]),
 ("Cyenopyrafen 30% SC", "acaricide", "Cyenopyrafen", "", 15, [("Kunoichi", "Insecticides India Ltd.")]),
 ("Etoxazole 10% SC", "acaricide", "Etoxazole", "", 43, [("Borneo", "Sumitomo Chemical India Ltd.")]),
 ("Fenazaquin 10 EC", "acaricide", "Fenazaquin", "", 30, [("Magister", ""), ("Majestic", "FIL Industries Pvt. Ltd")]),
 ("Hexythiazox 5.45% EC", "acaricide", "Hexythiazox", "5.45", 15, [("Endurer", "Coromandel International Ltd"), ("Maiden", "Biostadt India Ltd")]),
 ("Horticultural Mineral Oil", "oil", "Horticultural mineral oil", "", None, [("HP Spray Oil E", "Hindustan Petroleum Corporation Ltd. (HPCL)"), ("Servo Oil", "Indian Oil Corporation Ltd")]),
 ("Oxy-demeton Methyl 25% EC", "insecticide", "Oxydemeton-methyl", "", None, [("Metasystox", "UPL Sustainable Agro Solution")]),
 ("Propargite 57 EC", "acaricide", "Propargite", "57", 9, [("Omite", "Dhanuka Agritech Ltd"), ("Simba", "PI Industries Pvt. Ltd.")]),
 ("Propargite 42% + Hexythiazox 2% EC", "acaricide", "Propargite + Hexythiazox", "", 15, [("Ceasemite", "Indofil Industries Ltd")]),
 ("Spiromesifen 22.9% SC", "acaricide", "Spiromesifen", "", 30, [("Oberon", "Bayer Crop Science Ltd")]),
 ("Thiacloprid 21.7% SC", "insecticide", "Thiacloprid", "", 30, [("Alanto", "Bayer Crop Science Ltd")]),
]
