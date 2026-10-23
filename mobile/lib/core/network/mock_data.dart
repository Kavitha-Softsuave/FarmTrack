import '../models/models.dart';

/// Canned, realistic API answers for the mock backend (Hindi is a draft, like the real prompts).
///
/// Doses and waiting periods follow the HP 2026 apple schedule rows of `data/reference/product_master.csv`
/// (P007 difenoconazole), written so a voice can read them aloud.
class MockData {
  const MockData._();

  static final DateTime now = DateTime.utc(2026, 5, 12, 2, 30);

  /// Every crop id the voice catalogue can name (`crop_is_<id>`).
  static const List<String> supportedCrops = [
    'apple',
    'tomato',
    'potato',
    'maize',
    'grape',
    'pear',
    'plum',
    'peach',
    'apricot',
    'cherry',
    'walnut',
    'pomegranate',
    'kiwi',
    'strawberry',
    'pea',
    'cauliflower',
    'cabbage',
    'capsicum',
    'beans',
    'wheat',
    'paddy',
    'barley',
    'ginger',
    'cucumber',
    'mango',
    'citrus',
    'litchi',
  ];

  /// Crops for which the mock has approved advice data (the rest answer `no_approved_data`).
  static const Set<String> cropsWithData = {'apple', 'tomato', 'potato', 'maize', 'grape'};

  static const Map<String, List<String>> _names = {
    'apple': ['Apple', 'सेब'],
    'pear': ['Pear', 'नाशपाती'],
    'plum': ['Plum', 'आलूबुखारा'],
    'tomato': ['Tomato', 'टमाटर'],
    'potato': ['Potato', 'आलू'],
    'maize': ['Maize', 'मक्का'],
    'grape': ['Grapes', 'अंगूर'],
    'cauliflower': ['Cauliflower', 'फूलगोभी'],
  };

  static LocalizedText cropName(String id) {
    final n = _names[id];
    if (n != null) return LocalizedText.pair(en: n[0], hi: n[1]);
    final en = id.isEmpty ? id : '${id[0].toUpperCase()}${id.substring(1)}';
    return LocalizedText.pair(en: en, hi: en);
  }

  static FarmerOut farmer({String language = 'hi'}) => FarmerOut(
    id: 'F001',
    name: 'Ramesh Kumar',
    phoneMasked: '+91 ••••• •0001',
    language: language,
    district: 'Shimla',
    village: 'Kotgarh',
    crops: const ['apple', 'potato'],
    primaryCrop: 'apple',
    stationId: 'ST08',
  );

  static TokenOut tokens(int serial, {String language = 'hi'}) => TokenOut(
    accessToken: 'mock-access-$serial',
    refreshToken: 'mock-refresh-$serial',
    expiresIn: 900,
    farmer: farmer(language: language),
  );

  static MetaOut meta() => const MetaOut(
    appVersion: '0.1.0',
    env: 'mock',
    supportedLanguages: ['hi', 'en'],
    supportedCrops: supportedCrops,
    providers: {'llm': 'mock', 'vision': 'mock', 'tts': 'mock'},
  );

  // ------------------------------------------------------------------ scans

  static CropOut crop(String id, {double confidence = 0.93, bool confirm = false, String source = 'server'}) => CropOut(
    cropId: id,
    name: cropName(id),
    confidence: confidence,
    needsConfirmation: confirm,
    source: source,
    candidates: confirm
        ? [
            CropCandidateOut(cropId: id, name: cropName(id), confidence: confidence),
            CropCandidateOut(cropId: 'pear', name: cropName('pear'), confidence: 0.25),
            CropCandidateOut(cropId: 'plum', name: cropName('plum'), confidence: 0.12),
          ]
        : const [],
  );

