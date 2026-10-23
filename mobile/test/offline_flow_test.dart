import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/offline/offline_status.dart';
import 'package:farmtrack/core/offline/persistent_offline_queue.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/features/scan/scan_flow.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/features/home/home_screen.dart';

import 'offline_support.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// The offline queue through the real screens: scan without internet, "saved" screen, Home cards, reconnect.
void main() {
  Future<TestEnv> makeEnv({MockApiClient? api, List<MockScanScenario>? script}) async {
    final env = await TestEnv.create(loggedIn: true, api: api, scanScript: script ?? [MockScanScenario.ok]);
    env.connectivity.online = false;
    return env;
  }

  /// A real photo file (the queue copies it) queued in the fake camera.
  String queuePhoto(TestEnv env, {int bytes = 200}) {
    final file = File(
      '${env.supportDir.path}${Platform.pathSeparator}leaf_${env.picker.opened}_${env.picker.script.length}.jpg',
    )..writeAsBytesSync(List<int>.filled(bytes, 7));
    env.picker.script.add(file.path);
    return file.path;
  }

  Future<void> sendOnePhoto(WidgetTester tester, TestEnv env) async {
    queuePhoto(env);
    await tapKey(tester, 'home-scan');
    await tapKey(tester, 'camera-button');
    env.voice.clear();
    await tapKey(tester, 'send-photos');
  }

  Future<void> goOnline(WidgetTester tester, TestEnv env) async {
    env.connectivity.online = true;
    await tester.pumpAndSettle();
  }

  OfflineQueue queueOf(WidgetTester tester) => containerOf(tester).read(offlineQueueProvider);

  testWidgets('no internet: the photos are saved, offline_saved is spoken, Home shows the waiting card', (
    tester,
  ) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    expect(keyed('offline-waiting-card'), findsNothing);

    await sendOnePhoto(tester, env);

    expect(env.voice.spokenIds.last, 'offline_saved', reason: 'a calm "saved" screen, not an error');
    expect(keyed('saved-home'), findsOneWidget);
    expect(keyed('retry-button'), findsNothing);
    expect(queueOf(tester).pending, 1);
    expect(containerOf(tester).read(scanFlowProvider).phase, ScanPhase.queued);
    expectBigTouchTargets(tester);
    final pendingDir = Directory('${env.supportDir.path}${Platform.pathSeparator}pending');
    expect(pendingDir.listSync(), hasLength(2), reason: 'one json file and one folder with the photo copies');

    await tapKey(tester, 'saved-home');
    expect(keyed('home-scan'), findsOneWidget);
    expect(
      find.descendant(of: keyed('offline-waiting-card'), matching: find.text('भेजने के लिए रुके हैं: 1')),
      findsOneWidget,
    );
    expect(containerOf(tester).read(scanFlowProvider).photos, isEmpty, reason: 'the flow starts clean');

    env.voice.clear();
    await tapKey(tester, 'offline-waiting-card');
    expect(env.voice.spokenIds, ['offline_waiting']);
  });

  testWidgets('back online: it is sent once, back_online_sent is spoken, a result card opens the advice', (
    tester,
  ) async {
    useSmallPhone(tester);
    final api = LossyApi(scanScript: [MockScanScenario.ok]);
    final env = await makeEnv(api: api);
    api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');
    expect(api.scans, isEmpty);

    api.clearFailure();
    env.voice.clear();
    await goOnline(tester, env);

    expect(api.scans, hasLength(1), reason: 'sent exactly once');
    expect(queueOf(tester).pending, 0);
    expect(env.voice.spokenIds, ['back_online_sent', 'offline_result_ready']);
    expect(keyed('offline-waiting-card'), findsNothing);
    expect(keyed('offline-result-card'), findsOneWidget);
    expect(
      find.descendant(of: keyed('offline-result-card'), matching: find.text('नतीजा आ गया: देखने के लिए दबाइए')),
      findsOneWidget,
    );
    expect(api.attemptedKeys.toSet(), hasLength(1), reason: 'the live attempt and the queue used the same key');

    await tapKey(tester, 'offline-result-card');
    expect(keyed('severity-yellow'), findsOneWidget, reason: 'the existing advice screen shows the queued scan');
    expect(env.voice.spokenIds, contains('result_intro'));

    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();
    expect(keyed('offline-result-card'), findsNothing, reason: 'the card goes away once the result was opened');
  });

  testWidgets('a result that needs the crop confirmed opens the confirm screen as usual', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv(script: [MockScanScenario.confirmCrop]);
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');
    env.api.clearFailure();
    await goOnline(tester, env);

    await tapKey(tester, 'offline-result-card');
    expect(keyed('crop-yes'), findsOneWidget);
    await tapKey(tester, 'crop-yes');
    expect(keyed('severity-yellow'), findsOneWidget, reason: 'confirming the crop works on a queued scan');
    expect(env.api.confirmedCrops, ['apple']);
  });

  testWidgets('the answer of the first request is lost: the queued retry does not make a second scan', (tester) async {
    useSmallPhone(tester);
    final api = LossyApi(scanScript: [MockScanScenario.ok])..loseAnswers = 1;
    final env = await makeEnv(api: api);
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);

    expect(keyed('saved-home'), findsOneWidget, reason: 'a timeout counts as no connection');
    expect(api.scans, hasLength(1), reason: 'the server did process the first request');
    await tapKey(tester, 'saved-home');
    await goOnline(tester, env);

    expect(api.scans, hasLength(1), reason: 'the retry carried the same key, the server answered from memory');
    expect(api.uploadedPhotoPaths, hasLength(1));
    expect(queueOf(tester).pending, 0);
    expect(keyed('offline-result-card'), findsOneWidget);
  });

  testWidgets('a restart keeps the waiting photos and the result card', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');

    await tester.pumpWidget(const SizedBox()); // the app is closed
    await tester.pumpWidget(env.app(location: '/home')); // and opened again
    await tester.pumpAndSettle();
    expect(keyed('offline-waiting-card'), findsOneWidget, reason: 'loaded from the files');
    expect(env.api.scans, isEmpty);

    env.api.clearFailure();
    await goOnline(tester, env);
    expect(env.api.scans, hasLength(1));
    expect(keyed('offline-result-card'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(env.app(location: '/home'));
    await tester.pumpAndSettle();
    expect(keyed('offline-result-card'), findsOneWidget, reason: 'the card survives a second restart');
    await tapKey(tester, 'offline-result-card');
    expect(keyed('severity-yellow'), findsOneWidget, reason: 'the result is fetched with GET /v1/scans/{id}');
    expect(env.api.calls, contains('getScan'));
  });

  testWidgets('the timer retries by itself while the app is open (30 s)', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');
    env.api.clearFailure(); // the network is back, but no connectivity event arrives

    await tester.pump(const Duration(seconds: 29));
    expect(env.api.scans, isEmpty);
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(env.api.scans, hasLength(1));
    expect(keyed('offline-result-card'), findsOneWidget);
  });

  testWidgets('coming back to the app sends what waits; in the background nothing is announced', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    env.api.clearFailure();
    env.voice.clear();
    await tester.pump(const Duration(minutes: 20)); // the timer is off in the background
    expect(env.api.scans, isEmpty);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(env.api.scans, hasLength(1));
    expect(env.voice.spokenIds, ['back_online_sent', 'offline_result_ready']);
  });

  testWidgets('the server refuses the queued scan (4xx): it is dropped and the farmer is told once', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    await pumpApp(tester, env, location: '/home');
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');

    env.api.failWith(unprocessable, ops: {'createScan'});
    env.voice.clear();
    await goOnline(tester, env);
    expect(env.voice.spokenIds, ['error_try_again']);
    expect(queueOf(tester).pending, 0);
    expect(keyed('offline-waiting-card'), findsNothing);
    expect(keyed('offline-result-card'), findsNothing);
    expect(
      env.api.calls.where((c) => c == 'createScan'),
      hasLength(2),
      reason: 'the live attempt and one queue attempt',
    );
  });

  testWidgets('a full queue (20 items) says error_try_again and keeps the retry button', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    final container = await pumpApp(tester, env, location: '/home');
    final queue = container.read(offlineQueueProvider);
    for (var i = 0; i < 20; i++) {
      await queue.enqueueSprayLog(SprayLogIn(cropId: 'apple', freeText: 'x$i'));
    }
    await tester.pumpAndSettle();

    await sendOnePhoto(tester, env);
    expect(env.voice.spokenIds.last, 'error_try_again');
    expect(keyed('retry-button'), findsOneWidget);
    expect(keyed('saved-home'), findsNothing);
    expect(queue.pending, 20);
  });

  testWidgets('another farmer on the same phone does not send the first farmer\'s photo', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    final container = await pumpApp(tester, env, location: '/home');
    await signIn(container); // F001 (mock farmer)
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');
    final queue = queueOf(tester) as PersistentOfflineQueue;
    expect(queue.pending, 1);

    env.api.clearFailure();
    await container.read(sessionProvider.notifier).logout();
    await tester.pumpAndSettle();
    await container
        .read(sessionProvider.notifier)
        .login(
          TokenOut(
            accessToken: 'a',
            refreshToken: 'r',
            expiresIn: 900,
            farmer: const FarmerOut(id: 'F999', name: 'Someone else', language: 'hi'),
          ),
        );
    await goOnline(tester, env);
    expect(env.api.scans, isEmpty, reason: 'it waits for its owner');
    expect(queue.pending, 1);
  });

  testWidgets('a result that is ready shows only for the farmer who sent it', (tester) async {
    useSmallPhone(tester);
    final env = await makeEnv();
    env.api.failWith(const ApiException.network(), ops: {'createScan'});
    final container = await pumpApp(tester, env, location: '/home');
    await signIn(container); // F001
    await sendOnePhoto(tester, env);
    await tapKey(tester, 'saved-home');
    env.api.clearFailure();
    await goOnline(tester, env);
    expect(keyed('offline-result-card'), findsOneWidget);

    TokenOut login(String id) => TokenOut(
      accessToken: 'a',
      refreshToken: 'r',
      expiresIn: 900,
      farmer: FarmerOut(id: id, name: 'Farmer $id', language: 'hi'),
    );
    await container.read(sessionProvider.notifier).logout();
    await tester.pumpAndSettle();
    await container.read(sessionProvider.notifier).login(login('F999'));
    container.read(routerProvider).go('/home');
    await tester.pumpAndSettle();
    expect(keyed('home-scan'), findsOneWidget);
    expect(keyed('offline-result-card'), findsNothing, reason: 'a result of another farmer');

    await container.read(sessionProvider.notifier).logout();
    await tester.pumpAndSettle();
    await container.read(sessionProvider.notifier).login(login('F001'));
    container.read(routerProvider).go('/home');
    await tester.pumpAndSettle();
    expect(keyed('offline-result-card'), findsOneWidget, reason: 'the owner gets it back');
  });

  testWidgets('Home cards fit a 320 x 568 phone at the largest text size', (tester) async {
    useSmallPhone(tester, size: const Size(320, 568), textScale: 2.0);
    final env = await TestEnv.create(
      loggedIn: true,
      extraOverrides: [
        offlineStatusProvider.overrideWith(
          () => _FixedStatus(
            OfflineStatus(
              pending: 12,
              ready: [
                ReadyResult(scanId: 'a', at: DateTime.now()),
                ReadyResult(scanId: 'b', at: DateTime.now()),
              ],
            ),
          ),
        ),
      ],
    );
    await tester.pumpWidget(env.wrap(const HomeScreen()));
    await tester.pumpAndSettle();
    expect(keyed('offline-result-card'), findsOneWidget);
    expect(keyed('offline-waiting-card'), findsOneWidget);
    expect(find.text('2'), findsOneWidget, reason: 'a count badge when several results wait');
    expect(tester.takeException(), isNull);
    expectBigTouchTargets(tester);
  });
}

class _FixedStatus extends OfflineStatusNotifier {
  _FixedStatus(this.fixed);

  final OfflineStatus fixed;

  @override
  OfflineStatus build() => fixed;
}
