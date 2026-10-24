import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/features/diary/date_words.dart';
import 'package:farmtrack/features/diary/diary_providers.dart';
import 'package:farmtrack/features/offline/last_result.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// Offline reading and manual retry: the last advice, the diary list, a diary entry waiting after a restart, and the
/// "send now" tap on the waiting card.
void main() {
  Future<TestEnv> makeEnv({DateTime Function()? clock, MockApiClient? api, List<MockScanScenario>? script}) =>
      TestEnv.create(
        loggedIn: true,
        api: api,
        scanScript: script ?? [MockScanScenario.ok],
        extraOverrides: [if (clock != null) clockProvider.overrideWithValue(clock)],
      );

  String queuePhoto(TestEnv env) {
    final file = File('${env.supportDir.path}${Platform.pathSeparator}leaf_${env.picker.script.length}.jpg')
      ..writeAsBytesSync(List<int>.filled(200, 7));
    env.picker.script.add(file.path);
    return file.path;
  }

  Future<void> scanOnePhoto(WidgetTester tester, TestEnv env) async {
    queuePhoto(env);
    await tapKey(tester, 'home-scan');
    await tapKey(tester, 'camera-button');
    await tapKey(tester, 'send-photos');
  }

  group('manual retry', () {
    testWidgets('tapping the waiting card sends what waits right now', (tester) async {
      useSmallPhone(tester);
      final env = await makeEnv();
      env.connectivity.online = false;
      env.api.failWith(const ApiException.network(), ops: {'createScan'});
      await pumpApp(tester, env, location: '/home');
      await scanOnePhoto(tester, env);
      await tapKey(tester, 'saved-home');
      expect(env.api.scans, isEmpty);

      // The server is back, but no connectivity event came and the 30 s timer has not fired.
      env.api.clearFailure();
      await tapKey(tester, 'offline-waiting-card');
      expect(env.api.scans, hasLength(1));
      expect(containerOf(tester).read(offlineQueueProvider).pending, 0);
      expect(keyed('offline-result-card'), findsOneWidget);
    });

    testWidgets('a tap while the server is still down keeps the item and does not duplicate it', (tester) async {
      useSmallPhone(tester);
      final env = await makeEnv();
      env.connectivity.online = false;
      env.api.failWith(const ApiException.network(), ops: {'createScan'});
      await pumpApp(tester, env, location: '/home');
      await scanOnePhoto(tester, env);
      await tapKey(tester, 'saved-home');
      await tapKey(tester, 'offline-waiting-card');
      await tapKey(tester, 'offline-waiting-card');
      expect(containerOf(tester).read(offlineQueueProvider).pending, 1);
      expect(env.api.scans, isEmpty);
    });
  });

  group('the last advice can be read again without internet', () {
    testWidgets('after a scan Home offers the last advice; it opens from the phone with every call failing', (
      tester,
    ) async {
      useSmallPhone(tester);
      final env = await makeEnv(clock: () => fixedNow);
      await pumpApp(tester, env, location: '/home');
      expect(keyed('last-result-card'), findsNothing, reason: 'nothing yet');
      await scanOnePhoto(tester, env);
      expect(keyed('severity-yellow'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('last-result-card'), findsOneWidget);

      // Closed and opened again with no internet at all.
      await tester.pumpWidget(const SizedBox());
      env.connectivity.online = false;
      env.api.failWith(const ApiException.network());
      await tester.pumpWidget(env.app(location: '/home'));
      await tester.pumpAndSettle();
      expect(keyed('last-result-card'), findsOneWidget, reason: 'it survives a restart');
      env.voice.clear();
      await tapKey(tester, 'last-result-card');
      expect(keyed('severity-yellow'), findsOneWidget);
      expect(find.text('सेब का स्कैब (पपड़ी रोग)'), findsWidgets);
      expect(env.voice.spokenIds, contains('result_intro'));
      expect(env.voice.spokenTexts, isNotEmpty, reason: 'the advice is spoken again');
    });

    testWidgets('advice older than seven days is not offered', (tester) async {
      var now = fixedNow;
      useSmallPhone(tester);
      final env = await makeEnv(clock: () => now);
      await pumpApp(tester, env, location: '/home');
      await scanOnePhoto(tester, env);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('last-result-card'), findsOneWidget);

      now = fixedNow.add(const Duration(days: 8));
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(env.app(location: '/home'));
      await tester.pumpAndSettle();
      expect(keyed('last-result-card'), findsNothing);
    });

    test('only finished answers are kept: a crop question or an unusable photo is not', () {
      expect(LastResultCache.keeps(MockData.okScan('a')), isTrue);
      expect(LastResultCache.keeps(MockData.needsExpertScan('a')), isTrue);
      expect(LastResultCache.keeps(MockData.noApprovedDataScan('a')), isTrue);
      expect(LastResultCache.keeps(MockData.notADiseaseScan('a')), isTrue);
      expect(LastResultCache.keeps(MockData.confirmCropScan('a')), isFalse);
      expect(LastResultCache.keeps(MockData.photoUnusableScan('a')), isFalse);
    });
  });

  group('the diary offline', () {
    testWidgets('the last list the server gave is shown (with the offline marker) when it cannot be reached', (
      tester,
    ) async {
      useSmallPhone(tester);
      final api = MockApiClient(latency: Duration.zero);
      await api.createSprayLog(
        SprayLogIn(cropId: 'apple', freeText: 'Score', sprayedAt: DateTime.utc(2026, 5, 10, 12)),
      );
      final env = await makeEnv(clock: () => fixedNow, api: api);
      await pumpApp(tester, env, location: '/home');
      await tapKey(tester, 'home-diary');
      expect(find.textContaining('Score'), findsWidgets);
      expect(keyed('diary-offline'), findsNothing);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      api.failWith(const ApiException.network(), ops: {'listSprayLogs'});
      env.connectivity.online = false;
      await tapKey(tester, 'home-diary');
      expect(find.textContaining('Score'), findsWidgets, reason: 'read from the phone');
      expect(keyed('diary-offline'), findsOneWidget);
      expect(keyed('retry-button'), findsNothing, reason: 'not an error screen');
    });

    testWidgets('without a saved list the error screen with the retry button stays', (tester) async {
      useSmallPhone(tester);
      final api = MockApiClient(latency: Duration.zero)..failWith(const ApiException.network(), ops: {'listSprayLogs'});
      final env = await makeEnv(clock: () => fixedNow, api: api);
      await pumpApp(tester, env, location: '/home');
      await tapKey(tester, 'home-diary');
      expect(keyed('retry-button'), findsOneWidget);
    });

    testWidgets('a diary entry that waits for the internet still shows as waiting after a restart', (tester) async {
      useSmallPhone(tester);
      final api = MockApiClient(latency: Duration.zero);
      final env = await makeEnv(clock: () => fixedNow, api: api);
      env.connectivity.online = false;
      api.failWith(const ApiException.network(), ops: {'createSprayLog', 'listSprayLogs'});
      await pumpApp(tester, env, location: '/home');
      final queue = containerOf(tester).read(offlineQueueProvider);
      await queue.enqueueSprayLog(
        SprayLogIn(cropId: 'apple', freeText: 'Mancozeb', sprayedAt: DateTime.utc(2026, 5, 11, 12)),
      );

      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(env.app(location: '/home'));
      await tester.pumpAndSettle();
      await tapKey(tester, 'home-diary');
      expect(find.textContaining('Mancozeb'), findsWidgets);
      expect(containerOf(tester).read(pendingSpraysProvider).items, hasLength(1));

      // Back online: it is sent and the waiting mark goes away.
      api.clearFailure();
      env.connectivity.online = true;
      await tester.pumpAndSettle();
      expect(api.sprayLogsIn, hasLength(1));
      expect(containerOf(tester).read(pendingSpraysProvider).items, isEmpty);
    });
  });
}
