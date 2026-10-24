import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/voice/speak_on_enter.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/widgets/voice_scaffold.dart';

import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  testWidgets('speaks the script once when the screen appears, not again on rebuilds', (tester) async {
    final env = await TestEnv.create();
    Widget build() =>
        env.wrap(SpeakOnEnter(script: promptList(const ['welcome', 'scan_send']), child: const SizedBox()));
    await tester.pumpWidget(build());
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome', 'scan_send']);

    await tester.pumpWidget(build());
    await tester.pump();
    await tester.pumpWidget(build());
    await tester.pump();
    expect(env.voice.calls, hasLength(1));
  });

  testWidgets('speaks again when restartKey changes, and when it becomes enabled', (tester) async {
    final env = await TestEnv.create();
    Widget build({required Object key, bool enabled = true, List<String> ids = const ['welcome']}) =>
        env.wrap(SpeakOnEnter(script: promptList(ids), restartKey: key, enabled: enabled, child: const SizedBox()));

    await tester.pumpWidget(build(key: 1, enabled: false));
    await tester.pump();
    expect(env.voice.calls, isEmpty, reason: 'disabled screens say nothing');

    await tester.pumpWidget(build(key: 1));
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome']);

    await tester.pumpWidget(build(key: 2, ids: const ['scan_send']));
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome', 'scan_send']);
  });

  testWidgets('leaving a screen stops its own speech but never the speech of the screen that replaced it', (
    tester,
  ) async {
    final env = await TestEnv.create();
    var showFirst = true;
    late StateSetter update;
    await tester.pumpWidget(
      env.wrap(
        StatefulBuilder(
          builder: (context, setState) {
            update = setState;
            return Column(
              children: [
                if (showFirst)
                  SpeakOnEnter(
                    key: const ValueKey('first'),
                    script: promptList(const ['welcome']),
                    child: const SizedBox(),
                  ),
                SpeakOnEnter(
                  key: const ValueKey('second'),
                  script: promptList(const ['scan_send']),
                  child: const SizedBox(),
                ),
              ],
            );
          },
        ),
      ),
    );
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome', 'scan_send']);

    update(() => showFirst = false); // the first screen goes away while the second is the one speaking
    await tester.pump();
    expect(env.voice.stopCalls, 0, reason: 'the second screen owns the speech');
    expect(env.voice.state.value.caption, isNotEmpty);

    await tester.pumpWidget(env.wrap(const SizedBox())); // now the second screen goes away too
    expect(env.voice.stopCalls, 1);
    expect(env.voice.state.value.caption, isNull);
  });

  testWidgets('VoiceScaffold shows the spoken sentence as a caption; captions can be switched off', (tester) async {
    final env = await TestEnv.create();
    await tester.pumpWidget(env.wrap(VoiceScaffold(script: promptList(const ['scan_send']), body: const Text('body'))));
    await tester.pump();
    expect(keyed('voice-caption'), findsOneWidget);
    expect(find.textContaining('हरा सही का निशान'), findsOneWidget);

    final container = containerOf(tester);
    await container.read(settingsProvider.notifier).setCaptions(on: false);
    await tester.pump();
    expect(keyed('voice-caption'), findsNothing);
  });

  testWidgets('the caption floats over the content and is one line until tapped; it goes when the speech ends', (
    tester,
  ) async {
    useSmallPhone(tester);
    final env = await TestEnv.create();
    final long = List.filled(12, 'Spray the whole tree on a dry morning.').join(' ');
    await tester.pumpWidget(
      env.wrap(
        VoiceScaffold(
          script: [TextUtterance(long, lang: 'en')],
          body: const SizedBox(height: 900),
        ),
      ),
    );
    await tester.pump();
    final caption = keyed('voice-caption');
    expect(caption, findsOneWidget);
    final collapsed = tester.getSize(caption);
    expect(collapsed.height, lessThan(70), reason: 'one line only: the content keeps the room');

    await tester.tap(caption);
    await tester.pump();
    expect(tester.getSize(caption).height, greaterThan(collapsed.height), reason: 'a tap opens the whole sentence');
    await tester.tap(caption);
    await tester.pump();
    expect(tester.getSize(caption).height, collapsed.height);

    env.voice.finishSpeaking();
    await tester.pump();
    expect(caption, findsNothing, reason: 'nothing stays under the content once it has been said');
  });

  testWidgets('the speaker button is the right-most button of the slim top bar and replays the screen speech', (
    tester,
  ) async {
    useSmallPhone(tester);
    final env = await TestEnv.create();
    await tester.pumpWidget(
      env.wrap(
        VoiceScaffold(
          script: promptList(const ['welcome']),
          replayScript: promptList(const ['welcome', 'scan_send']),
          body: const Text('body'),
        ),
      ),
    );
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome']);

    final box = tester.getRect(keyed('speaker-button'));
    expect(box.right, greaterThan(360 - 40), reason: 'top-right');
    expect(box.top, lessThan(40), reason: 'in the slim top bar, not in a footer');
    expect(box.width, greaterThanOrEqualTo(56));

    await tester.tap(keyed('speaker-button'));
    await tester.pump();
    expect(env.voice.spokenIds, ['welcome', 'welcome', 'scan_send']);
  });

  testWidgets('a screen that speaks in answer to a tap uses its own owner, so the caption shows', (tester) async {
    final env = await TestEnv.create();
    final owner = Object();
    await tester.pumpWidget(
      env.wrap(VoiceScaffold(owner: owner, script: promptList(const ['welcome']), body: const Text('b'))),
    );
    await tester.pump();
    await env.voice.speak(promptList(const ['login_wrong']), owner: owner);
    await tester.pump();
    expect(find.textContaining('पासवर्ड सही नहीं है'), findsOneWidget);
  });

  testWidgets('a missing voice shows a banner so the words can still be read', (tester) async {
    final env = await TestEnv.create();
    await tester.pumpWidget(env.wrap(VoiceScaffold(script: promptList(const ['welcome']), body: const Text('b'))));
    await tester.pump();
    expect(keyed('voice-missing'), findsNothing);
    env.voice.markVoiceMissing('hi');
    await tester.pump();
    expect(keyed('voice-missing'), findsOneWidget);
  });
}
