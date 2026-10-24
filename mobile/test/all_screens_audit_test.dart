import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/features/alerts/alerts_providers.dart';
import 'package:farmtrack/features/ask/ask_flow.dart';
import 'package:farmtrack/features/ask/ask_suggestions.dart';
import 'package:farmtrack/features/scan/photo_picker.dart';
import 'package:farmtrack/features/scan/scan_flow.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// A mock server that can also hang, fail and answer with long texts, so every state of a screen can be reached.
class _AuditApi extends MockApiClient {
  _AuditApi() : super(latency: Duration.zero);

  bool hangCreate = false;
  bool hangConfirm = false;
  bool failCreate = false;
  bool hangAsk = false;
  bool longAnswer = false;
  bool manyWarnings = false;

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
    if (hangCreate) await Completer<void>().future;
    if (failCreate) throw const ApiException(kind: ApiErrorKind.server, code: 'boom', statusCode: 500);
    return super.createScan(photoPaths: photoPaths, idempotencyKey: idempotencyKey);
  }

  @override
  Future<ScanOut> confirmCrop(String scanId, String cropId) async {
    if (hangConfirm) await Completer<void>().future;
    return super.confirmCrop(scanId, cropId);
  }

  @override
  Future<AskOut> ask(AskIn question) async {
    if (hangAsk) await Completer<void>().future;
    if (longAnswer) {
      return AskOut(
        answer: List.filled(14, 'Keep the orchard floor clean and remove the fallen leaves.').join(' '),
        language: question.language,
        citations: const [
          CitationOut(noteId: 'N1', source: 'HP Horticulture Department / UHF Nauni Spray Schedule 2026'),
          CitationOut(noteId: 'N2', source: 'SKUAST-Kashmir 2026 guidance'),
        ],
      );
    }
    return super.ask(question);
  }

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) async {
    final out = await super.createSprayLog(log, idempotencyKey: idempotencyKey);
    if (!manyWarnings) return out;
    final warnings = [
      ...MockData.sprayWarnings(freeText: 'Miravis'),
      ...MockData.sprayWarnings(freeText: 'Mancozeb'),
      ...MockData.sprayWarnings(freeText: 'unknown product'),
    ];
    return SprayLogOut(
      id: out.id,
      cropId: out.cropId,
      productId: out.productId,
      productName: out.productName,
      sprayedAt: out.sprayedAt,
      adviceId: out.adviceId,
      warnings: warnings,
      syncedToZoho: true,
      spoken: MockData.sprayLogSpoken(warnings),
    );
  }
}

class _Ctx {
  _Ctx(this.container, this.env, this.api);

  final ProviderContainer container;
  final TestEnv env;
  final _AuditApi api;

  ScanFlowNotifier get flow => container.read(scanFlowProvider.notifier);

  void showScan(ScanOut scan) => flow.showResult(scan);
}

typedef _Prepare = FutureOr<void> Function(_Ctx ctx);
typedef _After = Future<void> Function(WidgetTester tester, _Ctx ctx);

class _Case {
  const _Case(this.name, this.route, {this.prepare, this.after, this.silent = false});

  final String name;
  final String route;
  final _Prepare? prepare;
  final _After? after;

  /// True where the audit starts on the very same screen, so nothing is spoken again (Home's own tests cover its speech).
  final bool silent;
}

final _longName = 'Mancozeb 75 WP together with a very long medicine name that has to wrap on a small phone';

