import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/push/notification_permission.dart';
import 'package:farmtrack/core/push/push_providers.dart';
import 'package:farmtrack/core/push/push_service.dart';
import 'package:farmtrack/core/push/push_token_source.dart';
import 'package:farmtrack/core/voice/utterance.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// A [PushService] with fakes for everything outside it, and a record of what it did.
class Rig {
  Rig({String? token, NotificationPermission permission = NotificationPermission.unsupported, this.loggedIn = true})
    : source = FakePushSource(token: token),
      port = FakePermissionPort(permission) {
    service = PushService(
      tokens: source,
      permission: port,
      registerDevice: (device) async {
        if (failRegister) throw const ApiException.network();
        registered.add(device);
      },
      speak: (items) async => spoken.addAll([
        for (final i in items)
          if (i is PromptUtterance) i.id,
      ]),
      isLoggedIn: () => loggedIn,
      wasPermissionAsked: () => asked,
      markPermissionAsked: () async => asked = true,
      platform: 'android',
      appVersion: '1.2.3',
      onAlertArrived: () => arrived++,
    )..attachNavigator(visited.add);
  }

  final FakePushSource source;
  final FakePermissionPort port;
  late final PushService service;
  bool loggedIn;
  bool asked = false;
  bool failRegister = false;
  int arrived = 0;
  final List<DeviceIn> registered = [];
  final List<String> spoken = [];
  final List<String> visited = [];
}

