import 'dart:async';

import '../models/models.dart';
import 'api_client.dart';
import '../errors/api_exception.dart';
import 'mock_data.dart';

/// What the next mock scan returns.
enum MockScanScenario {
  /// Low crop confidence: asks for the tick (apple, 0.55). Confirming returns the advice.
  confirmCrop,

  /// Apple scab with approved advice, products and spoken text.
  ok,
  photoBlurry,
  photoTooDark,
  needsExpert,
  noApprovedData,
  notADisease,
}

/// A backend in memory: realistic canned answers for every endpoint and every scan status, so the app can be
/// demonstrated without the server. Also the default in tests.
///
/// Scans cycle through [scanScript]; set [latency] to zero for tests; use [failWith] to simulate errors.
class MockApiClient implements ApiClient {
  MockApiClient({
    this.latency = const Duration(milliseconds: 500),
    List<MockScanScenario>? scanScript,
    this.validPassword = 'farm1234',
    this.baseUrl = 'http://mock.invalid',
    this.requireAuth = false,
  }) : scanScript = List.of(scanScript ?? defaultScript);

  /// confirm the crop, then advice, then a blurry photo, an expert case, no data, and "no disease".
  static const defaultScript = [
    MockScanScenario.confirmCrop,
    MockScanScenario.ok,
    MockScanScenario.photoBlurry,
    MockScanScenario.needsExpert,
    MockScanScenario.noApprovedData,
    MockScanScenario.notADisease,
  ];

  /// Fake network delay. [Duration.zero] skips waiting completely.
  Duration latency;

  /// Scenarios used by the next scans, in order; the list repeats.
  List<MockScanScenario> scanScript;
  final String validPassword;

  /// When true, endpoints other than login answer 401 until [login] succeeded in this process.
  final bool requireAuth;

  @override
  final String baseUrl;

  // ---- failure mode -------------------------------------------------------

  ApiException? _failure;
  int _failuresLeft = 0;
  Set<String> _failOps = const {};

  /// Makes calls fail with [error]: [times] calls (-1 = until [clearFailure]), only for the named [ops]
  /// (method names such as `createScan`; empty = every call).
  void failWith(ApiException error, {int times = -1, Set<String> ops = const {}}) {
    _failure = error;
    _failuresLeft = times;
    _failOps = ops;
  }

  void clearFailure() {
    _failure = null;
    _failuresLeft = 0;
    _failOps = const {};
  }

  // ---- recorded state (handy in tests) -------------------------------------

  /// Names of the methods called, in order.
  final List<String> calls = [];

  /// What every [login] call sent, in order (the user name as received, the device id).
  final List<({String username, String? deviceId})> loginCalls = [];
  final Map<String, ScanOut> scans = {};
  final List<String> confirmedCrops = [];
  final List<ExpertRequestIn> expertRequests = [];
  final List<SprayLogIn> sprayLogsIn = [];
  final List<SprayLogOut> _sprayLogs = [];
  final List<List<String>> uploadedPhotoPaths = [];

  /// Scenario hooks (null = the canned answer): what `field()` and `listAlerts()` return next.
  FieldOut? fieldOverride;
  List<AlertOut>? alertItems;
  final Set<String> _readAlertIds = {};

  /// Idempotency keys received, in order (null entries are calls without a key). A repeated key returns the first answer.
  final List<String?> idempotencyKeys = [];
  final Map<String, ScanOut> _scansByKey = {};
  final Map<String, SprayLogOut> _sprayLogsByKey = {};
  ({String? crop, double? confidence})? lastClientGuess;
  int _scanSerial = 0;
  int _tokenSerial = 0;
  int _logSerial = 0;
  String _language = 'hi';
  bool _signedIn = false;

  Future<void> _enter(String op, {CancelHandle? cancel, double delayFactor = 1}) async {
    calls.add(op);
    if (latency > Duration.zero) {
      final wait = Future<void>.delayed(latency * delayFactor);
      if (cancel == null) {
        await wait;
      } else {
        await Future.any([wait, cancel.onCancel]);
      }
    }
    if (cancel != null && cancel.isCancelled) throw const ApiException.cancelled();
    final error = _failure;
    if (error != null && (_failOps.isEmpty || _failOps.contains(op)) && _failuresLeft != 0) {
      if (_failuresLeft > 0) _failuresLeft--;
      throw error;
    }
  }

