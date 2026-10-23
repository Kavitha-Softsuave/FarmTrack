import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/features/alerts/alerts_providers.dart';
import 'package:farmtrack/features/diary/date_words.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

Future<TestEnv> alertsEnv({MockApiClient? api, String language = 'hi'}) => TestEnv.create(
  loggedIn: true,
  language: language,
  api: api ?? MockApiClient(latency: Duration.zero),
  extraOverrides: [clockProvider.overrideWithValue(() => fixedNow)],
);

/// Home, then the bell. Afterwards the voice log holds what the alert list said.
Future<void> openAlerts(WidgetTester tester, TestEnv env, {double textScale = 1.0, Size? size}) async {
  useSmallPhone(tester, textScale: textScale, size: size ?? const Size(360, 640));
  await pumpApp(tester, env, location: '/home');
  env.voice.clear();
  await tapKey(tester, 'home-alerts');
}

AlertOut alert(
  String id, {
  Severity level = Severity.yellow,
  DateTime? at,
  bool read = false,
  String? scanId,
  String? spokenHi,
}) => AlertOut(
  id: id,
  kind: 'scab_infection_risk',
  level: level,
  title: LocalizedText.pair(en: 'Title $id', hi: 'शीर्षक $id'),
  body: LocalizedText.pair(en: 'Body of $id.', hi: 'पूरा लिखा $id।'),
  spoken: SpokenOut(
    text: LocalizedText.pair(en: 'Say $id.', hi: spokenHi ?? 'बोला $id।'),
  ),
  createdAt: at ?? DateTime.utc(2026, 5, 11, 12),
  readAt: read ? DateTime.utc(2026, 5, 11, 13) : null,
  scanId: scanId,
);

