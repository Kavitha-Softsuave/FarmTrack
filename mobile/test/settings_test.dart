import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/config/app_version.dart';
import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/core/settings/app_settings.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/features/settings/settings_screen.dart';

import 'support/fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  Future<TestEnv> openSettings(WidgetTester tester, {String? language = 'hi', List<Override> extra = const []}) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(language: language, loggedIn: true, extraOverrides: extra);
    await pumpApp(tester, env, location: Routes.home);
    await tapKey(tester, 'home-settings');
    env.voice.clear();
    return env;
  }

  group('language', () {
    testWidgets('two big buttons; each says its own language name in that language, then the change is confirmed', (
      tester,
    ) async {
      final env = await openSettings(tester);
      expect(keyed('language-hi'), findsOneWidget);
      expect(keyed('language-en'), findsOneWidget);
      expect(tester.getSize(keyed('language-en')).height, greaterThanOrEqualTo(80));
      expect(find.text('हिन्दी'), findsOneWidget);
      expect(find.text('English'), findsOneWidget);

      await tapKey(tester, 'language-en');
      expect(env.voice.log, ['language_english@en', 'settings_language_changed@en']);
      expect(containerOf(tester).read(languageProvider), 'en');
      expect(env.prefs.getString('language'), 'en');
      expect(find.text('Language'), findsOneWidget, reason: 'the words of the screen follow at once');

      env.voice.clear();
      await tapKey(tester, 'language-hi');
      expect(env.voice.log, ['language_hindi@hi', 'settings_language_changed@hi']);
      expect(find.text('भाषा'), findsOneWidget);
    });

    testWidgets('the server is told with PATCH /v1/me, like the first language screen', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'language-en');
      expect(env.api.calls, contains('patchMe'));
      expect((await env.api.me()).language, 'en');
    });

    testWidgets('a failed PATCH does not break the change (offline): the app still switches language', (tester) async {
      final env = await openSettings(tester);
      env.api.failWith(const ApiException.network(), ops: {'patchMe'});
      await tapKey(tester, 'language-en');
      expect(containerOf(tester).read(languageProvider), 'en');
      expect(env.voice.log.last, 'settings_language_changed@en');
    });
  });

  group('speech speed', () {
    testWidgets('slow and normal (and fast) are big pictures; the choice is saved and demonstrated by speaking', (
      tester,
    ) async {
      final env = await openSettings(tester);
      expect(containerOf(tester).read(settingsProvider).speed, SpeechSpeed.normal, reason: 'normal is the default');
      for (final key in ['speed-slow', 'speed-normal']) {
        expect(tester.getSize(keyed(key)).width, greaterThanOrEqualTo(64), reason: key);
      }
      await tapKey(tester, 'speed-slow');
      expect(containerOf(tester).read(settingsProvider).speed, SpeechSpeed.slow);
      expect(env.prefs.getString('speech_speed'), 'slow');
      expect(env.voice.spokenIds, ['settings_speed']);
      await tapKey(tester, 'speed-normal');
      expect(containerOf(tester).read(settingsProvider).speed, SpeechSpeed.normal);
      expect(env.prefs.getString('speech_speed'), 'normal');
    });

    testWidgets('the speed buttons have the same names for a screen reader (Semantics)', (tester) async {
      final handle = tester.ensureSemantics();
      await openSettings(tester);
      expect(find.bySemanticsLabel('धीमा'), findsOneWidget);
      expect(find.bySemanticsLabel('सामान्य'), findsOneWidget);
      expect(find.bySemanticsLabel('तेज़'), findsOneWidget);
      handle.dispose();
    });

    test(
      'the default is normal, and slow is applied to the phone voice rate and to the playback speed of audio',
      () async {
        expect(const AppSettings().speed, SpeechSpeed.normal);
        expect(SpeechSpeed.slow.ttsRate, lessThan(SpeechSpeed.normal.ttsRate));
        expect(SpeechSpeed.slow.audioSpeed, lessThan(SpeechSpeed.normal.audioSpeed));
        expect(SpeechSpeed.normal.audioSpeed, 1.0);

        // The real voice service reads the setting at the moment it speaks (FakeTts / FakeAudio record what they got).
        final env = await TestEnv.create(loggedIn: true);
        final log = SoundLog();
        final tts = FakeTts(log);
        final audio = FakeAudio(log);
        final container = ProviderContainer(
          overrides: [
            resourcesProvider.overrideWithValue(env.resources),
            promptCatalogueProvider.overrideWithValue(env.catalogue),
            sharedPreferencesProvider.overrideWithValue(env.prefs),
            supportDirectoryProvider.overrideWithValue(env.supportDir),
            apiClientProvider.overrideWithValue(env.api),
            ttsPortProvider.overrideWithValue(tts),
            audioPortProvider.overrideWithValue(audio),
          ],
        );
        addTearDown(container.dispose);
        final voice = container.read(voiceServiceProvider);

        await voice.speak(const [PromptUtterance('home_intro')]);
        expect(tts.spoken.last.rate, SpeechSpeed.normal.ttsRate, reason: 'nothing chosen: normal');

        await container.read(settingsProvider.notifier).setSpeed(SpeechSpeed.slow);
        await voice.speak(const [PromptUtterance('home_intro')]);
        expect(tts.spoken.last.rate, SpeechSpeed.slow.ttsRate);

        // The same setting survives a restart (new container, same preferences).
        final again = ProviderContainer(overrides: [sharedPreferencesProvider.overrideWithValue(env.prefs)]);
        addTearDown(again.dispose);
        expect(again.read(settingsProvider).speed, SpeechSpeed.slow);
      },
    );
  });

  group('written words', () {
    testWidgets('the "show written words" switch exists and keeps working', (tester) async {
      final env = await openSettings(tester);
      expect(find.text('लिखे शब्द दिखाएँ'), findsOneWidget);
      await tapKey(tester, 'captions-off');
      expect(containerOf(tester).read(settingsProvider).captions, isFalse);
      expect(env.prefs.getBool('captions'), isFalse);
      await tapKey(tester, 'captions-on');
      expect(containerOf(tester).read(settingsProvider).captions, isTrue);
    });
  });

  group('log out', () {
    testWidgets('asks first: the red cross keeps the farmer logged in', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'log-out');
      expect(env.voice.spokenIds, ['settings_logout_confirm']);
      expect(keyed('logout-yes'), findsOneWidget);
      expect(keyed('logout-no'), findsOneWidget);
      expect(tester.getSize(keyed('logout-yes')).width, greaterThanOrEqualTo(96));
      expect(find.text('फार्मट्रैक से बाहर निकलें?'), findsOneWidget);
      expectBigTouchTargets(tester);

      await tapKey(tester, 'logout-no');
      expect(keyed('log-out'), findsOneWidget, reason: 'back on the settings screen');
      expect(await env.tokens.read(), isNotNull);
      expect(containerOf(tester).read(sessionProvider).isLoggedIn, isTrue);
    });

    testWidgets('the back arrow of the question also means "no"', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'log-out');
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('log-out'), findsOneWidget);
      expect(await env.tokens.read(), isNotNull);
    });

    testWidgets('the green tick logs out: tokens gone at once, the server told, the login screen is shown', (
      tester,
    ) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'log-out');
      await tapKey(tester, 'logout-yes');
      expect(keyed('login-username'), findsOneWidget);
      expect(await env.tokens.read(), isNull);
      expect(containerOf(tester).read(sessionProvider).isLoggedIn, isFalse);
      expect(env.api.calls, contains('logout'));
    });

    testWidgets('the cross and the tick can be heard by a screen reader', (tester) async {
      final handle = tester.ensureSemantics();
      await openSettings(tester);
      await tapKey(tester, 'log-out');
      expect(find.bySemanticsLabel('हाँ'), findsOneWidget);
      expect(find.bySemanticsLabel('नहीं'), findsOneWidget);
      handle.dispose();
    });
  });

  group('about', () {
    test('the version constant is the version of pubspec.yaml', () {
      final line = File('pubspec.yaml').readAsLinesSync().firstWhere((l) => l.startsWith('version:'));
      expect(line.split(':').last.trim().split('+').first, kAppVersion);
    });

    testWidgets('shows the app name and version; the server address only in debug builds', (tester) async {
      await openSettings(tester);
      await tester.ensureVisible(keyed('settings-about'));
      expect(find.text('फार्मट्रैक, संस्करण $kAppVersion'), findsOneWidget);
      expect(keyed('settings-server'), findsOneWidget, reason: 'flutter test is a debug build');
      expect(find.text('सर्वर: http://test.invalid'), findsOneWidget);
    });

    testWidgets('a release build does not show the server address', (tester) async {
      await openSettings(tester, language: 'en', extra: [showServerUrlProvider.overrideWithValue(false)]);
      await tester.ensureVisible(keyed('settings-about'));
      expect(find.text('FarmTrack, version $kAppVersion'), findsOneWidget);
      expect(keyed('settings-server'), findsNothing);
      expect(find.textContaining('http'), findsNothing);
    });
  });

  testWidgets('the screen speaks the speed and volume prompts when it opens', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true);
    await pumpApp(tester, env, location: Routes.home);
    env.voice.clear();
    final container = containerOf(tester);
    unawaited(container.read(routerProvider).push<void>(Routes.settings));
    await tester.pumpAndSettle();
    expect(env.voice.spokenIds, ['settings_speed', 'settings_volume']);
  });
}
