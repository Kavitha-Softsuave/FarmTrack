import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_status.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/theme/app_theme.dart';
import 'package:farmtrack/core/widgets/demo_clock_banner.dart';
import 'package:farmtrack/features/ask/ask_answer_screen.dart';
import 'package:farmtrack/features/ask/ask_flow.dart';
import 'package:farmtrack/features/ask/ask_screen.dart';
import 'package:farmtrack/features/ask/ask_suggestions.dart';
import 'package:farmtrack/features/ask/ask_type_screen.dart';
import 'package:farmtrack/features/home/home_screen.dart';
import 'package:farmtrack/features/offline/saved_offline_screen.dart';
import 'package:farmtrack/features/settings/logout_confirm_screen.dart';
import 'package:farmtrack/features/settings/settings_screen.dart';

import 'support/finders.dart';
import 'support/harness.dart';

class _FixedAsk extends AskFlowNotifier {
  _FixedAsk(this.fixed);

  final AskState fixed;

  @override
  AskState build() => fixed;
}

class _FixedStatus extends OfflineStatusNotifier {
  @override
  OfflineStatus build() => OfflineStatus(
    pending: 12,
    ready: [
      ReadyResult(scanId: 'a', at: DateTime.now()),
      ReadyResult(scanId: 'b', at: DateTime.now()),
    ],
  );
}

class _LoggedIn extends SessionNotifier {
  @override
  SessionState build() => const SessionState(SessionStatus.loggedIn, FarmerOut(id: 'F001', name: 'Ramesh'));
}

class _DemoApi extends MockApiClient {
  _DemoApi() : super(latency: Duration.zero);

  @override
  Future<MetaOut> meta() async =>
      MetaOut(appVersion: '0.1.0', env: 'dev', demoClock: DateTime.parse('2026-09-30T08:00:00+05:30'));
}

final _longAnswer = List.filled(
  14,
  'Keep the orchard floor clean and remove the fallen leaves.',
).join(' ').substring(0, 480);

AskState _answered({bool refused = false}) => AskState(
  question: 'When does apple scab spread?',
  phase: AskPhase.answered,
  answer: AskOut(
    answer: _longAnswer,
    language: 'en',
    refused: refused,
    citations: const [
      CitationOut(noteId: 'N1', source: 'HP Horticulture Department / UHF Nauni Spray Schedule 2026'),
      CitationOut(noteId: 'N2', source: 'SKUAST-Kashmir 2026 guidance'),
    ],
  ),
);

/// One screen under the real theme (`TestEnv.wrap` uses the default Material theme, whose buttons are smaller).
Widget themed(TestEnv env, Widget screen) => ProviderScope(
  retry: (_, _) => null,
  overrides: env.overrides,
  child: MaterialApp(theme: buildAppTheme(), home: screen),
);

