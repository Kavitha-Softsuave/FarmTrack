import 'json_utils.dart';
import 'localized.dart';

class WarningOut {
  const WarningOut({required this.code, this.level = Severity.yellow, this.text = const LocalizedText()});

  factory WarningOut.fromJson(Json json) => WarningOut(
    code: json.str('code'),
    level: Severity.parse(json['level']),
    text: LocalizedText.fromJson(json['text']),
  );

  final String code;
  final Severity level;
  final LocalizedText text;

  Json toJson() => {'code': code, 'level': level.wire, 'text': text.toJson()};
}

class ProductOut {
  const ProductOut({
    required this.productId,
    this.activeIngredient = const LocalizedText(),
    this.brandExamples = const [],
    this.formulation,
    this.category = '',
    this.fracIracCode,
    this.doseText = const LocalizedText(),
    this.doseMin,
    this.doseMax,
    this.doseUnit,
    this.waitingPeriodDays,
    this.warnings = const [],
  });

  factory ProductOut.fromJson(Json json) => ProductOut(
    productId: json.str('product_id'),
    activeIngredient: LocalizedText.fromJson(json['active_ingredient']),
    brandExamples: json.strList('brand_examples'),
    formulation: json.strOrNull('formulation'),
    category: json.str('category'),
    fracIracCode: json.strOrNull('frac_irac_code'),
    doseText: LocalizedText.fromJson(json['dose_text']),
    doseMin: json.doubleOrNull('dose_min'),
    doseMax: json.doubleOrNull('dose_max'),
    doseUnit: json.strOrNull('dose_unit'),
    waitingPeriodDays: json.intOrNull('waiting_period_days'),
    warnings: json.list('warnings', WarningOut.fromJson),
  );

  final String productId;
  final LocalizedText activeIngredient;
  final List<String> brandExamples;
  final String? formulation;
  final String category;
  final String? fracIracCode;

  /// A sentence the farmer can read or hear, e.g. "thirty millilitres in two hundred litres of water".
  final LocalizedText doseText;
  final double? doseMin;
  final double? doseMax;
  final String? doseUnit;
  final int? waitingPeriodDays;
  final List<WarningOut> warnings;

  Json toJson() => {
    'product_id': productId,
    'active_ingredient': activeIngredient.toJson(),
    'brand_examples': brandExamples,
    'formulation': formulation,
    'category': category,
    'frac_irac_code': fracIracCode,
    'dose_text': doseText.toJson(),
    'dose_min': doseMin,
    'dose_max': doseMax,
    'dose_unit': doseUnit,
    'waiting_period_days': waitingPeriodDays,
    'warnings': [for (final w in warnings) w.toJson()],
  };
}

enum TimingAction implements WireEnum {
  sprayNow('spray_now'),
  wait('wait'),
  repeatWithinDays('repeat_within_days'),
  notNeeded('not_needed'),
  unknown('unknown');

  const TimingAction(this.wire);

  @override
  final String wire;

  static TimingAction parse(Object? raw) => parseWire(values, raw, TimingAction.unknown);
}

class TimingOut {
  const TimingOut({
    this.action = TimingAction.unknown,
    this.text = const LocalizedText(),
    this.rainNext12hMm,
    this.repeatWithinDays,
  });

  factory TimingOut.fromJson(Json json) => TimingOut(
    action: TimingAction.parse(json['action']),
    text: LocalizedText.fromJson(json['text']),
    rainNext12hMm: json.doubleOrNull('rain_next_12h_mm'),
    repeatWithinDays: json.intOrNull('repeat_within_days'),
  );

  final TimingAction action;
  final LocalizedText text;
  final double? rainNext12hMm;
  final int? repeatWithinDays;

  Json toJson() => {
    'action': action.wire,
    'text': text.toJson(),
    'rain_next_12h_mm': rainNext12hMm,
    'repeat_within_days': repeatWithinDays,
  };
}

class AdviceOut {
  const AdviceOut({
    required this.id,
    this.scanId = '',
    this.cropId = '',
    this.diseaseId,
    this.severity = Severity.yellow,
    this.headline = const LocalizedText(),
    this.summary = const LocalizedText(),
    this.products = const [],
    this.timing,
    this.steps = const [],
    this.safety = const [],
    this.warnings = const [],
    this.sources = const [],
    this.validated = true,
    this.spoken = const SpokenOut(),
    this.createdAt,
  });

  factory AdviceOut.fromJson(Json json) => AdviceOut(
    id: json.str('id'),
    scanId: json.str('scan_id'),
    cropId: json.str('crop_id'),
    diseaseId: json.strOrNull('disease_id'),
    severity: Severity.parse(json['severity']),
    headline: LocalizedText.fromJson(json['headline']),
    summary: LocalizedText.fromJson(json['summary']),
    products: json.list('products', ProductOut.fromJson),
    timing: json.obj('timing', TimingOut.fromJson),
    steps: _texts(json['steps']),
    safety: _texts(json['safety']),
    warnings: json.list('warnings', WarningOut.fromJson),
    sources: json.strList('sources'),
    validated: json.boolOr('validated', true),
    spoken: SpokenOut.fromJson(json['spoken']),
    createdAt: json.dateOrNull('created_at'),
  );

  final String id;
  final String scanId;
  final String cropId;
  final String? diseaseId;
  final Severity severity;
  final LocalizedText headline;
  final LocalizedText summary;
  final List<ProductOut> products;
  final TimingOut? timing;
  final List<LocalizedText> steps;
  final List<LocalizedText> safety;
  final List<WarningOut> warnings;
  final List<String> sources;
  final bool validated;
  final SpokenOut spoken;
  final DateTime? createdAt;

  Json toJson() => {
    'id': id,
    'scan_id': scanId,
    'crop_id': cropId,
    'disease_id': diseaseId,
    'severity': severity.wire,
    'headline': headline.toJson(),
    'summary': summary.toJson(),
    'products': [for (final p in products) p.toJson()],
    'timing': timing?.toJson(),
    'steps': [for (final s in steps) s.toJson()],
    'safety': [for (final s in safety) s.toJson()],
    'warnings': [for (final w in warnings) w.toJson()],
    'sources': sources,
    'validated': validated,
    'spoken': spoken.toJson(),
    'created_at': createdAt?.toIso8601String(),
  };
}

List<LocalizedText> _texts(Object? raw) {
  if (raw is! List) return const [];
  return [for (final e in raw) LocalizedText.fromJson(e)];
}
