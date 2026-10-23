import 'dart:async';

import 'package:dio/dio.dart';

const _attemptKey = 'retryAttempt';

/// Retries idempotent GET requests when the connection fails or the server answers 502/503/504.
///
/// POST requests are never retried here: an upload or a spray log must not be sent twice by accident.
class RetryInterceptor extends Interceptor {
  RetryInterceptor({required this.dio, this.delays = const [Duration(milliseconds: 500), Duration(seconds: 1)]});

  final Dio dio;

  /// One entry per retry; its length is the number of retries.
  final List<Duration> delays;

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    final attempt = (options.extra[_attemptKey] as int?) ?? 0;
    if (options.method != 'GET' || attempt >= delays.length || !_isTransient(err)) {
      return handler.next(err);
    }
    if (delays[attempt] > Duration.zero) await Future<void>.delayed(delays[attempt]);
    try {
      final response = await dio.fetch<dynamic>(options.copyWith(extra: {...options.extra, _attemptKey: attempt + 1}));
      handler.resolve(response);
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  bool _isTransient(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionError:
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return true;
      case DioExceptionType.badResponse:
        final s = e.response?.statusCode ?? 0;
        return s == 502 || s == 503 || s == 504;
      case DioExceptionType.cancel:
      case DioExceptionType.badCertificate:
      case DioExceptionType.unknown:
        return false;
    }
  }
}
