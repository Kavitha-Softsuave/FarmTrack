import '../models/models.dart';

enum ApiErrorKind { network, timeout, cancelled, unauthorized, validation, rateLimited, server, client, unknown }

/// Every failure of an [ApiClient] call. The server's ErrorOut is mapped into [code], [message] and [details].
class ApiException implements Exception {
  const ApiException({required this.kind, required this.code, this.message = '', this.statusCode, this.details});

  const ApiException.network([String message = 'No internet connection.'])
    : this(kind: ApiErrorKind.network, code: 'network_error', message: message);

  const ApiException.timeout()
    : this(kind: ApiErrorKind.timeout, code: 'timeout', message: 'The request took too long.');

  const ApiException.cancelled() : this(kind: ApiErrorKind.cancelled, code: 'cancelled', message: 'Cancelled.');

  /// Builds the exception for an HTTP error response.
  factory ApiException.fromResponse(int statusCode, Object? body) {
    final Json? json = body is Map ? Json.from(body) : null;
    final out = json == null ? null : ErrorOut.fromJson(json);
    final kind = switch (statusCode) {
      401 => ApiErrorKind.unauthorized,
      422 => ApiErrorKind.validation,
      429 => ApiErrorKind.rateLimited,
      >= 500 => ApiErrorKind.server,
      >= 400 => ApiErrorKind.client,
      _ => ApiErrorKind.unknown,
    };
    return ApiException(
      kind: kind,
      statusCode: statusCode,
      code: out?.code ?? 'http_$statusCode',
      message: out?.message ?? '',
      details: out?.details,
    );
  }

  final ApiErrorKind kind;
  final String code;
  final String message;
  final int? statusCode;
  final Json? details;

  /// The phone cannot reach the server (no internet, DNS, timeout): show the "no internet" prompt.
  bool get isConnectionProblem => kind == ApiErrorKind.network || kind == ApiErrorKind.timeout;

  bool get isCancelled => kind == ApiErrorKind.cancelled;

  @override
  String toString() => 'ApiException($kind, $code${statusCode == null ? '' : ', $statusCode'}): $message';
}