/// Every route of `Routes`, in every state that changes its layout. Adding a route to `routes.dart` without a case here
/// fails the "every route is covered" test below.
final List<_Case> _loggedInCases = [
  const _Case('home', Routes.home, silent: true),
  const _Case('home after login', Routes.homeFresh, silent: true),
  const _Case('camera', Routes.scan),
  _Case(
    'camera, permission denied',
    Routes.scan,
    prepare: (c) => c.env.picker.script.add(const CameraPermissionDenied()),
    after: (tester, c) => tapKey(tester, 'camera-button'),
  ),
  _Case(
    'review, one photo',
    Routes.scanReview,
    prepare: (c) {
      c.flow
        ..reset()
        ..addPhoto('/tmp/leaf_0.jpg');
    },
  ),
  _Case(
    'review, four photos',
    Routes.scanReview,
    prepare: (c) {
      c.flow.reset();
      for (var i = 0; i < 4; i++) {
        c.flow.addPhoto('/tmp/leaf_$i.jpg');
      }
    },
  ),
  _Case(
    'uploading',
    Routes.scanUploading,
    prepare: (c) {
      c.api.hangCreate = true;
      c.flow
        ..reset()
        ..addPhoto('/tmp/leaf_0.jpg');
    },
  ),
  _Case(
    'upload failed (error screen)',
    Routes.scanUploading,
    prepare: (c) {
      c.api.failCreate = true;
      c.flow
        ..reset()
        ..addPhoto('/tmp/leaf_0.jpg');
    },
  ),
  _Case(
    'analysing',
    Routes.analysingFor('apple'),
    prepare: (c) {
      c.api.hangConfirm = true;
      c.api.scans['scan-1'] = MockData.confirmCropScan('scan-1');
      c.showScan(MockData.confirmCropScan('scan-1'));
    },
  ),
  _Case('retake, blurry', Routes.scanRetake, prepare: (c) => c.showScan(MockData.photoUnusableScan('s1'))),
  _Case(
    'retake, too dark',
    Routes.scanRetake,
    prepare: (c) => c.showScan(MockData.photoUnusableScan('s1', issue: 'too_dark')),
  ),
  _Case('is this your crop', Routes.scanConfirm, prepare: (c) => c.showScan(MockData.confirmCropScan('s1'))),
  _Case('choose the crop', Routes.scanCrops, prepare: (c) => c.showScan(MockData.confirmCropScan('s1'))),
  _Case('advice', Routes.scanAdvice, prepare: (c) => c.showScan(MockData.okScan('scan-1'))),
  _Case('expert: needs expert', Routes.scanExpert, prepare: (c) => c.showScan(MockData.needsExpertScan('s1'))),
  _Case('expert: no approved data', Routes.scanExpert, prepare: (c) => c.showScan(MockData.noApprovedDataScan('s1'))),
  _Case('expert: not a disease', Routes.scanExpert, prepare: (c) => c.showScan(MockData.notADiseaseScan('s1'))),
  const _Case('saved, will be sent later', Routes.scanSaved),
  _Case(
    'diary list',
    Routes.diary,
    prepare: (c) async {
      await c.api.createSprayLog(SprayLogIn(cropId: 'apple', freeText: _longName));
      await c.api.createSprayLog(const SprayLogIn(cropId: 'apple', adviceId: 'adv-1'));
    },
  ),
  _Case(
    'diary confirm (from an advice)',
    Routes.diaryFor(adviceId: 'adv-scan-1', cropId: 'apple'),
    prepare: (c) => c.showScan(MockData.okScan('scan-1')),
  ),
  _Case(
    'diary saved with three warnings',
    Routes.diaryFor(adviceId: 'adv-scan-1', cropId: 'apple'),
    prepare: (c) {
      c.api.manyWarnings = true;
      c.showScan(MockData.okScan('scan-1'));
    },
    after: (tester, c) => tapKey(tester, 'diary-save'),
  ),
  const _Case('diary add', Routes.diaryAdd),
  const _Case('my field', Routes.field),
  _Case('my field, old data', Routes.field, prepare: (c) => c.api.fieldOverride = MockData.fieldStale()),
  _Case('my field, no sensor data', Routes.field, prepare: (c) => c.api.fieldOverride = MockData.fieldNoData()),
  const _Case('alerts', Routes.alerts),
  _Case(
    'alerts, none',
    Routes.alerts,
    prepare: (c) {
      c.api.alertItems = [];
      c.container.invalidate(alertsProvider);
    },
  ),
  _Case('one alert (with a photo result)', Routes.alertDetailFor('alert-1')),
  _Case('one alert (read, no photo)', Routes.alertDetailFor('alert-2')),
  _Case('one alert that does not exist (error)', Routes.alertDetailFor('nope')),
  const _Case('ask: cards', Routes.ask),
  const _Case('ask: typing', Routes.askType),
  _Case(
    'ask: waiting',
    Routes.askAnswer,
    prepare: (c) {
      c.api.hangAsk = true;
      unawaited(c.container.read(askFlowProvider.notifier).ask('When does apple scab spread?'));
    },
  ),
  _Case(
    'ask: answer',
    Routes.askAnswer,
    prepare: (c) => c.container.read(askFlowProvider.notifier).ask('When does apple scab spread?'),
  ),
  _Case(
    'ask: long answer with sources',
    Routes.askAnswer,
    prepare: (c) async {
      c.api.longAnswer = true;
      await c.container.read(askFlowProvider.notifier).ask('When does apple scab spread?');
    },
  ),
  _Case(
    'ask: refused',
    Routes.askAnswer,
    prepare: (c) => c.container.read(askFlowProvider.notifier).ask('Who wins the lottery?'),
  ),
  const _Case('settings', Routes.settings),
  const _Case('log out question', Routes.settingsLogout),
];

