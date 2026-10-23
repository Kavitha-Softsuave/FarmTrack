import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:farmtrack/core/config/app_config.dart';
import 'package:farmtrack/core/connectivity/connectivity_service.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/core/settings/app_settings.dart';
import 'package:farmtrack/core/storage/token_store.dart';
import 'package:farmtrack/core/utils/haptics.dart';
import 'package:farmtrack/core/vision/on_device_detector.dart';
import 'package:farmtrack/core/widgets/status_views.dart';

import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  group('routes', () {
    test('final names for the screens MOBILE2 completes', () {
      expect(Routes.diary, '/diary');
      expect(Routes.field, '/field');
      expect(Routes.alerts, '/alerts');
      expect(Routes.ask, '/ask');
      expect(Routes.settings, '/settings');
    });

    test('diary links carry the preselected advice, crop and product; empty ones carry nothing', () {
      expect(
        Routes.diaryFor(adviceId: 'a1', cropId: 'apple', productId: 'P007'),
        '/diary?advice=a1&crop=apple&product=P007',
      );
      expect(Routes.diaryFor(), '/diary');
      expect(Routes.analysingFor('apple'), '/scan/analysing?crop=apple');
    });
  });

  group('token store', () {
    test('in-memory fake keeps, replaces and clears the tokens', () async {
      final store = InMemoryTokenStore();
      expect(await store.read(), isNull);
      await store.write(const StoredTokens(accessToken: 'a', refreshToken: 'r'));
      expect((await store.read())!.refreshToken, 'r');
      await store.write(const StoredTokens(accessToken: 'a2', refreshToken: 'r2'));
      expect((await store.read())!.accessToken, 'a2');
      await store.clear();
      expect(await store.read(), isNull);
    });
  });

  group('settings store', () {
    test('defaults, round trip and a damaged value', () async {
      SharedPreferences.setMockInitialValues({'speech_speed': 'warp', 'volume': 'low'});
      final store = SettingsStore(await SharedPreferences.getInstance());
      final loaded = store.load();
      expect(loaded.language, isNull);
      expect(loaded.speed, SpeechSpeed.normal, reason: 'unknown value falls back');
      expect(loaded.volume, VolumeLevel.low);
      expect(loaded.captions, isTrue, reason: 'captions are on by default');
      expect(loaded.onboardingDone, isFalse);

      await store.save(loaded.copyWith(language: 'en', speed: SpeechSpeed.fast, captions: false, onboardingDone: true));
      final again = store.load();
      expect(again.language, 'en');
      expect(again.speed, SpeechSpeed.fast);
      expect(again.captions, isFalse);
      expect(again.onboardingDone, isTrue);
    });

    test('speed and volume levels are ordered and in range', () {
      expect(SpeechSpeed.values.map((s) => s.ttsRate).toList(), [0.35, 0.5, 0.65]);
      expect(SpeechSpeed.values.map((s) => s.audioSpeed).toList(), [0.85, 1.0, 1.15]);
      expect(VolumeLevel.values.map((v) => v.value).every((v) => v > 0 && v <= 1), isTrue);
    });
  });

  group('app config', () {
    test('test config uses the mock API with no delay', () {
      const config = AppConfig.test();
      expect(config.useMockApi, isTrue);
      expect(config.mockLatency, Duration.zero);
      expect(config.maxPhotos, 4);
    });

    test('the mock API is the default under flutter test', () {
      expect(AppConfig.fromEnvironment().useMockApi, isTrue);
      expect(AppConfig.fromEnvironment().apiBaseUrl, 'http://10.0.2.2:8000');
    });
  });

  group('resources', () {
    test('languages, interface words and crop names come from data files', () {
      final r = loadResources();
      expect(r.languages.map((l) => l.code), ['hi', 'en']);
      expect(r.language('hi').nativeName, 'हिन्दी');
      expect(r.language('en').ttsLocales.first, 'en-IN');
      expect(r.language('hi').promptId, 'language_hindi');
      expect(r.t('a11y_yes', 'hi'), 'हाँ');
      expect(r.t('advice_wait_days', 'en', args: {'n': 14}), 'Wait 14 days before harvest');
      expect(r.t('no_such_key', 'en'), 'no_such_key');
      expect(r.cropName('apple', 'hi'), 'सेब');
      expect(
        r.cropName(
          'apple',
          'en',
          serverName: LocalizedText.pair(en: 'Apples', hi: 'x'),
        ),
        'Apples',
      );
      expect(r.cropName('olive', 'en'), 'Olive');
      expect(r.cropGroup('wheat'), 'cereal');
      expect(r.cropIds, containsAll(MockData.supportedCrops));
    });

    test('every interface word exists in every language', () {
      final strings = jsonDecode(File('assets/l10n/strings.json').readAsStringSync()) as Map<String, dynamic>;
      for (final section in ['ui', 'crops']) {
        for (final entry in (strings[section] as Map<String, dynamic>).entries) {
          final value = entry.value as Map<String, dynamic>;
          expect((value['en'] as String).trim(), isNotEmpty, reason: '$section.${entry.key} en');
          expect((value['hi'] as String).trim(), isNotEmpty, reason: '$section.${entry.key} hi');
        }
      }
    });
  });

  group('on-device detector', () {
    test('the stub has no model and returns nothing, so nothing is sent as client_crop', () async {
      expect(await const StubOnDeviceDetector().detect('/tmp/leaf.jpg'), isNull);
    });
  });

  group('connectivity', () {
    test('the fake reports changes', () async {
      final fake = FakeConnectivity();
      final changes = <bool>[];
      final sub = fake.onlineChanges.listen(changes.add);
      expect(await fake.isOnline(), isTrue);
      fake.online = false;
      fake.online = false; // no duplicate event
      fake.online = true;
      await Future<void>.delayed(Duration.zero);
      expect(changes, [false, true]);
      await sub.cancel();
    });
  });

  group('session', () {
    test('restore reads tokens and the saved profile at once, then refreshes the profile', () async {
      final env = await TestEnv.create(loggedIn: true);
      await env.prefs.setString('farmer_json', jsonEncode(MockData.farmer().toJson()));
      final container = ProviderContainer(overrides: env.overrides);
      addTearDown(container.dispose);
      await container.read(sessionProvider.notifier).restore();
      expect(container.read(sessionProvider).isLoggedIn, isTrue);
      expect(
        container.read(sessionProvider).farmer!.name,
        'Ramesh Kumar',
        reason: 'from the saved profile, before any network call',
      );
      await container.read(sessionProvider.notifier).refreshProfile();
      expect(env.api.calls, contains('me'));
    });

    test('no tokens: logged out', () async {
      final env = await TestEnv.create();
      final container = ProviderContainer(overrides: env.overrides);
      addTearDown(container.dispose);
      await container.read(sessionProvider.notifier).restore();
      expect(container.read(sessionProvider).status, SessionStatus.loggedOut);
    });

    test('syncLanguage tells the server only when the language differs', () async {
      final env = await TestEnv.create();
      final container = ProviderContainer(overrides: env.overrides);
      addTearDown(container.dispose);
      final session = container.read(sessionProvider.notifier);
      await session.login(MockData.tokens(1));
      await session.syncLanguage('hi');
      expect(env.api.calls, isNot(contains('patchMe')));
      await session.syncLanguage('en');
      expect(env.api.calls, contains('patchMe'));
      expect(container.read(sessionProvider).farmer!.language, 'en');
    });

    test('supported crops come from the server, or from the app\'s own table when offline', () async {
      final env = await TestEnv.create(loggedIn: true);
      final container = ProviderContainer(overrides: env.overrides);
      addTearDown(container.dispose);
      expect(await container.read(supportedCropsProvider.future), contains('apple'));

      final offline = ProviderContainer(overrides: env.overrides);
      addTearDown(offline.dispose);
      env.api.failWith(const ApiException.network());
      expect(await offline.read(supportedCropsProvider.future), containsAll(['apple', 'wheat']));
    });

    test('unreadAlertsProvider counts unread alerts, and is zero when logged out or offline', () async {
      final env = await TestEnv.create();
      final container = ProviderContainer(overrides: env.overrides);
      addTearDown(container.dispose);
      expect(await container.read(unreadAlertsProvider.future), 0);
      await container.read(sessionProvider.notifier).login(MockData.tokens(1));
      expect(await container.read(unreadAlertsProvider.future), 1);
    });
  });

  group('error screen', () {
    testWidgets('no internet: speaks error_no_internet, one big retry button', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create();
      var retried = 0;
      await tester.pumpWidget(
        env.wrap(ErrorRetryScreen(error: const ApiException.network(), onRetry: () => retried++)),
      );
      await tester.pump();
      expect(env.voice.spokenIds, ['error_no_internet']);
      expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
      expect(tester.getSize(keyed('retry-button')).width, greaterThanOrEqualTo(96));
      await tester.tap(keyed('retry-button'));
      expect(retried, 1);
      expectBigTouchTargets(tester);
    });

    testWidgets('anything else: speaks error_try_again', (tester) async {
      final env = await TestEnv.create();
      await tester.pumpWidget(env.wrap(ErrorRetryScreen(error: StateError('x'), onRetry: () {})));
      await tester.pump();
      expect(env.voice.spokenIds, ['error_try_again']);
      expect(errorPromptFor(const ApiException.timeout()), 'error_no_internet');
      expect(errorPromptFor(const ApiException(kind: ApiErrorKind.server, code: 'x')), 'error_try_again');
    });
  });

  test('haptics never throw, even without a vibration motor or platform channel', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    Haptics.success();
    Haptics.error();
    Haptics.tap();
  });

  test('ApiException.fromResponse picks the kind from the status code', () {
    expect(ApiException.fromResponse(401, null).kind, ApiErrorKind.unauthorized);
    expect(ApiException.fromResponse(404, {'code': 'not_found', 'message': 'x'}).code, 'not_found');
    expect(ApiException.fromResponse(503, 'plain').code, 'http_503');
    expect(const ApiException.cancelled().isCancelled, isTrue);
    expect(MockApiClient(latency: Duration.zero).baseUrl, startsWith('http'));
  });
}
