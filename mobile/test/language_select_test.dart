import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/l10n/app_resources.dart';
import 'package:farmtrack/features/onboarding/language_screen.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// The language list is data: a third language in `languages.json` gives a third button, with no code change.
void main() {
  const threeLanguages = '''
{
  "default_language": "hi",
  "languages": [
    {"code": "hi", "native_name": "हिन्दी", "prompt_id": "language_hindi", "badge": "अ", "tts_locales": ["hi-IN"]},
    {"code": "en", "native_name": "English", "prompt_id": "language_english", "badge": "A", "tts_locales": ["en-IN"]},
    {"code": "pa", "native_name": "ਪੰਜਾਬੀ", "tts_locales": ["pa-IN"]}
  ]
}''';

  AppResources resourcesWith(String languagesJson) => AppResources.fromJson(
    languagesJson: languagesJson,
    stringsJson: File('assets/l10n/strings.json').readAsStringSync(),
  );

  test('the shipped languages have a badge letter, and a missing badge falls back to the first letter', () {
    final shipped = loadResources();
    expect(shipped.languages.map((l) => l.badgeText), ['अ', 'A']);
    final custom = resourcesWith(threeLanguages);
    expect(custom.languages.map((l) => l.code), ['hi', 'en', 'pa']);
    expect(custom.languages.last.badgeText, 'ਪ', reason: 'the first letter of the native name');
    expect(custom.languages.last.promptId, isEmpty);
  });

  testWidgets('first launch: one huge button per language, each with its badge, in the data order', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true);
    await tester.pumpWidget(
      env.wrap(
        const Scaffold(
          body: SingleChildScrollView(child: LanguageButtons(onChosen: _noop)),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(keyed('language-hi'), findsOneWidget);
    expect(keyed('language-en'), findsOneWidget);
    expect(find.byKey(const ValueKey('language-badge-hi')), findsOneWidget);
    expect(find.text('अ'), findsOneWidget);
    expect(find.text('A'), findsOneWidget);
    expect(tester.getSize(keyed('language-hi')).height, greaterThanOrEqualTo(120));
  });

  testWidgets('three languages in the data: three buttons, stacked, the chosen one carries a tick', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true, resources: resourcesWith(threeLanguages));
    await tester.pumpWidget(
      env.wrap(
        const Scaffold(
          body: SingleChildScrollView(
            child: LanguageButtons(onChosen: _noop, selected: 'en', compact: true),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(keyed('language-pa'), findsOneWidget);
    expect(find.text('ਪੰਜਾਬੀ'), findsOneWidget);
    expect(keyed('language-selected-en'), findsOneWidget);
    expect(keyed('language-selected-hi'), findsNothing);
    // Stacked (not side by side): every button is as wide as the screen allows.
    expect(tester.getSize(keyed('language-hi')).width, tester.getSize(keyed('language-pa')).width);
    expect(tester.getTopLeft(keyed('language-pa')).dy, greaterThan(tester.getTopLeft(keyed('language-en')).dy));
    expect(tester.takeException(), isNull);
  });

  testWidgets('tapping a language applies it and speaks its name in its own voice before moving on', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true, language: 'hi');
    String? chosen;
    await tester.pumpWidget(
      env.wrap(
        Scaffold(
          body: LanguageButtons(
            onChosen: (code) async {
              chosen = code;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tapKey(tester, 'language-en');
    expect(chosen, 'en');
    expect(env.voice.log, ['language_english@en']);
    expect(env.prefs.getString('language'), 'en');
  });

  test('the shipped languages.json is valid JSON with unique codes', () {
    final json = jsonDecode(File('assets/l10n/languages.json').readAsStringSync()) as Map;
    final codes = [for (final l in json['languages'] as List) (l as Map)['code']];
    expect(codes.toSet(), hasLength(codes.length));
    expect(codes, contains(json['default_language']));
  });
}

Future<void> _noop(String code) async {}
