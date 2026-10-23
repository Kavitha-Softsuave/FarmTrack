import 'advice.dart';
import 'json_utils.dart';
import 'localized.dart';

class CropCandidateOut {
  const CropCandidateOut({required this.cropId, this.name = const LocalizedText(), this.confidence = 0});

  factory CropCandidateOut.fromJson(Json json) => CropCandidateOut(
    cropId: json.str('crop_id'),
    name: LocalizedText.fromJson(json['name']),
    confidence: json.doubleOr('confidence'),
  );

  final String cropId;
  final LocalizedText name;
  final double confidence;

  Json toJson() => {'crop_id': cropId, 'name': name.toJson(), 'confidence': confidence};
}

class CropOut {
  const CropOut({
    this.cropId,
    this.name,
    this.confidence = 0,
    this.needsConfirmation = false,
    this.unknown = false,
    this.candidates = const [],
    this.source = 'stub',
  });

  factory CropOut.fromJson(Json json) => CropOut(
    cropId: json.strOrNull('crop_id'),
    name: json.obj('name', LocalizedText.fromJson),
    confidence: json.doubleOr('confidence'),
    needsConfirmation: json.boolOr('needs_confirmation'),
    unknown: json.boolOr('unknown'),
    candidates: json.list('candidates', CropCandidateOut.fromJson),
    source: json.str('source', 'stub'),
  );

  final String? cropId;
  final LocalizedText? name;
  final double confidence;
  final bool needsConfirmation;
  final bool unknown;
  final List<CropCandidateOut> candidates;
  final String source;

  /// True when the server named a crop we can show and speak.
  bool get isKnown => !unknown && cropId != null && cropId!.isNotEmpty;

  Json toJson() => {
    'crop_id': cropId,
    'name': name?.toJson(),
    'confidence': confidence,
    'needs_confirmation': needsConfirmation,
    'unknown': unknown,
    'candidates': [for (final c in candidates) c.toJson()],
    'source': source,
  };
}

class QualityOut {
  const QualityOut({this.usable = true, this.issues = const [], this.tipPromptId});

  factory QualityOut.fromJson(Json json) => QualityOut(
    usable: json.boolOr('usable', true),
    issues: json.strList('issues'),
    tipPromptId: json.strOrNull('tip_prompt_id'),
  );

  final bool usable;
  final List<String> issues;
  final String? tipPromptId;

  Json toJson() => {'usable': usable, 'issues': issues, 'tip_prompt_id': tipPromptId};
}

class DiseaseCandidateOut {
  const DiseaseCandidateOut({required this.diseaseId, this.name = const LocalizedText(), this.confidence = 0});

  factory DiseaseCandidateOut.fromJson(Json json) => DiseaseCandidateOut(
    diseaseId: json.str('disease_id'),
    name: LocalizedText.fromJson(json['name']),
    confidence: json.doubleOr('confidence'),
  );

  final String diseaseId;
  final LocalizedText name;
  final double confidence;

  Json toJson() => {'disease_id': diseaseId, 'name': name.toJson(), 'confidence': confidence};
}

enum DiseaseRoute implements WireEnum {
  autoAdvice('auto_advice'),
  expertQueue('expert_queue'),
  none('none');

  const DiseaseRoute(this.wire);

  @override
  final String wire;

  static DiseaseRoute parse(Object? raw) => parseWire(values, raw, DiseaseRoute.none);
}

class DiseaseOut {
  const DiseaseOut({
    this.diseaseId,
    this.name,
    this.confidence = 0,
    this.route = DiseaseRoute.none,
    this.candidates = const [],
  });

  factory DiseaseOut.fromJson(Json json) => DiseaseOut(
    diseaseId: json.strOrNull('disease_id'),
    name: json.obj('name', LocalizedText.fromJson),
    confidence: json.doubleOr('confidence'),
    route: DiseaseRoute.parse(json['route']),
    candidates: json.list('candidates', DiseaseCandidateOut.fromJson),
  );

  final String? diseaseId;
  final LocalizedText? name;
  final double confidence;
  final DiseaseRoute route;
  final List<DiseaseCandidateOut> candidates;

  Json toJson() => {
    'disease_id': diseaseId,
    'name': name?.toJson(),
    'confidence': confidence,
    'route': route.wire,
    'candidates': [for (final c in candidates) c.toJson()],
  };
}