void main() {
  group('the alert list', () {
    testWidgets(
      'newest first; unread ones are highlighted with colour, a thick border, bold words and the word "New"',
      (tester) async {
        final env = await alertsEnv();
        await openAlerts(tester, env);

        final unread = keyed('alert-alert-1');
        final read = keyed('alert-alert-2');
        expect(unread, findsOneWidget);
        expect(tester.getTopLeft(unread).dy, lessThan(tester.getTopLeft(read).dy));

        // Level: colour, picture and word.
        expect(find.descendant(of: unread, matching: find.byIcon(Icons.report_rounded)), findsOneWidget);
        expect(find.descendant(of: unread, matching: find.text('गंभीर')), findsOneWidget);
        expect(find.descendant(of: read, matching: find.byIcon(Icons.warning_amber_rounded)), findsOneWidget);
        expect(find.descendant(of: read, matching: find.text('सावधान')), findsOneWidget);
        expect(find.descendant(of: unread, matching: find.byIcon(Icons.notifications_rounded)), findsOneWidget);

        // Unread: a "New" label, a thick border, bold words, a tinted background.
        expect(keyed('alert-new-alert-1'), findsOneWidget);
        expect(find.descendant(of: unread, matching: find.text('नई')), findsOneWidget);
        expect(keyed('alert-new-alert-2'), findsNothing);
        final unreadMaterial = tester.widget<Material>(unread);
        final readMaterial = tester.widget<Material>(read);
        expect((unreadMaterial.shape! as RoundedRectangleBorder).side.width, 4);
        expect((readMaterial.shape! as RoundedRectangleBorder).side.width, 2);
        expect(unreadMaterial.color, isNot(readMaterial.color));
        final unreadTitle = tester.widget<Text>(
          find.descendant(of: unread, matching: find.text('बारिश ने छिड़काव धो दिया')),
        );
        final readTitle = tester.widget<Text>(find.descendant(of: read, matching: find.text('स्कैब का मौसम')));
        expect(unreadTitle.style!.fontWeight, FontWeight.w800);
        expect(readTitle.style!.fontWeight, FontWeight.w500);

        expect(find.descendant(of: unread, matching: find.text('आज, 12 मई')), findsOneWidget);
        expect(env.voice.spokenIds, ['alert_open']);
        expect(env.voice.unknownIds, isEmpty);
        expectBigTouchTargets(tester);
      },
    );

    testWidgets('the server order does not matter: they are shown newest first', (tester) async {
      final api = MockApiClient(latency: Duration.zero)
        ..alertItems = [
          alert('old', at: DateTime.utc(2026, 5, 1, 12)),
          alert('new', at: DateTime.utc(2026, 5, 11, 12)),
          alert('undated').copyWithDate(null),
        ];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      final tops = [
        for (final id in ['new', 'old', 'undated']) tester.getTopLeft(keyed('alert-$id')).dy,
      ];
      expect(tops, [...tops]..sort());
    });

    testWidgets('empty: a picture, words and alert_none', (tester) async {
      final api = MockApiClient(latency: Duration.zero)..alertItems = [];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      expect(keyed('alerts-empty'), findsOneWidget);
      expect(find.text('कोई सूचना नहीं'), findsOneWidget);
      expect(env.voice.spokenIds, ['alert_none']);
    });

    testWidgets('a failed load shows the error screen; the retry shows the list', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      api.failWith(const ApiException.network(), ops: {'listAlerts'});
      env.voice.clear();
      await tapKey(tester, 'home-alerts');
      expect(keyed('retry-button'), findsOneWidget);
      expect(env.voice.spokenIds, ['error_no_internet']);
      api.clearFailure();
      await tapKey(tester, 'retry-button');
      expect(keyed('alert-alert-1'), findsOneWidget);
    });

    testWidgets('english', (tester) async {
      final env = await alertsEnv(language: 'en');
      await openAlerts(tester, env);
      expect(find.text('Rain washed your spray'), findsOneWidget);
      expect(find.text('New'), findsOneWidget);
      expect(find.text('Serious'), findsOneWidget);
    });
  });

  group('opening an alert', () {
    testWidgets('speaks its text, shows level, title and body, marks it read and the bell badge goes', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      expect(find.descendant(of: keyed('alert-badge'), matching: find.text('1')), findsOneWidget);
      await tapKey(tester, 'home-alerts');
      env.voice.clear();
      await tapKey(tester, 'alert-alert-1');

      expect(env.voice.spokenTexts, [MockData.alerts().items.first.spoken.text.hi]);
      expect(keyed('severity-red'), findsOneWidget);
      expect(find.byIcon(Icons.report_rounded), findsWidgets);
      expect(find.text('गंभीर'), findsOneWidget);
      expect(find.text('बारिश ने छिड़काव धो दिया'), findsOneWidget);
      expect(keyed('alert-body'), findsOneWidget);
      expect(api.calls, contains('markAlertRead'));
      expectBigTouchTargets(tester);

      // Back to the list: no longer highlighted. Back to Home: no badge.
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('alert-new-alert-1'), findsNothing);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('alert-badge'), findsNothing);
    });

    testWidgets('an alert that is already read is not marked again', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      await tapKey(tester, 'alert-alert-2');
      expect(api.calls, isNot(contains('markAlertRead')));
    });

    testWidgets('reading is silent when there is no internet: the alert stays unread', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      api.failWith(const ApiException.network(), ops: {'markAlertRead'});
      env.voice.clear();
      await tapKey(tester, 'alert-alert-1');
      expect(env.voice.spokenTexts, hasLength(1));
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('alert-new-alert-1'), findsOneWidget);
    });

    testWidgets('without a spoken text the body is read; a green alert has a tick and the word "fine"', (tester) async {
      final api = MockApiClient(latency: Duration.zero)
        ..alertItems = [
          AlertOut(
            id: 'g',
            level: Severity.green,
            title: LocalizedText.pair(en: 'All well', hi: 'सब ठीक'),
            body: LocalizedText.pair(en: 'Nothing to do.', hi: 'कुछ करना नहीं।'),
            createdAt: DateTime.utc(2026, 5, 11, 12),
          ),
        ];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      expect(find.descendant(of: keyed('alert-g'), matching: find.byIcon(Icons.check_rounded)), findsOneWidget);
      env.voice.clear();
      await tapKey(tester, 'alert-g');
      expect(env.voice.spokenTexts, ['कुछ करना नहीं।']);
      expect(keyed('severity-green'), findsOneWidget);
      expect(find.text('ठीक'), findsOneWidget);
      expect(keyed('alert-open-scan'), findsNothing);
    });

    testWidgets('the speaker button says the alert again', (tester) async {
      final env = await alertsEnv();
      await openAlerts(tester, env);
      env.voice.clear();
      await tapKey(tester, 'alert-alert-2');
      final first = List.of(env.voice.log);
      expect(first, hasLength(1));
      env.voice.clear();
      await tapKey(tester, 'speaker-button');
      expect(env.voice.log, first);
    });

    testWidgets('an alert that is not in the list leads back to the list', (tester) async {
      final env = await alertsEnv();
      useSmallPhone(tester);
      final container = await pumpApp(tester, env, location: '/home');
      unawaited(container.read(routerProvider).push<void>(Routes.alertDetailFor('no-such-alert')));
      await tester.pumpAndSettle();
      expect(keyed('alert-alert-1'), findsOneWidget);
    });

    testWidgets('a detail link without an id leads back to the list', (tester) async {
      final env = await alertsEnv();
      useSmallPhone(tester);
      final container = await pumpApp(tester, env, location: '/home');
      unawaited(container.read(routerProvider).push<void>(Routes.alertDetail));
      await tester.pumpAndSettle();
      expect(keyed('alert-alert-1'), findsOneWidget);
    });
  });

  group('an alert about a photo', () {
    testWidgets('has a big green arrow; it opens that scan\'s advice on the normal result screen', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      env.voice.clear();
      await tapKey(tester, 'alert-alert-1');
      expect(keyed('alert-open-scan'), findsOneWidget);
      expect(env.voice.spokenIds, ['alert_see_scan']);
      expect(env.voice.spokenTexts, hasLength(1), reason: 'the alert text comes first, then the hint');
      expect(env.voice.log.last, 'alert_see_scan@hi');
      expectBigTouchTargets(tester);

      env.voice.clear();
      await tapKey(tester, 'alert-open-scan');
      expect(api.calls, contains('getScan'));
      // The advice screen: severity band, the medicine and the "I sprayed" button.
      expect(keyed('severity-yellow'), findsOneWidget);
      expect(keyed('product-P007'), findsOneWidget);
      expect(keyed('i-sprayed'), findsOneWidget);
      expect(env.voice.spokenIds.first, 'result_intro');

      // "I sprayed" works from here: the diary knows the medicine.
      env.voice.clear();
      await tapKey(tester, 'i-sprayed');
      expect(env.voice.spokenTexts, ['डिफेनोकोनाज़ोल, Score']);
      await tapKey(tester, 'diary-save');
      expect(api.sprayLogsIn.single.adviceId, 'adv-${MockData.alertScanId}');
    });

    testWidgets('an expert case opens the expert screen', (tester) async {
      final api = MockApiClient(latency: Duration.zero)
        ..scans['x'] = MockData.needsExpertScan('x')
        ..alertItems = [alert('a', scanId: 'x')];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      await tapKey(tester, 'alert-a');
      await tapKey(tester, 'alert-open-scan');
      expect(find.byIcon(Icons.support_agent_rounded), findsWidgets);
      expect(env.voice.spokenIds, contains('result_expert'));
    });

    testWidgets('a scan that has no result yet says error_try_again and stays', (tester) async {
      final api = MockApiClient(latency: Duration.zero)
        ..scans['x'] = MockData.confirmCropScan('x')
        ..alertItems = [alert('a', scanId: 'x')];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      await tapKey(tester, 'alert-a');
      env.voice.clear();
      await tapKey(tester, 'alert-open-scan');
      expect(env.voice.spokenIds, ['error_try_again']);
      expect(keyed('alert-open-scan'), findsOneWidget);
    });

    testWidgets('no internet: speaks error_no_internet, keeps the alert and the button; a second try works', (
      tester,
    ) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      await tapKey(tester, 'alert-alert-1');
      api.failWith(const ApiException.network(), ops: {'getScan'});
      env.voice.clear();
      await tapKey(tester, 'alert-open-scan');
      expect(env.voice.spokenIds, ['error_no_internet']);
      expect(keyed('alert-open-scan'), findsOneWidget);
      api.clearFailure();
      await tapKey(tester, 'alert-open-scan');
      expect(keyed('i-sprayed'), findsOneWidget);
    });

    testWidgets('a scan that is gone (404) says error_try_again', (tester) async {
      final api = MockApiClient(latency: Duration.zero)..alertItems = [alert('a', scanId: 'gone')];
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      await tapKey(tester, 'alert-a');
      env.voice.clear();
      await tapKey(tester, 'alert-open-scan');
      expect(env.voice.spokenIds, ['error_try_again']);
    });
  });

  group('refreshing', () {
    testWidgets('when the app comes back, the list and the badge load again', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      await openAlerts(tester, env);
      expect(keyed('alert-fresh'), findsNothing);
      final before = api.calls.where((c) => c == 'listAlerts').length;
      api.alertItems = [
        alert('fresh', level: Severity.red, at: DateTime.utc(2026, 5, 12, 5)),
        ...MockData.alerts().items,
      ];
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(api.calls.where((c) => c == 'listAlerts').length, greaterThan(before));
      expect(keyed('alert-fresh'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(find.descendant(of: keyed('alert-badge'), matching: find.text('2')), findsOneWidget);
    });

    testWidgets('every five minutes while Home or the list is open, and not before', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      useSmallPhone(tester);
      await pumpApp(tester, env, location: '/home');
      int listed() => api.calls.where((c) => c == 'listAlerts').length;
      final start = listed();
      await tester.pump(const Duration(minutes: 4));
      expect(listed(), start, reason: 'not yet');
      api.alertItems = [alert('fresh'), ...MockData.alerts().items];
      await tester.pump(const Duration(minutes: 1, seconds: 1));
      await tester.pumpAndSettle();
      expect(listed(), greaterThan(start));
      expect(
        find.descendant(of: keyed('alert-badge'), matching: find.text('2')),
        findsOneWidget,
        reason: 'Home is refreshed',
      );

      // On the alert list it refreshes the list too.
      await tapKey(tester, 'home-alerts');
      expect(keyed('alert-fresh'), findsOneWidget);
      api.alertItems = [alert('fresher', at: DateTime.utc(2026, 5, 12, 9)), alert('fresh'), ...MockData.alerts().items];
      await tester.pump(const Duration(minutes: 5, seconds: 1));
      await tester.pumpAndSettle();
      expect(keyed('alert-fresher'), findsOneWidget);
    });

    testWidgets('a refresh does not speak again and does not flicker to a spinner', (tester) async {
      final env = await alertsEnv();
      await openAlerts(tester, env);
      final spoken = List.of(env.voice.log);
      await tester.pump(const Duration(minutes: 5, seconds: 1));
      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsNothing);
      await tester.pumpAndSettle();
      expect(env.voice.log, spoken);
    });
  });

  group('layout', () {
    for (final (name, size, scale) in [
      ('320x568', const Size(320, 568), 1.0),
      ('360x640 at 1.6x text', const Size(360, 640), 1.6),
      ('320x568 at 1.6x text', const Size(320, 568), 1.6),
    ]) {
      testWidgets('list and detail fit on $name', (tester) async {
        final api = MockApiClient(latency: Duration.zero)
          ..alertItems = [
            alert('long', level: Severity.red, scanId: MockData.alertScanId).copyWithTitle(
              LocalizedText.pair(
                en: 'A title that is quite long and has to wrap over several lines',
                hi: 'एक बहुत लंबा शीर्षक जिसे कई पंक्तियों में लिखना पड़ता है ताकि पूरा दिखे',
              ),
            ),
            alert('b'),
          ];
        final env = await alertsEnv(api: api);
        await openAlerts(tester, env, textScale: scale, size: size);
        expect(tester.takeException(), isNull);
        expectBigTouchTargets(tester);
        await tapKey(tester, 'alert-long');
        expect(tester.takeException(), isNull);
        expectBigTouchTargets(tester);
        final arrow = tester.getRect(keyed('alert-open-scan'));
        expect(arrow.bottom, lessThanOrEqualTo(size.height));
      });
    }
  });

  group('helpers', () {
    test('newestFirst keeps the order of equal times and puts undated alerts last', () {
      final t = DateTime.utc(2026, 5, 1);
      final sorted = newestFirst([
        alert('a', at: t),
        alert('b', at: t),
        alert('c', at: t.add(const Duration(hours: 1))),
        alert('d').copyWithDate(null),
      ]);
      expect([for (final a in sorted) a.id], ['c', 'a', 'b', 'd']);
    });

    testWidgets('alerts of one farmer are not shown to the next one who logs in', (tester) async {
      final api = MockApiClient(latency: Duration.zero);
      final env = await alertsEnv(api: api);
      final container = await pumpApp(tester, env, location: '/home');
      expect((await container.read(alertsProvider.future)).items, hasLength(2));
      await container.read(sessionProvider.notifier).logout();
      await tester.pumpAndSettle();
      await container.read(sessionProvider.notifier).login(MockData.tokens(2));
      api.alertItems = [alert('mine')];
      container.read(alertsProvider);
      expect((await container.read(alertsProvider.future)).items.single.id, 'mine');
    });
  });
}

extension on AlertOut {
  AlertOut copyWithDate(DateTime? at) => AlertOut(
    id: id,
    kind: kind,
    level: level,
    title: title,
    body: body,
    spoken: spoken,
    createdAt: at,
    readAt: readAt,
    scanId: scanId,
  );

  AlertOut copyWithTitle(LocalizedText newTitle) => AlertOut(
    id: id,
    kind: kind,
    level: level,
    title: newTitle,
    body: body,
    spoken: spoken,
    createdAt: createdAt,
    readAt: readAt,
    scanId: scanId,
  );
}
