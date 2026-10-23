import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/network/dio_api_client.dart';
import 'package:farmtrack/core/storage/token_store.dart';

typedef Handler = FutureOr<ResponseBody> Function(RequestOptions options, int attempt);

/// An in-memory server for Dio: records requests and answers with [handler].
class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);

  final Handler handler;
  final List<RequestOptions> requests = [];
  final Map<String, int> _attempts = {};

  int count(String method, String path) => requests.where((r) => r.method == method && r.path == path).length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    await requestStream?.drain<void>(); // like a real adapter: the body is consumed
    requests.add(options);
    final key = '${options.method} ${options.path}';
    final attempt = _attempts[key] = (_attempts[key] ?? 0) + 1;
    return handler(options, attempt);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody json(Object body, [int status = 200]) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    'content-type': ['application/json'],
  },
);

ResponseBody text(String body, int status) => ResponseBody.fromString(
  body,
  status,
  headers: {
    'content-type': ['text/html'],
  },
);

Map<String, Object?> tokenBody(String access, String refresh) => {
  'access_token': access,
  'refresh_token': refresh,
  'token_type': 'bearer',
  'expires_in': 900,
  'farmer': {'id': 'F1', 'name': 'Ramesh', 'phone_masked': '+91 ****', 'language': 'hi'},
};

Map<String, Object?> farmerBody() => {'id': 'F1', 'name': 'Ramesh', 'phone_masked': '+91 ****', 'language': 'hi'};

DioApiClient client(FakeAdapter adapter, InMemoryTokenStore store, {void Function()? onExpired}) => DioApiClient(
  baseUrl: 'http://api.test/',
  tokens: store,
  adapter: adapter,
  onSessionExpired: onExpired,
  retryDelays: const [Duration.zero, Duration.zero],
);

InMemoryTokenStore signedIn() => InMemoryTokenStore(const StoredTokens(accessToken: 'old', refreshToken: 'r-old'));

Future<ApiException> failure(Future<Object?> call) async {
  try {
    await call;
  } on ApiException catch (e) {
    return e;
  }
  fail('expected an ApiException');
}

