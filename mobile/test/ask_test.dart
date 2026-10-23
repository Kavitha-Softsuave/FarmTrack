import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/features/ask/ask_flow.dart';
import 'package:farmtrack/features/ask/ask_suggestions.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// Remembers every question that reaches the server.
class _AskApi extends MockApiClient {
  _AskApi({super.latency = Duration.zero});

  final List<AskIn> asked = [];

  @override
  Future<AskOut> ask(AskIn question) {
    asked.add(question);
    return super.ask(question);
  }
}

/// A logged-in farmer. The suggestion cards come from the file directly: loading an asset in the middle of a widget
/// test depends on real time passing, which makes tests flaky (the real loader has its own test below).
Future<TestEnv> askEnv({String? language = 'hi', MockApiClient? api}) => TestEnv.create(
  language: language,
  loggedIn: true,
  api: api,
  extraOverrides: [askSuggestionsProvider.overrideWith((ref) => loadSuggestions())],
);

/// Opens [route] as the first screen (the app always starts at Home; `go` replaces it, like a deep link).
Future<ProviderContainer> openRoute(WidgetTester tester, TestEnv env, String route) async {
  final container = await pumpApp(tester, env, location: '/home');
  env.voice.clear(); // what Home said is not what the test is about
  container.read(routerProvider).go(route);
  await tester.pumpAndSettle();
  return container;
}

List<AskSuggestion> loadSuggestions() =>
    parseAskSuggestions(File('assets/l10n/ask_suggestions.json').readAsStringSync());

