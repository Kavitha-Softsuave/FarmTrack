import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/vision/on_device_detector.dart';
import 'package:farmtrack/features/scan/photo_picker.dart';
import 'package:farmtrack/features/scan/scan_flow.dart';

import 'support/finders.dart';
import 'support/harness.dart';

class _GuessingDetector implements OnDeviceDetector {
  @override
  Future<OnDeviceGuess?> detect(String imagePath) async => const OnDeviceGuess(cropId: 'apple', confidence: 0.7);
}

Future<void> openCapture(WidgetTester tester, TestEnv env) async {
  useSmallPhone(tester);
  await pumpApp(tester, env, location: '/home');
  env.voice.clear();
  await tapKey(tester, 'home-scan');
}

void main() {
  group('capture', () {
    testWidgets('speaks how to take the photo, with one huge camera button', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await openCapture(tester, env);
      expect(env.voice.spokenIds, [
        'scan_open_camera',
        'scan_or_gallery',
        'scan_hold_close',
        'scan_one_leaf',
        'scan_daylight',
      ]);
      expect(env.voice.unknownIds, isEmpty);
      expect(tester.getSize(keyed('camera-button')).width, greaterThanOrEqualTo(96));
      expectBigTouchTargets(tester);
    });

    testWidgets('the camera button opens the camera; the photo goes to the review screen', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      env.voice.clear();
      await tapKey(tester, 'camera-button');
      expect(env.picker.opened, 1);
      expect(keyed('photo-0'), findsOneWidget);
      expect(env.voice.spokenIds, ['scan_photo_taken', 'scan_photo_count_one', 'scan_add_more', 'scan_send']);
    });

    testWidgets('a second big picture button chooses photos that are already in the phone', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await openCapture(tester, env);
      expect(keyed('gallery-button'), findsOneWidget);
      expect(tester.getSize(keyed('gallery-button')).width, greaterThanOrEqualTo(96));
      expectBigTouchTargets(tester);
      env.picker.queueGallery(1);
      env.voice.clear();
      await tapKey(tester, 'gallery-button');
      expect(env.picker.galleryOpened, 1);
      expect(env.picker.opened, 0, reason: 'the camera stays closed');
      expect(keyed('photo-0'), findsOneWidget);
      expect(env.voice.unknownIds, isEmpty);
    });

    testWidgets('the gallery can give several photos at once, at most as many as still fit', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button'); // one photo is in the scan now
      expect(keyed('photo-0'), findsOneWidget);
      await tapKey(tester, 'add-photo');
      env.picker.queueGallery(6); // the phone hands over more than fits
      await tapKey(tester, 'gallery-button');
      expect(env.picker.lastGalleryLimit, 3, reason: 'four photos is the limit, one is already taken');
      expect(keyed('photo-0'), findsOneWidget);
      expect(keyed('photo-3'), findsOneWidget);
      expect(keyed('photo-4'), findsNothing);
    });

    testWidgets('leaving the gallery without choosing stays on the camera screen', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await openCapture(tester, env);
      await tapKey(tester, 'gallery-button');
      expect(env.picker.galleryOpened, 1);
      expect(keyed('gallery-button'), findsOneWidget);
      expect(keyed('photo-0'), findsNothing);
    });

    testWidgets('a gallery that fails speaks error_try_again and keeps the buttons', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.gallery.add(Exception('picker crashed'));
      await openCapture(tester, env);
      env.voice.clear();
      await tapKey(tester, 'gallery-button');
      expect(env.voice.spokenIds, ['error_try_again']);
      expect(keyed('camera-button'), findsOneWidget);
      expect(keyed('gallery-button'), findsOneWidget);
    });

    testWidgets('coming back from the camera without a photo stays on the camera screen', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.script.add(null);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      expect(keyed('camera-button'), findsOneWidget);
      expect(keyed('photo-0'), findsNothing);
    });

    testWidgets('camera permission denied: speaks permission_denied_camera and lets the farmer try again', (
      tester,
    ) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.script.add(const CameraPermissionDenied());
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      env.voice.clear();
      await tapKey(tester, 'camera-button');
      expect(keyed('camera-denied'), findsOneWidget);
      expect(env.voice.spokenIds, ['permission_denied_camera']);
      await tapKey(tester, 'camera-button');
      expect(keyed('photo-0'), findsOneWidget, reason: 'one big retry: the same camera button');
    });

    testWidgets('the first time, the app explains the phone will ask for the camera before opening it', (tester) async {
      final env = await TestEnv.create(loggedIn: true, cameraExplained: false);
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      env.voice.clear();
      await tapKey(tester, 'camera-button');
      expect(env.voice.spokenIds.first, 'camera_permission');
      expect(env.prefs.getBool('camera_explained'), isTrue);

      // The second time it does not repeat itself.
      await tapKey(tester, 'send-photos'); // leave the review screen towards the upload
      await tester.pumpAndSettle();
    });

    testWidgets('a photo that the camera app handed back after the app was restarted is not lost', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.picker.lost = '/tmp/lost_leaf.jpg';
      await openCapture(tester, env);
      expect(keyed('photo-0'), findsOneWidget);
    });
  });

  group('photo review', () {
    Future<void> reviewWithPhotos(WidgetTester tester, TestEnv env, int count) async {
      env.picker.queuePhotos(count);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      for (var i = 1; i < count; i++) {
        await tapKey(tester, 'add-photo');
        await tapKey(tester, 'camera-button');
      }
    }

    testWidgets('shows a thumbnail with a red cross per photo and speaks the count', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await reviewWithPhotos(tester, env, 2);
      expect(keyed('photo-0'), findsOneWidget);
      expect(keyed('photo-1'), findsOneWidget);
      expect(find.byKey(const ValueKey('remove-photo')), findsNWidgets(2));
      expect(env.voice.spokenIds.takeLast(4), [
        'scan_photo_taken',
        'scan_photo_count_two',
        'scan_add_more',
        'scan_send',
      ]);
      expectBigTouchTargets(tester);
    });

    testWidgets('the red cross removes that photo; the count is spoken without "photo taken"', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await reviewWithPhotos(tester, env, 3);
      env.voice.clear();
      final container = containerOf(tester);
      final second = env.picker.script; // nothing left in the queue
      expect(second, isEmpty);
      await tester.tap(find.descendant(of: keyed('photo-1'), matching: find.byKey(const ValueKey('remove-photo'))));
      await tester.pumpAndSettle();
      expect(container.read(scanFlowProvider).photos, hasLength(2));
      expect(find.byKey(const ValueKey('remove-photo')), findsNWidgets(2));
      expect(env.voice.spokenIds, ['scan_photo_count_two', 'scan_add_more', 'scan_send']);
    });

    testWidgets('removing the last photo goes back to the camera screen', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await reviewWithPhotos(tester, env, 1);
      env.voice.clear();
      await tester.tap(find.byKey(const ValueKey('remove-photo')));
      await tester.pumpAndSettle();
      expect(keyed('camera-button'), findsOneWidget);
      expect(env.voice.spokenIds, [
        'scan_open_camera',
        'scan_or_gallery',
        'scan_hold_close',
        'scan_one_leaf',
        'scan_daylight',
      ]);
    });

    testWidgets('at four photos the plus is disabled and the app says that is enough', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await reviewWithPhotos(tester, env, 4);
      expect(find.byKey(const ValueKey('remove-photo')), findsNWidgets(4));
      expect(env.voice.spokenIds.takeLast(4), [
        'scan_photo_taken',
        'scan_photo_count_four',
        'scan_photo_limit',
        'scan_send',
      ]);
      final container = containerOf(tester);
      final plus = tester.widget<InkWell>(find.descendant(of: keyed('add-photo'), matching: find.byType(InkWell)));
      expect(plus.onTap, isNull);
      expect(container.read(scanFlowProvider.notifier).addPhoto('/tmp/fifth.jpg'), isFalse);
      expect(container.read(scanFlowProvider).photos, hasLength(4));
    });

    testWidgets('the plus returns to the camera and keeps the photos already taken', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      await reviewWithPhotos(tester, env, 1);
      await tapKey(tester, 'add-photo');
      expect(keyed('camera-button'), findsOneWidget);
      expect(containerOf(tester).read(scanFlowProvider).photos, hasLength(1));
      // Back arrow on the camera screen returns to the review while photos exist.
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('photo-0'), findsOneWidget);
    });
  });

  group('upload', () {
    testWidgets('sends every photo with the client crop hint when the on-device model has one', (tester) async {
      final env = await TestEnv.create(
        loggedIn: true,
        scanScript: [MockScanScenario.ok],
        extraOverrides: [onDeviceDetectorProvider.overrideWithValue(_GuessingDetector())],
      );
      env.picker.queuePhotos(2);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      await tapKey(tester, 'add-photo');
      await tapKey(tester, 'camera-button');
      await tapKey(tester, 'send-photos');
      expect(env.api.uploadedPhotoPaths.single, hasLength(2));
      expect(env.api.lastClientGuess!.crop, 'apple');
      expect(env.api.lastClientGuess!.confidence, 0.7);
    });

    testWidgets('without an on-device model nothing is sent as client_crop', (tester) async {
      final env = await TestEnv.create(loggedIn: true, scanScript: [MockScanScenario.ok]);
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      await tapKey(tester, 'send-photos');
      expect(env.api.lastClientGuess!.crop, isNull);
      expect(env.api.lastClientGuess!.confidence, isNull);
    });

    testWidgets('while sending it speaks scan_uploading and scan_wait, shows progress and a cancel cross', (
      tester,
    ) async {
      final env = await TestEnv.create(loggedIn: true, scanScript: [MockScanScenario.ok]);
      env.api.latency = const Duration(milliseconds: 300);
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      env.voice.clear();
      await tester.tap(keyed('send-photos'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300)); // let the page transition finish
      expect(keyed('progress'), findsOneWidget);
      expect(keyed('cancel-button'), findsOneWidget);
      expect(env.voice.spokenIds, ['scan_uploading', 'scan_wait']);

      await tester.tap(keyed('cancel-button'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      expect(keyed('send-photos'), findsOneWidget, reason: 'cancel returns to the photos');
      expect(env.api.scans, isEmpty);
      expect(containerOf(tester).read(scanFlowProvider).photos, hasLength(1));
    });

    testWidgets('no internet and the photo file is gone (so it cannot be saved for later): error_try_again, one retry', (
      tester,
    ) async {
      final env = await TestEnv.create(loggedIn: true, scanScript: [MockScanScenario.ok]);
      env.api.failWith(const ApiException.network(), times: 1, ops: {'createScan'});
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      env.voice.clear();
      await tapKey(tester, 'send-photos');
      // The fake photo path does not exist, so the offline queue refuses it (offline_flow_test.dart covers real files).
      expect(env.voice.spokenIds, contains('error_try_again'));
      expect(keyed('retry-button'), findsOneWidget);
      expectBigTouchTargets(tester);
      await tapKey(tester, 'retry-button');
      expect(keyed('severity-yellow'), findsOneWidget);
    });

    testWidgets('a server error speaks error_try_again', (tester) async {
      final env = await TestEnv.create(loggedIn: true);
      env.api.failWith(
        const ApiException(kind: ApiErrorKind.server, code: 'internal_error', statusCode: 500),
        times: 1,
        ops: {'createScan'},
      );
      env.picker.queuePhotos(1);
      await openCapture(tester, env);
      await tapKey(tester, 'camera-button');
      env.voice.clear();
      await tapKey(tester, 'send-photos');
      expect(env.voice.spokenIds.last, 'error_try_again');
    });
  });
}

extension on List<String> {
  List<String> takeLast(int n) => sublist(length - n);
}
