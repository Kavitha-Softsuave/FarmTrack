import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/widgets/big_buttons.dart';
import 'package:farmtrack/features/diary/date_words.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// The real server writes crop ids with a capital (`Apple`): in the crop list and in the farmer's own crops.
class _ServerCaseApi extends MockApiClient {
  _ServerCaseApi() : super(latency: Duration.zero);

  static String cap(String id) => '${id[0].toUpperCase()}${id.substring(1)}';

  @override
  Future<MetaOut> meta() async =>
      MetaOut(env: 'mock', supportedCrops: [for (final c in MockData.supportedCrops) cap(c)]);

  @override
  Future<FarmerOut> me() async {
    final farmer = MockData.farmer();
    return FarmerOut(
      id: farmer.id,
      name: farmer.name,
      language: farmer.language,
      crops: [for (final c in farmer.crops) cap(c)],
      primaryCrop: 'Apple',
    );
  }
}

Future<TestEnv> addEnv({
  MockApiClient? api,
  FakeOfflineQueue? queue,
  String language = 'hi',
  List<String> earlier = const [],
}) async {
  final mock = api ?? MockApiClient(latency: Duration.zero);
  for (final (i, name) in earlier.indexed) {
    await mock.createSprayLog(SprayLogIn(cropId: 'apple', freeText: name, sprayedAt: DateTime.utc(2026, 5, 1 + i, 12)));
  }
  return TestEnv.create(
    loggedIn: true,
    language: language,
    api: mock,
    extraOverrides: [
      clockProvider.overrideWithValue(() => fixedNow),
      if (queue != null) offlineQueueProvider.overrideWithValue(queue),
    ],
  );
}

/// Home, the diary, the plus button. Afterwards the voice log holds what the crop step said.
Future<void> openAdd(WidgetTester tester, TestEnv env, {double textScale = 1.0, Size? size}) async {
  useSmallPhone(tester, textScale: textScale, size: size ?? const Size(360, 640));
  await pumpApp(tester, env, location: '/home');
  await tapKey(tester, 'home-diary');
  env.voice.clear();
  await tapKey(tester, 'diary-add');
}

Future<void> typeName(WidgetTester tester, String name) async {
  await tester.enterText(keyed('diary-name-field'), name);
  await tester.pumpAndSettle();
}

