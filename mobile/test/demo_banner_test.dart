import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/widgets/demo_clock_banner.dart';

import 'support/contrast.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// A server whose `/v1/meta` we control.
class _MetaApi extends MockApiClient {
  _MetaApi({this.clock, this.env = 'dev'}) : super(latency: Duration.zero);

  DateTime? clock;
  String env;
  int metaCalls = 0;

  @override
  Future<MetaOut> meta() async {
    metaCalls++;
    await super.meta(); // honours failWith
    return MetaOut(appVersion: '0.1.0', env: env, demoClock: clock, supportedLanguages: const ['hi', 'en']);
  }
}

final _may12 = DateTime.parse('2026-05-12T08:00:00+05:30');

void main() {
  final fetch = demoBannerFetchProvider.overrideWithValue(true);

  Future<TestEnv> env(_MetaApi api, {String language = 'hi', List<Override> extra = const []}) =>
      TestEnv.create(language: language, loggedIn: true, api: api, extraOverrides: [fetch, ...extra]);

  testWidgets('a demo clock shows a thin strip with the date at the top of every screen; the voice never reads it', (
    tester,
  ) async {
    useSmallPhone(tester);
    final api = _MetaApi(clock: _may12);
    final e = await env(api);
    final container = await pumpApp(tester, e, location: '/home');
    expect(find.text('डेमो की तारीख़: 12 मई 2026'), findsOneWidget);
    expect(find.text('डेमो की तारीख़: 12 मई 2026').hitTestable(), findsOneWidget);

    final strip = keyed('demo-banner');
    expect(tester.getTopLeft(strip).dy, 0, reason: 'at the very top');
    expect(tester.getSize(strip).width, 360, reason: 'full width');
    expect(tester.getSize(strip).height, lessThan(40), reason: 'thin');

    // Other screens (a pushed one and the login screen) show it too.
    final router = container.read(routerProvider);
    for (final route in ['/ask', '/settings', '/diary', '/field']) {
      router.go(route);
      await tester.pumpAndSettle();
      expect(strip, findsOneWidget, reason: route);
    }
    expect(e.voice.spokenTexts.where((t) => t.contains('12')), isEmpty, reason: 'never spoken');
    expect(e.voice.spokenIds.where((id) => id.startsWith('demo_')), isEmpty);
    expect(api.metaCalls, 1, reason: 'one request, shared by all screens');
  });

  testWidgets('the date is written in the app language; Indian time decides the day', (tester) async {
    useSmallPhone(tester);
    // 20:00 UTC is 01:30 the next day in India.
    final api = _MetaApi(clock: DateTime.utc(2026, 5, 12, 20));
    final e = await env(api, language: 'en');
    await pumpApp(tester, e, location: '/home');
    expect(find.text('Demo date: 13 May 2026'), findsOneWidget);
  });

  test('formatDemoDate uses Indian time and the month names it is given', () {
    final months = 'January,February,March,April,May,June,July,August,September,October,November,December'.split(',');
    expect(formatDemoDate(DateTime.utc(2026, 12, 31, 18, 29), months), '31 December 2026');
    expect(formatDemoDate(DateTime.utc(2026, 12, 31, 18, 30), months), '1 January 2027');
    expect(formatDemoDate(DateTime.parse('2026-05-12T08:00:00+05:30'), months), '12 May 2026');
    expect(formatDemoDate(DateTime.utc(2026, 5, 12), const []), '12 5 2026', reason: 'no names: the number, no crash');
  });

  testWidgets('no demo clock, no strip', (tester) async {
    useSmallPhone(tester);
    final e = await env(_MetaApi());
    await pumpApp(tester, e, location: '/home');
    expect(keyed('demo-banner'), findsNothing);
  });

  testWidgets('the strip is high contrast text on ink and fits a 320 dp phone at the largest text size', (
    tester,
  ) async {
    useSmallPhone(tester, size: const Size(320, 568), textScale: 2.0);
    final e = await env(_MetaApi(clock: DateTime.parse('2026-09-30T08:00:00+05:30')), language: 'en');
    await tester.pumpWidget(e.wrap(const Scaffold(body: SafeArea(child: DemoClockBanner()))));
    await tester.pumpAndSettle();
    final text = tester.widget<Text>(find.text('Demo date: 30 September 2026'));
    final box = tester.widget<Container>(keyed('demo-banner'));
    expect(contrast(text.style!.color!, box.color!), greaterThanOrEqualTo(7), reason: 'AAA');
    expect(tester.takeException(), isNull);
    expect(tester.getSize(keyed('demo-banner')).width, 320);
    final words = tester.getRect(find.text('Demo date: 30 September 2026'));
    expect(words.width, lessThanOrEqualTo(320), reason: 'the words scale down instead of overflowing');
  });

  group('release builds against production', () {
    testWidgets('a release build talking to a prod server does not show it', (tester) async {
      useSmallPhone(tester);
      final e = await env(
        _MetaApi(clock: _may12, env: 'prod'),
        extra: [releaseBuildProvider.overrideWithValue(true)],
      );
      await pumpApp(tester, e, location: '/home');
      expect(keyed('demo-banner'), findsNothing);
    });

    testWidgets('a release build talking to a staging server shows it (the demo build)', (tester) async {
      useSmallPhone(tester);
      final e = await env(
        _MetaApi(clock: _may12, env: 'staging'),
        extra: [releaseBuildProvider.overrideWithValue(true)],
      );
      await pumpApp(tester, e, location: '/home');
      expect(keyed('demo-banner'), findsOneWidget);
    });

    testWidgets('a debug build shows it whatever the server says', (tester) async {
      useSmallPhone(tester);
      final e = await env(
        _MetaApi(clock: _may12, env: 'prod'),
        extra: [releaseBuildProvider.overrideWithValue(false)],
      );
      await pumpApp(tester, e, location: '/home');
      expect(keyed('demo-banner'), findsOneWidget);
    });
  });

  group('network', () {
    testWidgets('offline at start: no strip; it appears when the phone is back online', (tester) async {
      useSmallPhone(tester);
      final api = _MetaApi(clock: _may12)..failWith(const ApiException.network(), ops: {'meta'});
      final e = await env(api);
      e.connectivity.online = false;
      await pumpApp(tester, e, location: '/home');
      expect(keyed('demo-banner'), findsNothing);

      api.clearFailure();
      e.connectivity.online = true;
      await tester.pumpAndSettle();
      expect(keyed('demo-banner'), findsOneWidget);
    });

    testWidgets('coming back to the app asks again, so a changed demo date shows up', (tester) async {
      useSmallPhone(tester);
      final api = _MetaApi(clock: _may12);
      final e = await env(api);
      await pumpApp(tester, e, location: '/home');
      expect(find.text('डेमो की तारीख़: 12 मई 2026'), findsOneWidget);

      api.clock = DateTime.parse('2026-06-01T08:00:00+05:30');
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(find.text('डेमो की तारीख़: 1 जून 2026'), findsOneWidget);
    });
  });

  testWidgets('under flutter test the app does not ask the server for the demo clock unless a test turns it on', (
    tester,
  ) async {
    // Other tests queue failures for specific calls; an extra GET /v1/meta must never take one of them.
    final plain = await TestEnv.create(loggedIn: true);
    await pumpApp(tester, plain, location: '/home');
    expect(plain.api.calls, isNot(contains('meta')));
    expect(containerOf(tester).read(demoBannerFetchProvider), isFalse);
    expect(keyed('demo-banner'), findsNothing);
  });

  test('the providers have the defaults the production app needs', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    // In a `flutter test` run kReleaseMode is false (this is not a release build).
    expect(container.read(releaseBuildProvider), isFalse);
  });
}