  void _requireLogin() {
    if (requireAuth && !_signedIn) {
      throw const ApiException(
        kind: ApiErrorKind.unauthorized,
        code: 'not_authenticated',
        message: 'Please log in.',
        statusCode: 401,
      );
    }
  }

  // ------------------------------------------------------------------ endpoints

  @override
  Future<HealthOut> health() async {
    await _enter('health');
    return const HealthOut(status: 'ok', db: true);
  }

  @override
  Future<MetaOut> meta() async {
    await _enter('meta');
    return MockData.meta();
  }

  /// Demo accounts: `f001` to `f099` with [validPassword] (the same pair the dev backend seeds: f001 to f050).
  @override
  Future<TokenOut> login({required String username, required String password, String? deviceId}) async {
    await _enter('login');
    loginCalls.add((username: username, deviceId: deviceId));
    if (!RegExp(r'^f0\d\d$').hasMatch(username.trim().toLowerCase()) || password != validPassword) {
      throw const ApiException(
        kind: ApiErrorKind.unauthorized,
        code: 'invalid_credentials',
        message: 'The user name or password is not correct.',
        statusCode: 401,
      );
    }
    _signedIn = true;
    _tokenSerial++;
    return MockData.tokens(_tokenSerial, language: _language);
  }

  @override
  Future<void> logout(String refreshToken) async {
    await _enter('logout');
    _signedIn = false;
  }

  @override
  Future<FarmerOut> me() async {
    await _enter('me');
    _requireLogin();
    return MockData.farmer(language: _language);
  }

  @override
  Future<FarmerOut> patchMe(FarmerPatch patch) async {
    await _enter('patchMe');
    _requireLogin();
    _language = patch.language ?? _language;
    return MockData.farmer(language: _language);
  }

  ScanOut _scanFor(MockScanScenario scenario, String id) => switch (scenario) {
    MockScanScenario.confirmCrop => MockData.confirmCropScan(id),
    MockScanScenario.ok => MockData.okScan(id),
    MockScanScenario.photoBlurry => MockData.photoUnusableScan(id),
    MockScanScenario.photoTooDark => MockData.photoUnusableScan(id, issue: 'too_dark'),
    MockScanScenario.needsExpert => MockData.needsExpertScan(id),
    MockScanScenario.noApprovedData => MockData.noApprovedDataScan(id),
    MockScanScenario.notADisease => MockData.notADiseaseScan(id),
  };

  void _progress(UploadProgressCallback? onProgress) {
    if (onProgress == null) return;
    for (final done in const [25, 50, 75, 100]) {
      onProgress(done, 100);
    }
  }

