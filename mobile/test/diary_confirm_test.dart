import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/features/diary/date_words.dart';
import 'package:farmtrack/features/diary/diary_providers.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// A mock server whose scan answer is the one the test builds.
class _ScanApi extends MockApiClient {
  _ScanApi(this.scan) : super(latency: Duration.zero);

  final ScanOut scan;

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
  }) async {
    calls.add('createScan');
    scans[scan.id] = scan;
    return scan;
  }
}

/// An ok scan whose advice has two medicines.
ScanOut twoMedicineScan() {
  final base = MockData.scabAdvice('scan-1');
  final product = base.products.single;
  return ScanOut.fromJson({
    ...MockData.okScan('scan-1').toJson(),
    'advice': {
      ...base.toJson(),
      'products': [
        product.toJson(),
        {
          ...product.toJson(),
          'product_id': 'P006',
          'active_ingredient': {'en': 'Propineb', 'hi': 'प्रोपीनेब'},
          'brand_examples': ['Antracol'],
          'dose_text': {'en': 'Two grams in one litre of water.', 'hi': 'एक लीटर पानी में दो ग्राम।'},
        },
      ],
    },
  });
}

Future<TestEnv> envWith({MockApiClient? api, FakeOfflineQueue? queue, String language = 'hi', bool loggedIn = true}) =>
    TestEnv.create(
      loggedIn: loggedIn,
      language: language,
      api: api ?? MockApiClient(latency: Duration.zero, scanScript: [MockScanScenario.ok]),
      extraOverrides: [
        clockProvider.overrideWithValue(() => fixedNow),
        if (queue != null) offlineQueueProvider.overrideWithValue(queue),
      ],
    );

/// Scan one leaf, then tap "I sprayed" on the advice. Afterwards the voice log holds the confirm screen's speech.
Future<void> openConfirm(WidgetTester tester, TestEnv env, {double textScale = 1.0, Size? size}) async {
  useSmallPhone(tester, textScale: textScale, size: size ?? const Size(360, 640));
  env.picker.queuePhotos(1);
  await pumpApp(tester, env, location: '/home');
  await tapKey(tester, 'home-scan');
  await tapKey(tester, 'camera-button');
  await tapKey(tester, 'send-photos');
  env.voice.clear();
  await tapKey(tester, 'i-sprayed');
}

