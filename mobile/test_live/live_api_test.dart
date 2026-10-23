// Live contract check: the real DioApiClient talks over real HTTP to a locally started real backend.
//
// NOT part of the default `flutter test` (that only runs test/). Start it with `tool\run_live_check.ps1` (or `.sh`), which starts
// the backend fully offline on 127.0.0.1:8765, runs `flutter test test_live` and stops the backend again. By hand:
//   flutter test test_live --dart-define=LIVE_API_URL=http://127.0.0.1:8765 --dart-define=LIVE_HINTS=true
//
// LIVE_HINTS=true means the backend was started with DEMO_DISEASE_HINTS=Apple=Apple___Apple_scab:0.9, so an apple scan must end in
// advice; without it the (stub) disease model answers nothing and a scan goes to the expert queue.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/dio_api_client.dart';
import 'package:farmtrack/core/storage/token_store.dart';

const _baseUrl = String.fromEnvironment('LIVE_API_URL', defaultValue: 'http://127.0.0.1:8765');
const _hints = bool.fromEnvironment('LIVE_HINTS');
const _demoUser = 'f001'; // farmer F001, Apple, Theog (data/farmers.csv, fabricated); demo accounts are f001 to f050
const _demoPassword = 'farm1234'; // the dev backend's shared demo password

/// Where the real test photos are (the tests run with mobile/ as the working directory).
String _photo(String relative) => File('../data/images/testset_v1/leaf/$relative').absolute.path.replaceAll('\\', '/');

final _warnings = <String>[];

/// A check that only warns: used where the backend may not offer a feature yet.
void soft(bool ok, String message) {
  if (ok) return;
  _warnings.add(message);
  // ignore: avoid_print
  print('LIVE WARNING: $message');
}

Future<String> _get(String path) async {
  final client = HttpClient();
  try {
    final request = await client.getUrl(Uri.parse('$_baseUrl$path'));
    final response = await request.close();
    return await response.transform(utf8.decoder).join();
  } finally {
    client.close(force: true);
  }
}

