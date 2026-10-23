import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';

import 'support/harness.dart';

MockApiClient mock([List<MockScanScenario>? script]) => MockApiClient(latency: Duration.zero, scanScript: script);

Future<ScanOut> scan(MockApiClient api) => api.createScan(photoPaths: const ['/tmp/a.jpg']);

void main() {
  final catalogue = loadCatalogue();

  group('every endpoint answers with realistic data', () {
    test('health, meta, voice catalogue', () async {
      final api = mock();
      expect((await api.health()).status, 'ok');
      final meta = await api.meta();
      expect(meta.supportedCrops, containsAll(['apple', 'tomato', 'potato']));
      expect(meta.supportedLanguages, ['hi', 'en']);
      expect((await api.voiceCatalogue('hi')).language, 'hi');
    });

    test('login: user name and password, profile, language change', () async {
      final api = mock();
      final token = await api.login(username: 'f001', password: 'farm1234', deviceId: 'dev-1');
      expect(api.loginCalls.single, (username: 'f001', deviceId: 'dev-1'));
      expect(token.accessToken, isNotEmpty);
      expect(token.refreshToken, isNotEmpty);
      expect(token.farmer.name, 'Ramesh Kumar');
      expect((await api.me()).primaryCrop, 'apple');
      expect((await api.patchMe(const FarmerPatch(language: 'en'))).language, 'en');
      expect((await api.me()).language, 'en');
      await api.logout(token.refreshToken);
      expect(api.calls.last, 'logout');
    });

    test('every demo account f001 to f050 logs in, case and spaces in the user name do not matter', () async {
      final api = mock();
      for (final user in ['f002', 'f050', 'F013', ' f007 ']) {
        expect(
          (await api.login(username: user, password: 'farm1234')).accessToken,
          isNotEmpty,
          reason: user,
        );
      }
    });

    test('a wrong password or an unknown user is 401 invalid_credentials, like the real server', () async {
      final api = mock();
      for (final (user, password) in [('f001', 'nope1234'), ('nobody', 'farm1234'), ('', ''), ('f001', 'FARM1234')]) {
        final e = await api
            .login(username: user, password: password)
            .then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
        expect(e, isNotNull, reason: "'$user' / '$password'");
        expect(e!.code, 'invalid_credentials');
        expect(e.kind, ApiErrorKind.unauthorized);
        expect(e.statusCode, 401);
      }
    });

    test('login follows the failure injection switches', () async {
      final api = mock()..failWith(const ApiException.network(), times: 1, ops: {'login'});
      final e = await api
          .login(username: 'f001', password: 'farm1234')
          .then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
      expect(e!.isConnectionProblem, isTrue);
      expect((await api.login(username: 'f001', password: 'farm1234')).farmer.id, 'F001');
    });

    test('field, alerts, spray diary, ask, expert request, device', () async {
      final api = mock();
      final field = await api.field();
      expect(field.forecast, hasLength(7));
      expect(field.spoken.text.hi, isNotEmpty);
      final alerts = await api.listAlerts();
      expect(alerts.unread, 1);
      expect(alerts.items.first.level, Severity.red);
      expect((await api.markAlertRead('alert-1')).isRead, isTrue);

      final log = await api.createSprayLog(const SprayLogIn(cropId: 'apple', productId: 'P007', adviceId: 'a1'));
      expect(log.syncedToZoho, isTrue);
      expect(log.productName, contains('Difenoconazole'));
      expect((await api.listSprayLogs()).single.id, log.id);

      final answer = await api.ask(const AskIn(question: 'How to spray?', language: 'en'));
      expect(answer.refused, isFalse);
      expect(answer.answer, contains('approved'));
      expect((await api.ask(const AskIn(question: 'lottery numbers'))).refused, isTrue);

      expect((await api.createExpertRequest(const ExpertRequestIn(scanId: 's'))).status, 'open');
      await api.registerDevice(const DeviceIn(platform: 'ios', pushToken: 't'));
    });

    test('downloading audio fails like an offline phone (the mock has no audio)', () async {
      final e = await mock()
          .downloadBytes('/audio/x.mp3')
          .then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
      expect(e!.isConnectionProblem, isTrue);
    });
  });

  group('scan statuses', () {
    test('the default script walks through confirm_crop, ok, photo_unusable, needs_expert, no_approved_data, not_a_disease', () async {
      final api = mock();
      final seen = [for (var i = 0; i < 7; i++) (await scan(api)).status];
      expect(seen, [
        ScanStatus.confirmCrop,
        ScanStatus.ok,
        ScanStatus.photoUnusable,
        ScanStatus.needsExpert,
        ScanStatus.noApprovedData,
        ScanStatus.notADisease,
        ScanStatus.confirmCrop,
      ]);
    });

    test(
      'ok carries advice with a product, dose sentence, timing, warnings and spoken text in both languages',
      () async {
        final s = await scan(mock([MockScanScenario.ok]));
        final a = s.advice!;
        expect(s.crop!.cropId, 'apple');
        expect(a.products.single.doseText.hi, isNotEmpty);
        expect(a.products.single.doseText.en, isNotEmpty);
        expect(a.products.single.waitingPeriodDays, 14);
        expect(a.timing!.action, TimingAction.sprayNow);
        expect(a.warnings.map((w) => w.level), containsAll([Severity.yellow, Severity.red]));
        expect(a.spoken.text.hi, isNotEmpty);
        expect(a.spoken.text.en, isNotEmpty);
        expect(s.nextSteps.single.promptId, 'result_next_diary');
      },
    );

    test('every scan answer: both languages, known prompt ids, and it survives JSON like a real response', () async {
      for (final scenario in MockScanScenario.values) {
        final s = await scan(mock([scenario]));
        expect(s.spoken.text.hi, isNotEmpty, reason: '$scenario hi');
        expect(s.spoken.text.en, isNotEmpty, reason: '$scenario en');
        for (final step in s.nextSteps) {
          expect(catalogue.contains(step.promptId), isTrue, reason: '${step.promptId} of $scenario');
        }
        final tip = s.quality.tipPromptId;
        if (tip != null) expect(catalogue.contains(tip), isTrue);
        final again = ScanOut.fromJson(s.toJson());
        expect(again.status, s.status, reason: '$scenario');
      }
    });

    test('confirm_crop: confirming apple gives the advice, other crops follow the approved-data rules', () async {
      final api = mock([MockScanScenario.confirmCrop]);
      final first = await scan(api);
      expect(first.crop!.needsConfirmation, isTrue);
      expect(first.crop!.candidates.map((c) => c.cropId), ['apple', 'pear', 'plum']);
      expect((await api.confirmCrop(first.id, 'apple')).status, ScanStatus.ok);
      expect((await api.confirmCrop(first.id, 'potato')).status, ScanStatus.needsExpert);
      expect((await api.confirmCrop(first.id, 'kiwi')).status, ScanStatus.noApprovedData);
      expect(api.confirmedCrops, ['apple', 'potato', 'kiwi']);
      expect((await api.getScan(first.id)).crop!.cropId, 'kiwi');
      expect((await api.listScans()).items, hasLength(1));
    });

    test('unknown scan ids are a 404', () async {
      final e = await mock().getScan('nope').then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
      expect(e!.statusCode, 404);
    });

    test('photos of the uploads and the client crop hint are recorded', () async {
      final api = mock([MockScanScenario.ok]);
      await api.createScan(photoPaths: const ['/a.jpg', '/b.jpg'], clientCrop: 'apple', clientConfidence: 0.4);
      expect(api.uploadedPhotoPaths.single, ['/a.jpg', '/b.jpg']);
      expect(api.lastClientGuess!.crop, 'apple');
    });

    test('every supported crop has a prompt, a Hindi and an English name', () {
      for (final crop in MockData.supportedCrops) {
        expect(catalogue.contains('crop_is_$crop'), isTrue);
        expect(MockData.cropName(crop).en, isNotEmpty);
      }
    });
  });

  group('network behaviour for demos and tests', () {
    test('latency delays every call; zero latency does not wait', () async {
      final api = MockApiClient(latency: const Duration(milliseconds: 60));
      final started = DateTime.now();
      await api.meta();
      expect(DateTime.now().difference(started).inMilliseconds, greaterThanOrEqualTo(50));
    });

    test('failWith fails every call, or only some, or only a number of times', () async {
      final api = mock();
      api.failWith(const ApiException.network());
      expect(api.meta(), throwsA(isA<ApiException>()));
      expect(api.field(), throwsA(isA<ApiException>()));
      api.clearFailure();
      await api.meta();

      api.failWith(const ApiException.timeout(), times: 2, ops: {'field'});
      await api.meta(); // other calls are fine
      await expectLater(api.field(), throwsA(isA<ApiException>()));
      await expectLater(api.field(), throwsA(isA<ApiException>()));
      expect((await api.field()).village, 'Kotgarh');
    });

    test('an upload can be cancelled while it "travels"', () async {
      final api = MockApiClient(latency: const Duration(milliseconds: 200), scanScript: [MockScanScenario.ok]);
      final cancel = CancelHandle();
      final call = api.createScan(photoPaths: const ['/a.jpg'], cancel: cancel);
      final result = expectLater(call, throwsA(predicate<ApiException>((e) => e.isCancelled)));
      await Future<void>.delayed(const Duration(milliseconds: 20));
      cancel.cancel();
      await result;
      expect(api.scans, isEmpty);
    });

    test('upload progress is reported up to 100 percent', () async {
      final progress = <double>[];
      await mock().createScan(photoPaths: const ['/a.jpg'], onProgress: (sent, total) => progress.add(sent / total));
      expect(progress.last, 1.0);
      expect(progress, orderedEquals([...progress]..sort()));
    });

    test('requireAuth makes the mock answer 401 until the farmer logged in', () async {
      final api = MockApiClient(latency: Duration.zero, requireAuth: true);
      final e = await api.me().then<ApiException?>((_) => null, onError: (Object e) => e as ApiException);
      expect(e!.kind, ApiErrorKind.unauthorized);
      await api.login(username: 'f001', password: 'farm1234');
      expect((await api.me()).id, 'F001');
    });
  });
}