/// Routes only a logged-out farmer sees (each case starts a fresh app).
const _publicRoutes = {Routes.splash, Routes.language, Routes.welcome, Routes.login};

Future<void> _settle(WidgetTester tester) async {
  // Some screens have an endless progress bar, so `pumpAndSettle` would never return.
  for (var i = 0; i < 10; i++) {
    await tester.pump(const Duration(milliseconds: 120));
  }
}

/// All checks for the screen that is showing now. Returns what failed (empty = fine).
Future<List<String>> _check(WidgetTester tester, TestEnv env, String name, {required bool silent}) async {
  final problems = <String>[];
  final error = tester.takeException();
  if (error != null) problems.add('exception or overflow: ${error.toString().split('\n').take(4).join(' | ')}');
  try {
    expectBigTouchTargets(tester);
  } on TestFailure catch (e) {
    problems.add('touch target below 56 dp: ${e.message?.split('\n').first}');
  }
  final small = await meetsGuideline(androidTapTargetGuideline).matchAsync(tester);
  if (small != null) {
    problems.add('tap target below 48 dp: ${small is String ? small.trim().split('\n').take(4).join(' | ') : small}');
  }
  final unlabeled = await meetsGuideline(labeledTapTargetGuideline).matchAsync(tester);
  if (unlabeled != null) {
    problems.add(
      'control without a label: ${unlabeled is String ? unlabeled.trim().split('\n').take(4).join(' | ') : unlabeled}',
    );
  }
  if (!silent && env.voice.calls.isEmpty) {
    problems.add('says nothing when it opens');
  }
  if (env.voice.unknownIds.isNotEmpty) problems.add('unknown prompt ids ${env.voice.unknownIds}');
  return problems.map((p) => '$name: $p').toList();
}