void main() {
  group('suggestion data (assets/l10n/ask_suggestions.json)', () {
    final suggestions = loadSuggestions();
    final catalogue = loadCatalogue();

    test('eight to ten cards, each with a label and a question in both languages and a known picture', () {
      expect(suggestions.length, inInclusiveRange(8, 10));
      expect(suggestions.map((s) => s.id).toSet(), hasLength(suggestions.length), reason: 'ids are unique');
      final raw =
          (jsonDecode(File('assets/l10n/ask_suggestions.json').readAsStringSync()) as Map)['suggestions'] as List;
      for (final s in raw.cast<Map>()) {
        expect(askIconNames, contains(s['icon']), reason: 'unknown picture ${s['icon']}');
      }
      for (final s in suggestions) {
        for (final lang in ['en', 'hi']) {
          expect(s.label.hasLang(lang), isTrue, reason: '${s.id} label $lang');
          expect(s.question.hasLang(lang), isTrue, reason: '${s.id} question $lang');
          expect(s.question.forLang(lang).length, lessThan(AskFlowNotifier.maxLength));
        }
      }
    });

    test('every card names a voice prompt whose text is exactly its question (so bundled audio can be used)', () {
      for (final s in suggestions) {
        expect(s.promptId, isNotNull, reason: s.id);
        expect(catalogue.contains(s.promptId!), isTrue, reason: '${s.promptId} is not in voice/prompts.json');
        for (final lang in ['en', 'hi']) {
          expect(catalogue.text(s.promptId!, lang), s.question.forLang(lang), reason: '${s.id} $lang');
        }
      }
    });

    test('no question asks for a medicine or a dose without naming a disease (the server refuses those)', () {
      final forbidden = RegExp(
        r'\b(dose|dosage|how much|which (medicine|fungicide|spray|pesticide|chemical)|what (medicine|fungicide|spray))\b',
        caseSensitive: false,
      );
      for (final s in suggestions) {
        expect(forbidden.hasMatch(s.question.en), isFalse, reason: s.question.en);
        expect(s.question.hi, isNot(contains('मात्रा')), reason: s.question.hi);
        expect(RegExp(r'[0-9०-९]').hasMatch(s.question.hi + s.label.hi), isFalse, reason: 'no digits in Hindi text');
      }
    });

    test('unusable cards (no question) are skipped and unknown pictures fall back to the question mark', () {
      final parsed = parseAskSuggestions(
        jsonEncode({
          'suggestions': [
            {
              'id': 'ok',
              'icon': 'no_such_picture',
              'label': {'en': 'A'},
              'question': {'en': 'Q?'},
            },
            {
              'id': 'broken',
              'label': {'en': 'B'},
            },
            'junk',
          ],
        }),
      );
      expect(parsed.map((s) => s.id), ['ok']);
      expect(parsed.single.icon, askIcon('nothing'));
    });
  });

  group('the Ask screen', () {
    testWidgets('speaks ask_intro and what to tap; ten big cards and a big own-question button', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await pumpApp(tester, env, location: '/home');
      env.voice.clear();
      await tapKey(tester, 'home-ask');
      expect(env.voice.spokenIds, ['ask_intro', 'ask_tap_picture']);
      expect(keyed('ask-own'), findsOneWidget);
      final first = suggestionsKeys();
      expect(first, hasLength(10));
      for (final key in first) {
        await tester.ensureVisible(keyed(key));
        final size = tester.getSize(keyed(key));
        expect(size.height, greaterThanOrEqualTo(96), reason: key);
        expect(size.width, greaterThanOrEqualTo(96), reason: key);
      }
      expect(tester.getSize(keyed('ask-own')).height, greaterThanOrEqualTo(96));
      expectBigTouchTargets(tester);
    });

    testWidgets('every picture button can be heard by a screen reader (Semantics labels)', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      final handle = tester.ensureSemantics();
      await openRoute(tester, env, '/ask');
      expect(find.bySemanticsLabel('अपना सवाल पूछें'), findsOneWidget);
      expect(find.bySemanticsLabel('छिड़काव के बाद बारिश'), findsOneWidget);
      expect(find.bySemanticsLabel('पीछे'), findsNothing, reason: 'opened as the first screen: no back arrow');
      handle.dispose();
    });

    testWidgets(
      'tapping a card speaks the question, sends it with the language and the main crop, then speaks the answer',
      (tester) async {
        useSmallPhone(tester);
        final api = _AskApi();
        final env = await askEnv(api: api);
        await pumpApp(tester, env, location: '/home');
        await tapKey(tester, 'home-ask');
        env.voice.clear();
        await tapKey(tester, 'ask-card-rain_after_spray');

        expect(api.asked, hasLength(1));
        expect(api.asked.single.question, 'छिड़काव के बाद बारिश हो जाए तो क्या करना चाहिए?');
        expect(api.asked.single.language, 'hi');
        expect(api.asked.single.cropId, 'apple', reason: 'the farmer\'s main crop');
        expect(env.voice.log, hasLength(2), reason: 'the question, then the answer (nothing in between with no wait)');
        expect(env.voice.log.first, 'ask_q_rain_after_spray@hi', reason: 'the question is spoken first');
        expect(
          env.voice.log.last,
          'सेब के स्कैब में सिर्फ़ मंज़ूर की हुई दवा छिड़किए और उसके साथ कोई और दवा मत मिलाइए।@hi',
        );
        expect(env.voice.unknownIds, isEmpty);
        // The answer is on screen as large text, the source small.
        expect(find.descendant(of: keyed('ask-answer'), matching: find.textContaining('अनुमोदित दवा')), findsOneWidget);
        expect(find.text('स्रोत: HP Horticulture Department 2026'), findsOneWidget);
        final answerStyle = tester
            .widget<Text>(find.descendant(of: keyed('ask-answer'), matching: find.byType(Text)))
            .style!;
        final sourceStyle = tester.widget<Text>(keyed('ask-sources')).style!;
        expect(answerStyle.fontSize, greaterThan(sourceStyle.fontSize!), reason: 'answer large, sources small');
        expect(keyed('voice-caption'), findsNothing, reason: 'the answer itself is the caption');
        expectBigTouchTargets(tester);
      },
    );

    testWidgets('in English the English question is sent and the answer is spoken in English', (tester) async {
      useSmallPhone(tester);
      final api = _AskApi();
      final env = await askEnv(language: 'en', api: api);
      await openRoute(tester, env, '/ask');
      env.voice.clear();
      await tapKey(tester, 'ask-card-scab_risk');
      expect(api.asked.single.question, 'When does apple scab spread?');
      expect(api.asked.single.language, 'en');
      expect(env.voice.log.first, 'ask_q_scab_risk@en');
      expect(env.voice.log.last, startsWith('For apple scab, spray only the approved medicine'));
      expect(env.voice.log.last, endsWith('@en'));
      expect(find.text('Source: HP Horticulture Department 2026'), findsOneWidget);
    });

    testWidgets('the speaker button says the answer again; back returns to the cards; the house goes Home', (
      tester,
    ) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await pumpApp(tester, env, location: '/home');
      await tapKey(tester, 'home-ask');
      await tapKey(tester, 'ask-card-mix_medicines');
      env.voice.clear();
      await tester.tap(keyed('speaker-button'));
      await tester.pump();
      expect(env.voice.log, hasLength(1));
      expect(env.voice.log.single, contains('@hi'));
      expect(env.voice.spokenTexts.single, contains('मंज़ूर की हुई दवा'));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('ask-own'), findsOneWidget);
      await tapKey(tester, 'ask-card-spray_gap');
      await tapKey(tester, 'ask-home');
      expect(keyed('home-scan'), findsOneWidget);
    });

    testWidgets(
      'while the server thinks: the question, then ask_wait, then the answer (the answer never cuts the question)',
      (tester) async {
        useSmallPhone(tester);
        final api = _AskApi(latency: const Duration(milliseconds: 400));
        final env = await askEnv(api: api);
        await openRoute(tester, env, '/ask');
        env.voice.clear();
        await tester.tap(keyed('ask-card-harvest_wait'));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 300));
        expect(keyed('ask-waiting-bar'), findsOneWidget);
        expect(env.voice.log, ['ask_q_harvest_wait@hi', 'ask_wait@hi']);

        await tester.pump(const Duration(seconds: 2));
        await tester.pump();
        expect(keyed('ask-answer'), findsOneWidget);
        expect(env.voice.log, hasLength(3));
        expect(env.voice.log.last, contains('सिर्फ़ मंज़ूर की हुई'));
      },
    );
  });

  group('typing your own question', () {
    Future<(TestEnv, _AskApi)> openTyping(WidgetTester tester, {String? language = 'hi'}) async {
      useSmallPhone(tester);
      final api = _AskApi();
      final env = await askEnv(language: language, api: api);
      await pumpApp(tester, env, location: '/home');
      await tapKey(tester, 'home-ask');
      env.voice.clear();
      await tapKey(tester, 'ask-own');
      return (env, api);
    }

    testWidgets('speaks ask_type_question; the green tick waits for at least two characters', (tester) async {
      await openTyping(tester);
      expect(find.byType(TextField), findsOneWidget);
      var tick = tester.widget<InkWell>(find.descendant(of: keyed('ask-send'), matching: find.byType(InkWell)));
      expect(tick.onTap, isNull, reason: 'nothing to send yet');
      await tester.enterText(keyed('ask-field'), 'a');
      await tester.pump();
      tick = tester.widget<InkWell>(find.descendant(of: keyed('ask-send'), matching: find.byType(InkWell)));
      expect(tick.onTap, isNull);
      await tester.enterText(keyed('ask-field'), 'ab');
      await tester.pump();
      tick = tester.widget<InkWell>(find.descendant(of: keyed('ask-send'), matching: find.byType(InkWell)));
      expect(tick.onTap, isNotNull);
      expectBigTouchTargets(tester);
    });

    testWidgets('the typed question goes to the server in the app language with the main crop; it is not read back', (
      tester,
    ) async {
      final (env, api) = await openTyping(tester, language: 'en');
      await tester.enterText(keyed('ask-field'), 'Why are my apple leaves curling?');
      await tester.pump();
      env.voice.clear();
      await tapKey(tester, 'ask-send');
      expect(api.asked.single.question, 'Why are my apple leaves curling?');
      expect(api.asked.single.language, 'en');
      expect(api.asked.single.cropId, 'apple');
      expect(env.voice.spokenIds.where((id) => id.startsWith('ask_q_')), isEmpty);
      expect(env.voice.spokenTexts, hasLength(1), reason: 'only the answer is spoken');
      expect(keyed('ask-answer'), findsOneWidget);
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(keyed('ask-own'), findsOneWidget, reason: 'back from the answer returns to the cards, not the keyboard');
    });

    testWidgets('at most 500 characters can be typed', (tester) async {
      await openTyping(tester);
      await tester.enterText(keyed('ask-field'), 'x' * 650);
      await tester.pump();
      expect(tester.widget<TextField>(keyed('ask-field')).controller!.text.length, 500);
      expect(find.text('500/500'), findsOneWidget);
    });

    testWidgets('speaks ask_tap_send after asking to type', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await openRoute(tester, env, '/ask/type');
      expect(env.voice.spokenIds, ['ask_type_question', 'ask_tap_send']);
    });
  });

  group('refused answers', () {
    testWidgets('a refusal is spoken and a big expert button sends the question to a farm expert', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await openRoute(tester, env, '/ask/type');
      await tester.enterText(keyed('ask-field'), 'Which lottery number is lucky?');
      await tester.pump();
      env.voice.clear();
      await tapKey(tester, 'ask-send');

      expect(env.voice.spokenTexts, ['इस सवाल का जवाब हमें नहीं मिला। कृपया खेती के जानकार से पूछिए।']);
      expect(find.byIcon(Icons.info_outline_rounded), findsOneWidget);
      expect(keyed('ask-expert'), findsOneWidget);
      expect(tester.getSize(keyed('ask-expert')).width, greaterThanOrEqualTo(96));

      env.voice.clear();
      await tapKey(tester, 'ask-expert');
      expect(env.api.expertRequests.single.message, 'Which lottery number is lucky?');
      expect(env.api.expertRequests.single.scanId, isNull, reason: 'a question, not a scan');
      expect(env.voice.spokenIds, ['ask_expert_sent']);
      expect(keyed('ask-expert-sent'), findsOneWidget);
      expect(find.text('सुरक्षित रख लिया'), findsOneWidget);
      expect(keyed('ask-expert'), findsNothing, reason: 'sent once');
    });

    testWidgets('the refusal text of the server is what is spoken and shown', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv(api: _RefusingApi());
      await openRoute(tester, env, '/ask');
      env.voice.clear();
      await tapKey(tester, 'ask-card-keep_healthy');
      expect(env.voice.spokenTexts, ['इसके लिए मेरे पास मंज़ूर की हुई सलाह नहीं है। कृपया जानकार से बात कीजिए।']);
      expect(find.text('I do not have approved advice for this. Please talk to an expert.'), findsOneWidget);
      expect(find.text('जवाब नहीं मिला'), findsOneWidget);
    });

    testWidgets('a refusal with no words at all says the ask_no_answer prompt', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv(api: _RefusingApi(withText: false));
      await openRoute(tester, env, '/ask');
      env.voice.clear();
      await tapKey(tester, 'ask-card-keep_healthy');
      expect(env.voice.spokenIds, ['ask_q_keep_healthy', 'ask_no_answer']);
      expect(keyed('ask-expert'), findsOneWidget);
      expect(keyed('ask-refusal'), findsNothing, reason: 'there is no text to show');
    });

    testWidgets('an expert request that fails speaks the error and keeps the button', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await openRoute(tester, env, '/ask/type');
      await tester.enterText(keyed('ask-field'), 'lottery please');
      await tester.pump();
      await tapKey(tester, 'ask-send');
      env.api.failWith(const ApiException.network(), ops: {'createExpertRequest'});
      env.voice.clear();
      await tapKey(tester, 'ask-expert');
      expect(env.voice.spokenIds, ['error_no_internet']);
      expect(keyed('ask-expert'), findsOneWidget);
      env.api.clearFailure();
      await tapKey(tester, 'ask-expert');
      expect(env.api.expertRequests, hasLength(1));
    });
  });

  group('errors', () {
    testWidgets('no internet: error_no_internet with one retry button; retry asks the same question again', (
      tester,
    ) async {
      useSmallPhone(tester);
      final api = _AskApi();
      final env = await askEnv(api: api);
      await openRoute(tester, env, '/ask');
      api.failWith(const ApiException.network(), times: 1, ops: {'ask'});
      env.voice.clear();
      await tapKey(tester, 'ask-card-fallen_leaves');
      expect(env.voice.spokenIds.last, 'error_no_internet');
      expect(keyed('retry-button'), findsOneWidget);
      expectBigTouchTargets(tester);

      env.voice.clear();
      await tapKey(tester, 'retry-button');
      expect(api.asked, hasLength(2));
      expect(api.asked.last.question, api.asked.first.question);
      expect(keyed('ask-answer'), findsOneWidget);
      expect(env.voice.spokenTexts, hasLength(1), reason: 'the answer is spoken once');
    });

    testWidgets('a server error says error_try_again', (tester) async {
      useSmallPhone(tester);
      final env = await askEnv();
      await openRoute(tester, env, '/ask');
      env.api.failWith(
        const ApiException(kind: ApiErrorKind.server, code: 'oops', statusCode: 500),
        ops: {'ask'},
      );
      env.voice.clear();
      await tapKey(tester, 'ask-card-same_chemical');
      expect(env.voice.spokenIds.last, 'error_try_again');
    });

    testWidgets('the answer screen opened with no question goes back to the cards', (tester) async {
      final env = await askEnv();
      await openRoute(tester, env, '/ask/answer');
      expect(keyed('ask-own'), findsOneWidget);
    });

    testWidgets('the ask flow ignores a question that is too short and cuts one that is too long', (tester) async {
      final env = await askEnv();
      final container = await pumpApp(tester, env, location: '/home');
      final flow = container.read(askFlowProvider.notifier);
      expect(await flow.ask(' x '), isNull);
      expect(container.read(askFlowProvider).phase, AskPhase.idle);
      await flow.ask('y' * 700);
      expect(container.read(askFlowProvider).question.length, 500);
      expect(container.read(askFlowProvider).phase, AskPhase.answered);
      expect(MockData.supportedCrops, contains('apple'));
    });
  });

  testWidgets('the real asset loader reads the same data file from the app bundle', (tester) async {
    expect(File('pubspec.yaml').readAsStringSync(), contains('- assets/l10n/'), reason: 'the whole folder is bundled');
    final loaded = await tester.runAsync(() => loadAskSuggestions(rootBundle));
    expect(loaded!.map((s) => s.id), loadSuggestions().map((s) => s.id));
  });
}

List<String> suggestionsKeys() => [for (final s in loadSuggestions()) 'ask-card-${s.id}'];

/// The refusal comes from the server with its own words.
class _RefusingApi extends MockApiClient {
  _RefusingApi({this.withText = true}) : super(latency: Duration.zero);

  final bool withText;

  @override
  Future<AskOut> ask(AskIn question) async => withText
      ? AskOut(
          answer: 'I do not have approved advice for this. Please talk to an expert.',
          language: question.language,
          refused: true,
          spoken: SpokenOut(
            text: LocalizedText.pair(
              en: 'I do not have approved advice for this. Please talk to an expert.',
              hi: 'इसके लिए मेरे पास मंज़ूर की हुई सलाह नहीं है। कृपया जानकार से बात कीजिए।',
            ),
          ),
        )
      : AskOut(language: question.language, refused: true);
}