enum NextAction implements WireEnum {
  confirmCrop('confirm_crop'),
  addPhoto('add_photo'),
  retake('retake'),
  markSprayed('mark_sprayed'),
  askExpert('ask_expert'),
  done('done'),
  unknown('unknown');

  const NextAction(this.wire);

  @override
  final String wire;

  static NextAction parse(Object? raw) => parseWire(values, raw, NextAction.unknown);
}

class NextStep {
  const NextStep({required this.action, required this.promptId});

  factory NextStep.fromJson(Json json) =>
      NextStep(action: NextAction.parse(json['action']), promptId: json.str('prompt_id'));

  final NextAction action;
  final String promptId;

  Json toJson() => {'action': action.wire, 'prompt_id': promptId};
}

enum ScanStatus implements WireEnum {
  ok('ok'),
  confirmCrop('confirm_crop'),
  needsExpert('needs_expert'),
  noApprovedData('no_approved_data'),
  photoUnusable('photo_unusable'),
  notADisease('not_a_disease');

  const ScanStatus(this.wire);

  @override
  final String wire;

  /// Unknown statuses read as [needsExpert]: sending a person to the expert is always the safe answer.
  static ScanStatus parse(Object? raw) => parseWire(values, raw, ScanStatus.needsExpert);
}

class ScanOut {
  const ScanOut({
    required this.id,
    required this.status,
    this.createdAt,
    this.photos = 0,
    this.crop,
    this.quality = const QualityOut(),
    this.disease,
    this.advice,
    this.reviewTaskId,
    this.nextSteps = const [],
    this.spoken = const SpokenOut(),
  });

  factory ScanOut.fromJson(Json json) => ScanOut(
    id: json.str('id'),
    status: ScanStatus.parse(json['status']),
    createdAt: json.dateOrNull('created_at'),
    photos: json.intOr('photos'),
    crop: json.obj('crop', CropOut.fromJson),
    quality: json.obj('quality', QualityOut.fromJson) ?? const QualityOut(),
    disease: json.obj('disease', DiseaseOut.fromJson),
    advice: json.obj('advice', AdviceOut.fromJson),
    reviewTaskId: json.strOrNull('review_task_id'),
    nextSteps: json.list('next_steps', NextStep.fromJson),
    spoken: SpokenOut.fromJson(json['spoken']),
  );

  final String id;
  final ScanStatus status;
  final DateTime? createdAt;
  final int photos;
  final CropOut? crop;
  final QualityOut quality;
  final DiseaseOut? disease;
  final AdviceOut? advice;
  final String? reviewTaskId;
  final List<NextStep> nextSteps;
  final SpokenOut spoken;

  /// Prompt ids the server wants spoken for [action], in order.
  List<String> promptsFor(NextAction action) => [
    for (final s in nextSteps)
      if (s.action == action && s.promptId.isNotEmpty) s.promptId,
  ];

  Json toJson() => {
    'id': id,
    'status': status.wire,
    'created_at': createdAt?.toIso8601String(),
    'photos': photos,
    'crop': crop?.toJson(),
    'quality': quality.toJson(),
    'disease': disease?.toJson(),
    'advice': advice?.toJson(),
    'review_task_id': reviewTaskId,
    'next_steps': [for (final s in nextSteps) s.toJson()],
    'spoken': spoken.toJson(),
  };
}

class ScanListOut {
  const ScanListOut({this.items = const [], this.nextCursor});

  factory ScanListOut.fromJson(Json json) =>
      ScanListOut(items: json.list('items', ScanOut.fromJson), nextCursor: json.strOrNull('next_cursor'));

  final List<ScanOut> items;
  final String? nextCursor;

  Json toJson() => {
    'items': [for (final s in items) s.toJson()],
    'next_cursor': nextCursor,
  };
}

class CropConfirmIn {
  const CropConfirmIn({required this.cropId});

  final String cropId;

  Json toJson() => {'crop_id': cropId};
}

class ExpertRequestIn {
  const ExpertRequestIn({this.scanId, this.message});

  final String? scanId;
  final String? message;

  Json toJson() => compact({'scan_id': scanId, 'message': message});
}

class ExpertRequestOut {
  const ExpertRequestOut({required this.id, this.status = 'open'});

  factory ExpertRequestOut.fromJson(Json json) =>
      ExpertRequestOut(id: json.str('id'), status: json.str('status', 'open'));

  final String id;

  /// `open` or `resolved`.
  final String status;

  Json toJson() => {'id': id, 'status': status};
}
