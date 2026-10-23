import 'dart:async';

import 'package:dio/dio.dart';

import '../models/models.dart';
import '../storage/token_store.dart';

/// Marks a request that must not carry (or refresh) the access token: login, refresh, public downloads.
const skipAuthKey = 'skipAuth';
const _retriedKey = 'authRetried';

enum _RefreshOutcome { ok, rejected, unreachable }

/// Adds the bearer token and, on a 401, rotates the refresh token once and replays the request.
///
/// Refresh tokens rotate on every use and the server revokes the device when one is replayed, so concurrent
/// 401s share a single refresh call.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required this.dio, required this.refreshDio, required this.tokens, this.onSessionExpired});

  /// The client the original requests run on (used to replay them).
  final Dio dio;

  /// A bare client without interceptors, used only for the refresh call.
  final Dio refreshDio;
  final TokenStore tokens;
  final void Function()? onSessionExpired;

  Future<_RefreshOutcome>? _refreshing;

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    if (options.extra[skipAuthKey] != true) {
      final stored = await tokens.read();
      if (stored != null) options.headers['Authorization'] = 'Bearer ${stored.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final options = err.requestOptions;
    final unauthorized = err.response?.statusCode == 401;
    if (!unauthorized || options.extra[skipAuthKey] == true || options.extra[_retriedKey] == true) {
      return handler.next(err);
    }

    final sentHeader = options.headers['Authorization'];
    final stored = await tokens.read();
    if (stored == null) return handler.next(err);

    // Another request already rotated the tokens while this one was in flight: just replay with the new one.
    final alreadyRotated = sentHeader != null && sentHeader != 'Bearer ${stored.accessToken}';
    if (!alreadyRotated) {
      final outcome = await (_refreshing ??= _refresh(stored.refreshToken).whenComplete(() => _refreshing = null));
      switch (outcome) {
        case _RefreshOutcome.rejected:
          await tokens.clear();
          onSessionExpired?.call();
          return handler.next(err);
        case _RefreshOutcome.unreachable:
          return handler.reject(
            DioException(requestOptions: options, type: DioExceptionType.connectionError, error: err.error),
          );
        case _RefreshOutcome.ok:
          break;
      }
    }

    final fresh = await tokens.read();
    if (fresh == null) return handler.next(err);
    try {
      final replay = options.copyWith(
        headers: {...options.headers, 'Authorization': 'Bearer ${fresh.accessToken}'},
        extra: {...options.extra, _retriedKey: true},
        data: options.data is FormData ? (options.data as FormData).clone() : options.data,
      );
      handler.resolve(await dio.fetch<dynamic>(replay));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  Future<_RefreshOutcome> _refresh(String refreshToken) async {
    try {
      final response = await refreshDio.post<Object?>(
        '/v1/auth/refresh',
        data: RefreshIn(refreshToken: refreshToken).toJson(),
        options: Options(extra: {skipAuthKey: true}),
      );
      final body = response.data;
      if (body is! Map) return _RefreshOutcome.rejected;
      final token = TokenOut.fromJson(Json.from(body));
      if (token.accessToken.isEmpty || token.refreshToken.isEmpty) return _RefreshOutcome.rejected;
      await tokens.write(StoredTokens(accessToken: token.accessToken, refreshToken: token.refreshToken));
      return _RefreshOutcome.ok;
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status != null && status >= 400 && status < 500) return _RefreshOutcome.rejected;
      return _RefreshOutcome.unreachable;
    }
  }
}