void main() {
  final suggestions = parseAskSuggestions(File('assets/l10n/ask_suggestions.json').readAsStringSync());
  final fixedSuggestions = askSuggestionsProvider.overrideWith((ref) => suggestions);

  /// name -> the widget and the overrides that put it in the state to check.
  final screens = <String, (Widget, List<Override>)>{
    'ask cards': (const AskScreen(), [fixedSuggestions]),
    'ask typing': (const AskTypeScreen(), []),
    'ask waiting': (
      const AskAnswerScreen(),
      [
        askFlowProvider.overrideWith(
          () => _FixedAsk(const AskState(question: 'q?', promptId: 'ask_q_scab_risk', phase: AskPhase.asking)),
        ),
      ],
    ),
    'ask answer (long, with sources)': (
      const AskAnswerScreen(),
      [askFlowProvider.overrideWith(() => _FixedAsk(_answered()))],
    ),
    'ask refusal': (const AskAnswerScreen(), [askFlowProvider.overrideWith(() => _FixedAsk(_answered(refused: true)))]),
    'settings': (const SettingsScreen(), [sessionProvider.overrideWith(_LoggedIn.new)]),
    'log out question': (const LogoutConfirmScreen(), []),
    'saved offline': (const SavedOfflineScreen(), []),
    'home with the offline cards': (const HomeScreen(), [offlineStatusProvider.overrideWith(_FixedStatus.new)]),
  };

  for (final size in const [Size(320, 568), Size(360, 640)]) {
    for (final scale in const [1.0, 1.6, 2.0]) {
      for (final language in const ['hi', 'en']) {
        testWidgets(
          'every screen fits ${size.width.toInt()}x${size.height.toInt()} at text size $scale in $language (no overflow, big targets)',
          (tester) async {
            useSmallPhone(tester, size: size, textScale: scale);
            for (final entry in screens.entries) {
              final env = await TestEnv.create(
                language: language,
                loggedIn: true,
                api: _DemoApi(), // the demo strip is on: it must fit too
                extraOverrides: [demoBannerFetchProvider.overrideWithValue(true), ...entry.value.$2],
              );
              await tester.pumpWidget(themed(env, entry.value.$1));
              // The waiting screen has an endless bar: pump a few frames instead of settling.
              for (var i = 0; i < 6; i++) {
                await tester.pump(const Duration(milliseconds: 50));
              }
              expect(tester.takeException(), isNull, reason: '${entry.key} at $scale on ${size.width}');
              expect(keyed('demo-banner'), findsOneWidget, reason: '${entry.key}: the demo strip is on every screen');
              expectBigTouchTargets(tester);
              await tester.pumpWidget(const SizedBox());
            }
          },
        );
      }
    }
  }

  group('the phone asks for no animations', () {
    void noAnimations(WidgetTester tester) {
      tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(
        disableAnimations: true,
      );
      addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    }

    testWidgets('the waiting bar stands still', (tester) async {
      useSmallPhone(tester);
      final env = await TestEnv.create(
        loggedIn: true,
        extraOverrides: [
          askFlowProvider.overrideWith(
            () => _FixedAsk(const AskState(question: 'q?', promptId: 'ask_q_scab_risk', phase: AskPhase.asking)),
          ),
        ],
      );
      await tester.pumpWidget(themed(env, const AskAnswerScreen()));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(LinearProgressIndicator), findsOneWidget, reason: 'by default the bar moves');
      await tester.pumpWidget(const SizedBox());

      noAnimations(tester);
      await tester.pumpWidget(themed(env, const AskAnswerScreen()));
      await tester.pumpAndSettle(); // nothing moves, so it settles
      expect(find.byType(LinearProgressIndicator), findsNothing);
      expect(keyed('ask-waiting-bar'), findsOneWidget);
    });

    testWidgets('screens change without the fade', (tester) async {
      useSmallPhone(tester);
      Finder fadeAboveSettings() =>
          find.ancestor(of: find.byType(SettingsScreen), matching: find.byType(FadeTransition));

      final env = await TestEnv.create(loggedIn: true);
      final container = await pumpApp(tester, env, location: '/home');
      container.read(routerProvider).go('/settings');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 40));
      expect(fadeAboveSettings(), findsWidgets, reason: 'by default a short fade');
      await tester.pumpAndSettle();

      noAnimations(tester);
      container.read(routerProvider).go('/home');
      await tester.pumpAndSettle();
      container.read(routerProvider).go('/settings');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 40));
      expect(fadeAboveSettings(), findsNothing);
      expect(find.byType(SettingsScreen), findsOneWidget);
    });
  });

  test('every interface word the new screens look up exists in both languages', () {
    final strings = (jsonDecode(File('assets/l10n/strings.json').readAsStringSync()) as Map)['ui'] as Map;
    final files = [
      for (final dir in [
        'lib/features/auth',
        'lib/features/ask',
        'lib/features/settings',
        'lib/features/offline',
        'lib/core/offline',
      ])
        ...Directory(dir).listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart')),
      File('lib/core/widgets/demo_clock_banner.dart'),
      File('lib/features/home/home_screen.dart'),
    ];
    final used = <String>{};
    for (final file in files) {
      for (final m in RegExp(r"\bt\('([a-z0-9_]+)'").allMatches(file.readAsStringSync())) {
        used.add(m.group(1)!);
      }
    }
    expect(used.length, greaterThan(15), reason: 'the scan found too few keys: the pattern is broken');
    for (final key in used) {
      final entry = strings[key];
      expect(entry, isA<Map>(), reason: 'missing interface word "$key" in assets/l10n/strings.json');
      for (final lang in ['en', 'hi']) {
        expect(((entry as Map)[lang] as String?)?.trim() ?? '', isNotEmpty, reason: '"$key" has no $lang text');
      }
    }
  });

  testWidgets(
    'the real app keeps text between 1.0 and 2.0 (every screen is checked at 2.0 in all_screens_audit_test)',
    (tester) async {
      useSmallPhone(tester, textScale: 3.0);
      final env = await TestEnv.create(loggedIn: true);
      await pumpApp(tester, env, location: '/home');
      final scale = MediaQuery.of(tester.element(find.byType(HomeScreen))).textScaler.scale(10);
      expect(scale, closeTo(20, 0.01));
    },
  );
}