void main() {
  final suggestions = parseAskSuggestions(File('assets/l10n/ask_suggestions.json').readAsStringSync());
  final fixedSuggestions = askSuggestionsProvider.overrideWith((ref) => suggestions);

  test('every route of the app has a case in this audit', () {
    final routes = <String>{
      for (final line in File('lib/core/router/routes.dart').readAsLinesSync())
        ...RegExp(r"static const \w+ = '(/[^']*)';").allMatches(line).map((m) => m.group(1)!),
    };
    final covered = {..._publicRoutes, for (final c in _loggedInCases) Uri.parse(c.route).path};
    expect(routes.difference(covered), isEmpty, reason: 'routes without an audit case');
  });

  for (final size in const [Size(320, 568), Size(360, 640)]) {
    for (final scale in const [1.0, 1.6, 2.0]) {
      for (final language in const ['hi', 'en']) {
        final label = '${size.width.toInt()}x${size.height.toInt()}, text size $scale, $language';

        testWidgets('every screen of a logged-in farmer: $label', (tester) async {
          useSmallPhone(tester, size: size, textScale: scale);
          final semantics = tester.ensureSemantics();
          final api = _AuditApi();
          final env = await TestEnv.create(
            language: language,
            loggedIn: true,
            api: api,
            extraOverrides: [fixedSuggestions],
          );
          final container = await pumpApp(tester, env, location: '/home');
          final router = container.read(routerProvider);
          final ctx = _Ctx(container, env, api);
          final failures = <String>[];

          for (final c in _loggedInCases) {
            // Back to a clean Home between screens (also resets every flow).
            router.go(Routes.home);
            await _settle(tester);
            ctx.flow.reset();
            container.read(askFlowProvider.notifier).reset();
            api
              ..hangCreate = false
              ..hangConfirm = false
              ..failCreate = false
              ..hangAsk = false
              ..longAnswer = false
              ..manyWarnings = false
              ..fieldOverride = null
              ..alertItems = null;
            env.picker.script.clear();
            tester.takeException();

            await c.prepare?.call(ctx);
            env.voice.clear();
            router.go(c.route);
            await _settle(tester);
            await c.after?.call(tester, ctx);
            await _settle(tester);
            failures.addAll(await _check(tester, env, c.name, silent: c.silent));
          }

          semantics.dispose();
          expect(failures, isEmpty, reason: '\n${failures.join('\n')}');
        });

        testWidgets('the screens before login: $label', (tester) async {
          useSmallPhone(tester, size: size, textScale: scale);
          final semantics = tester.ensureSemantics();
          final failures = <String>[];

          // Splash: only the layout (it is the one screen that is silent).
          var env = await TestEnv.create(language: language);
          await tester.pumpWidget(env.app());
          await tester.pump();
          failures.addAll(await _check(tester, env, 'splash', silent: true));
          await tester.pumpWidget(const SizedBox());

          // Language: nothing chosen yet.
          env = await TestEnv.create(language: null);
          await pumpApp(tester, env);
          expect(find.byType(MaterialApp), findsOneWidget);
          failures.addAll(await _check(tester, env, 'choose a language', silent: false));
          await tester.pumpWidget(const SizedBox());

          // Welcome: language known, first start.
          env = await TestEnv.create(language: language);
          await pumpApp(tester, env);
          failures.addAll(await _check(tester, env, 'welcome', silent: false));
          await tester.pumpWidget(const SizedBox());

          // Login: empty, typed, password shown, wrong password (the caption shows what was spoken), too many tries.
          env = await TestEnv.create(language: language, onboardingDone: true);
          await pumpApp(tester, env);
          failures.addAll(await _check(tester, env, 'login', silent: false));
          env.voice.clear();
          await enterLogin(tester, username: 'f001', password: 'wrong-password');
          failures.addAll(await _check(tester, env, 'login typed', silent: true));
          await tapKey(tester, 'login-eye');
          failures.addAll(await _check(tester, env, 'login with the password shown', silent: false));
          env.voice.clear();
          await tapKey(tester, 'login-submit');
          failures.addAll(await _check(tester, env, 'login wrong password', silent: false));
          env.voice.clear();
          env.api.failWith(
            const ApiException(kind: ApiErrorKind.rateLimited, code: 'rate_limited', statusCode: 429),
            ops: {'login'},
          );
          await tapKey(tester, 'login-submit');
          failures.addAll(await _check(tester, env, 'login too many tries', silent: false));
          env.voice.clear();
          env.api.failWith(const ApiException.network(), ops: {'login'});
          await tapKey(tester, 'login-submit');
          failures.addAll(await _check(tester, env, 'login no internet', silent: false));
          await tester.pumpWidget(const SizedBox());

          semantics.dispose();
          expect(failures, isEmpty, reason: '\n${failures.join('\n')}');
        });
      }
    }
  }
}
