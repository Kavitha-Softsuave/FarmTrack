import 'advice.dart';
import 'json_utils.dart';
import 'localized.dart';

class SprayLogIn {
  const SprayLogIn({required this.cropId, this.adviceId, this.productId, this.freeText, this.sprayedAt, this.notes});

  final String cropId;
  final String? adviceId;
  final String? productId;
  final String? freeText;
  final DateTime? sprayedAt;
  final String? notes;

  Json toJson() => compact({
    'crop_id': cropId,
    'advice_id': adviceId,
    'product_id': productId,
    'free_text': freeText,
    'sprayed_at': sprayedAt?.toIso8601String(),
    'notes': notes,
  });
}

class SprayLogOut {
  const SprayLogOut({
    required this.id,
    this.cropId = '',
    this.productId,
    this.productName,
    this.sprayedAt,
    this.adviceId,
    this.warnings = const [],
    this.syncedToZoho = false,
    this.spoken,
  });

  factory SprayLogOut.fromJson(Json json) => SprayLogOut(
    id: json.str('id'),
    cropId: json.str('crop_id'),
    productId: json.strOrNull('product_id'),
    productName: json.strOrNull('product_name'),
    sprayedAt: json.dateOrNull('sprayed_at'),
    adviceId: json.strOrNull('advice_id'),
    warnings: json.list('warnings', WarningOut.fromJson),
    syncedToZoho: json.boolOr('synced_to_zoho'),
    spoken: json['spoken'] is Map ? SpokenOut.fromJson(json['spoken']) : null,
  );

  final String id;
  final String cropId;
  final String? productId;
  final String? productName;
  final DateTime? sprayedAt;
  final String? adviceId;
  final List<WarningOut> warnings;
  final bool syncedToZoho;
  final SpokenOut? spoken;

  Json toJson() => {
    'id': id,
    'crop_id': cropId,
    'product_id': productId,
    'product_name': productName,
    'sprayed_at': sprayedAt?.toIso8601String(),
    'advice_id': adviceId,
    'warnings': [for (final w in warnings) w.toJson()],
    'synced_to_zoho': syncedToZoho,
    'spoken': spoken?.toJson(),
  };
}