Future<ApiException> failureOf(Future<Object?> call) async {
  try {
    await call;
  } on ApiException catch (e) {
    return e;
  }
  throw TestFailure('the call was expected to fail');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late InMemoryTokenStore store;
  late DioApiClient api;
  var sessionExpiredCalls = 0;
  late bool serverHasIdempotency;

  // Shared state of the journey (the tests below run in order).
  late FarmerOut farmer;
  ScanOut? scan;
  ScanOut? confirmScan;
  String? adviceId;

  DioApiClient newClient(TokenStore tokens, {void Function()? onExpired}) =>
      DioApiClient(baseUrl: _baseUrl, tokens: tokens, onSessionExpired: onExpired);

  setUpAll(() async {
    HttpOverrides.global = null; // the test binding blocks real HTTP by default
    store = InMemoryTokenStore();
    api = newClient(store, onExpired: () => sessionExpiredCalls++);
    final spec = jsonDecode(await _get('/openapi.json')) as Map;
    serverHasIdempotency = jsonEncode(spec['paths']).contains('Idempotency-Key');
  });

  tearDownAll(() {
    // ignore: avoid_print
    print(
      _warnings.isEmpty
          ? 'LIVE: no warnings'
          : 'LIVE: ${_warnings.length} warning(s):\n  - ${_warnings.join('\n  - ')}',
    );
  });

  group('public endpoints', () {
    test('health answers ok with a working database', () async {
      final health = await api.health();
      expect(health.status, 'ok');
      expect(health.db, isTrue);
    });

    test('meta describes an OFFLINE backend (nothing can leave this machine)', () async {
      final meta = await api.meta();
      expect(meta.env, isIn(['dev', 'test']), reason: 'refusing to run against a non-dev backend');
      expect(meta.providers['llm'], 'mock', reason: 'the live check must never reach a real LLM');
      expect(meta.providers['tts'], 'null');
      expect(meta.providers['push'], 'log');
      expect(meta.providers['zoho'], 'mock');
      expect(meta.supportedLanguages, ['hi', 'en']);
      expect(meta.supportedCrops, contains('Apple'));
      expect(meta.demoClock, isNotNull);
    });

    test('the voice catalogue has the same prompts in both languages', () async {
      final hi = await api.voiceCatalogue('hi');
      final en = await api.voiceCatalogue('en');
      expect((hi.language, en.language), ('hi', 'en'));
      expect(hi.prompts.length, greaterThan(100));
      expect({for (final p in hi.prompts) p.id}, {for (final p in en.prompts) p.id});
      expect(hi.prompts.every((p) => p.text.trim().isNotEmpty), isTrue);
    });

    test('a relative url is resolved against the base url (downloadBytes, no token needed)', () async {
      final bytes = await newClient(InMemoryTokenStore()).downloadBytes('/health');
      expect(jsonDecode(utf8.decode(bytes)), {'status': 'ok', 'db': true});
    });
  });

  group('login', () {
    test('without a token a protected call is refused with not_authenticated', () async {
      final e = await failureOf(newClient(InMemoryTokenStore()).me());
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(e.code, 'not_authenticated');
    });

    test('a wrong password and an unknown user name are both 401 invalid_credentials', () async {
      final wrong = await failureOf(api.login(username: _demoUser, password: 'not-the-password'));
      expect(wrong.kind, ApiErrorKind.unauthorized);
      expect(wrong.code, 'invalid_credentials');
      expect(wrong.statusCode, 401);
      final unknown = await failureOf(api.login(username: 'nobody.here', password: _demoPassword));
      expect(unknown.code, 'invalid_credentials', reason: 'the server must not tell which part was wrong');
      expect(sessionExpiredCalls, 0, reason: 'a 401 on login must not trigger a refresh or end a session');
    });

    test(
      'the right user name and password log in (with a per-install device id); the tokens go to the store',
      () async {
        final token = await api.login(username: _demoUser, password: _demoPassword, deviceId: 'live-test-phone-main');
        expect(token.accessToken, isNotEmpty);
        expect(token.refreshToken, isNotEmpty);
        expect(token.tokenType, 'bearer');
        expect(token.expiresIn, greaterThan(0));
        expect(token.farmer.id, 'F001');
        farmer = token.farmer;
        await store.write(StoredTokens(accessToken: token.accessToken, refreshToken: token.refreshToken));
        expect(await store.read(), isNotNull);
      },
    );

    test('the user name is case-insensitive (the app sends it lower-case)', () async {
      final token = await api.login(username: 'F001', password: _demoPassword, deviceId: 'live-test-phone-case');
      expect(token.farmer.id, 'F001');
    });

    test('me, and the language patch the app sends after login', () async {
      final me = await api.me();
      expect(me.id, farmer.id);
      expect(me.primaryCrop, 'Apple');
      expect((await api.patchMe(const FarmerPatch(language: 'en'))).language, 'en');
      expect((await api.patchMe(const FarmerPatch(language: 'hi'))).language, 'hi');
    });

    test('a device can be registered for push', () async {
      await api.registerDevice(
        const DeviceIn(platform: 'android', pushToken: 'live-check-push-token', appVersion: '1.0.0+1'),
      );
    });
  });

  group('scan journey with real photos', () {
    test('upload a scab photo: progress is reported, the answer parses, medicine only with advice', () async {
      final progress = <int>[];
      scan = await api.createScan(
        photoPaths: [_photo('Apple___Apple_scab/SCB_09.jpg')],
        clientCrop: 'Apple',
        clientConfidence: 0.9,
        takenAt: DateTime.now(),
        onProgress: (sent, total) => progress.add(sent),
      );
      final s = scan!;
      // ignore: avoid_print
      print('LIVE scan status=${s.status.wire} disease=${s.disease?.diseaseId} route=${s.disease?.route.wire}');
      expect(s.id, matches(RegExp(r'^[0-9a-f]{32}$')));
      expect(s.createdAt, isNotNull);
      expect(s.photos, 1);
      expect(s.crop?.cropId, 'Apple');
      expect(s.quality.usable, isTrue);
      expect(progress, isNotEmpty, reason: 'upload progress callbacks');
      expect(s.spoken.text.isEmpty, isFalse);
      if (_hints) {
        expect(s.status, ScanStatus.ok, reason: 'DEMO_DISEASE_HINTS forces apple scab, which gets advice');
        expect(s.disease!.diseaseId, 'Apple___Apple_scab');
      }
      if (s.status == ScanStatus.ok) {
        final advice = s.advice!;
        expect(advice.products, isNotEmpty);
        expect(advice.scanId, s.id);
        expect(advice.timing, isNotNull);
        expect(advice.spoken.text.hasLang('hi') && advice.spoken.text.hasLang('en'), isTrue);
        adviceId = advice.id;
      } else {
        expect(s.advice?.products ?? const [], isEmpty, reason: 'no medicine unless the scan is ok');
      }
    });

    test('get and list return what the upload returned', () async {
      final s = scan!;
      final again = await api.getScan(s.id);
      expect((again.id, again.status), (s.id, s.status));
      final list = await api.listScans(limit: 5);
      expect(list.items.map((e) => e.id), contains(s.id));
    });

    test('the same Idempotency-Key returns the first scan again', () async {
      const key = 'live-check-scan-key-0001';
      final photo = [_photo('Apple___Apple_scab/SCB_06.jpg')];
      final first = await api.createScan(
        photoPaths: photo,
        clientCrop: 'Apple',
        clientConfidence: 0.9,
        idempotencyKey: key,
      );
      final second = await api.createScan(
        photoPaths: photo,
        clientCrop: 'Apple',
        clientConfidence: 0.9,
        idempotencyKey: key,
      );
      if (serverHasIdempotency) {
        expect(second.id, first.id, reason: 'the server advertises Idempotency-Key');
      } else {
        soft(second.id == first.id, 'the backend ignores Idempotency-Key: a retry creates a second scan');
      }
    });

    test('no client crop: the farmer\'s crop must be confirmed, then the pipeline continues', () async {
      confirmScan = await api.createScan(photoPaths: [_photo('Apple___Apple_scab/SCB_05l.jpg')]);
      final c = confirmScan!;
      expect(c.status, ScanStatus.confirmCrop);
      expect(c.crop!.isKnown, isTrue);
      expect(c.crop!.needsConfirmation, isTrue);
      expect(c.advice, isNull);
      expect(c.nextSteps.map((e) => e.action), contains(NextAction.confirmCrop));
      final confirmed = await api.confirmCrop(c.id, c.crop!.cropId!);
      expect(confirmed.id, c.id);
      expect(confirmed.crop!.source, 'farmer_confirmed');
      expect(confirmed.status, _hints ? ScanStatus.ok : isNot(ScanStatus.confirmCrop));
    });

    test('a crop the server does not know is refused as validation error', () async {
      final e = await failureOf(api.confirmCrop(confirmScan!.id, 'Dragonfruit'));
      expect(e.kind, ApiErrorKind.validation);
      expect(e.code, 'unknown_crop');
    });

    test('a file that is not an image is refused with invalid_image', () async {
      final dir = Directory.systemTemp.createTempSync('live_fake_photo');
      addTearDown(() => dir.deleteSync(recursive: true));
      final fake = File('${dir.path}/leaf.jpg')..writeAsStringSync('this is not a photo');
      final e = await failureOf(api.createScan(photoPaths: [fake.path.replaceAll('\\', '/')]));
      expect(e.statusCode, 400);
      expect(e.code, 'invalid_image');
    });

    test('an unknown scan is scan_not_found', () async {
      final e = await failureOf(api.getScan('0' * 32));
      expect(e.kind, ApiErrorKind.client);
      expect(e.code, 'scan_not_found');
    });

    test('add a second photo to a scan', () async {
      final updated = await api.addPhotos(scan!.id, [_photo('Apple___Apple_scab/SCB_06.jpg')]);
      expect(updated.id, scan!.id);
      expect(updated.photos, 2);
    });
  });

  group('diary, field, alerts, ask, expert', () {
    test('spray log: only the advice id (the plain "I sprayed" tick), twice with one key', () async {
      final log = adviceId == null
          ? const SprayLogIn(cropId: 'Apple', freeText: 'mancozeb')
          : SprayLogIn(cropId: 'Apple', adviceId: adviceId);
      const key = 'live-check-spray-key-0001';
      final first = await api.createSprayLog(log, idempotencyKey: key);
      expect(first.id, isNotEmpty);
      expect(first.cropId, 'Apple');
      expect(first.productName, isNotEmpty);
      expect(first.sprayedAt, isNotNull);
      expect(first.spoken?.text.isEmpty, isFalse);
      if (adviceId != null) {
        expect(first.adviceId, adviceId);
        expect(first.productId, isNotNull, reason: 'advice only: the first product of the advice');
      }
      final second = await api.createSprayLog(log, idempotencyKey: key);
      if (serverHasIdempotency) {
        expect(second.id, first.id, reason: 'the server advertises Idempotency-Key');
      } else {
        soft(second.id == first.id, 'the backend ignores Idempotency-Key: a retry writes the diary twice');
      }
      final list = await api.listSprayLogs();
      expect(list.map((e) => e.id), contains(first.id));
    });

    test('spray log: a time without offset (what DateTime.now() writes) is read as India time', () async {
      final sprayed = DateTime(2026, 5, 12, 23, 30); // late evening, phone time
      final log = await api.createSprayLog(SprayLogIn(cropId: 'Apple', freeText: 'mancozeb', sprayedAt: sprayed));
      if (sprayed.timeZoneOffset == const Duration(hours: 5, minutes: 30)) {
        expect(
          log.sprayedAt!.isAtSameMomentAs(sprayed),
          isTrue,
          reason: 'the server read ${sprayed.toIso8601String()} differently',
        );
      } else {
        // ignore: avoid_print
        print('LIVE NOTE: this machine is not on India time, the spray time check is skipped');
      }
    });

    test('spray log: a typed name that is not in the catalogue is saved with a warning', () async {
      final log = await api.createSprayLog(const SprayLogIn(cropId: 'Apple', freeText: 'my own homemade mix'));
      expect(log.productId, isNull);
      expect(log.warnings.map((w) => w.code), contains('PRODUCT_NOT_RECOGNISED'));
    });

    test('crop ids are accepted in any case: the app tables are lower case, the server says Apple', () async {
      final log = await api.createSprayLog(const SprayLogIn(cropId: 'apple', freeText: 'mancozeb'));
      expect(log.cropId, 'Apple', reason: 'the server writes the canonical name back');
      final answer = await api.ask(
        const AskIn(question: 'What should I do if it rains after spraying?', language: 'en', cropId: 'apple'),
      );
      expect(answer.refused, isFalse);
      final again = await api.confirmCrop(confirmScan!.id, 'apple');
      expect(again.crop!.cropId, 'Apple');
    });

    test('spray log: an advice of another farmer or an unknown advice is advice_not_found', () async {
      final e = await failureOf(api.createSprayLog(SprayLogIn(cropId: 'Apple', adviceId: 'f' * 32, productId: 'P011')));
      expect(e.code, 'advice_not_found');
    });

    test('my field: readings, a seven day forecast and risks in both languages', () async {
      final field = await api.field();
      expect(field.stationId, farmer.stationId);
      expect(field.asOf, isNotNull);
      expect(field.forecast.length, 7);
      expect(field.risks, isNotEmpty);
      expect(field.risks.every((r) => r.title.hasLang('hi') && r.title.hasLang('en')), isTrue);
      expect(field.spoken.text.isEmpty, isFalse);
    });

    test('alerts: the list parses and an alert can be marked read', () async {
      final list = await api.listAlerts();
      expect(list.unread, greaterThanOrEqualTo(0));
      // The scheduler is off here, so a fresh database has no alerts; the shape is covered by the fixture test.
      if (list.items.isNotEmpty) {
        final read = await api.markAlertRead(list.items.first.id);
        expect(read.isRead, isTrue);
      }
      final e = await failureOf(api.markAlertRead('0' * 32));
      expect(e.code, 'alert_not_found');
    });

    test('ask: answered with a citation, refused for a crop without approved data', () async {
      final answered = await api.ask(
        const AskIn(question: 'What should I do if it rains after spraying?', language: 'en', cropId: 'Apple'),
      );
      expect(answered.refused, isFalse);
      expect(answered.answer, isNotEmpty);
      expect(answered.citations, isNotEmpty);
      final hindi = await api.ask(
        const AskIn(question: 'स्प्रे के बाद बारिश हो जाए तो क्या करूँ?', language: 'hi', cropId: 'Apple'),
      );
      expect(hindi.refused, isFalse, reason: 'a Hindi question survives the trip as UTF-8');
      expect(hindi.language, 'hi');
      expect(hindi.answer, matches(RegExp(r'[ऀ-ॿ]')));
      final refused = await api.ask(const AskIn(question: 'Which medicine for my pea crop?', language: 'en'));
      expect(refused.refused, isTrue);
      expect(refused.citations, isEmpty);
      final tooShort = await failureOf(api.ask(const AskIn(question: '?')));
      expect(tooShort.kind, ApiErrorKind.validation);
    });

    test('expert request with and without a scan', () async {
      final withScan = await api.createExpertRequest(ExpertRequestIn(scanId: scan!.id, message: 'live check'));
      expect((withScan.id.isNotEmpty, withScan.status), (true, 'open'));
      final plain = await api.createExpertRequest(const ExpertRequestIn(message: 'a plain question'));
      expect((plain.id.isNotEmpty, plain.status), (true, 'open'));
      final e = await failureOf(api.createExpertRequest(ExpertRequestIn(scanId: 'e' * 32)));
      expect(e.code, 'scan_not_found');
    });
  });

  group('tokens', () {
    test('an expired access token is refreshed once, the call is replayed and the refresh token rotates', () async {
      final before = (await store.read())!;
      await store.write(StoredTokens(accessToken: 'expired-access-token', refreshToken: before.refreshToken));
      final me = await api.me();
      expect(me.id, farmer.id);
      final after = (await store.read())!;
      expect(after.accessToken, isNot('expired-access-token'));
      expect(after.refreshToken, isNot(before.refreshToken), reason: 'refresh tokens rotate on every use');
      expect(sessionExpiredCalls, 0);
    });

    test('several calls with an expired token share one refresh (a second refresh would revoke the device)', () async {
      final current = (await store.read())!;
      await store.write(StoredTokens(accessToken: 'expired-again', refreshToken: current.refreshToken));
      final results = await Future.wait([api.me(), api.field(), api.listAlerts(), api.listSprayLogs()]);
      expect(results.first, isA<FarmerOut>());
      expect(sessionExpiredCalls, 0, reason: 'the farmer must still be logged in');
      expect((await store.read())!.refreshToken, isNot(current.refreshToken));
    });

    test('logout revokes the refresh token; the next 401 ends the session', () async {
      final current = (await store.read())!;
      await api.logout(current.refreshToken);
      await store.write(StoredTokens(accessToken: 'expired-after-logout', refreshToken: current.refreshToken));
      final e = await failureOf(api.me());
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(sessionExpiredCalls, 1);
      expect(await store.read(), isNull, reason: 'the rejected refresh clears the tokens');
    });

    test(
      'a refresh token used twice (a lost answer) is refused; does it log out the other phones of the farmer?',
      () async {
        // Each phone sends its own per-install device id at login, like the app (deviceIdProvider).
        Future<TokenOut> login(String deviceId) =>
            api.login(username: _demoUser, password: _demoPassword, deviceId: deviceId);

        final first = await login('live-test-phone-a');
        final firstStore = InMemoryTokenStore(
          StoredTokens(accessToken: first.accessToken, refreshToken: first.refreshToken),
        );
        var firstExpired = 0;
        final firstApi = newClient(firstStore, onExpired: () => firstExpired++);
        // The phone refreshes, but pretend the answer was lost: it still holds the OLD refresh token.
        await firstStore.write(StoredTokens(accessToken: 'expired', refreshToken: first.refreshToken));
        await firstApi.me(); // rotates: first.refreshToken is now used up
        final other = await login('live-test-phone-b'); // the farmer's second phone
        await firstStore.write(StoredTokens(accessToken: 'expired', refreshToken: first.refreshToken)); // the replay
        final replay = await failureOf(firstApi.me());
        expect(replay.kind, ApiErrorKind.unauthorized);
        expect(firstExpired, 1);
        final otherStore = InMemoryTokenStore(StoredTokens(accessToken: 'expired', refreshToken: other.refreshToken));
        var otherAlive = true;
        try {
          await newClient(otherStore).me();
        } on ApiException {
          otherAlive = false;
        }
        soft(
          otherAlive,
          'a replayed refresh token logged out the other phone of the farmer although the phones use different device ids '
          '(a lost refresh answer on one phone must not log out the other)',
        );
      },
    );
  });
}