void main() {
  group('the confirm screen after "I sprayed"', () {
    testWidgets('shows the crop picture, the medicine and a big tick and cross; speaks name, question, tick, cross', (
      tester,
    ) async {
      final env = await envWith();
      await openConfirm(tester, env);

      expect(keyed('diary-crop-name'), findsOneWidget);
      expect(find.text('सेब'), findsWidgets);
      expect(keyed('diary-product-P007'), findsOneWidget);
      expect(find.text('डिफेनोकोनाज़ोल'), findsOneWidget);
      expect(keyed('diary-save'), findsOneWidget);
      expect(keyed('diary-cancel'), findsOneWidget);
      expect(env.voice.spokenTexts, ['डिफेनोकोनाज़ोल, Score']);
      expect(env.voice.spokenIds, ['diary_did_spray', 'diary_tick_sprayed', 'diary_cross_back']);
      // The name comes first, then the question.
      expect(env.voice.log.first, startsWith('डिफेनोकोनाज़ोल, Score'));
      expect(env.voice.unknownIds, isEmpty);
      expectBigTouchTargets(tester);
    });

    testWidgets(
      'the tick saves the advice (one medicine: no product id) with a fresh idempotency key and speaks diary_saved',
      (tester) async {
        final env = await envWith();
        await openConfirm(tester, env);
        env.voice.clear();
        await tapKey(tester, 'diary-save');

        final sent = env.api.sprayLogsIn.single;
        expect(sent.cropId, 'apple');
        expect(sent.adviceId, 'adv-scan-1');
        expect(
          sent.productId,
          isNull,
          reason: 'only one medicine: the advice id alone means the one that was read out',
        );
        expect(sent.freeText, isNull);
        expect(sent.sprayedAt, isNull, reason: 'today: the server uses its own clock');
        expect(env.api.idempotencyKeys.last, matches(RegExp(r'^[0-9a-f]{32}$')));
        expect(keyed('saved-ok'), findsOneWidget);
        expect(env.voice.spokenIds, ['diary_saved']);
        expect(find.byType(FilledButton), findsNothing);
        expectBigTouchTargets(tester);
      },
    );

    testWidgets('the cross goes back to the advice and saves nothing', (tester) async {
      final env = await envWith();
      await openConfirm(tester, env);
      await tapKey(tester, 'diary-cancel');
      expect(keyed('i-sprayed'), findsOneWidget);
      expect(env.api.sprayLogsIn, isEmpty);
    });

    testWidgets('several medicines: big cards, the tapped one speaks its name and dose and is the one saved', (
      tester,
    ) async {
      final env = await envWith(api: _ScanApi(twoMedicineScan()));
      await openConfirm(tester, env);

      expect(keyed('diary-product-P007'), findsOneWidget);
      expect(keyed('diary-product-P006'), findsOneWidget);
      expect(env.voice.spokenIds, ['diary_pick_product', 'diary_did_spray', 'diary_tick_sprayed', 'diary_cross_back']);
      expect(env.voice.spokenTexts, isEmpty);
      env.voice.clear();

      await tapKey(tester, 'diary-product-P006');
      expect(env.voice.spokenTexts, ['प्रोपीनेब, Antracol', 'एक लीटर पानी में दो ग्राम।']);
      expect(
        find.descendant(of: keyed('diary-product-P006'), matching: find.byIcon(Icons.check_rounded)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: keyed('diary-product-P007'), matching: find.byIcon(Icons.check_rounded)),
        findsNothing,
      );
      expectBigTouchTargets(tester);

      await tapKey(tester, 'diary-save');
      expect(env.api.sprayLogsIn.single.productId, 'P006', reason: 'the farmer picked one of several: send it');
      expect(env.api.sprayLogsIn.single.adviceId, 'adv-scan-1');
    });

    testWidgets('yesterday: spoken, saved with yesterday\'s date at noon', (tester) async {
      final env = await envWith();
      await openConfirm(tester, env);
      env.voice.clear();
      await tapKey(tester, 'day-yesterday');
      expect(env.voice.spokenIds, ['diary_yesterday']);
      await tapKey(tester, 'diary-save');
      final day = env.api.sprayLogsIn.single.sprayedAt!;
      expect(day.isUtc, isTrue);
      final local = day.toLocal();
      expect((local.year, local.month, local.day, local.hour), (2026, 5, 11, 12));
    });

    testWidgets('today again after yesterday sends no date', (tester) async {
      final env = await envWith();
      await openConfirm(tester, env);
      await tapKey(tester, 'day-yesterday');
      await tapKey(tester, 'day-today');
      await tapKey(tester, 'diary-save');
      expect(env.api.sprayLogsIn.single.sprayedAt, isNull);
    });

    testWidgets(
      'another day: the last fourteen days as big buttons, dates in words, the choice is spoken without digits',
      (tester) async {
        final env = await envWith();
        await openConfirm(tester, env);
        env.voice.clear();
        await tapKey(tester, 'day-other');
        expect(env.voice.spokenIds, ['diary_other_day', 'diary_pick_date']);
        for (var back = 0; back < 14; back++) {
          expect(keyed('day-option-$back'), findsOneWidget, reason: 'day $back');
        }
        expect(keyed('day-option-14'), findsNothing);
        expect(find.text('12 मई'), findsOneWidget);
        expect(find.text('29 अप्रैल'), findsOneWidget);
        expectBigTouchTargets(tester);

        env.voice.clear();
        await tapKey(tester, 'day-option-5');
        // 12 May minus five days: the seventh, spoken in words.
        expect(env.voice.spokenTexts, ['सात मई']);
        expect(env.voice.spokenTexts.single, isNot(matches(RegExp(r'\d'))));
        expect(keyed('diary-save'), findsOneWidget);
        expect(find.descendant(of: keyed('day-other'), matching: find.text('7 मई')), findsOneWidget);

        await tapKey(tester, 'diary-save');
        final local = env.api.sprayLogsIn.single.sprayedAt!.toLocal();
        expect((local.month, local.day), (5, 7));
      },
    );

    testWidgets('an older day button sends that day; picking today or yesterday in the chooser selects those buttons', (
      tester,
    ) async {
      final env = await envWith();
      await openConfirm(tester, env);
      await tapKey(tester, 'day-other');
      await tapKey(tester, 'day-option-1');
      expect(env.voice.spokenIds.last, 'diary_yesterday');
      await tapKey(tester, 'diary-save');
      expect(env.api.sprayLogsIn.single.sprayedAt!.toLocal().day, 11);
    });

    testWidgets('english: everything is read and spoken in English', (tester) async {
      final env = await envWith(language: 'en');
      await openConfirm(tester, env);
      expect(find.text('Apple'), findsWidgets);
      expect(find.text('Today'), findsOneWidget);
      expect(find.text('Yesterday'), findsOneWidget);
      expect(env.voice.spokenTexts, ['Difenoconazole, Score']);
      await tapKey(tester, 'day-other');
      await tapKey(tester, 'day-option-3');
      expect(env.voice.spokenTexts.last, 'nine May');
      expect(find.descendant(of: keyed('day-other'), matching: find.text('9 May')), findsOneWidget);
    });
  });

  group('warnings after saving', () {
    SprayLogOut twoWarnings(SprayLogIn log) => SprayLogOut(
      id: 'log-1',
      cropId: log.cropId,
      productId: 'P007',
      productName: 'Difenoconazole (Score)',
      warnings: [
        WarningOut(
          code: 'off_label',
          level: Severity.red,
          text: LocalizedText.pair(en: 'Not allowed on this crop.', hi: 'इस फसल पर मंज़ूर नहीं है।'),
        ),
        WarningOut(
          code: 'too_soon',
          level: Severity.yellow,
          text: LocalizedText.pair(en: 'You sprayed this a few days ago.', hi: 'आपने कुछ दिन पहले यही छिड़का था।'),
        ),
      ],
      spoken: SpokenOut(
        text: LocalizedText.pair(
          en: 'Done. It is saved in your diary. Please listen carefully. There is a warning about this medicine. Not allowed on this crop.',
          hi: 'हो गया। डायरी में लिख लिया। ध्यान से सुनिए। इस दवा के बारे में एक चेतावनी है। इस फसल पर मंज़ूर नहीं है।',
        ),
        audio: {'hi': const AudioRef(url: '/audio/saved_hi.mp3', sha256: 'abc')},
      ),
    );

    testWidgets(
      'every warning is a card with colour, picture and words, and is spoken: first from the server text, then the rest',
      (tester) async {
        final env = await envWith(api: ScriptedSprayApi(twoWarnings));
        await openConfirm(tester, env);
        env.voice.clear();
        await tapKey(tester, 'diary-save');

        // Speech: the server's spoken text (with its audio, it already holds "Done" and the first warning), then warning two.
        expect(env.voice.spoken, hasLength(2));
        final first = env.voice.spoken.first as TextUtterance;
        expect(first.text, contains('इस फसल पर मंज़ूर नहीं है।'));
        expect(first.audio!.url, '/audio/saved_hi.mp3');
        expect((env.voice.spoken.last as TextUtterance).text, 'आपने कुछ दिन पहले यही छिड़का था।');

        // Cards: colour (border), a picture of its own, and words.
        final red = keyed('warning-off_label');
        final yellow = keyed('warning-too_soon');
        expect(red, findsOneWidget);
        expect(yellow, findsOneWidget);
        expect(find.descendant(of: red, matching: find.byIcon(Icons.report_rounded)), findsOneWidget);
        expect(find.descendant(of: red, matching: find.text('गंभीर')), findsOneWidget);
        expect(find.descendant(of: red, matching: find.text('इस फसल पर मंज़ूर नहीं है।')), findsOneWidget);
        expect(find.descendant(of: yellow, matching: find.byIcon(Icons.warning_amber_rounded)), findsOneWidget);
        expect(find.descendant(of: yellow, matching: find.text('सावधान')), findsOneWidget);
        expect(find.descendant(of: yellow, matching: find.text('आपने कुछ दिन पहले यही छिड़का था।')), findsOneWidget);
        final decoration = tester.widget<Container>(red).decoration! as BoxDecoration;
        expect(decoration.color, isNot(Colors.white));
        expect(decoration.border, isNotNull);
        expectBigTouchTargets(tester);
      },
    );

    testWidgets('each card has a speaker button that says only that warning', (tester) async {
      final env = await envWith(api: ScriptedSprayApi(twoWarnings));
      await openConfirm(tester, env);
      await tapKey(tester, 'diary-save');
      env.voice.clear();
      await tapKey(tester, 'warning-speak-too_soon');
      expect(env.voice.spokenTexts, ['आपने कुछ दिन पहले यही छिड़का था।']);
      env.voice.clear();
      await tapKey(tester, 'warning-speak-off_label');
      expect(env.voice.spokenTexts, ['इस फसल पर मंज़ूर नहीं है।']);
    });

    testWidgets('without a usable server text: diary_saved, diary_warning, then every warning text', (tester) async {
      final env = await envWith(
        api: ScriptedSprayApi(
          (log) => SprayLogOut(
            id: 'log-1',
            cropId: log.cropId,
            warnings: [
              WarningOut(
                code: 'a_one',
                level: Severity.yellow,
                text: LocalizedText.pair(en: 'One.', hi: 'पहली।'),
              ),
              WarningOut(
                code: 'b_two',
                level: Severity.red,
                text: LocalizedText.pair(en: 'Two.', hi: 'दूसरी।'),
              ),
            ],
          ),
        ),
      );
      await openConfirm(tester, env);
      env.voice.clear();
      await tapKey(tester, 'diary-save');
      expect(env.voice.log, ['diary_saved@hi', 'diary_warning@hi', 'पहली।@hi', 'दूसरी।@hi']);
    });

    testWidgets('a saved entry without warnings says only diary_saved and shows no warning card', (tester) async {
      final env = await envWith();
      await openConfirm(tester, env);
      env.voice.clear();
      await tapKey(tester, 'diary-save');
      expect(env.voice.log, ['diary_saved@hi']);
      expect(find.byIcon(Icons.report_rounded), findsNothing);
    });
  });

  group('no internet and errors', () {
    testWidgets('offline: the entry waits in the queue, speaks diary_saved_offline and shows as waiting in the diary', (
      tester,
    ) async {
      final keys = <String?>[];
      final api = _FlakySprayApi(keys, failures: 99, error: const ApiException.network());
      final queue = FakeOfflineQueue();
      final env = await envWith(api: api, queue: queue);
      await openConfirm(tester, env);
      env.voice.clear();
      await tapKey(tester, 'diary-save');

      expect(env.voice.spokenIds, ['diary_saved_offline']);
      expect(keyed('saved-offline'), findsOneWidget);
      expect(find.text('भेजना बाकी है'), findsOneWidget);
      expect(queue.sprayLogs.single.key, keys.single, reason: 'the queued retry carries the key of the live attempt');
      final queued = queue.sprayLogs.single.log;
      expect(queued.adviceId, 'adv-scan-1');
      expect(queued.cropId, 'apple');
      expect(
        queued.sprayedAt,
        isNotNull,
        reason: 'today is stamped now, or the server would use the day it is finally sent',
      );
      expect(queued.sprayedAt!.toLocal().day, 12);

      // The diary list marks it as waiting.
      await tapKey(tester, 'diary-done'); // back to Home
      await tapKey(tester, 'home-diary');
      final entry = keyed('diary-entry-${queue.sprayLogs.single.key}');
      expect(entry, findsOneWidget);
      expect(find.descendant(of: entry, matching: find.text('भेजना बाकी है')), findsOneWidget);
      expect(find.descendant(of: entry, matching: find.byIcon(Icons.schedule_rounded)), findsOneWidget);
      expect(find.descendant(of: entry, matching: find.textContaining('Score')), findsOneWidget);
    });

    testWidgets('a server error shows the error screen; retry sends the same key and then saves', (tester) async {
      final api = MockApiClient(latency: Duration.zero, scanScript: [MockScanScenario.ok]);
      final env = await envWith(api: api);
      await openConfirm(tester, env);
      api.failWith(
        const ApiException(kind: ApiErrorKind.server, code: 'oops', statusCode: 500),
        times: 1,
        ops: {'createSprayLog'},
      );
      env.voice.clear();
      await tapKey(tester, 'diary-save');
      expect(keyed('retry-button'), findsOneWidget);
      expect(env.voice.spokenIds, ['error_try_again']);
      expect(api.sprayLogsIn, isEmpty);

      await tapKey(tester, 'retry-button');
      expect(keyed('saved-ok'), findsOneWidget);
      expect(api.sprayLogsIn, hasLength(1));
    });

    testWidgets('the retry after a failure reuses the idempotency key', (tester) async {
      final keys = <String?>[];
      final env = await envWith(api: _FlakySprayApi(keys));
      await openConfirm(tester, env);
      await tapKey(tester, 'diary-save');
      expect(keyed('retry-button'), findsOneWidget);
      await tapKey(tester, 'retry-button');
      expect(keyed('saved-ok'), findsOneWidget);
      expect(keys, hasLength(2));
      expect(keys.first, isNotNull);
      expect(keys.first, keys.last);
    });
  });

  group('layout', () {
    for (final (name, size, scale) in [
      ('320x568', const Size(320, 568), 1.0),
      ('360x640 at 1.6x text', const Size(360, 640), 1.6),
      ('320x568 at 1.6x text', const Size(320, 568), 1.6),
    ]) {
      testWidgets('confirm and saved screens do not overflow on $name', (tester) async {
        final env = await envWith(api: _ScanApi(twoMedicineScan()));
        await openConfirm(tester, env, textScale: scale, size: size);
        expect(tester.takeException(), isNull);
        expect(keyed('diary-save'), findsOneWidget);
        await tester.ensureVisible(keyed('diary-save'));
        // The tick is always on screen, never hidden below the fold.
        final tick = tester.getRect(keyed('diary-save'));
        expect(tick.bottom, lessThanOrEqualTo(size.height));
        expect(tick.top, greaterThanOrEqualTo(0));
        await tapKey(tester, 'day-other');
        expect(tester.takeException(), isNull);
        await tapKey(tester, 'day-option-2');
        expect(tester.takeException(), isNull);
        await tapKey(tester, 'diary-save');
        expect(tester.takeException(), isNull);
        expect(keyed('saved-ok'), findsOneWidget);
      });
    }
  });

  group('dates and entries', () {
    test('a day in words: written with digits, spoken without', () {
      final env = loadResources();
      final words = DateWords((key) => env.t(key, 'en'));
      expect(words.written(DateTime(2026, 5, 12)), '12 May');
      expect(words.spoken(DateTime(2026, 5, 12)), 'twelve May');
      expect(words.spoken(DateTime(2026, 12, 31)), 'thirty one December');
      expect(words.weekday(DateTime(2026, 5, 12)), 'Tuesday');
      final hi = DateWords((key) => env.t(key, 'hi'));
      expect(hi.spoken(DateTime(2026, 10, 1)), 'एक अक्टूबर');
    });

    test('every day and month of the year has a word in both languages (no digits in anything spoken)', () {
      final env = loadResources();
      for (final lang in ['en', 'hi']) {
        final words = DateWords((key) => env.t(key, lang));
        for (var month = 1; month <= 12; month++) {
          for (var day = 1; day <= 28; day++) {
            expect(
              words.spoken(DateTime(2026, month, day)),
              isNot(matches(RegExp(r'\d'))),
              reason: '$lang $month/$day',
            );
          }
        }
        expect(words.spoken(DateTime(2026, 1, 29)), isNot(matches(RegExp(r'\d'))));
        expect(words.spoken(DateTime(2026, 1, 30)), isNot(matches(RegExp(r'\d'))));
        expect(words.spoken(DateTime(2026, 1, 31)), isNot(matches(RegExp(r'\d'))));
      }
    });

    test('daysAgo counts calendar days, whatever the time of day', () {
      final now = DateTime(2026, 5, 12, 0, 5);
      expect(daysAgo(DateTime(2026, 5, 12, 23, 59), now), 0);
      expect(daysAgo(DateTime(2026, 5, 11, 23, 59), now), 1);
      expect(daysAgo(DateTime(2026, 4, 28), now), 14);
      expect(daysAgo(DateTime(2026, 5, 13), now), -1);
    });

    test(
      'entries: newest day first, waiting ones before server ones of the same day, recent names without repeats',
      () {
        final now = DateTime(2026, 5, 12, 9);
        final server = [
          SprayLogOut(id: 's1', cropId: 'apple', productName: 'Score', sprayedAt: DateTime(2026, 5, 12, 8)),
          SprayLogOut(id: 's2', cropId: 'apple', productName: 'score', sprayedAt: DateTime(2026, 5, 10, 8)),
          SprayLogOut(id: 's3', cropId: 'apple', productName: 'Mancozeb', sprayedAt: DateTime(2026, 5, 1, 8)),
        ];
        final pending = [
          PendingSpray(
            key: 'k1',
            log: SprayLogIn(cropId: 'apple', sprayedAt: DateTime(2026, 5, 12, 7)),
            name: 'Antracol',
          ),
          PendingSpray(
            key: 'k2',
            log: SprayLogIn(cropId: 'apple', sprayedAt: DateTime(2026, 5, 11, 7)),
            name: '',
          ),
        ];
        final entries = mergeDiaryEntries(server, pending, now);
        expect([for (final e in entries) e.id], ['k1', 's1', 'k2', 's2', 's3']);
        expect(entries.first.pending, isTrue);
        expect(recentMedicineNames(entries), ['Antracol', 'Score', 'Mancozeb']);
        expect(recentMedicineNames(entries, limit: 2), ['Antracol', 'Score']);
      },
    );
  });
}

/// A server that fails the first call after seeing its key, then saves.
class _FlakySprayApi extends MockApiClient {
  _FlakySprayApi(
    this.keys, {
    this.failures = 1,
    this.error = const ApiException(kind: ApiErrorKind.server, code: 'oops', statusCode: 500),
  }) : super(latency: Duration.zero, scanScript: [MockScanScenario.ok]);

  final List<String?> keys;

  /// How many calls fail, and with what.
  final int failures;
  final ApiException error;

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) {
    keys.add(idempotencyKey);
    if (keys.length <= failures) throw error;
    return super.createSprayLog(log, idempotencyKey: idempotencyKey);
  }
}