void main() {
  group('requests', () {
    test('public endpoints carry no token; private ones carry the bearer token', () async {
      final adapter = FakeAdapter(
        (o, _) => json(o.path == '/v1/meta' ? {'app_version': '1', 'env': 'dev'} : farmerBody()),
      );
      final api = client(adapter, signedIn());
      final meta = await api.meta();
      expect(meta.env, 'dev');
      expect(adapter.requests.last.headers.containsKey('Authorization'), isFalse);
      final me = await api.me();
      expect(me.name, 'Ramesh');
      expect(adapter.requests.last.headers['Authorization'], 'Bearer old');
      expect(adapter.requests.last.uri.toString(), 'http://api.test/v1/me');
    });

    test('login: user name and password go to POST /v1/auth/login as documented, without a token', () async {
      final adapter = FakeAdapter((o, _) => json(tokenBody('a1', 'r1')));
      final api = client(adapter, signedIn());
      final token = await api.login(username: 'f001', password: 'farm1234', deviceId: 'dev');
      expect(token.accessToken, 'a1');
      expect(adapter.requests.last.method, 'POST');
      expect(adapter.requests.last.uri.toString(), 'http://api.test/v1/auth/login');
      expect(adapter.requests.last.data, {'username': 'f001', 'password': 'farm1234', 'device_id': 'dev'});
      expect(adapter.requests.last.headers.containsKey('Authorization'), isFalse);
      await api.login(username: 'f001', password: 'farm1234');
      expect(adapter.requests.last.data, {'username': 'f001', 'password': 'farm1234'});
    });

    test('confirm crop, expert request, spray log, ask, alerts and field use the documented paths', () async {
      final adapter = FakeAdapter((o, _) {
        switch ('${o.method} ${o.path}') {
          case 'POST /v1/scans/s1/crop':
            return json({'id': 's1', 'status': 'ok', 'photos': 1});
          case 'POST /v1/expert-requests':
            return json({'id': 'e1', 'status': 'open'});
          case 'POST /v1/spray-logs':
            return json({'id': 'l1', 'crop_id': 'apple', 'sprayed_at': '2026-05-12T03:00:00Z'});
          case 'GET /v1/spray-logs':
            return json([
              {'id': 'l1', 'crop_id': 'apple', 'sprayed_at': '2026-05-12T03:00:00Z'},
            ]);
          case 'POST /v1/ask':
            return json({'answer': 'x', 'language': 'hi'});
          case 'GET /v1/alerts':
            return json({'items': [], 'unread': 2});
          case 'POST /v1/alerts/a1/read':
            return json({'id': 'a1', 'read_at': '2026-05-12T03:00:00Z'});
          case 'GET /v1/field':
            return json({'station_id': 'ST08', 'village': 'K', 'as_of': '2026-05-12T03:00:00Z'});
          case 'GET /v1/voice/catalogue':
            return json({'version': 'v', 'language': 'hi', 'prompts': []});
          case 'POST /v1/devices':
            return ResponseBody.fromString('', 204);
          case 'POST /v1/auth/logout':
            return ResponseBody.fromString('', 204);
          case 'PATCH /v1/me':
            return json(farmerBody());
          case 'GET /v1/scans':
            return json({'items': [], 'next_cursor': null});
        }
        return json({'code': 'not_found', 'message': 'no'}, 404);
      });
      final api = client(adapter, signedIn());
      expect((await api.confirmCrop('s1', 'apple')).status, ScanStatus.ok);
      expect(adapter.requests.last.data, {'crop_id': 'apple'});
      expect((await api.createExpertRequest(const ExpertRequestIn(scanId: 's1'))).id, 'e1');
      expect((await api.createSprayLog(const SprayLogIn(cropId: 'apple', productId: 'P007'))).id, 'l1');
      expect(adapter.requests.last.data, {'crop_id': 'apple', 'product_id': 'P007'});
      expect(await api.listSprayLogs(limit: 5), hasLength(1));
      expect(adapter.requests.last.queryParameters, {'limit': 5});
      expect((await api.ask(const AskIn(question: 'q'))).answer, 'x');
      expect((await api.listAlerts()).unread, 2);
      expect((await api.markAlertRead('a1')).isRead, isTrue);
      expect((await api.field()).village, 'K');
      expect((await api.voiceCatalogue('hi')).version, 'v');
      expect(adapter.requests.last.queryParameters, {'lang': 'hi'});
      await api.registerDevice(const DeviceIn(platform: 'android', pushToken: 't'));
      await api.logout('r-old');
      expect(adapter.requests.last.path, '/v1/auth/logout');
      expect(adapter.requests.last.data, {'refresh_token': 'r-old'});
      expect(adapter.requests.last.headers.containsKey('Authorization'), isFalse);
      expect((await api.patchMe(const FarmerPatch(language: 'en'))).id, 'F1');
      expect((await api.listScans(limit: 3, cursor: 'c')).items, isEmpty);
      expect(adapter.requests.last.queryParameters, {'limit': 3, 'cursor': 'c'});
    });

    test('createScan uploads every photo as multipart `photos` with the optional client fields', () async {
      final dir = Directory.systemTemp.createTempSync('upload');
      final a = File('${dir.path}/a.jpg')..writeAsBytesSync([1, 2, 3]);
      final b = File('${dir.path}/b.png')..writeAsBytesSync([4, 5]);
      final adapter = FakeAdapter((o, _) => json({'id': 's1', 'status': 'confirm_crop', 'photos': 2}));
      final api = client(adapter, signedIn());
      final progress = <int>[];
      final scan = await api.createScan(
        photoPaths: [a.path, b.path],
        clientCrop: 'apple',
        clientConfidence: 0.7,
        takenAt: DateTime.utc(2026, 5, 12),
        onProgress: (sent, total) => progress.add(sent),
      );
      expect(scan.status, ScanStatus.confirmCrop);
      final form = adapter.requests.last.data as FormData;
      expect(form.files.map((f) => f.key), ['photos', 'photos']);
      expect(form.files.map((f) => f.value.filename), ['a.jpg', 'b.png']);
      expect(form.files.map((f) => f.value.contentType.toString()), ['image/jpeg', 'image/png']);
      expect(Map.fromEntries(form.fields), {
        'client_crop': 'apple',
        'client_confidence': '0.7',
        'taken_at': '2026-05-12T00:00:00.000Z',
      });
      expect(adapter.requests.last.headers['Authorization'], 'Bearer old');
    });

    test('a cancelled upload throws a cancelled ApiException', () async {
      final dir = Directory.systemTemp.createTempSync('cancel');
      final a = File('${dir.path}/a.jpg')..writeAsBytesSync([1]);
      final adapter = FakeAdapter((o, _) async {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        return json({'id': 's', 'status': 'ok'});
      });
      final api = client(adapter, signedIn());
      final cancel = CancelHandle();
      final call = failure(api.createScan(photoPaths: [a.path], cancel: cancel));
      await Future<void>.delayed(const Duration(milliseconds: 20));
      cancel.cancel();
      final error = await call;
      expect(error.isCancelled, isTrue);
    });

    test('audio downloads resolve a relative url against the base url and send no token', () async {
      final adapter = FakeAdapter((o, _) => ResponseBody.fromBytes([9, 9, 9], 200));
      final api = client(adapter, signedIn());
      expect(await api.downloadBytes('/audio/ab12.mp3'), [9, 9, 9]);
      expect(adapter.requests.last.uri.toString(), 'http://api.test/audio/ab12.mp3');
      expect(adapter.requests.last.headers.containsKey('Authorization'), isFalse);
      await api.downloadBytes('audio/cd34.mp3');
      expect(adapter.requests.last.uri.toString(), 'http://api.test/audio/cd34.mp3');
      await api.downloadBytes('https://cdn.test/audio/x.mp3');
      expect(adapter.requests.last.uri.toString(), 'https://cdn.test/audio/x.mp3');
      expect(api.baseUrl, 'http://api.test');
    });
  });

  group('error mapping', () {
    ApiClient apiFor(ResponseBody Function() body) => client(FakeAdapter((o, _) => body()), signedIn());

    test('an ErrorOut body becomes code, message and details', () async {
      final api = apiFor(
        () => json({
          'code': 'invalid_image',
          'message': 'Wrong',
          'details': {'attempts_left': 2},
        }, 400),
      );
      final e = await failure(api.confirmCrop('s1', 'apple'));
      expect(e.kind, ApiErrorKind.client);
      expect(e.code, 'invalid_image');
      expect(e.message, 'Wrong');
      expect(e.details!['attempts_left'], 2);
      expect(e.statusCode, 400);
      expect(e.isConnectionProblem, isFalse);
    });

    test('422, 429 and 5xx get their own kinds; a non-JSON error still yields a usable exception', () async {
      var e = await failure(
        apiFor(() => json({'code': 'validation_error', 'message': 'bad', 'detail': []}, 422))
            .login(username: 'f001', password: 'farm1234'),
      );
      expect(e.kind, ApiErrorKind.validation);
      e = await failure(
        apiFor(
          () => json({
            'code': 'rate_limited',
            'message': 'slow',
            'details': {'retry_after_seconds': 30},
          }, 429),
        ).login(username: 'f001', password: 'farm1234'),
      );
      expect(e.kind, ApiErrorKind.rateLimited);
      expect(e.details!['retry_after_seconds'], 30);
      e = await failure(
        apiFor(() => json({'code': 'internal_error', 'message': 'x'}, 500))
            .login(username: 'f001', password: 'farm1234'),
      );
      expect(e.kind, ApiErrorKind.server);
      e = await failure(
        apiFor(() => text('<html>Bad gateway</html>', 502)).login(username: 'f001', password: 'farm1234'),
      );
      expect(e.kind, ApiErrorKind.server);
      expect(e.code, 'http_502');
    });

    test('an unexpected 200 body is a clean error, not a crash', () async {
      final e = await failure(apiFor(() => text('<html>captive portal</html>', 200)).meta());
      expect(e.code, 'bad_response');
    });

    test('connection failures and timeouts', () async {
      final offline = DioApiClient(
        baseUrl: 'http://api.test',
        tokens: InMemoryTokenStore(),
        retryDelays: const [],
        adapter: FakeAdapter((o, _) => throw DioException.connectionError(requestOptions: o, reason: 'no route')),
      );
      final e = await failure(offline.login(username: 'f001', password: 'farm1234'));
      expect(e.kind, ApiErrorKind.network);
      expect(e.isConnectionProblem, isTrue);

      final slow = DioApiClient(
        baseUrl: 'http://api.test',
        tokens: InMemoryTokenStore(),
        retryDelays: const [],
        adapter: FakeAdapter(
          (o, _) => throw DioException.receiveTimeout(timeout: const Duration(seconds: 1), requestOptions: o),
        ),
      );
      final t = await failure(slow.login(username: 'f001', password: 'farm1234'));
      expect(t.kind, ApiErrorKind.timeout);
      expect(t.isConnectionProblem, isTrue);
    });
  });

  group('retry of idempotent GETs', () {
    test('a GET is retried after connection errors and 503, with the delays configured', () async {
      final adapter = FakeAdapter((o, attempt) {
        if (attempt == 1) throw DioException.connectionError(requestOptions: o, reason: 'x');
        if (attempt == 2) return json({'code': 'service_unavailable', 'message': 'x'}, 503);
        return json({'app_version': '1', 'env': 'dev'});
      });
      final api = client(adapter, InMemoryTokenStore());
      expect((await api.meta()).env, 'dev');
      expect(adapter.count('GET', '/v1/meta'), 3);
    });

    test('it gives up after the configured number of retries', () async {
      final adapter = FakeAdapter((o, _) => throw DioException.connectionError(requestOptions: o, reason: 'x'));
      final e = await failure(client(adapter, InMemoryTokenStore()).meta());
      expect(e.kind, ApiErrorKind.network);
      expect(adapter.count('GET', '/v1/meta'), 3, reason: 'one try and two retries');
    });

    test('POST is never retried, and 4xx is never retried', () async {
      final adapter = FakeAdapter((o, _) => throw DioException.connectionError(requestOptions: o, reason: 'x'));
      await failure(client(adapter, signedIn()).createExpertRequest(const ExpertRequestIn(scanId: 's')));
      expect(adapter.count('POST', '/v1/expert-requests'), 1);

      final notFound = FakeAdapter((o, _) => json({'code': 'not_found', 'message': 'x'}, 404));
      await failure(client(notFound, signedIn()).getScan('nope'));
      expect(notFound.count('GET', '/v1/scans/nope'), 1);
    });
  });

  group('token refresh', () {
    test('a 401 rotates the refresh token once and replays the request with the new token', () async {
      final store = signedIn();
      final adapter = FakeAdapter((o, attempt) {
        if (o.path == '/v1/auth/refresh') return json(tokenBody('new-access', 'r-new'));
        return o.headers['Authorization'] == 'Bearer new-access'
            ? json(farmerBody())
            : json({'code': 'invalid_token', 'message': 'expired'}, 401);
      });
      final me = await client(adapter, store).me();
      expect(me.id, 'F1');
      expect(adapter.count('POST', '/v1/auth/refresh'), 1);
      expect(adapter.requests.firstWhere((r) => r.path == '/v1/auth/refresh').data, {'refresh_token': 'r-old'});
      expect(adapter.count('GET', '/v1/me'), 2);
      final stored = await store.read();
      expect(stored!.accessToken, 'new-access');
      expect(stored.refreshToken, 'r-new', reason: 'rotated');
    });

    test(
      'several requests failing together share a single refresh (a replayed refresh token would revoke the device)',
      () async {
        final store = signedIn();
        final adapter = FakeAdapter((o, _) async {
          if (o.path == '/v1/auth/refresh') {
            await Future<void>.delayed(const Duration(milliseconds: 30));
            return json(tokenBody('n', 'r-n'));
          }
          return o.headers['Authorization'] == 'Bearer n'
              ? json({'items': [], 'unread': 0})
              : json({'code': 'invalid_token', 'message': 'x'}, 401);
        });
        final api = client(adapter, store);
        final results = await Future.wait([api.listAlerts(), api.listAlerts(), api.listAlerts()]);
        expect(results, hasLength(3));
        expect(adapter.count('POST', '/v1/auth/refresh'), 1);
      },
    );

    test('a rejected refresh token ends the session: tokens cleared, callback called, 401 surfaced', () async {
      final store = signedIn();
      var expired = 0;
      final adapter = FakeAdapter(
        (o, _) => o.path == '/v1/auth/refresh'
            ? json({'code': 'invalid_refresh_token', 'message': 'Please log in again.'}, 401)
            : json({'code': 'invalid_token', 'message': 'x'}, 401),
      );
      final e = await failure(client(adapter, store, onExpired: () => expired++).me());
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(expired, 1);
      expect(await store.read(), isNull);
    });

    test('with no network the tokens are kept and the farmer stays logged in', () async {
      final store = signedIn();
      var expired = 0;
      final adapter = FakeAdapter((o, _) {
        if (o.path == '/v1/auth/refresh') throw DioException.connectionError(requestOptions: o, reason: 'offline');
        return json({'code': 'invalid_token', 'message': 'x'}, 401);
      });
      final e = await failure(client(adapter, store, onExpired: () => expired++).me());
      expect(e.isConnectionProblem, isTrue);
      expect(expired, 0);
      expect((await store.read())!.refreshToken, 'r-old');
    });

    test('a wrong password (401 invalid_credentials) is a normal error and never triggers a refresh', () async {
      final adapter = FakeAdapter(
        (o, _) => json({'code': 'invalid_credentials', 'message': 'The user name or password is not correct.'}, 401),
      );
      final e = await failure(client(adapter, signedIn()).login(username: 'f001', password: 'wrong-pass'));
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(e.code, 'invalid_credentials');
      expect(e.statusCode, 401);
      expect(e.isConnectionProblem, isFalse);
      expect(adapter.count('POST', '/v1/auth/refresh'), 0);
      expect(adapter.count('POST', '/v1/auth/login'), 1, reason: 'a login is never replayed');
    });

    test('too many login tries: 429 rate_limited with Retry-After seconds', () async {
      final adapter = FakeAdapter(
        (o, _) => json({
          'code': 'rate_limited',
          'message': 'Too many tries.',
          'details': {'retry_after_seconds': 60},
        }, 429),
      );
      final e = await failure(client(adapter, InMemoryTokenStore()).login(username: 'f001', password: 'wrong-pass'));
      expect(e.kind, ApiErrorKind.rateLimited);
      expect(e.code, 'rate_limited');
      expect(e.details!['retry_after_seconds'], 60);
    });

    test('an upload that gets a 401 is replayed with a fresh copy of the multipart body', () async {
      final dir = Directory.systemTemp.createTempSync('replay');
      final a = File('${dir.path}/a.jpg')..writeAsBytesSync([1, 2, 3]);
      final store = signedIn();
      final adapter = FakeAdapter((o, _) {
        if (o.path == '/v1/auth/refresh') return json(tokenBody('n', 'r-n'));
        return o.headers['Authorization'] == 'Bearer n'
            ? json({'id': 's1', 'status': 'ok', 'photos': 1})
            : json({'code': 'invalid_token', 'message': 'x'}, 401);
      });
      final scan = await client(adapter, store).createScan(photoPaths: [a.path]);
      expect(scan.id, 's1');
      expect(adapter.count('POST', '/v1/scans'), 2);
      final replayed = adapter.requests.last.data as FormData;
      expect(replayed.files.single.value.filename, 'a.jpg');
    });
  });
}
