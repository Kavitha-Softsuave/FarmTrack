import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_status.dart';
import 'package:farmtrack/features/home/home_screen.dart';
import 'package:farmtrack/core/theme/app_theme.dart';
import 'package:farmtrack/features/diary/diary_providers.dart';

import 'diary_confirm_test.dart' show envWith, openConfirm;
import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// The advice screen's "I sprayed" must match what the voice says ("tap the green tick"), and after the entry is
/// written it must look DONE (green tick, "Sprayed"), never yellow. Only an entry still waiting for the internet is
/// grey ("waiting"). Yellow is for warnings only.
class _TwoWaiting extends OfflineStatusNotifier {
  @override
  OfflineStatus build() => const OfflineStatus(pending: 2);
}

class _OfflineSprayApi extends MockApiClient {
  _OfflineSprayApi() : super(latency: Duration.zero, scanScript: [MockScanScenario.ok]);

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) => throw const ApiException.network();
}

Color? _fill(WidgetTester tester, String key) {
  final material = tester.widget<Material>(find.descendant(of: keyed(key), matching: find.byType(Material)).first);
  return material.color;
}

void main() {
  testWidgets('before spraying, "I sprayed" on the advice is the green tick the voice talks about, not yellow', (
    tester,
  ) async {
    final env = await envWith();
    await openConfirm(tester, env); // scan, advice, tap "I sprayed" -> confirm screen
    await tapKey(tester, 'diary-cancel'); // the red cross: back to the advice, nothing written

    final button = keyed('i-sprayed');
    expect(button, findsOneWidget);
    expect(find.descendant(of: button, matching: find.byIcon(AppIcons.tick)), findsOneWidget);
    expect(find.descendant(of: button, matching: find.byIcon(AppIcons.notebook)), findsNothing);
    expect(_fill(tester, 'i-sprayed'), AppColors.green);
    expect(find.byIcon(AppIcons.notebook), findsNothing, reason: 'no yellow notebook on the advice any more');
    expect(keyed('sprayed-done'), findsNothing);
    expect(keyed('sprayed-waiting'), findsNothing);
    // The sentence that names the tick is spoken.
    expect(env.voice.spokenIds, isNot(contains('result_next_diary')));
  });

  testWidgets('after the entry is saved the advice shows a green "Sprayed" mark and the tick is gone', (tester) async {
    final env = await envWith();
    await openConfirm(tester, env);
    await tapKey(tester, 'diary-save');
    expect(keyed('saved-ok'), findsOneWidget);
    expect(containerOf(tester).read(sprayStateProvider('adv-scan-1')), SprayState.done);

    // Home: the last advice carries the green tick; opening it shows the advice as done.
    await tapKey(tester, 'diary-done');
    expect(keyed('last-result-sprayed'), findsOneWidget);
    env.voice.clear();
    await tapKey(tester, 'last-result-card');
    final done = keyed('sprayed-done');
    expect(done, findsOneWidget);
    expect(keyed('i-sprayed'), findsNothing, reason: 'it was sprayed: nothing left to tick');
    final chip = tester.widget<Container>(done);
    expect((chip.decoration! as BoxDecoration).color, AppColors.green);
    expect(find.descendant(of: done, matching: find.byIcon(AppIcons.tick)), findsOneWidget);
    expect(find.text('छिड़काव हो गया'), findsOneWidget);
    // Nothing yellow in the action row, and the "next step" sentence is not spoken again.
    expect(env.voice.spokenIds, isNot(contains('diary_tick_sprayed')));
  });

  testWidgets('the sprayed mark is kept in the phone preferences, so it survives a restart', (tester) async {
    final env = await envWith();
    await openConfirm(tester, env);
    await tapKey(tester, 'diary-save');
    await tester.pump();
    final keys = env.prefs.getKeys().where((k) => k.startsWith('sprayed_advices_')).toList();
    expect(keys, hasLength(1));
    expect(env.prefs.getStringList(keys.single), ['adv-scan-1']);
  });

  testWidgets('saved with no internet: grey "waiting", never yellow; green once it was sent', (tester) async {
    final queue = FakeOfflineQueue();
    final env = await envWith(api: _OfflineSprayApi(), queue: queue);
    await openConfirm(tester, env);
    await tapKey(tester, 'diary-save');
    expect(keyed('saved-offline'), findsOneWidget);
    expect(containerOf(tester).read(sprayStateProvider('adv-scan-1')), SprayState.waiting);

    await tapKey(tester, 'diary-done');
    await tapKey(tester, 'last-result-card');
    expect(keyed('sprayed-waiting'), findsOneWidget);
    expect(keyed('sprayed-done'), findsNothing);
    final chip = tester.widget<Container>(keyed('sprayed-waiting'));
    expect((chip.decoration! as BoxDecoration).color, AppColors.inkSoft);
    expect(find.descendant(of: keyed('sprayed-waiting'), matching: find.byIcon(AppIcons.clock)), findsOneWidget);
  });

  testWidgets('the "waiting to send" card of Home is grey, not yellow', (tester) async {
    final env = await TestEnv.create(
      loggedIn: true,
      extraOverrides: [offlineStatusProvider.overrideWith(_TwoWaiting.new)],
    );
    await tester.pumpWidget(env.wrap(const HomeScreen()));
    await tester.pump();
    final card = tester.widget<Material>(
      find.descendant(of: keyed('offline-waiting-card'), matching: find.byType(Material)).first,
    );
    expect(card.color, AppColors.neutralSoft);
    expect(card.color, isNot(AppColors.amberSoft));
  });
}
