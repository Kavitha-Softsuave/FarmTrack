import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/features/scan/scan_flow.dart';

import 'support/finders.dart';
import 'support/harness.dart';

class _BrokenFileApi extends MockApiClient {
  _BrokenFileApi() : super(latency: Duration.zero);

  @override
  Future<ScanOut> createScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
    String? idempotencyKey,
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  }) async => throw StateError('the photo file is gone');
}

void main() {
  testWidgets('the upload screen opened with no photos starts again at the camera', (tester) async {
    final env = await TestEnv.create(loggedIn: true);
    final container = await pumpApp(tester, env, location: '/home');
    container.read(routerProvider).go('/scan/uploading');
    await tester.pumpAndSettle();
    expect(keyed('camera-button'), findsOneWidget);
  });

  testWidgets('screens that need a scan, opened without one, go back to the start', (tester) async {
    final env = await TestEnv.create(loggedIn: true);
    final container = await pumpApp(tester, env, location: '/home');
    final router = container.read(routerProvider);
    for (final route in ['/scan/analysing?crop=apple', '/scan/confirm', '/scan/advice', '/scan/expert']) {
      router.go('/scan/review'); // somewhere that is not home
      await tester.pumpAndSettle();
      router.go(route);
      await tester.pumpAndSettle();
      expect(keyed('home-scan'), findsOneWidget, reason: route);
    }
  });

  testWidgets('a photo file that disappeared gives the error screen, not an endless wait', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true, api: _BrokenFileApi());
    env.picker.queuePhotos(1);
    await pumpApp(tester, env, location: '/home');
    await tapKey(tester, 'home-scan');
    await tapKey(tester, 'camera-button');
    env.voice.clear();
    await tapKey(tester, 'send-photos');
    expect(keyed('retry-button'), findsOneWidget);
    expect(env.voice.spokenIds.last, 'error_try_again');
    // The way back to the photos is the back arrow of the error screen.
    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();
    expect(keyed('send-photos'), findsOneWidget);
    expect(containerOf(tester).read(scanFlowProvider).phase, ScanPhase.idle);
  });

  testWidgets('starting a new scan while one is running ignores the old answer', (tester) async {
    final env = await TestEnv.create(loggedIn: true);
    final container = await pumpApp(tester, env, location: '/home');
    final flow = container.read(scanFlowProvider.notifier);
    flow.addPhoto('/tmp/a.jpg');
    final first = flow.submit();
    flow.reset(); // the farmer started over
    expect(await first, isNull);
    expect(container.read(scanFlowProvider).scan, isNull);
    expect(container.read(scanFlowProvider).photos, isEmpty);
  });
}
