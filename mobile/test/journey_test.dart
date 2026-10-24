import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/network/mock_api_client.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// Walks through every screen of the app on small phones and at large text sizes. Any overflow, layout error or
/// exception fails the test; every screen must also keep its touch targets at 56 dp or more.
void main() {
  const profiles = [
    (name: 'text scale 1.5 on a 360x640 phone', size: Size(360, 640), scale: 1.5),
    (name: 'text scale 1.0 on a 320x568 phone', size: Size(320, 568), scale: 1.0),
    (name: 'text scale 1.6 on a 411x891 phone', size: Size(411, 891), scale: 1.6),
  ];

  for (final profile in profiles) {
    testWidgets('every screen works at ${profile.name}', (tester) async {
      useSmallPhone(tester, size: profile.size, textScale: profile.scale);
      final env = await TestEnv.create(
        language: null,
        homeTourDone: false,
        cameraExplained: false,
        scanScript: [
          MockScanScenario.confirmCrop,
          MockScanScenario.photoBlurry,
          MockScanScenario.needsExpert,
          MockScanScenario.noApprovedData,
        ],
      );
      await pumpApp(tester, env);
      void targets() => expectBigTouchTargets(tester);

      // first launch
      expect(keyed('language-hi'), findsOneWidget);
      targets();
      await tapKey(tester, 'language-hi');
      targets();
      await tapKey(tester, 'welcome-continue');

      // login
      targets();
      await enterLogin(tester, username: 'f001', password: 'farm1234');
      await tapKey(tester, 'login-eye');
      targets();
      await tapKey(tester, 'login-submit');

      // home and settings
      expect(keyed('home-scan'), findsOneWidget);
      targets();
      await tapKey(tester, 'home-settings');
      targets();
      await tapKey(tester, 'speed-slow');
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      for (final key in ['home-field', 'home-diary', 'home-ask', 'home-alerts']) {
        await tapKey(tester, key);
        targets();
        await tester.tap(find.byIcon(Icons.arrow_back_rounded));
        await tester.pumpAndSettle();
      }

      // scan: camera, two photos, confirm crop -> grid -> advice
      env.picker.queuePhotos(3);
      await tapKey(tester, 'home-scan');
      targets();
      await tapKey(tester, 'camera-button');
      targets();
      await tapKey(tester, 'add-photo');
      await tapKey(tester, 'camera-button');
      targets();
      await tapKey(tester, 'send-photos');
      targets();
      await tapKey(tester, 'crop-no');
      targets();
      await tapKey(tester, 'crops-next');
      targets();
      await tapKey(tester, 'crops-prev');
      await tapKey(tester, 'crop-apple');
      expect(keyed('severity-yellow'), findsOneWidget);
      targets();
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      // blurry photo, expert case, no data
      await tapKey(tester, 'home-scan');
      await tapKey(tester, 'camera-button');
      await tapKey(tester, 'send-photos');
      expect(keyed('retake-camera'), findsOneWidget);
      targets();
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();

      for (final status in ['needs_expert', 'no_approved_data']) {
        env.picker.queuePhotos(1);
        await tapKey(tester, 'home-scan');
        await tapKey(tester, 'camera-button');
        await tapKey(tester, 'send-photos');
        expect(keyed('expert-icon-$status'), findsOneWidget);
        targets();
        await tapKey(tester, 'ask-expert');
        targets();
        await tester.tap(find.byIcon(Icons.arrow_back_rounded));
        await tester.pumpAndSettle();
      }
      expect(env.voice.unknownIds, isEmpty, reason: 'every spoken prompt id exists');
    });
  }
}
