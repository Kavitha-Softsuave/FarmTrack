import 'dart:async';
import 'dart:io' show SocketException;

import 'package:dio/dio.dart';

import '../models/models.dart';
import '../storage/token_store.dart';
import 'api_client.dart';
import '../errors/api_exception.dart';
import 'auth_interceptor.dart';
import 'retry_interceptor.dart';

/// Maps any Dio failure to an [ApiException] (the server's ErrorOut body is parsed when there is one).
ApiException mapDioException(DioException e) {
  switch (e.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.transformTimeout:
      return const ApiException.timeout();
    case DioExceptionType.connectionError:
      return const ApiException.network();
    case DioExceptionType.cancel:
      return const ApiException.cancelled();
    case DioExceptionType.badResponse:
      return ApiException.fromResponse(e.response?.statusCode ?? 0, e.response?.data);
    case DioExceptionType.badCertificate:
      return const ApiException(
        kind: ApiErrorKind.unknown,
        code: 'bad_certificate',
        message: 'Secure connection failed.',
      );
    case DioExceptionType.unknown:
      if (e.error is SocketException) return const ApiException.network();
      return ApiException(kind: ApiErrorKind.unknown, code: 'unknown', message: '${e.error ?? e.message ?? ''}');
  }
}

class DioApiClient implements ApiClient {
  DioApiClient({
    required String baseUrl,
    required TokenStore tokens,
    void Function()? onSessionExpired,
    HttpClientAdapter? adapter,
    List<Duration> retryDelays = const [Duration(milliseconds: 500), Duration(seconds: 1)],
  }) : _baseUrl = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl,
       _dio = Dio(_options(baseUrl)) {
    final refreshDio = Dio(_options(baseUrl));
    if (adapter != null) {
      _dio.httpClientAdapter = adapter;
      refreshDio.httpClientAdapter = adapter;
    }
    _dio.interceptors.addAll([
      AuthInterceptor(dio: _dio, refreshDio: refreshDio, tokens: tokens, onSessionExpired: onSessionExpired),
      RetryInterceptor(dio: _dio, delays: retryDelays),
    ]);
  }

  static BaseOptions _options(String baseUrl) => BaseOptions(
    baseUrl: baseUrl,
    connectTimeout: const Duration(seconds: 10),
    sendTimeout: const Duration(seconds: 30),
    receiveTimeout: const Duration(seconds: 30),
    headers: {'Accept': 'application/json'},
  );

  final String _baseUrl;
  final Dio _dio;

  @override
  String get baseUrl => _baseUrl;

  // ------------------------------------------------------------------ helpers

  Future<T> _call<T>(Future<Response<Object?>> Function() request, T Function(Json) parse) async {
    final Response<Object?> response;
    try {
      response = await request();
    } on DioException catch (e) {
      throw mapDioException(e);
    }
    final body = response.data;
    if (body is! Map) {
      throw const ApiException(kind: ApiErrorKind.server, code: 'bad_response', message: 'Unexpected answer.');
    }
    try {
      return parse(Json.from(body));
    } on Object catch (_) {
      throw const ApiException(kind: ApiErrorKind.server, code: 'bad_response', message: 'Unexpected answer.');
    }
  }

  Future<List<T>> _callList<T>(Future<Response<Object?>> Function() request, T Function(Json) parse) async {
    final Response<Object?> response;
    try {
      response = await request();
    } on DioException catch (e) {
      throw mapDioException(e);
    }
    final body = response.data;
    if (body is! List) {
      throw const ApiException(kind: ApiErrorKind.server, code: 'bad_response', message: 'Unexpected answer.');
    }
    return [
      for (final e in body)
        if (e is Map) parse(Json.from(e)),
    ];
  }

  Options get _noAuth => Options(extra: {skipAuthKey: true});

  Future<FormData> _photoForm(List<String> paths, Map<String, Object?> fields) async {
    final form = FormData();
    for (final path in paths) {
      final isPng = path.toLowerCase().endsWith('.png');
      form.files.add(
        MapEntry(
          'photos',
          await MultipartFile.fromFile(
            path,
            filename: path.split('/').last,
            contentType: DioMediaType('image', isPng ? 'png' : 'jpeg'),
          ),
        ),
      );
    }
    for (final e in fields.entries) {
      if (e.value != null) form.fields.add(MapEntry(e.key, '${e.value}'));
    }
    return form;
  }

  CancelToken? _token(CancelHandle? handle) {
    if (handle == null) return null;
    final token = CancelToken();
    if (handle.isCancelled) {
      token.cancel();
    } else {
      unawaited(handle.onCancel.then((_) => token.cancel()));
    }
    return token;
  }

  Options get _uploadOptions =>
      Options(sendTimeout: const Duration(seconds: 90), receiveTimeout: const Duration(seconds: 120));

  // ------------------------------------------------------------------ endpoints

  @override
  Future<HealthOut> health() => _call(() => _dio.get<Object?>('/health', options: _noAuth), HealthOut.fromJson);

  @override
  Future<MetaOut> meta() => _call(() => _dio.get<Object?>('/v1/meta', options: _noAuth), MetaOut.fromJson);