  @override
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
  }) async {
    await _enter('createScan', cancel: cancel, delayFactor: 3);
    _requireLogin();
    idempotencyKeys.add(idempotencyKey);
    final earlier = idempotencyKey == null ? null : _scansByKey[idempotencyKey];
    if (earlier != null) return earlier;
    _progress(onProgress);
    uploadedPhotoPaths.add(List.of(photoPaths));
    lastClientGuess = (crop: clientCrop, confidence: clientConfidence);
    final scenario = scanScript[_scanSerial % scanScript.length];
    _scanSerial++;
    final id = 'scan-$_scanSerial';
    final scan = _scanFor(scenario, id);
    scans[id] = scan;
    if (idempotencyKey != null) _scansByKey[idempotencyKey] = scan;
    return scan;
  }

  @override
  Future<ScanOut> addPhotos(
    String scanId,
    List<String> photoPaths, {
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  }) async {
    await _enter('addPhotos', cancel: cancel, delayFactor: 3);
    _requireLogin();
    _progress(onProgress);
    final scan = scans[scanId] ?? (throw _notFound('scan'));
    uploadedPhotoPaths.add(List.of(photoPaths));
    return scan;
  }

  @override
  Future<ScanOut> confirmCrop(String scanId, String cropId) async {
    await _enter('confirmCrop', delayFactor: 2);
    _requireLogin();
    if (!scans.containsKey(scanId)) throw _notFound('scan');
    confirmedCrops.add(cropId);
    final ScanOut scan;
    if (cropId == 'apple') {
      scan = MockData.okScan(scanId, source: 'farmer');
    } else if (MockData.cropsWithData.contains(cropId)) {
      scan = MockData.needsExpertScan(scanId, cropId: cropId);
    } else {
      scan = MockData.noApprovedDataScan(scanId, cropId: cropId);
    }
    scans[scanId] = scan;
    return scan;
  }

  @override
  Future<ScanOut> getScan(String scanId) async {
    await _enter('getScan');
    _requireLogin();
    if (scanId == MockData.alertScanId && !scans.containsKey(scanId)) return MockData.okScan(scanId);
    return scans[scanId] ?? (throw _notFound('scan'));
  }

  @override
  Future<ScanListOut> listScans({int limit = 20, String? cursor}) async {
    await _enter('listScans');
    _requireLogin();
    return ScanListOut(items: scans.values.toList().reversed.take(limit).toList());
  }

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) async {
    await _enter('createSprayLog');
    _requireLogin();
    idempotencyKeys.add(idempotencyKey);
    final earlier = idempotencyKey == null ? null : _sprayLogsByKey[idempotencyKey];
    if (earlier != null) return earlier;
    sprayLogsIn.add(log);
    _logSerial++;
    final warnings = MockData.sprayWarnings(freeText: log.freeText, productId: log.productId);
    final out = SprayLogOut(
      id: 'log-$_logSerial',
      cropId: log.cropId,
      productId: MockData.sprayProductId(log),
      productName: MockData.sprayProductName(log),
      sprayedAt: log.sprayedAt ?? MockData.now,
      adviceId: log.adviceId,
      warnings: warnings,
      syncedToZoho: true,
      spoken: MockData.sprayLogSpoken(warnings),
    );
    _sprayLogs.insert(0, out);
    if (idempotencyKey != null) _sprayLogsByKey[idempotencyKey] = out;
    return out;
  }

  @override
  Future<List<SprayLogOut>> listSprayLogs({int limit = 50}) async {
    await _enter('listSprayLogs');
    _requireLogin();
    return _sprayLogs.take(limit).toList();
  }

  @override
  Future<FieldOut> field() async {
    await _enter('field');
    _requireLogin();
    return fieldOverride ?? MockData.field();
  }

  List<AlertOut> _alerts() => [
    for (final a in alertItems ?? MockData.alerts().items)
      if (_readAlertIds.contains(a.id) && !a.isRead) a.copyWithRead(MockData.now) else a,
  ];

  @override
  Future<AlertListOut> listAlerts({int limit = 30}) async {
    await _enter('listAlerts');
    _requireLogin();
    final all = _alerts();
    return AlertListOut(items: all.take(limit).toList(), unread: all.where((a) => !a.isRead).length);
  }

  @override
  Future<AlertOut> markAlertRead(String alertId) async {
    await _enter('markAlertRead');
    _requireLogin();
    final alert = _alerts().firstWhere((a) => a.id == alertId, orElse: () => throw _notFound('alert'));
    _readAlertIds.add(alertId);
    return alert.isRead ? alert : alert.copyWithRead(MockData.now);
  }

  @override
  Future<void> registerDevice(DeviceIn device) async {
    await _enter('registerDevice');
    _requireLogin();
  }

  @override
  Future<AskOut> ask(AskIn question) async {
    await _enter('ask', delayFactor: 2);
    _requireLogin();
    if (question.question.trim().isEmpty || question.question.toLowerCase().contains('lottery')) {
      return MockData.refusedAnswer(question.language);
    }
    return MockData.answer(question.question, question.language);
  }

  @override
  Future<ExpertRequestOut> createExpertRequest(ExpertRequestIn request) async {
    await _enter('createExpertRequest');
    _requireLogin();
    expertRequests.add(request);
    return ExpertRequestOut(id: 'expert-${expertRequests.length}');
  }

  @override
  Future<VoiceCatalogueOut> voiceCatalogue(String lang) async {
    await _enter('voiceCatalogue');
    return VoiceCatalogueOut(version: 'mock', language: lang);
  }

  @override
  Future<List<int>> downloadBytes(String url) async {
    await _enter('downloadBytes');
    throw const ApiException.network('The mock server has no audio files.');
  }

  ApiException _notFound(String what) =>
      ApiException(kind: ApiErrorKind.client, code: 'not_found', message: 'No such $what.', statusCode: 404);
}