  static ScanOut confirmCropScan(String id) => ScanOut(
    id: id,
    status: ScanStatus.confirmCrop,
    createdAt: now,
    photos: 1,
    crop: crop('apple', confidence: 0.55, confirm: true),
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'This looks like apple. Is this the right crop?',
        hi: 'यह सेब की फसल लगती है। क्या यह सही फसल है?',
      ),
    ),
    nextSteps: const [NextStep(action: NextAction.confirmCrop, promptId: 'crop_confirm_prompt')],
  );

  static ScanOut photoUnusableScan(String id, {String issue = 'blurry'}) {
    final tip = switch (issue) {
      'too_dark' || 'too_bright' => 'scan_retake_dark',
      'too_small' => 'scan_retake_far',
      'no_leaf' => 'scan_retake_no_leaf',
      _ => 'scan_retake_blurry',
    };
    return ScanOut(
      id: id,
      status: ScanStatus.photoUnusable,
      createdAt: now,
      photos: 1,
      quality: QualityOut(usable: false, issues: [issue], tipPromptId: tip),
      spoken: SpokenOut(
        text: LocalizedText.pair(
          en: 'The photo is not clear. Hold the phone still and take it again.',
          hi: 'फोटो साफ़ नहीं है। फोन को स्थिर रखकर फिर से फोटो खींचिए।',
        ),
      ),
      nextSteps: const [NextStep(action: NextAction.retake, promptId: 'scan_retake_tap')],
    );
  }

  static AdviceOut scabAdvice(String scanId) => AdviceOut(
    id: 'adv-$scanId',
    scanId: scanId,
    cropId: 'apple',
    diseaseId: 'Apple___Apple_scab',
    severity: Severity.yellow,
    headline: LocalizedText.pair(en: 'Apple scab', hi: 'सेब का स्कैब (पपड़ी रोग)'),
    summary: LocalizedText.pair(
      en: 'There are brown, velvety spots on the leaves. Spray soon, before the next rain.',
      hi: 'पत्तियों पर भूरे, मखमली धब्बे हैं। अगली बारिश से पहले जल्दी छिड़काव कीजिए।',
    ),
    products: [
      ProductOut(
        productId: 'P007',
        activeIngredient: LocalizedText.pair(en: 'Difenoconazole', hi: 'डिफेनोकोनाज़ोल'),
        brandExamples: const ['Score'],
        formulation: '25 EC',
        category: 'fungicide',
        fracIracCode: '3',
        doseText: LocalizedText.pair(
          en: 'Thirty millilitres in two hundred litres of water.',
          hi: 'दो सौ लीटर पानी में तीस मिलीलीटर।',
        ),
        doseMin: 30,
        doseMax: 30,
        doseUnit: 'ml/200L',
        waitingPeriodDays: 14,
      ),
    ],
    timing: TimingOut(
      action: TimingAction.sprayNow,
      text: LocalizedText.pair(
        en: 'Spray today. No rain is expected in the next twelve hours.',
        hi: 'आज छिड़काव कीजिए। अगले बारह घंटे बारिश की उम्मीद नहीं है।',
      ),
      rainNext12hMm: 0,
    ),
    steps: [
      LocalizedText.pair(
        en: 'Mix the medicine in clean water as shown.',
        hi: 'दवा को साफ़ पानी में बताई गई मात्रा में घोलिए।',
      ),
      LocalizedText.pair(
        en: 'Spray the whole tree, on the top and the bottom of the leaves.',
        hi: 'पूरे पेड़ पर, पत्तियों के ऊपर और नीचे दोनों तरफ छिड़काव कीजिए।',
      ),
    ],
    safety: [
      LocalizedText.pair(
        en: 'Wear a mask and gloves. Keep children and animals away.',
        hi: 'मुँह पर कपड़ा और हाथों में दस्ताने पहनिए। बच्चों और जानवरों को दूर रखिए।',
      ),
    ],
    warnings: [
      WarningOut(
        code: 'no_mixing',
        level: Severity.yellow,
        text: LocalizedText.pair(
          en: 'Do not mix any other chemical, nutrient or hormone with this spray.',
          hi: 'इस दवा के साथ कोई और दवा, खाद या हार्मोन मत मिलाइए।',
        ),
      ),
      WarningOut(
        code: 'rain_wash',
        level: Severity.red,
        text: LocalizedText.pair(
          en: 'If heavy rain comes within twelve hours, spray again within seven days.',
          hi: 'बारह घंटे के अंदर तेज़ बारिश हो जाए तो सात दिन के अंदर दोबारा छिड़काव कीजिए।',
        ),
      ),
    ],
    sources: const ['HP Horticulture Department spray schedule 2026'],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en:
            'This is apple scab. Spray Difenoconazole, the brand name is Score. '
            'Mix thirty millilitres in two hundred litres of water. '
            'Spray today, no rain is expected for twelve hours. '
            'Do not mix any other chemical with it. '
            'Wait fourteen days before you pick the fruit.',
        hi:
            'यह सेब का स्कैब है। डिफेनोकोनाज़ोल दवा छिड़किए, इसका नाम स्कोर है। '
            'दो सौ लीटर पानी में तीस मिलीलीटर दवा घोलिए। '
            'आज ही छिड़काव कीजिए, अगले बारह घंटे बारिश की उम्मीद नहीं है। '
            'इसके साथ कोई और दवा मत मिलाइए। '
            'फल तोड़ने से चौदह दिन पहले तक रुकिए।',
      ),
    ),
    createdAt: now,
  );

  static ScanOut okScan(String id, {String cropId = 'apple', String source = 'server'}) => ScanOut(
    id: id,
    status: ScanStatus.ok,
    createdAt: now,
    photos: 1,
    crop: crop(cropId, source: source),
    disease: DiseaseOut(
      diseaseId: 'Apple___Apple_scab',
      name: LocalizedText.pair(en: 'Apple scab', hi: 'सेब का स्कैब (पपड़ी रोग)'),
      confidence: 0.88,
      route: DiseaseRoute.autoAdvice,
    ),
    advice: scabAdvice(id),
    nextSteps: const [NextStep(action: NextAction.markSprayed, promptId: 'result_next_diary')],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'This looks like apple scab. Please listen to the advice.',
        hi: 'यह सेब का स्कैब लगता है। कृपया सलाह सुनिए।',
      ),
    ),
  );

  static ScanOut needsExpertScan(String id, {String cropId = 'apple'}) => ScanOut(
    id: id,
    status: ScanStatus.needsExpert,
    createdAt: now,
    photos: 1,
    crop: crop(cropId),
    disease: DiseaseOut(
      diseaseId: 'Apple___Marssonina_blotch',
      name: LocalizedText.pair(en: 'Leaf spot (Marssonina?)', hi: 'पत्ती के धब्बे (मार्सोनिना?)'),
      confidence: 0.41,
      route: DiseaseRoute.expertQueue,
      candidates: [
        DiseaseCandidateOut(
          diseaseId: 'Apple___Marssonina_blotch',
          name: LocalizedText.pair(en: 'Marssonina blotch', hi: 'मार्सोनिना धब्बा'),
          confidence: 0.41,
        ),
        DiseaseCandidateOut(
          diseaseId: 'Apple___Alternaria_leaf_spot',
          name: LocalizedText.pair(en: 'Alternaria leaf spot', hi: 'अल्टरनेरिया पत्ती धब्बा'),
          confidence: 0.33,
        ),
      ],
    ),
    reviewTaskId: 'task-$id',
    nextSteps: const [NextStep(action: NextAction.askExpert, promptId: 'result_expert')],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en:
            'We are not sure about this leaf. A farm expert will look at your photos. '
            'Until then, keep the leaves dry and remove badly spotted leaves.',
        hi:
            'इस पत्ती के बारे में हमें पक्का नहीं पता। खेती के जानकार आपकी फोटो देखेंगे। '
            'तब तक पत्तियों को सूखा रखिए और ज़्यादा धब्बे वाली पत्तियाँ हटा दीजिए।',
      ),
    ),
  );

  static ScanOut noApprovedDataScan(String id, {String cropId = 'cauliflower'}) => ScanOut(
    id: id,
    status: ScanStatus.noApprovedData,
    createdAt: now,
    photos: 1,
    crop: crop(cropId),
    nextSteps: const [NextStep(action: NextAction.askExpert, promptId: 'result_no_data')],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'We do not have approved advice for this crop yet. Please ask a farm expert.',
        hi: 'इस फसल की मंज़ूर की हुई सलाह अभी हमारे पास नहीं है। कृपया खेती के जानकार से पूछिए।',
      ),
    ),
  );

  static ScanOut notADiseaseScan(String id, {String cropId = 'apple'}) => ScanOut(
    id: id,
    status: ScanStatus.notADisease,
    createdAt: now,
    photos: 1,
    crop: crop(cropId),
    nextSteps: const [NextStep(action: NextAction.addPhoto, promptId: 'result_not_disease')],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'We could not see a disease in this photo. If you are still worried, take another photo.',
        hi: 'इस फोटो में हमें कोई बीमारी नहीं दिखी। फिर भी चिंता हो तो दूसरी फोटो खींचिए।',
      ),
    ),
  );

  // ------------------------------------------------------------------ spray diary

  /// A scan the mock can always return from `getScan` (the one the first mock alert is about).
  static const alertScanId = 'scan-alert';

  /// The medicine of a diary entry: the given product, else (only an advice id) the mock advice's first product.
  static String? sprayProductId(SprayLogIn log) {
    if (log.productId != null) return log.productId;
    final typed = (log.freeText ?? '').trim();
    return log.adviceId != null && typed.isEmpty ? 'P007' : null;
  }

  static String? sprayProductName(SprayLogIn log) => switch (sprayProductId(log)) {
    'P007' => 'Difenoconazole (Score)',
    'P006' => 'Propineb',
    final id? => log.freeText ?? id,
    null => log.freeText,
  };

  static const _offLabelNames = ['miravis', 'fenpropathrin'];
  static const _proposedBanNames = ['mancozeb', 'captan', 'carbendazim'];
  static const _knownNames = ['score', 'difenoconazole', 'propineb'];

  /// The checks the real server runs on a diary entry, reduced to the typed name: an off-label product (red), a
  /// product that may be banned (yellow), a name that is not in the list (yellow `PRODUCT_NOT_RECOGNISED`).
  static List<WarningOut> sprayWarnings({String? freeText, String? productId}) {
    final text = (freeText ?? '').trim().toLowerCase();
    if (text.isEmpty) return const [];
    if (_offLabelNames.any(text.contains)) {
      return [
        WarningOut(
          code: 'off_label',
          level: Severity.red,
          text: LocalizedText.pair(
            en: 'This medicine is not allowed on this crop. Please do not use it again.',
            hi: 'यह दवा इस फसल पर मंज़ूर नहीं है। कृपया इसे दोबारा मत छिड़किए।',
          ),
        ),
      ];
    }
    if (_proposedBanNames.any(text.contains)) {
      return [
        WarningOut(
          code: 'proposed_ban',
          level: Severity.yellow,
          text: LocalizedText.pair(
            en: 'This medicine may be banned soon. Ask a farm expert before you buy more.',
            hi: 'इस दवा पर जल्द रोक लग सकती है। और खरीदने से पहले खेती के जानकार से पूछिए।',
          ),
        ),
      ];
    }
    if (_knownNames.any(text.contains)) return const [];
    return [
      WarningOut(
        code: 'PRODUCT_NOT_RECOGNISED',
        level: Severity.yellow,
        text: LocalizedText.pair(
          en:
              'This medicine is not in our list, so we could not check it. '
              'Please ask a farm expert before you spray it again.',
          hi:
              'यह दवा हमारी सूची में नहीं मिली, इसलिए इसकी जाँच नहीं हो सकी। '
              'दोबारा छिड़कने से पहले खेती के जानकार से पूछ लीजिए।',
        ),
      ),
    ];
  }

  /// What the server says after saving: "Done", and with warnings the lead-in and the first warning only (like the
  /// real server, so the app must read the other warnings itself).
  static SpokenOut sprayLogSpoken(List<WarningOut> warnings) {
    if (warnings.isEmpty) {
      return SpokenOut(
        text: LocalizedText.pair(
          en: 'Done. It is saved in your diary.',
          hi: 'हो गया। यह आपकी डायरी में लिख दिया गया है।',
        ),
      );
    }
    final first = warnings.first.text;
    return SpokenOut(
      text: LocalizedText.pair(
        en:
            'Done. It is saved in your diary. Please listen carefully. '
            'There is a warning about this medicine. ${first.en}',
        hi:
            'हो गया। यह आपकी डायरी में लिख दिया गया है। ध्यान से सुनिए। '
            'इस दवा के बारे में एक चेतावनी है। ${first.hi}',
      ),
    );
  }

  // ------------------------------------------------------------------ field, alerts, ask

  static FieldOut field() => FieldOut(
    stationId: 'ST08',
    village: 'Kotgarh',
    asOf: now,
    readings: const ReadingsOut(tempC: 17.5, rhPct: 82, rain24hMm: 6.5, leafWetnessMin: 340, soilMoisturePct: 31),
    forecast: [
      for (var i = 0; i < 7; i++)
        ForecastDayOut(
          day: '2026-05-${(12 + i).toString().padLeft(2, '0')}',
          tminC: 8 + (i % 3).toDouble(),
          tmaxC: 18 + (i % 4).toDouble(),
          rainMm: i == 2 || i == 3 ? 12 : 0,
        ),
    ],
    risks: [
      RiskOut(
        id: 'scab_infection',
        level: Severity.yellow,
        title: LocalizedText.pair(en: 'Scab risk', hi: 'स्कैब का ख़तरा'),
        text: LocalizedText.pair(
          en: 'Leaves stayed wet for many hours. Scab can spread.',
          hi: 'पत्तियाँ कई घंटे गीली रहीं। स्कैब फैल सकता है।',
        ),
      ),
    ],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'It is seventeen degrees and humid in Kotgarh. Rain is expected in two days.',
        hi: 'कोटगढ़ में सत्रह डिग्री तापमान है और नमी है। दो दिन बाद बारिश की उम्मीद है।',
      ),
    ),
  );

  /// The sensor is offline: the answer is old and the server says so in its spoken text.
  static FieldOut fieldStale() {
    final base = field();
    return FieldOut(
      stationId: base.stationId,
      village: base.village,
      asOf: DateTime.utc(2026, 5, 9, 4),
      stale: true,
      readings: base.readings,
      forecast: base.forecast,
      risks: base.risks,
      spoken: SpokenOut(
        text: LocalizedText.pair(
          en: 'This information is old. Turn on the internet to see new information. ${base.spoken.text.en}',
          hi: 'यह जानकारी पुरानी है। नई जानकारी के लिए इंटरनेट चालू कीजिए। ${base.spoken.text.hi}',
        ),
      ),
    );
  }

  /// No station and no weather for this farmer yet.
  static FieldOut fieldNoData() => FieldOut(
    asOf: now,
    stale: true,
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en:
            'This information is old. Turn on the internet to see new information. '
            'There is no information for your field yet.',
        hi:
            'यह जानकारी पुरानी है। नई जानकारी के लिए इंटरनेट चालू कीजिए। '
            'आपके खेत की जानकारी अभी नहीं है।',
      ),
    ),
  );

  static AlertListOut alerts() => AlertListOut(
    unread: 1,
    items: [
      AlertOut(
        id: 'alert-1',
        kind: 'rain_wash',
        level: Severity.red,
        title: LocalizedText.pair(en: 'Rain washed your spray', hi: 'बारिश ने छिड़काव धो दिया'),
        body: LocalizedText.pair(
          en: 'Heavy rain came within twelve hours of your spray. Spray again within seven days.',
          hi: 'छिड़काव के बारह घंटे के अंदर तेज़ बारिश हुई। सात दिन के अंदर दोबारा छिड़काव कीजिए।',
        ),
        spoken: SpokenOut(
          text: LocalizedText.pair(
            en: 'Heavy rain washed your spray. Please spray again within seven days.',
            hi: 'तेज़ बारिश ने आपका छिड़काव धो दिया। कृपया सात दिन के अंदर दोबारा छिड़काव कीजिए।',
          ),
        ),
        createdAt: now,
        scanId: alertScanId,
      ),
      AlertOut(
        id: 'alert-2',
        kind: 'scab_weather',
        level: Severity.yellow,
        title: LocalizedText.pair(en: 'Scab weather', hi: 'स्कैब का मौसम'),
        body: LocalizedText.pair(
          en: 'Wet weather is coming. Scab can start.',
          hi: 'गीला मौसम आ रहा है। स्कैब शुरू हो सकता है।',
        ),
        spoken: SpokenOut(
          text: LocalizedText.pair(
            en: 'Wet weather is coming. Scab can start.',
            hi: 'गीला मौसम आ रहा है। स्कैब शुरू हो सकता है।',
          ),
        ),
        createdAt: DateTime.utc(2026, 5, 10, 4),
        readAt: DateTime.utc(2026, 5, 10, 6),
      ),
    ],
  );

  static AskOut answer(String question, String language) => AskOut(
    answer: language == 'hi'
        ? 'सेब के स्कैब में अनुमोदित दवा ही छिड़कें और उसके साथ कोई और दवा न मिलाएँ।'
        : 'For apple scab, spray only the approved medicine and do not mix any other chemical with it.',
    language: language,
    citations: const [CitationOut(noteId: 'N0042', source: 'HP Horticulture Department 2026')],
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'For apple scab, spray only the approved medicine and do not mix any other chemical with it.',
        hi: 'सेब के स्कैब में सिर्फ़ मंज़ूर की हुई दवा छिड़किए और उसके साथ कोई और दवा मत मिलाइए।',
      ),
    ),
  );

  static AskOut refusedAnswer(String language) => AskOut(
    answer: '',
    language: language,
    refused: true,
    spoken: SpokenOut(
      text: LocalizedText.pair(
        en: 'We could not find an answer to this question. Please ask a farm expert.',
        hi: 'इस सवाल का जवाब हमें नहीं मिला। कृपया खेती के जानकार से पूछिए।',
      ),
    ),
  );
}
