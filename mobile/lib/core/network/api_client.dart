import 'dart:async';

import '../models/models.dart';

/// Lets the farmer cancel a running upload.
class CancelHandle {
  final Completer<void> _completer = Completer<void>();

  bool get isCancelled => _completer.isCompleted;

  Future<void> get onCancel => _completer.future;

  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }
}

typedef UploadProgressCallback = void Function(int sent, int total);

/// The whole backend as seen by the app (`contracts/openapi.json`). Every method throws [ApiException].
///
/// Implementations: `DioApiClient` (real) and `MockApiClient` (canned, for demos and tests).
abstract interface class ApiClient {
  /// Base URL against which relative audio urls are resolved.
  String get baseUrl;

  Future<HealthOut> health();
  Future<MetaOut> meta();

  /// User name and password (`POST /v1/auth/login`). A wrong pair is a 401 `invalid_credentials`, too many tries a 429.
  Future<TokenOut> login({required String username, required String password, String? deviceId});

  /// Revokes the refresh token on the server (always 204). The access token simply runs out.
  Future<void> logout(String refreshToken);

  Future<FarmerOut> me();
  Future<FarmerOut> patchMe(FarmerPatch patch);

  /// Uploads 1 to 4 photos. The pipeline always answers 200 with a status.
  ///
  /// [idempotencyKey] is sent as the `Idempotency-Key` header: the offline queue passes the same key on every retry, so
  /// a lost response never makes a second scan (the server returns the first answer again).
  Future<ScanOut> createScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
    String? idempotencyKey,
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  });
  Future<ScanOut> addPhotos(
    String scanId,
    List<String> photoPaths, {
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  });
  Future<ScanOut> confirmCrop(String scanId, String cropId);
  Future<ScanOut> getScan(String scanId);
  Future<ScanListOut> listScans({int limit = 20, String? cursor});

  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey});
  Future<List<SprayLogOut>> listSprayLogs({int limit = 50});

  Future<FieldOut> field();
  Future<AlertListOut> listAlerts({int limit = 30});
  Future<AlertOut> markAlertRead(String alertId);
  Future<void> registerDevice(DeviceIn device);

  Future<AskOut> ask(AskIn question);
  Future<ExpertRequestOut> createExpertRequest(ExpertRequestIn request);

  Future<VoiceCatalogueOut> voiceCatalogue(String lang);

  /// Downloads a (cacheable, public) audio file. [url] may be relative to [baseUrl].
  Future<List<int>> downloadBytes(String url);
}