  @override
  Future<TokenOut> login({required String username, required String password, String? deviceId}) => _call(
    () => _dio.post<Object?>(
      '/v1/auth/login',
      data: LoginIn(username: username, password: password, deviceId: deviceId).toJson(),
      options: _noAuth,
    ),
    TokenOut.fromJson,
  );

  @override
  Future<void> logout(String refreshToken) async {
    try {
      await _dio.post<Object?>(
        '/v1/auth/logout',
        data: RefreshIn(refreshToken: refreshToken).toJson(),
        options: _noAuth,
      );
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Future<FarmerOut> me() => _call(() => _dio.get<Object?>('/v1/me'), FarmerOut.fromJson);

  @override
  Future<FarmerOut> patchMe(FarmerPatch patch) =>
      _call(() => _dio.patch<Object?>('/v1/me', data: patch.toJson()), FarmerOut.fromJson);

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
    final form = await _photoForm(photoPaths, {
      'client_crop': clientCrop,
      'client_confidence': clientConfidence,
      'taken_at': takenAt?.toIso8601String(),
      'lat': lat,
      'lon': lon,
    });
    final token = _token(cancel);
    return _call(
      () => _dio.post<Object?>(
        '/v1/scans',
        data: form,
        options: idempotencyKey == null
            ? _uploadOptions
            : _uploadOptions.copyWith(headers: {'Idempotency-Key': idempotencyKey}),
        cancelToken: token,
        onSendProgress: onProgress,
      ),
      ScanOut.fromJson,
    );
  }

  @override
  Future<ScanOut> addPhotos(
    String scanId,
    List<String> photoPaths, {
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  }) async {
    final form = await _photoForm(photoPaths, const {});
    final token = _token(cancel);
    return _call(
      () => _dio.post<Object?>(
        '/v1/scans/$scanId/photos',
        data: form,
        options: _uploadOptions,
        cancelToken: token,
        onSendProgress: onProgress,
      ),
      ScanOut.fromJson,
    );
  }

  @override
  Future<ScanOut> confirmCrop(String scanId, String cropId) => _call(
    () => _dio.post<Object?>('/v1/scans/$scanId/crop', data: CropConfirmIn(cropId: cropId).toJson()),
    ScanOut.fromJson,
  );

  @override
  Future<ScanOut> getScan(String scanId) => _call(() => _dio.get<Object?>('/v1/scans/$scanId'), ScanOut.fromJson);

  @override
  Future<ScanListOut> listScans({int limit = 20, String? cursor}) => _call(
    () => _dio.get<Object?>('/v1/scans', queryParameters: {'limit': limit, 'cursor': ?cursor}),
    ScanListOut.fromJson,
  );

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) => _call(
    () => _dio.post<Object?>(
      '/v1/spray-logs',
      data: log.toJson(),
      options: idempotencyKey == null ? null : Options(headers: {'Idempotency-Key': idempotencyKey}),
    ),
    SprayLogOut.fromJson,
  );

  @override
  Future<List<SprayLogOut>> listSprayLogs({int limit = 50}) =>
      _callList(() => _dio.get<Object?>('/v1/spray-logs', queryParameters: {'limit': limit}), SprayLogOut.fromJson);

  @override
  Future<FieldOut> field() => _call(() => _dio.get<Object?>('/v1/field'), FieldOut.fromJson);

  @override
  Future<AlertListOut> listAlerts({int limit = 30}) =>
      _call(() => _dio.get<Object?>('/v1/alerts', queryParameters: {'limit': limit}), AlertListOut.fromJson);

  @override
  Future<AlertOut> markAlertRead(String alertId) =>
      _call(() => _dio.post<Object?>('/v1/alerts/$alertId/read'), AlertOut.fromJson);

  @override
  Future<void> registerDevice(DeviceIn device) async {
    try {
      await _dio.post<Object?>('/v1/devices', data: device.toJson());
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }

  @override
  Future<AskOut> ask(AskIn question) =>
      _call(() => _dio.post<Object?>('/v1/ask', data: question.toJson()), AskOut.fromJson);

  @override
  Future<ExpertRequestOut> createExpertRequest(ExpertRequestIn request) =>
      _call(() => _dio.post<Object?>('/v1/expert-requests', data: request.toJson()), ExpertRequestOut.fromJson);

  @override
  Future<VoiceCatalogueOut> voiceCatalogue(String lang) => _call(
    () => _dio.get<Object?>('/v1/voice/catalogue', queryParameters: {'lang': lang}, options: _noAuth),
    VoiceCatalogueOut.fromJson,
  );

  @override
  Future<List<int>> downloadBytes(String url) async {
    final target = url.startsWith('http://') || url.startsWith('https://')
        ? url
        : '$_baseUrl${url.startsWith('/') ? '' : '/'}$url';
    try {
      final response = await _dio.get<List<int>>(
        target,
        options: Options(responseType: ResponseType.bytes, extra: {skipAuthKey: true}),
      );
      return response.data ?? const [];
    } on DioException catch (e) {
      throw mapDioException(e);
    }
  }
}