void main() {
  group('write a spray: crop, medicine, day', () {
    testWidgets('the farmer\'s own crops come first, as big pictures; the prompt is spoken', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      expect(env.voice.spokenIds, ['diary_pick_crop']);
      final apple = tester.getTopLeft(keyed('crop-apple'));
      final potato = tester.getTopLeft(keyed('crop-potato'));
      final tomato = tester.getTopLeft(keyed('crop-tomato'));
      // The demo farmer grows apple and potato: the first row; tomato comes on the next row.
      expect(potato.dy, apple.dy);
      expect(tomato.dy, greaterThan(apple.dy));
      expectBigTouchTargets(tester);
    });

    testWidgets('crop ids with a capital, as the server writes them, still get the Hindi name and the right picture', (
      tester,
    ) async {
      final env = await addEnv(api: _ServerCaseApi());
      await openAdd(tester, env);
      // Own crops first, once each (the server lists them again), in the app's own words.
      expect(find.descendant(of: keyed('crop-Apple'), matching: find.text('सेब')), findsOneWidget);
      expect(find.descendant(of: keyed('crop-Potato'), matching: find.text('आलू')), findsOneWidget);
      expect(find.descendant(of: keyed('crop-Apple'), matching: find.byIcon(Icons.park_rounded)), findsOneWidget);
      expect(find.descendant(of: keyed('crop-Potato'), matching: find.byIcon(Icons.eco_rounded)), findsOneWidget);
      expect(find.byKey(const ValueKey('crop-apple')), findsNothing);

      await tapKey(tester, 'crop-Potato');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      expect(find.text('आलू'), findsWidgets);
      await tapKey(tester, 'diary-save');
      expect(env.api.sprayLogsIn.single.cropId, 'Potato', reason: 'the id is sent as the server listed it');
    });

    testWidgets('the whole way: crop, typed name, confirm, save, warnings, back to the list', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);

      await tapKey(tester, 'crop-apple');
      expect(env.voice.spokenIds, ['diary_pick_crop', 'diary_type_medicine']);
      expect(keyed('diary-name-field'), findsOneWidget);
      // The tick waits for a name.
      expect(tester.widget<TickButton>(keyed('diary-next')).onPressed, isNull);

      await typeName(tester, 'Mancozeb');
      expect(tester.widget<TickButton>(keyed('diary-next')).onPressed, isNotNull);
      env.voice.clear();
      await tapKey(tester, 'diary-next');
      expect(env.voice.spokenTexts, ['Mancozeb']);
      expect(env.voice.spokenIds, ['diary_tap_save']);
      expect(find.descendant(of: keyed('diary-medicine-name'), matching: find.text('Mancozeb')), findsOneWidget);
      expect(keyed('diary-cancel'), findsNothing, reason: 'nothing to refuse: the farmer wrote this spray down');
      expectBigTouchTargets(tester);

      env.voice.clear();
      await tapKey(tester, 'diary-save');
      final sent = env.api.sprayLogsIn.single;
      expect(sent.cropId, 'apple');
      expect(sent.freeText, 'Mancozeb');
      expect(sent.adviceId, isNull);
      expect(sent.productId, isNull);
      expect(sent.sprayedAt, isNull);
      expect(keyed('saved-ok'), findsOneWidget);
      // The mock server warns about a medicine that may be banned: card with picture and words, and spoken.
      expect(keyed('warning-proposed_ban'), findsOneWidget);
      expect(
        find.descendant(of: keyed('warning-proposed_ban'), matching: find.byIcon(Icons.warning_amber_rounded)),
        findsOneWidget,
      );
      expect(find.descendant(of: keyed('warning-proposed_ban'), matching: find.text('सावधान')), findsOneWidget);
      expect(env.voice.spokenTexts.single, contains('जल्द रोक लग सकती है'));

      // Done: back to the list, which shows the new entry.
      await tapKey(tester, 'diary-done');
      expect(keyed('diary-add'), findsOneWidget);
      expect(keyed('diary-entry-log-1'), findsOneWidget);
      expect(find.descendant(of: keyed('diary-entry-log-1'), matching: find.text('Mancozeb')), findsOneWidget);
    });

    testWidgets('a medicine that is not in the list gets the yellow "not recognised" card', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-potato');
      await typeName(tester, 'Mystery Spray 5');
      await tapKey(tester, 'diary-next');
      await tapKey(tester, 'diary-save');
      expect(env.api.sprayLogsIn.single.cropId, 'potato');
      final card = keyed('warning-PRODUCT_NOT_RECOGNISED');
      expect(card, findsOneWidget);
      expect(find.descendant(of: card, matching: find.text('सावधान')), findsOneWidget);
      expect(find.descendant(of: card, matching: find.textContaining('सूची में नहीं मिली')), findsOneWidget);
    });

    testWidgets('an off-label medicine gets a red card with its own picture', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Miravis Duo');
      await tapKey(tester, 'diary-next');
      await tapKey(tester, 'diary-save');
      final card = keyed('warning-off_label');
      expect(find.descendant(of: card, matching: find.byIcon(Icons.report_rounded)), findsOneWidget);
      expect(find.descendant(of: card, matching: find.text('गंभीर')), findsOneWidget);
    });

    testWidgets('a medicine without warnings: only diary_saved, no card', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      env.voice.clear();
      await tapKey(tester, 'diary-save');
      expect(env.voice.spokenIds, ['diary_saved']);
      expect(find.byIcon(Icons.warning_amber_rounded), findsNothing);
    });

    testWidgets('the name is limited to 200 characters', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'x' * 250);
      final field = tester.widget<TextField>(keyed('diary-name-field'));
      expect(field.maxLength, 200);
      expect(field.controller!.text.length, 200);
      expect(field.keyboardType, TextInputType.text);
    });

    testWidgets(
      'names used before are big buttons, newest first, without repeats; one tap goes to the confirm screen',
      (tester) async {
        final env = await addEnv(earlier: ['Score', 'Antracol', 'score', 'Mancozeb']);
        await openAdd(tester, env);
        await tapKey(tester, 'crop-apple');
        // Newest first: Mancozeb (4 May), then Score (3 May, the same name as the 1 May one), then Antracol.
        expect(find.descendant(of: keyed('recent-0'), matching: find.text('Mancozeb')), findsOneWidget);
        expect(find.descendant(of: keyed('recent-1'), matching: find.text('score')), findsOneWidget);
        expect(find.descendant(of: keyed('recent-2'), matching: find.text('Antracol')), findsOneWidget);
        expect(keyed('recent-3'), findsNothing);
        expectBigTouchTargets(tester);

        env.voice.clear();
        await tapKey(tester, 'recent-2');
        expect(env.voice.spokenTexts, ['Antracol']);
        expect(env.voice.spokenIds, ['diary_tap_save']);
        await tapKey(tester, 'diary-save');
        expect(env.api.sprayLogsIn.last.freeText, 'Antracol');
      },
    );

    testWidgets('the speaker button on the medicine screen also reads the "or tap a name" hint when names exist', (
      tester,
    ) async {
      final env = await addEnv(earlier: ['Score']);
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      env.voice.clear();
      await tapKey(tester, 'speaker-button');
      expect(env.voice.spokenIds, ['diary_type_medicine', 'diary_pick_recent']);
    });

    testWidgets('the day: yesterday and another day work in this flow too', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      await tapKey(tester, 'day-other');
      await tapKey(tester, 'day-option-9');
      expect(find.descendant(of: keyed('day-other'), matching: find.text('3 मई')), findsOneWidget);
      await tapKey(tester, 'diary-save');
      final local = env.api.sprayLogsIn.single.sprayedAt!.toLocal();
      expect((local.month, local.day), (5, 3));
      // The saved screen shows the day in words.
      expect(find.textContaining('3 मई'), findsOneWidget);
    });

    testWidgets('the back arrow walks back one step at a time', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      await tapKey(tester, 'day-other');
      expect(keyed('day-option-0'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('diary-save'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('diary-name-field'), findsOneWidget);
      expect(tester.widget<TextField>(keyed('diary-name-field')).controller!.text, 'Score');
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('crop-apple'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('diary-add'), findsOneWidget);
      expect(env.api.sprayLogsIn, isEmpty);
    });

    testWidgets('crops are paged with big arrows; every crop of the server can be chosen', (tester) async {
      final env = await addEnv();
      await openAdd(tester, env);
      expect(keyed('crops-next'), findsOneWidget);
      expect(keyed('crops-prev'), findsNothing);
      await tapKey(tester, 'crops-next');
      expect(keyed('crops-prev'), findsOneWidget);
      expect(keyed('crop-apple'), findsNothing);
      expectBigTouchTargets(tester);
      await tapKey(tester, 'crops-prev');
      expect(keyed('crop-apple'), findsOneWidget);
    });

    testWidgets('english: words, speech and the day names', (tester) async {
      final env = await addEnv(language: 'en');
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      expect(find.text('Today'), findsOneWidget);
      await tapKey(tester, 'diary-save');
      expect(find.text('Saved'), findsOneWidget);
      expect(find.textContaining('Today, 12 May'), findsOneWidget);
    });
  });

  group('write a spray without internet', () {
    testWidgets('it waits in the queue with a date, says so, and the entry shows as waiting in the list', (
      tester,
    ) async {
      final api = MockApiClient(latency: Duration.zero);
      final queue = FakeOfflineQueue();
      final env = await addEnv(api: api, queue: queue);
      await openAdd(tester, env);
      await tapKey(tester, 'crop-apple');
      await typeName(tester, 'Score');
      await tapKey(tester, 'diary-next');
      api.failWith(const ApiException.network(), ops: {'createSprayLog'});
      env.voice.clear();
      await tapKey(tester, 'diary-save');
      expect(env.voice.spokenIds, ['diary_saved_offline']);
      expect(keyed('saved-offline'), findsOneWidget);
      final queued = queue.sprayLogs.single.log;
      expect(queued.freeText, 'Score');
      expect(queued.sprayedAt, isNotNull);

      api.clearFailure();
      await tapKey(tester, 'diary-done');
      final entry = keyed('diary-entry-${queue.sprayLogs.single.key}');
      expect(entry, findsOneWidget);
      expect(find.descendant(of: entry, matching: find.text('भेजना बाकी है')), findsOneWidget);
    });
  });

  group('layout', () {
    for (final (name, size, scale) in [
      ('320x568', const Size(320, 568), 1.0),
      ('360x640 at 1.6x text', const Size(360, 640), 1.6),
      ('320x568 at 1.6x text', const Size(320, 568), 1.6),
    ]) {
      testWidgets('every step fits on $name', (tester) async {
        final env = await addEnv(earlier: ['Score', 'Antracol', 'Mancozeb']);
        await openAdd(tester, env, textScale: scale, size: size);
        expect(tester.takeException(), isNull);
        await tapKey(tester, 'crop-apple');
        expect(tester.takeException(), isNull);
        expectBigTouchTargets(tester);
        await typeName(tester, 'A long medicine name that needs more than one line to be shown on a small phone');
        expect(tester.takeException(), isNull);
        await tapKey(tester, 'diary-next');
        expect(tester.takeException(), isNull);
        final tick = tester.getRect(keyed('diary-save'));
        expect(tick.bottom, lessThanOrEqualTo(size.height));
        await tapKey(tester, 'diary-save');
        expect(tester.takeException(), isNull);
        expect(keyed('saved-ok'), findsOneWidget);
        expectBigTouchTargets(tester);
      });
    }
  });

  test('the utterances of the add flow carry no digits', () {
    // Dates are spoken as words everywhere: 1..31 and the 12 months, in both languages.
    final env = loadResources();
    for (final lang in ['en', 'hi']) {
      final words = DateWords((key) => env.t(key, lang));
      final spoken = TextUtterance(words.spoken(DateTime(2026, 5, 30)), lang: lang);
      expect(spoken.text, isNot(matches(RegExp(r'\d'))));
    }
  });
}
