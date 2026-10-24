import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/offline/offline_status.dart';
import 'package:farmtrack/core/widgets/big_buttons.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/widgets/voice_scaffold.dart';
import 'package:farmtrack/features/home/home_screen.dart';

import 'diary_confirm_test.dart' show envWith, openConfirm;
import 'support/finders.dart';
import 'support/harness.dart';

/// The frame must leave the content as the main thing on a small phone with large text: one slim bar on top, the
/// speaker inside it, no footer, a caption that floats instead of taking a row.
class _Waiting extends OfflineStatusNotifier {
  @override
  OfflineStatus build() => const OfflineStatus(pending: 3);
}

void main() {
  const small = Size(320, 568);

  testWidgets('the frame: one slim bar on top holding the speaker, the content below, no footer', (tester) async {
    useSmallPhone(tester, size: small, textScale: 1.5);
    final env = await TestEnv.create();
    await tester.pumpWidget(
      env.wrap(
        VoiceScaffold(
          script: promptList(const ['welcome']),
          body: const SizedBox(key: ValueKey('content'), height: 40),
        ),
      ),
    );
    await tester.pump();
    final speaker = tester.getRect(keyed('speaker-button'));
    expect(speaker.top, lessThan(12), reason: 'the speaker sits in the top bar');
    expect(speaker.bottom, lessThan(80));
    // Everything under the bar is content: nothing reserved at the bottom (no action here).
    final content = tester.getRect(keyed('content'));
    expect(content.top, greaterThan(speaker.bottom - 8));
    final scroll = tester.getRect(find.byType(SingleChildScrollView).first);
    expect(scroll.bottom, greaterThan(small.height - 24), reason: 'no footer under the content');
    expect(scroll.height, greaterThan(small.height * 0.85), reason: 'the scrolling area is almost the whole screen');
  });

  testWidgets('with an action the only thing under the content is that action', (tester) async {
    useSmallPhone(tester, size: small, textScale: 1.5);
    final env = await TestEnv.create();
    await tester.pumpWidget(
      env.wrap(
        VoiceScaffold(
          script: promptList(const ['welcome']),
          body: const SizedBox(height: 40),
          bottomRight: const TickButton(semanticLabel: 'ok', onPressed: _noop),
        ),
      ),
    );
    await tester.pump();
    final scroll = tester.getRect(find.byType(SingleChildScrollView).first);
    expect(scroll.height, greaterThan(small.height * 0.7));
    final tick = tester.getRect(find.byType(TickButton));
    expect(tick.bottom, lessThanOrEqualTo(small.height));
    expect(tick.height, greaterThanOrEqualTo(56));
  });

  for (final scale in const [1.3, 1.5]) {
    testWidgets('Home at 320x568, text $scale: the four buttons are all on screen without scrolling', (tester) async {
      useSmallPhone(tester, size: small, textScale: scale);
      final env = await TestEnv.create(loggedIn: true, language: 'hi');
      await tester.pumpWidget(env.wrap(const HomeScreen()));
      await tester.pump();
      expect(tester.takeException(), isNull);
      for (final key in const ['home-scan', 'home-field', 'home-diary', 'home-ask']) {
        final r = tester.getRect(keyed(key));
        expect(r.bottom, lessThanOrEqualTo(small.height), reason: '$key is on screen');
        expect(r.top, greaterThanOrEqualTo(0));
        expect(r.height, greaterThanOrEqualTo(56));
      }
      final scan = tester.getRect(keyed('home-scan'));
      expect(scan.width, greaterThan(small.width - 40), reason: 'the photo button is the big one');
      expect(scan.height, greaterThan(tester.getRect(keyed('home-diary')).height));
      expectBigTouchTargets(tester);
    });
  }

  testWidgets('Home with a "waiting to send" card still shows the photo button', (tester) async {
    useSmallPhone(tester, size: small, textScale: 1.3);
    final env = await TestEnv.create(
      loggedIn: true,
      extraOverrides: [offlineStatusProvider.overrideWith(_Waiting.new)],
    );
    await tester.pumpWidget(env.wrap(const HomeScreen()));
    await tester.pump();
    expect(tester.takeException(), isNull);
    // The cards may push the lowest row down a little; the photo button must stay in view.
    expect(tester.getRect(keyed('home-scan')).bottom, lessThanOrEqualTo(small.height));
  });

  testWidgets('Advice at 320x568, text 1.5: the green tick is in view and the first view is short', (tester) async {
    final env = await envWith();
    await openConfirm(tester, env, textScale: 1.5, size: small);
    await tapKey(tester, 'diary-cancel');
    expect(tester.takeException(), isNull);
    final tick = tester.getRect(keyed('i-sprayed'));
    expect(tick.bottom, lessThanOrEqualTo(small.height));
    expect(tick.height, greaterThanOrEqualTo(56));
    expect(keyed('severity-yellow'), findsOneWidget);
    expect(tester.getRect(keyed('severity-yellow')).top, lessThan(120), reason: 'the band starts right under the bar');
    expect(keyed('advice-more'), findsOneWidget, reason: 'the details wait behind "More"');
    expect(keyed('advice-summary'), findsNothing);
    await tapKey(tester, 'advice-more');
    expect(tester.takeException(), isNull);
    expect(keyed('advice-summary'), findsOneWidget);
  });
}

void _noop() {}