void main() {
  group('registering the device', () {
    test('sends the token with the platform and the app version, once', () async {
      final rig = Rig(token: 'tok-1');
      expect(await rig.service.syncRegistration(), isTrue);
      expect(await rig.service.syncRegistration(), isTrue);
      expect(rig.registered, hasLength(1));
      expect(rig.registered.single.pushToken, 'tok-1');
      expect(rig.registered.single.platform, 'android');
      expect(rig.registered.single.appVersion, '1.2.3');
    });

    test('does nothing without a token (the default source) or without a login', () async {
      final noToken = Rig();
      expect(await noToken.service.syncRegistration(), isFalse);
      expect(noToken.registered, isEmpty);
      final loggedOut = Rig(token: 'tok', loggedIn: false);
      expect(await loggedOut.service.syncRegistration(), isFalse);
      expect(loggedOut.registered, isEmpty);
      expect(await const NoopPushTokenSource().getToken(), isNull);
      expect(await const NoopPushTokenSource().getInitialMessage(), isNull);
    });

    test('a rotated token is sent again', () async {
      final rig = Rig(token: 'tok-1');
      await rig.service.start();
      expect(rig.registered.map((d) => d.pushToken), ['tok-1']);
      rig.source.token = 'tok-2';
      rig.source.refresh.add('tok-2');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(rig.registered.map((d) => d.pushToken), ['tok-1', 'tok-2']);
    });

    test(
      'after logout and a new login the same token is registered again (the phone may belong to someone else now)',
      () async {
        final rig = Rig(token: 'tok-1');
        await rig.service.syncRegistration();
        rig.loggedIn = false;
        rig.service.onLoggedOut();
        expect(await rig.service.syncRegistration(), isFalse);
        rig.loggedIn = true;
        await rig.service.onLoggedIn();
        expect(rig.registered, hasLength(2));
      },
    );

    test('a failure is not fatal and is retried at the next chance', () async {
      final rig = Rig(token: 'tok-1')..failRegister = true;
      expect(await rig.service.syncRegistration(), isFalse);
      await rig.service.onLoggedIn(); // never throws
      expect(rig.registered, isEmpty);
      rig.failRegister = false;
      expect(await rig.service.syncRegistration(), isTrue);
      expect(rig.registered, hasLength(1));
    });

    test('two calls at the same time register once', () async {
      final rig = Rig(token: 'tok-1');
      final results = await Future.wait([rig.service.syncRegistration(), rig.service.syncRegistration()]);
      expect(results, [true, true]);
      expect(rig.registered, hasLength(1));
    });
  });

  group('the notification permission', () {
    test('a build without a plugin asks nothing and says nothing', () async {
      final rig = Rig(permission: NotificationPermission.unsupported);
      expect(await rig.service.ensurePermission(), NotificationPermission.unsupported);
      expect(rig.spoken, isEmpty);
      expect(rig.port.requests, 0);
      expect(rig.asked, isFalse);
      expect(await const UnsupportedNotificationPermissionPort().status(), NotificationPermission.unsupported);
      expect(await const UnsupportedNotificationPermissionPort().request(), NotificationPermission.unsupported);
    });

    test(
      'not asked yet: explains with notification_permission, then shows the system question, then registers',
      () async {
        final rig = Rig(token: 'tok', permission: NotificationPermission.notDetermined);
        expect(await rig.service.ensurePermission(), NotificationPermission.granted);
        expect(rig.spoken, ['notification_permission']);
        expect(rig.port.requests, 1);
        expect(rig.asked, isTrue);
        expect(rig.registered, hasLength(1));
      },
    );

    test('refused: says permission_denied_notifications and never asks again', () async {
      final rig = Rig(permission: NotificationPermission.notDetermined)..port.answer = NotificationPermission.denied;
      expect(await rig.service.ensurePermission(), NotificationPermission.denied);
      expect(rig.spoken, ['notification_permission', 'permission_denied_notifications']);
      rig.spoken.clear();
      await rig.service.ensurePermission();
      expect(rig.spoken, isEmpty);
      expect(rig.port.requests, 1);
    });

    test('already refused in the phone settings: said once, no system question', () async {
      final rig = Rig(permission: NotificationPermission.denied);
      await rig.service.ensurePermission();
      expect(rig.spoken, ['permission_denied_notifications']);
      expect(rig.port.requests, 0);
      rig.spoken.clear();
      await rig.service.ensurePermission();
      expect(rig.spoken, isEmpty);
    });

    test('already allowed: no words, but the device is registered', () async {
      final rig = Rig(token: 'tok', permission: NotificationPermission.granted);
      await rig.service.ensurePermission();
      expect(rig.spoken, isEmpty);
      expect(rig.registered, hasLength(1));
    });

    test('the prompts exist in the voice catalogue', () {
      final catalogue = loadCatalogue();
      for (final id in ['notification_permission', 'permission_denied_notifications', 'alert_new', 'alert_open']) {
        expect(catalogue.contains(id), isTrue, reason: id);
      }
    });
  });

  group('messages', () {
    test('a tapped notification opens its alert', () {
      final rig = Rig();
      rig.service.handleNotificationTap({'alert_id': 'a-17', 'kind': 'rain_washoff', 'level': 'red'});
      expect(rig.visited, ['/alerts/detail?id=a-17']);
    });

    test('a message without an alert id (or with rubbish) opens the alert list', () {
      final rig = Rig();
      rig.service.handleNotificationTap({'kind': 'rain_washoff'});
      rig.service.handleNotificationTap({'alert_id': 42, 'level': 'purple'});
      rig.service.handleNotificationTap({});
      expect(rig.visited, ['/alerts', '/alerts', '/alerts']);
    });

    test('maps loosely typed data from the plugin', () {
      final tap = PushTap.fromData({'alert_id': ' a1 ', 'kind': 'x', 'level': 'red', 'extra': 1});
      expect((tap.alertId, tap.kind, tap.level), ('a1', 'x', Severity.red));
      final odd = PushTap.fromData({1: 'x', 'alert_id': ''});
      expect(odd.alertId, isNull);
      expect(odd.level, Severity.yellow, reason: 'unknown level: be careful');
    });

    test('a tap before the login waits and is delivered once, after the login', () async {
      final rig = Rig(loggedIn: false);
      rig.service.handleNotificationTap({'alert_id': 'a1'});
      expect(rig.visited, isEmpty);
      rig.loggedIn = true;
      await rig.service.onLoggedIn();
      expect(rig.visited, ['/alerts/detail?id=a1']);
      await rig.service.onLoggedIn();
      expect(rig.visited, hasLength(1));
    });

    test('a tap before the router exists waits for it', () {
      final rig = Rig();
      final delayed = PushService(
        tokens: rig.source,
        permission: rig.port,
        registerDevice: (_) async {},
        speak: (_) async {},
        isLoggedIn: () => true,
        wasPermissionAsked: () => true,
        markPermissionAsked: () async {},
        platform: 'ios',
      );
      delayed.handleNotificationTap({'alert_id': 'a2'});
      final seen = <String>[];
      delayed.attachNavigator(seen.add);
      expect(seen, ['/alerts/detail?id=a2']);
    });

    test('a message while the app is open is announced and refreshes the alerts', () {
      final rig = Rig();
      rig.service.handleForegroundMessage({'alert_id': 'a1'});
      expect(rig.spoken, ['alert_new', 'alert_open']);
      expect(rig.arrived, 1);
      rig.loggedIn = false;
      rig.service.handleForegroundMessage({'alert_id': 'a1'});
      expect(rig.spoken, hasLength(2), reason: 'nobody is logged in');
    });

    test('start() wires the plugin streams and the notification that started the app', () async {
      final rig = Rig(token: 'tok');
      rig.source.initial = {'alert_id': 'launch'};
      await rig.service.start();
      await rig.service.start(); // safe to repeat
      expect(rig.visited, ['/alerts/detail?id=launch']);
      rig.source.taps.add({'alert_id': 'tap'});
      rig.source.foreground.add({'alert_id': 'fg'});
      await Future<void>.delayed(Duration.zero);
      expect(rig.visited, ['/alerts/detail?id=launch', '/alerts/detail?id=tap']);
      expect(rig.spoken, ['alert_new', 'alert_open']);
      rig.service.dispose();
      rig.source.taps.add({'alert_id': 'after'});
      await Future<void>.delayed(Duration.zero);
      expect(rig.visited, hasLength(2));
    });
  });

  group('in the app', () {
    testWidgets('the default build registers nothing and asks nothing', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      expect(env.api.calls, isNot(contains('registerDevice')));
      expect(env.voice.spokenIds, isNot(contains('notification_permission')));
    });

    testWidgets('with a token, Home registers the device; logout then login registers it again', (tester) async {
      final source = FakePushSource(token: 'tok-1');
      final env = await TestEnv.create(
        loggedIn: true,
        extraOverrides: [pushTokenSourceProvider.overrideWithValue(source)],
      );
      useSmallPhone(tester);
      final container = await pumpApp(tester, env, location: '/home');
      expect(env.api.calls.where((c) => c == 'registerDevice'), hasLength(1));

      await container.read(sessionProvider.notifier).logout();
      await tester.pumpAndSettle();
      await container.read(sessionProvider.notifier).login(MockData.tokens(2));
      await tester.pumpAndSettle();
      expect(env.api.calls.where((c) => c == 'registerDevice'), hasLength(2));
    });

    testWidgets('a message while the app is open says alert_new and the bell badge counts it', (tester) async {
      final source = FakePushSource(token: 'tok-1');
      final api = MockApiClient(latency: Duration.zero);
      final env = await TestEnv.create(
        loggedIn: true,
        api: api,
        extraOverrides: [pushTokenSourceProvider.overrideWithValue(source)],
      );
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      expect(find.descendant(of: keyed('alert-badge'), matching: find.text('1')), findsOneWidget);
      env.voice.clear();
      api.alertItems = [
        AlertOut(id: 'new', level: Severity.red, createdAt: DateTime.utc(2026, 5, 12, 8)),
        ...MockData.alerts().items,
      ];
      source.foreground.add({'alert_id': 'new', 'kind': 'rain_washoff', 'level': 'red'});
      await tester.pumpAndSettle();
      expect(env.voice.spokenIds, ['alert_new', 'alert_open']);
      expect(find.descendant(of: keyed('alert-badge'), matching: find.text('2')), findsOneWidget);
    });

    testWidgets('tapping a notification opens that alert and speaks it', (tester) async {
      final source = FakePushSource(token: 'tok-1');
      final env = await TestEnv.create(
        loggedIn: true,
        extraOverrides: [pushTokenSourceProvider.overrideWithValue(source)],
      );
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      env.voice.clear();
      source.taps.add({'alert_id': 'alert-2', 'kind': 'scab_weather', 'level': 'yellow'});
      await tester.pumpAndSettle();
      expect(env.voice.spokenTexts, [MockData.alerts().items.last.spoken.text.hi]);
      expect(keyed('severity-yellow'), findsOneWidget);
      // Back goes to where the farmer was: Home.
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('home-scan'), findsOneWidget);
    });

    testWidgets('the notification that started the app opens its alert once Home is up', (tester) async {
      final source = FakePushSource(token: 'tok-1')..initial = {'alert_id': 'alert-1', 'level': 'red'};
      final env = await TestEnv.create(
        loggedIn: true,
        extraOverrides: [pushTokenSourceProvider.overrideWithValue(source)],
      );
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      expect(keyed('severity-red'), findsOneWidget);
      expect(keyed('alert-open-scan'), findsOneWidget);
    });

    testWidgets('a real permission port: Home explains by voice, shows the question, and remembers the answer', (
      tester,
    ) async {
      final port = FakePermissionPort(NotificationPermission.notDetermined, answer: NotificationPermission.denied);
      final env = await TestEnv.create(
        loggedIn: true,
        extraOverrides: [notificationPermissionPortProvider.overrideWithValue(port)],
      );
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      expect(
        env.voice.spokenIds,
        containsAllInOrder(['home_intro', 'notification_permission', 'permission_denied_notifications']),
      );
      expect(port.requests, 1);
      expect(env.prefs.getBool('push_permission_asked'), isTrue);

      // Another visit to Home does not ask again.
      env.voice.clear();
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(env.app(location: '/home'));
      await tester.pumpAndSettle();
      expect(env.voice.spokenIds, isNot(contains('notification_permission')));
      expect(port.requests, 1);
    });
  });
}
