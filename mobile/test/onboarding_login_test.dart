import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/theme/app_theme.dart';

import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  const loginScript = ['login_intro', 'login_ask_username', 'login_ask_password', 'login_tap_tick'];

  group('splash decides where to go', () {
    testWidgets('first launch: language chooser', (tester) async {
      final env = await TestEnv.create(language: null);
      await pumpApp(tester, env);
      expect(keyed('language-hi'), findsOneWidget);
      expect(keyed('language-en'), findsOneWidget);
    });

    testWidgets('language chosen, onboarding not finished: welcome', (tester) async {
      final env = await TestEnv.create();
      await pumpApp(tester, env);
      expect(keyed('welcome-continue'), findsOneWidget);
    });

    testWidgets('onboarding finished, not logged in: the login screen speaks its four sentences', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await pumpApp(tester, env);
      expect(keyed('login-username'), findsOneWidget);
      expect(keyed('login-password'), findsOneWidget);
      expect(env.voice.spokenIds, loginScript);
    });

    testWidgets('logged in: home, even when the server cannot be reached', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.api.failWith(const ApiException.network());
      await pumpApp(tester, env);
      expect(keyed('home-scan'), findsOneWidget);
      expect(containerOf(tester).read(sessionProvider).isLoggedIn, isTrue);
    });

    testWidgets('logged out farmers cannot open any other screen: the app always asks for the login', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      final container = await pumpApp(tester, env);
      for (final route in ['/home', '/scan', '/settings', '/diary', '/ask']) {
        container.read(routerProvider).go(route);
        await tester.pumpAndSettle();
        expect(keyed('login-submit'), findsOneWidget, reason: route);
      }
    });

    testWidgets('logged out without a language: the language chooser first', (tester) async {
      final env = await TestEnv.create(language: null);
      final container = await pumpApp(tester, env);
      container.read(routerProvider).go('/home');
      await tester.pumpAndSettle();
      expect(keyed('language-hi'), findsOneWidget);
    });
  });

  group('language chooser', () {
    testWidgets('speaks the request in Hindi, then in English, and labels each button in its own script', (
      tester,
    ) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(language: null);
      await pumpApp(tester, env);
      expect(env.voice.log, ['choose_language@hi', 'choose_language@en']);
      expect(find.text('हिन्दी'), findsOneWidget);
      expect(find.text('English'), findsOneWidget);
      expectBigTouchTargets(tester);
    });

    testWidgets('tapping Hindi plays its own prompt in the Hindi voice, saves the choice and welcomes in Hindi', (
      tester,
    ) async {
      final env = await TestEnv.create(language: null);
      final container = await pumpApp(tester, env);
      env.voice.clear();
      await tapKey(tester, 'language-hi');
      expect(env.voice.log, ['language_hindi@hi', 'welcome@hi', 'tap_green_tick@hi']);
      expect(container.read(languageProvider), 'hi');
      expect(env.prefs.getString('language'), 'hi');
    });

    testWidgets('tapping English plays "English." in the English voice and welcomes in English', (tester) async {
      final env = await TestEnv.create(language: null);
      final container = await pumpApp(tester, env);
      env.voice.clear();
      await tapKey(tester, 'language-en');
      expect(env.voice.log, ['language_english@en', 'welcome@en', 'tap_green_tick@en']);
      expect(container.read(languageProvider), 'en');
      expect(find.textContaining('Now tap the green tick'), findsOneWidget, reason: 'the caption follows the speech');
    });

    testWidgets('welcome: the green tick finishes onboarding and opens the login screen', (tester) async {
      final env = await TestEnv.create();
      final container = await pumpApp(tester, env);
      expect(env.voice.spokenIds, ['welcome', 'tap_green_tick']);
      await tapKey(tester, 'welcome-continue');
      expect(container.read(settingsProvider).onboardingDone, isTrue);
      expect(keyed('login-username'), findsOneWidget);
      expect(env.voice.spokenIds.sublist(env.voice.spokenIds.length - 4), loginScript);
    });
  });

  group('login with the mock API', () {
    Future<ProviderContainer> openLogin(WidgetTester tester, TestEnv env) async {
      useSmallPhone(tester);
      final container = await pumpApp(tester, env);
      env.voice.clear();
      return container;
    }

    EditableText editable(WidgetTester tester, String key) =>
        tester.widget<EditableText>(find.descendant(of: keyed(key), matching: find.byType(EditableText)));

    testWidgets('success: lands on home with the welcome and the first-visit tour, and keeps only the user name', (
      tester,
    ) async {
      final env = await TestEnv.create(onboardingDone: true, homeTourDone: false);
      final container = await openLogin(tester, env);
      await logInWith(tester, username: 'f001', password: 'farm1234');
      expect(keyed('home-scan'), findsOneWidget);
      expect(env.voice.spokenIds, [
        'login_ok',
        'home_intro',
        'home_scan',
        'home_field',
        'home_diary',
        'home_ask',
        'home_settings',
      ]);
      expect(container.read(sessionProvider).isLoggedIn, isTrue);
      expect(container.read(sessionProvider).farmer!.name, 'Ramesh Kumar');
      final stored = await env.tokens.read();
      expect(stored!.accessToken, startsWith('mock-access'));
      expect(env.prefs.getString('farmer_json'), contains('Ramesh'));
      expect(env.prefs.getString('last_username'), 'f001');
      for (final key in env.prefs.getKeys()) {
        expect('${env.prefs.get(key)}', isNot(contains('farm1234')), reason: 'the password is never stored ($key)');
      }
    });

    testWidgets('the user name is trimmed and lower-cased before it is sent; the language is synced', (tester) async {
      final env = await TestEnv.create(onboardingDone: true, language: 'en');
      final container = await openLogin(tester, env);
      await logInWith(tester, username: '  F007 ', password: 'farm1234');
      expect(env.api.loginCalls.single.username, 'f007');
      expect(env.api.calls, contains('patchMe'), reason: 'the mock farmer speaks Hindi, the app English');
      expect(container.read(sessionProvider).farmer!.language, 'en');
      expect(env.prefs.getString('last_username'), 'f007');
    });

    testWidgets('the per-install device id is sent and stays the same', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      final container = await openLogin(tester, env);
      await logInWith(tester);
      final id = env.api.loginCalls.single.deviceId;
      expect(id, isNotNull);
      expect(id!.length, greaterThanOrEqualTo(8));
      expect(id, container.read(deviceIdProvider));
      expect(env.prefs.getString('device_id'), id);
    });

    testWidgets('a wrong password speaks login_wrong, keeps what was typed and allows another try', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await logInWith(tester, username: 'f001', password: 'wrong-password');
      expect(env.voice.spokenIds, ['login_wrong']);
      expect(env.api.calls, contains('login'));
      expect(keyed('login-submit'), findsOneWidget);
      expect(find.text('f001'), findsOneWidget);
      expect(editable(tester, 'login-password').obscureText, isTrue, reason: 'the password stays hidden');
      expect(await env.tokens.read(), isNull);
      expect(env.prefs.getString('last_username'), isNull, reason: 'only a successful login is remembered');

      env.voice.clear();
      await enterLogin(tester, password: 'farm1234');
      await tapKey(tester, 'login-submit');
      expect(keyed('home-scan'), findsOneWidget);
      expect(env.voice.spokenIds.first, 'login_ok');
    });

    testWidgets('an unknown user name speaks login_wrong too', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await logInWith(tester, username: 'nobody', password: 'farm1234');
      expect(env.voice.spokenIds, ['login_wrong']);
    });

    testWidgets('empty fields speak login_fields_needed and send nothing', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await tapKey(tester, 'login-submit');
      expect(env.voice.spokenIds, ['login_fields_needed']);
      for (final (user, password) in [('f001', ''), ('', 'farm1234'), ('   ', 'farm1234')]) {
        env.voice.clear();
        await enterLogin(tester, username: user, password: password);
        await tapKey(tester, 'login-submit');
        expect(env.voice.spokenIds, ['login_fields_needed'], reason: "'$user' / '$password'");
      }
      expect(env.api.calls, isNot(contains('login')));
    });

    testWidgets('a pair that cannot exist (too short, odd letters) is "not right" without asking the server', (
      tester,
    ) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await logInWith(tester, username: 'f001', password: 'abc');
      expect(env.voice.spokenIds, ['login_wrong']);
      env.voice.clear();
      await logInWith(tester, username: 'f 001', password: 'farm1234');
      expect(env.voice.spokenIds, ['login_wrong']);
      expect(env.api.calls, isNot(contains('login')));
    });

    testWidgets('a server validation error (422) is also "not right"', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      env.api.failWith(
        const ApiException(kind: ApiErrorKind.validation, code: 'validation_error', statusCode: 422),
        ops: {'login'},
      );
      await logInWith(tester);
      expect(env.voice.spokenIds, ['login_wrong']);
    });

    testWidgets('no internet: speaks error_no_internet, stays on the login screen, and works once online', (
      tester,
    ) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      env.api.failWith(const ApiException.network());
      await logInWith(tester);
      expect(env.voice.spokenIds, ['error_no_internet']);
      expect(keyed('login-submit'), findsOneWidget);
      expect(find.text('f001'), findsOneWidget);
      env.api.clearFailure();
      await tapKey(tester, 'login-submit');
      expect(keyed('home-scan'), findsOneWidget);
    });

    testWidgets('too many tries (429 rate_limited): speaks error_try_again', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      env.api.failWith(
        const ApiException(
          kind: ApiErrorKind.rateLimited,
          code: 'rate_limited',
          statusCode: 429,
          details: {'retry_after_seconds': 60},
        ),
      );
      await logInWith(tester);
      expect(env.voice.spokenIds, ['error_try_again']);
      expect(keyed('login-submit'), findsOneWidget);
    });

    testWidgets('a server error speaks error_try_again', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      env.api.failWith(const ApiException(kind: ApiErrorKind.server, code: 'internal_error', statusCode: 500));
      await logInWith(tester);
      expect(env.voice.spokenIds, ['error_try_again']);
    });

    testWidgets('the eye shows and hides the password and says so', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await enterLogin(tester, password: 'farm1234');
      expect(editable(tester, 'login-password').obscureText, isTrue);

      await tapKey(tester, 'login-eye');
      expect(editable(tester, 'login-password').obscureText, isFalse);
      expect(find.text('farm1234'), findsOneWidget);
      expect(find.byIcon(AppIcons.eyeOff), findsOneWidget);
      expect(env.voice.spokenIds, ['login_show_password']);

      await tapKey(tester, 'login-eye');
      expect(editable(tester, 'login-password').obscureText, isTrue);
      expect(find.byIcon(AppIcons.eye), findsOneWidget);
      expect(env.voice.spokenIds, ['login_show_password', 'login_hide_password']);
    });

    testWidgets('the last user name is prefilled (the password field gets the focus), the password never is', (
      tester,
    ) async {
      final env = await TestEnv.create(onboardingDone: true);
      await env.prefs.setString('last_username', 'f012');
      await openLogin(tester, env);
      expect(find.text('f012'), findsOneWidget);
      expect(editable(tester, 'login-username').controller.text, 'f012');
      expect(editable(tester, 'login-password').controller.text, isEmpty);
      expect(editable(tester, 'login-password').focusNode.hasFocus, isTrue);
      await enterLogin(tester, password: 'farm1234');
      await tapKey(tester, 'login-submit');
      expect(env.api.loginCalls.single.username, 'f012');
      expect(keyed('home-scan'), findsOneWidget);
    });

    testWidgets('after logging out the last user name is there again', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      final container = await openLogin(tester, env);
      await logInWith(tester, username: 'f003');
      await container.read(sessionProvider.notifier).logout();
      await tester.pumpAndSettle();
      expect(keyed('login-username'), findsOneWidget);
      expect(find.text('f003'), findsOneWidget);
      expect(editable(tester, 'login-password').controller.text, isEmpty);
    });

    testWidgets('the speaker button says the whole login script again', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await tester.tap(find.byIcon(AppIcons.speaker));
      await tester.pumpAndSettle();
      expect(env.voice.spokenIds, loginScript);
    });

    testWidgets('the back arrow returns to the welcome screen', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      await tester.tap(find.byIcon(AppIcons.back));
      await tester.pumpAndSettle();
      expect(keyed('welcome-continue'), findsOneWidget);
    });

    testWidgets('fields, eye and tick are at least 56 dp', (tester) async {
      final env = await TestEnv.create(onboardingDone: true);
      await openLogin(tester, env);
      expectBigTouchTargets(tester);
      for (final key in ['login-username', 'login-password', 'login-eye', 'login-submit']) {
        final size = tester.getSize(keyed(key));
        expect(size.height, greaterThanOrEqualTo(64), reason: '$key height');
        expect(size.width, greaterThanOrEqualTo(64), reason: '$key width');
      }
    });

    for (final language in ['hi', 'en']) {
      for (final keyboard in [0.0, 250.0]) {
        final open = keyboard > 0 ? ' with the keyboard open' : '';
        testWidgets('no overflow at 320x568 and text size 2.0 in $language$open', (tester) async {
          useSmallPhone(tester, size: const Size(320, 568), textScale: 2.0);
          addTearDown(tester.view.resetViewInsets);
          final env = await TestEnv.create(onboardingDone: true, language: language);
          await pumpApp(tester, env);
          expect(tester.takeException(), isNull);
          // The keyboard comes up after the screen is open (it covers the bottom of the phone).
          tester.view.viewInsets = FakeViewPadding(bottom: keyboard);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          expect(tester.getRect(keyed('login-submit')).bottom, lessThanOrEqualTo(568 - keyboard));
          if (keyboard > 0) {
            expect(keyed('voice-caption'), findsNothing, reason: 'the caption makes room for the fields');
            // The fields keep a usable window: at least one whole field plus its label.
            final window = tester.getRect(find.byType(SingleChildScrollView).first).height;
            expect(window, greaterThanOrEqualTo(120));
          }
          await enterLogin(tester, username: 'f001', password: 'farm1234');
          await tapKey(tester, 'login-eye');
          expect(tester.takeException(), isNull);
          await tapKey(tester, 'login-submit');
          expect(tester.takeException(), isNull);
          expect(keyed('home-scan'), findsOneWidget);
        });
      }
    }
  });
}
