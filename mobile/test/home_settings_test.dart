import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/core/settings/app_settings.dart';

import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  group('home', () {
    testWidgets(
      'four big picture buttons, a gear and a bell; every target is at least 64 dp, the picture buttons much larger',
      (tester) async {
        useSmallPhone(tester);
        final env = await TestEnv.create(loggedIn: true);
        await pumpApp(tester, env);
        for (final key in ['home-scan', 'home-field', 'home-diary', 'home-ask']) {
          final size = tester.getSize(keyed(key));
          expect(size.width, greaterThanOrEqualTo(96), reason: key);
          expect(size.height, greaterThanOrEqualTo(96), reason: key);
        }
        expect(find.byIcon(Icons.photo_camera_rounded), findsOneWidget);
        expect(find.byIcon(Icons.cloud_rounded), findsOneWidget);
        expect(find.byIcon(Icons.edit_note_rounded), findsOneWidget);
        expect(find.byIcon(Icons.live_help_rounded), findsOneWidget);
        expect(find.byIcon(Icons.settings_rounded), findsOneWidget);
        expect(find.byIcon(Icons.notifications_rounded), findsOneWidget);
        expectBigTouchTargets(tester);
      },
    );

    testWidgets(
      'first visit: speaks the intro and then each button; later visits only the intro; the speaker replays everything',
      (tester) async {
        final env = await TestEnv.create(loggedIn: true, homeTourDone: false);
        final container = await pumpApp(tester, env);
        expect(env.voice.spokenIds, [
          'home_intro',
          'home_scan',
          'home_field',
          'home_diary',
          'home_ask',
          'home_settings',
        ]);
        expect(container.read(settingsProvider).homeTourDone, isTrue);

        env.voice.clear();
        await tester.tap(keyed('speaker-button'));
        await tester.pump();
        expect(env.voice.spokenIds, hasLength(6), reason: 'the speaker button replays the whole tour');

        // A second visit (new Home screen): only the short intro.
        env.voice.clear();
        await tester.pumpWidget(const SizedBox());
        await tester.pumpWidget(env.app(location: '/home'));
        await tester.pumpAndSettle();
        expect(env.voice.spokenIds, ['home_intro']);
      },
    );

    testWidgets('each button opens its screen, which speaks its own introduction', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(loggedIn: true);
      await pumpApp(tester, env);
      final expected = {
        'home-field': 'field_intro',
        'home-diary': 'diary_intro',
        'home-ask': 'ask_intro',
        'home-alerts': 'alert_open',
        'home-settings': 'settings_speed',
      };
      for (final entry in expected.entries) {
        env.voice.clear();
        await tapKey(tester, entry.key);
        expect(env.voice.spokenIds.first, entry.value, reason: entry.key);
        await tester.tap(find.byIcon(Icons.arrow_back_rounded));
        await tester.pumpAndSettle();
        expect(keyed('home-scan'), findsOneWidget);
      }
    });

    testWidgets('the bell shows how many alerts are unread; the offline sign shows with no network', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(loggedIn: true);
      await pumpApp(tester, env);
      expect(find.descendant(of: keyed('alert-badge'), matching: find.text('1')), findsOneWidget);
      expect(find.byIcon(Icons.cloud_off_rounded), findsNothing);
      env.connectivity.online = false;
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
    });
  });

  group('settings', () {
    Future<TestEnv> openSettings(WidgetTester tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(loggedIn: true);
      await pumpApp(tester, env, location: Routes.home);
      await tapKey(tester, 'home-settings');
      env.voice.clear();
      return env;
    }

    testWidgets('speaks about speed and volume; every control is a big picture', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(loggedIn: true);
      await pumpApp(tester, env, location: Routes.home);
      env.voice.clear();
      await tapKey(tester, 'home-settings');
      expect(env.voice.spokenIds, ['settings_speed', 'settings_volume']);
      expectBigTouchTargets(tester);
    });

    testWidgets('speed: the choice is applied, saved and demonstrated by speaking', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'speed-slow');
      expect(containerOf(tester).read(settingsProvider).speed, SpeechSpeed.slow);
      expect(env.prefs.getString('speech_speed'), 'slow');
      expect(env.voice.spokenIds, ['settings_speed']);
      await tapKey(tester, 'speed-fast');
      expect(containerOf(tester).read(settingsProvider).speed, SpeechSpeed.fast);
    });

    testWidgets('volume: the choice is applied, saved and demonstrated by speaking', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'volume-low');
      expect(containerOf(tester).read(settingsProvider).volume, VolumeLevel.low);
      expect(env.prefs.getString('volume'), 'low');
      expect(env.voice.spokenIds, ['settings_volume']);
    });

    testWidgets('language: switching to English changes the words, tells the server and confirms in English', (
      tester,
    ) async {
      final env = await openSettings(tester);
      expect(find.text('भाषा'), findsOneWidget);
      await tapKey(tester, 'language-en');
      expect(containerOf(tester).read(languageProvider), 'en');
      expect(env.prefs.getString('language'), 'en');
      expect(env.voice.log.last, 'settings_language_changed@en');
      expect(find.text('Language'), findsOneWidget);
      expect(env.api.calls, contains('patchMe'));
      expect((await env.api.me()).language, 'en');
    });

    testWidgets('captions can be switched off and on; the choice is saved', (tester) async {
      final env = await openSettings(tester);
      expect(keyed('voice-caption'), findsOneWidget);
      await tapKey(tester, 'captions-off');
      expect(containerOf(tester).read(settingsProvider).captions, isFalse);
      expect(env.prefs.getBool('captions'), isFalse);
      expect(keyed('voice-caption'), findsNothing);
      await tapKey(tester, 'captions-on');
      expect(env.prefs.getBool('captions'), isTrue);
    });

    testWidgets('log out asks for a tick or a cross; the tick clears the login and returns to the login screen', (
      tester,
    ) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'log-out');
      expect(env.voice.spokenIds, ['settings_logout_confirm']);
      expect(await env.tokens.read(), isNotNull, reason: 'nothing happens before the farmer confirms');
      await tapKey(tester, 'logout-yes');
      expect(keyed('login-username'), findsOneWidget);
      expect(await env.tokens.read(), isNull);
      expect(containerOf(tester).read(sessionProvider).isLoggedIn, isFalse);
      expect(env.api.calls, contains('logout'), reason: 'the server is told so it can revoke the refresh token');
    });

    testWidgets('settings survive a restart', (tester) async {
      final env = await openSettings(tester);
      await tapKey(tester, 'speed-slow');
      await tapKey(tester, 'volume-medium');
      await tapKey(tester, 'captions-off');
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(env.app(location: Routes.settings));
      await tester.pumpAndSettle();
      final settings = containerOf(tester).read(settingsProvider);
      expect(settings.speed, SpeechSpeed.slow);
      expect(settings.volume, VolumeLevel.medium);
      expect(settings.captions, isFalse);
      expect(settings.language, 'hi');
    });
  });

  group('session', () {
    testWidgets('when the server rejects the refresh token the farmer is sent to the login screen', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(loggedIn: true);
      final container = await pumpApp(tester, env);
      expect(keyed('home-scan'), findsOneWidget);
      container.read(sessionProvider.notifier).expire();
      await tester.pumpAndSettle();
      expect(keyed('login-username'), findsOneWidget);
    });

    testWidgets('logged-out farmers cannot open private screens by route', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await pumpApp(tester, env, location: Routes.scan);
      expect(keyed('login-username'), findsOneWidget);
      expect(keyed('camera-button'), findsNothing);
    });
  });
}
