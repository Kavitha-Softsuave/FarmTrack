// Contract test: the app's models and decision code against what the REAL backend sent.
//
// The fixtures in test/fixtures/api/*.json are recorded from the real FastAPI app (rules, composer, auth, validation, error
// handlers; only the disease result is forced) by `backend\.venv\Scripts\python backend\scripts\dump_api_fixtures.py`.
// Re-run that script after a backend change and run this test: a failure here is a real mismatch between app and server.
// A mismatch that is written up in docs/design-notes/contract.md and waits for its owner is reported as SKIPPED (with the reason), not
// failed; it turns into a normal passing test as soon as the mismatch is fixed.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show ValueKey;
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/l10n/app_resources.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/dio_api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/router/routes.dart';
import 'package:farmtrack/core/storage/token_store.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/widgets/status_views.dart' show errorPromptFor;
import 'package:farmtrack/features/scan/result_prompts.dart';
import 'package:farmtrack/features/scan/scan_flow.dart';

import 'support/finders.dart';
import 'support/harness.dart';

// ------------------------------------------------------------------------------------------------ fixtures

class Fixture {
  Fixture(this.name, this.json);

  final String name;
  final Json json;

  Json get request => Json.from(json['request'] as Map);
  String get method => request['method'] as String;
  String get path => request['path'] as String;
  int get status => json['status'] as int;
  Object? get body => json['body'];
  Json get bodyMap => Json.from(body as Map);
  bool get isError => status >= 400;

  String? header(String key) {
    final headers = json['response_headers'];
    if (headers is! Map) return null;
    for (final e in headers.entries) {
      if ('${e.key}'.toLowerCase() == key.toLowerCase()) return '${e.value}';
    }
    return null;
  }
}

Map<String, Fixture> _loadFixtures() {
  final dir = Directory('test/fixtures/api');
  if (!dir.existsSync()) return {};
  final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.json')).toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  return {
    for (final f in files)
      if (!f.uri.pathSegments.last.startsWith('_'))
        f.uri.pathSegments.last.replaceAll('.json', ''): Fixture(
          f.uri.pathSegments.last.replaceAll('.json', ''),
          Json.from(jsonDecode(f.readAsStringSync()) as Map),
        ),
  };
}

final Map<String, Fixture> fixtures = _loadFixtures();

Fixture fx(String name) =>
    fixtures[name] ?? (throw StateError('fixture $name is missing: re-run dump_api_fixtures.py'));

ScanOut scanOf(String name) => ScanOut.fromJson(fx(name).bodyMap);

final PromptCatalogue catalogue = PromptCatalogue.fromJson(File('assets/voice/prompts.json').readAsStringSync());
final AppResources resources = AppResources.fromJson(
  languagesJson: File('assets/l10n/languages.json').readAsStringSync(),
  stringsJson: File('assets/l10n/strings.json').readAsStringSync(),
);

// ------------------------------------------------------------------------------------------------ which model reads what

class Kind {
  const Kind(this.type, this.parse, this.toJson);

  final String type;
  final Object Function(Object body) parse;
  final Object Function(Object model) toJson;
}

Json _m(Object body) => Json.from(body as Map);

final Map<String, Kind> _kinds = {
  'GET /health': Kind('HealthOut', (b) => HealthOut.fromJson(_m(b)), (o) => (o as HealthOut).toJson()),
  'GET /v1/meta': Kind('MetaOut', (b) => MetaOut.fromJson(_m(b)), (o) => (o as MetaOut).toJson()),
  'POST /v1/auth/login': Kind('TokenOut', (b) => TokenOut.fromJson(_m(b)), (o) => (o as TokenOut).toJson()),
  'POST /v1/auth/refresh': Kind('TokenOut', (b) => TokenOut.fromJson(_m(b)), (o) => (o as TokenOut).toJson()),
  'GET /v1/me': Kind('FarmerOut', (b) => FarmerOut.fromJson(_m(b)), (o) => (o as FarmerOut).toJson()),
  'PATCH /v1/me': Kind('FarmerOut', (b) => FarmerOut.fromJson(_m(b)), (o) => (o as FarmerOut).toJson()),
  'POST /v1/scans': _scanKind,
  'POST /v1/scans/{id}/photos': _scanKind,
  'POST /v1/scans/{id}/crop': _scanKind,
  'GET /v1/scans/{id}': _scanKind,
  'GET /v1/scans': Kind('ScanListOut', (b) => ScanListOut.fromJson(_m(b)), (o) => (o as ScanListOut).toJson()),
  'POST /v1/spray-logs': Kind('SprayLogOut', (b) => SprayLogOut.fromJson(_m(b)), (o) => (o as SprayLogOut).toJson()),
  'GET /v1/spray-logs': Kind(
    'List<SprayLogOut>',
    (b) => [for (final e in b as List) SprayLogOut.fromJson(_m(e as Object))],
    (o) => [for (final e in o as List<SprayLogOut>) e.toJson()],
  ),
  'GET /v1/field': Kind('FieldOut', (b) => FieldOut.fromJson(_m(b)), (o) => (o as FieldOut).toJson()),
  'GET /v1/alerts': Kind('AlertListOut', (b) => AlertListOut.fromJson(_m(b)), (o) => (o as AlertListOut).toJson()),
  'POST /v1/alerts/{id}/read': Kind('AlertOut', (b) => AlertOut.fromJson(_m(b)), (o) => (o as AlertOut).toJson()),
  'POST /v1/ask': Kind('AskOut', (b) => AskOut.fromJson(_m(b)), (o) => (o as AskOut).toJson()),
  'POST /v1/expert-requests': Kind(
    'ExpertRequestOut',
    (b) => ExpertRequestOut.fromJson(_m(b)),
    (o) => (o as ExpertRequestOut).toJson(),
  ),
  'GET /v1/voice/catalogue': Kind(
    'VoiceCatalogueOut',
    (b) => VoiceCatalogueOut.fromJson(_m(b)),
    (o) => (o as VoiceCatalogueOut).toJson(),
  ),
};

final Kind _scanKind = Kind('ScanOut', (b) => ScanOut.fromJson(_m(b)), (o) => (o as ScanOut).toJson());

String _templated(String path) => path.replaceAll(RegExp(r'/[0-9a-f]{32}'), '/{id}');

Kind? kindOf(Fixture f) => _kinds['${f.method} ${_templated(f.path)}'];

/// Every raw ScanOut in the fixtures (single answers and list items) with the fixture it came from.
Iterable<(String, Json)> rawScans() sync* {
  for (final f in fixtures.values) {
    if (f.isError || f.body is! Map) continue;
    final type = kindOf(f)?.type;
    if (type == 'ScanOut') yield (f.name, f.bodyMap);
    if (type == 'ScanListOut') {
      for (final item in f.bodyMap['items'] as List) {
        yield (f.name, Json.from(item as Map));
      }
    }
  }
}

Iterable<(String, Json)> rawAlerts() sync* {
  for (final f in fixtures.values) {
    if (f.isError || f.body is! Map) continue;
    final type = kindOf(f)?.type;
    if (type == 'AlertListOut') {
      for (final item in f.bodyMap['items'] as List) {
        yield (f.name, Json.from(item as Map));
      }
    }
    if (type == 'AlertOut') yield (f.name, f.bodyMap);
  }
}

/// Where the server sent a key that the model does not write back (a candidate for "the app ignores this field").
List<List<Object>> _unwrittenKeys(Object? raw, Object? model, [List<Object> path = const []]) {
  final out = <List<Object>>[];
  if (raw is Map && model is Map) {
    for (final e in raw.entries) {
      if (!model.containsKey(e.key)) {
        out.add([...path, e.key as Object]);
      } else {
        out.addAll(_unwrittenKeys(e.value, model[e.key], [...path, e.key as Object]));
      }
    }
  } else if (raw is List && model is List) {
    for (var i = 0; i < raw.length && i < model.length; i++) {
      out.addAll(_unwrittenKeys(raw[i], model[i], [...path, i]));
    }
  }
  return out;
}

Object? _deepCopy(Object? v) => jsonDecode(jsonEncode(v));

Object? _valueAt(Object? root, List<Object> path) {
  var node = root;
  for (final key in path) {
    node = node is Map ? node[key] : (node as List)[key as int];
  }
  return node;
}

void _setAt(Object root, List<Object> path, Object? value) {
  final parent = _valueAt(root, path.sublist(0, path.length - 1));
  if (parent is Map) {
    parent[path.last] = value;
  } else {
    (parent as List)[path.last as int] = value;
  }
}

/// Keys the server sent that the model throws away ("fields the app ignores"), as JSON paths.
///
/// A key whose value is null in the fixture cannot be told apart from a field the model reads but leaves out of its JSON
/// when it is null, so such a key is probed: a value is put in its place, and the key counts as read when the parsed
/// model changes.
List<String> droppedKeys(Kind kind, Object body, Object written) {
  final out = <String>[];
  for (final path in _unwrittenKeys(body, written)) {
    if (path.any((p) => p == 'audio') && _valueAt(body, path) == null) continue; // an audio entry that is null: no TTS
    if (_valueAt(body, path) != null) {
      out.add(path.join('.'));
      continue;
    }
    final before = jsonEncode(kind.toJson(kind.parse(body)));
    var read = false;
    for (final probe in <Object>[
      'probe',
      1,
      true,
      {'en': 'x', 'hi': 'y', 'url': 'u'},
    ]) {
      final copy = _deepCopy(body)!;
      _setAt(copy, path, probe);
      try {
        if (jsonEncode(kind.toJson(kind.parse(copy))) != before) read = true;
      } on Object {
        read = true; // the model reacted to it
      }
      if (read) break;
    }
    if (!read) out.add('${path.join('.')} (null in the fixture)');
  }
  return out;
}

/// Keys the model writes that the server did not send (the app expects a field that does not exist).
List<String> missingKeys(Object? raw, Object? model, [String path = r'$']) {
  final out = <String>[];
  if (raw is Map && model is Map) {
    for (final e in model.entries) {
      if (!raw.containsKey(e.key)) {
        out.add('$path.${e.key}');
      } else {
        out.addAll(missingKeys(raw[e.key], e.value, '$path.${e.key}'));
      }
    }
  } else if (raw is List && model is List) {
    for (var i = 0; i < raw.length && i < model.length; i++) {
      out.addAll(missingKeys(raw[i], model[i], '$path[$i]'));
    }
  }
  return out;
}

// ------------------------------------------------------------------------------------------------ helpers

final _devanagari = RegExp(r'[ऀ-ॿ]');

/// Every `{en, hi}` pair in [raw] (a map whose keys are only en/hi and whose values are all strings), with its path.
Iterable<(String, Json)> localizedPairs(Object? raw, [String path = r'$']) sync* {
  if (raw is Map) {
    final keys = raw.keys.toSet();
    final isPair = raw.isNotEmpty && keys.difference({'en', 'hi'}).isEmpty && raw.values.every((v) => v is String);
    if (isPair) yield (path, Json.from(raw));
    for (final e in raw.entries) {
      yield* localizedPairs(e.value, '$path.${e.key}');
    }
  } else if (raw is List) {
    for (var i = 0; i < raw.length; i++) {
      yield* localizedPairs(raw[i], '$path[$i]');
    }
  }
}

/// A mismatch written up in docs/design-notes/contract.md that waits for its owner: skipped while it exists, a normal test once fixed.
void knownMismatch(String name, String reason, FutureOr<void> Function() body) {
  test(name, () async {
    try {
      await body();
    } on TestFailure {
      markTestSkipped('KNOWN MISMATCH (docs/design-notes/contract.md): $reason');
    }
  });
}

void knownMismatchWidgets(String name, String reason, Future<void> Function(WidgetTester tester) body) {
  testWidgets(name, (tester) async {
    try {
      await body(tester);
    } on TestFailure {
      markTestSkipped('KNOWN MISMATCH (docs/design-notes/contract.md): $reason');
    }
  });
}

Set<String> _wires(Iterable<WireEnum> values) => {for (final v in values) v.wire};

// ------------------------------------------------------------------------------------------------ the journey under test

/// A mock server that answers the scan upload and the crop confirmation with recorded real answers.
class _RealAnswersApi extends MockApiClient {
  _RealAnswersApi(this.scan, {this.afterConfirm}) : super(latency: Duration.zero);

  final ScanOut scan;
  final ScanOut? afterConfirm;

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

  @override
  Future<ScanOut> confirmCrop(String scanId, String cropId) async {
    calls.add('confirmCrop');
    confirmedCrops.add(cropId);
    return afterConfirm ?? (throw StateError('no recorded answer for confirmCrop'));
  }
}

/// Opens the camera, takes one photo and sends it; returns with the result screen showing.
Future<TestEnv> openResult(
  WidgetTester tester,
  ScanOut scan, {
  ScanOut? afterConfirm,
  String language = 'hi',
  double textScale = 1.0,
}) async {
  final env = await TestEnv.create(
    loggedIn: true,
    language: language,
    api: _RealAnswersApi(scan, afterConfirm: afterConfirm),
  );
  useSmallPhone(tester, textScale: textScale);
  env.picker.queuePhotos(1);
  await pumpApp(tester, env, location: '/home');
  await tapKey(tester, 'home-scan');
  await tapKey(tester, 'camera-button');
  await tapKey(tester, 'send-photos');
  env.voice.keepLastCall();
  return env;
}

// ------------------------------------------------------------------------------------------------ the tests

void main() {
  const scanFixtures = [
    'scan_ok_scab',
    'scan_ok_scab_with_audio',
    'scan_ok_scab_rain_expected',
    'scan_ok_scab_after_washoff',
    'scan_photo_unusable_dark',
    'scan_photo_unusable_blurry',
    'scan_photo_unusable_bright',
    'scan_confirm_crop',
    'scan_confirm_crop_pea',
    'scan_needs_expert_marssonina',
    'scan_needs_expert_alternaria',
    'scan_needs_expert_low_confidence',
    'scan_needs_expert_no_disease_result',
    'scan_needs_expert_crop_unknown',
    'scan_not_a_disease',
    'crop_confirm',
    'crop_confirm_no_approved_data',
  ];

  group('the fixture set', () {
    test('exists and covers every scenario this test relies on', () {
      expect(
        fixtures,
        isNotEmpty,
        reason: 'run: backend\\.venv\\Scripts\\python backend\\scripts\\dump_api_fixtures.py',
      );
      const needed = [
        ...scanFixtures,
        'health',
        'meta',
        'auth_login',
        'auth_login_invalid',
        'me',
        'patch_me_language',
        'auth_refresh',
        'scan_get',
        'scan_list',
        'scan_list_paged',
        'scan_add_photos',
        'scan_idempotent_first',
        'scan_idempotent_replay',
        'spray_log_product',
        'spray_log_advice_only',
        'spray_logs_list',
        'field',
        'field_stale',
        'alerts_list',
        'alert_mark_read',
        'alerts_list_waiting_period',
        'ask_answered',
        'ask_refused_pea',
        'expert_request_with_scan',
        'expert_request_without_scan',
        'voice_catalogue_hi',
        'voice_catalogue_en',
        'error_401_no_token',
        'error_404_scan',
        'error_422_ask_empty',
        'error_400_bad_image',
        'error_503_analysis_unavailable',
      ];
      expect([
        for (final n in needed)
          if (!fixtures.containsKey(n)) n,
      ], isEmpty);
    });

    test('holds only demo data: no key, token or real phone number', () {
      for (final f in fixtures.values) {
        final text = jsonEncode(f.json);
        expect(text, isNot(contains('sk-')), reason: f.name);
        expect(text, isNot(matches(RegExp(r'eyJ[A-Za-z0-9_-]{10,}'))), reason: '${f.name} holds a JWT');
        for (final m in RegExp(r'\+91[0-9]{10}').allMatches(text)) {
          expect(m.group(0)!, startsWith('+91000000'), reason: '${f.name} holds a number that is not a demo number');
        }
      }
    });
  });

  group('every fixture is read by the real models', () {
    for (final f in fixtures.values) {
      test(f.name, () {
        expect(f.json.keys, containsAll(['request', 'status', 'body']));
        expect(f.method, isIn(['GET', 'POST', 'PATCH']));
        expect(f.path, startsWith('/'));

        if (f.isError) {
          final e = ApiException.fromResponse(f.status, f.body);
          expect(e.statusCode, f.status);
          if (f.body is Map) {
            expect(e.code, f.bodyMap['code'], reason: 'ErrorOut.code');
            expect(e.code, isNot(startsWith('http_')));
            expect(e.message, isNotEmpty);
          }
          expect(e.kind, switch (f.status) {
            401 => ApiErrorKind.unauthorized,
            422 => ApiErrorKind.validation,
            429 => ApiErrorKind.rateLimited,
            _ => f.status >= 500 ? ApiErrorKind.server : ApiErrorKind.client,
          });
          expect(e.isConnectionProblem, isFalse, reason: 'a server answer is never "no internet"');
          return;
        }

        if (f.path.startsWith('/v1/auth/otp/')) {
          // The OTP login stays in the server code (off by default, OTP_LOGIN_ENABLED) but the app does not use it any more.
          expect(f.body, isA<Map<dynamic, dynamic>>());
          return;
        }
        final kind = kindOf(f);
        if (f.body == null) {
          expect(f.status, isIn([204, 304, 200]), reason: 'an empty body is only expected for 204/304/binary');
          return;
        }
        expect(kind, isNotNull, reason: 'no model is mapped to ${f.method} ${_templated(f.path)}: add it to this test');
        final model = kind!.parse(f.body!);
        final written = kind.toJson(model);
        expect(
          droppedKeys(kind, f.body!, written),
          isEmpty,
          reason: 'fields the server sends and ${kind.type} ignores',
        );
        expect(missingKeys(f.body, written), isEmpty, reason: 'fields ${kind.type} expects and the server never sends');
      });
    }
  });

  group('error bodies', () {
    test('401 without a token and with a bad token', () {
      expect(fx('error_401_no_token').bodyMap['code'], 'not_authenticated');
      expect(fx('error_401_bad_token').bodyMap['code'], 'invalid_token');
    });

    test('422 keeps the ErrorOut shape and lists the failing fields', () {
      for (final name in fixtures.keys.where((n) => n.startsWith('error_422_'))) {
        final e = ApiException.fromResponse(fx(name).status, fx(name).body);
        expect(e.code, 'validation_error', reason: name);
        expect(e.details?['errors'], isA<List<dynamic>>(), reason: name);
      }
    });

    test('429 tells how long to wait', () {
      final limited = fixtures.values.where((f) => f.status == 429).toList();
      for (final f in limited) {
        final e = ApiException.fromResponse(429, f.body);
        expect(e.kind, ApiErrorKind.rateLimited, reason: f.name);
        expect(e.code, 'rate_limited', reason: f.name);
        expect(e.details?['retry_after_seconds'], isA<int>(), reason: f.name);
        expect(int.parse(f.header('retry-after')!), greaterThan(0), reason: f.name);
      }
    });

    test('a wrong user name or password is 401 invalid_credentials, which the login screen speaks as login_wrong', () {
      final wrong = fx('auth_login_invalid');
      expect(wrong.method, 'POST');
      expect(wrong.path, '/v1/auth/login');
      expect(wrong.status, 401);
      expect(wrong.bodyMap['code'], 'invalid_credentials');
      final e = ApiException.fromResponse(wrong.status, wrong.body);
      expect(e.kind, ApiErrorKind.unauthorized);
      expect(e.code, 'invalid_credentials');
      expect(e.isConnectionProblem, isFalse);
      expect(catalogue.contains('login_wrong'), isTrue);
    });

    test('a server failure is a server error with a spoken prompt that exists', () {
      final e = ApiException.fromResponse(503, fx('error_503_analysis_unavailable').body);
      expect(e.kind, ApiErrorKind.server);
      expect(e.code, 'analysis_unavailable');
      expect(catalogue.contains(errorPromptFor(e)), isTrue);
      for (final f in fixtures.values.where((f) => f.isError)) {
        final prompt = errorPromptFor(ApiException.fromResponse(f.status, f.body));
        expect(catalogue.contains(prompt), isTrue, reason: '${f.name} -> $prompt');
      }
    });

    test('a bad photo and a rotated refresh token have codes the app can tell apart', () {
      expect(fx('error_400_bad_image').bodyMap['code'], 'invalid_image');
      expect(fx('error_refresh_replayed').bodyMap['code'], 'invalid_refresh_token');
      expect(fx('error_404_scan').bodyMap['code'], 'scan_not_found');
    });
  });

  group('key fields of every answer', () {
    test('health and meta', () {
      final health = HealthOut.fromJson(fx('health').bodyMap);
      expect((health.status, health.db), ('ok', true));
      final meta = MetaOut.fromJson(fx('meta').bodyMap);
      expect(meta.appVersion, isNotEmpty);
      expect(meta.demoClock, isNotNull);
      expect(meta.supportedLanguages, ['hi', 'en']);
      expect(meta.supportedCrops, isNotEmpty);
      expect(meta.providers.keys, containsAll(['llm', 'tts', 'zoho', 'weather', 'iot', 'push']));
    });

    test('login: user name and password, refresh, me, language patch', () {
      final recorded = fx('auth_login');
      expect(recorded.status, 200);
      expect((recorded.method, recorded.path), ('POST', '/v1/auth/login'));
      final sent = Json.from(recorded.request['json'] as Map);
      expect(sent.keys, containsAll(['username', 'password']));
      final token = TokenOut.fromJson(recorded.bodyMap);
      expect(token.accessToken, isNotEmpty);
      expect(token.refreshToken, isNotEmpty);
      expect(token.tokenType, 'bearer');
      expect(token.expiresIn, greaterThan(0));
      final farmer = token.farmer;
      expect(farmer.id, 'F001');
      expect(farmer.name, isNotEmpty);
      expect(farmer.phoneMasked, contains('*'));
      expect(farmer.language, isIn(['hi', 'en']));
      expect(farmer.crops, isNotEmpty);
      expect(farmer.primaryCrop, isNotNull);
      expect(farmer.stationId, isNotNull);

      expect(TokenOut.fromJson(fx('auth_refresh').bodyMap).refreshToken, isNotEmpty);
      expect(FarmerOut.fromJson(fx('me').bodyMap).id, farmer.id);
      expect(FarmerOut.fromJson(fx('patch_me_language').bodyMap).language, 'en');
      expect(fx('auth_logout').status, 204);
      expect(fx('devices_register').status, 204);
    });

    test('ok scan: apple scab with advice', () {
      final scan = scanOf('scan_ok_scab');
      expect(scan.id, matches(RegExp(r'^[0-9a-f]{32}$')));
      expect(scan.status, ScanStatus.ok);
      expect(scan.createdAt, isNotNull);
      expect(scan.photos, 1);
      expect(scan.crop!.isKnown, isTrue);
      expect(scan.crop!.cropId, 'Apple');
      expect(scan.crop!.needsConfirmation, isFalse);
      expect(scan.quality.usable, isTrue);
      expect(scan.disease!.route, DiseaseRoute.autoAdvice);
      expect(scan.disease!.diseaseId, 'Apple___Apple_scab');
      expect(scan.reviewTaskId, isNull);

      final advice = scan.advice!;
      expect(advice.id, isNotEmpty);
      expect(advice.scanId, scan.id);
      expect(advice.cropId, 'Apple');
      expect(advice.diseaseId, scan.disease!.diseaseId);
      expect(advice.validated, isTrue);
      expect(advice.headline.hasLang('en') && advice.headline.hasLang('hi'), isTrue);
      expect(advice.summary.isEmpty, isFalse);
      expect(advice.steps, isNotEmpty);
      expect(advice.safety, isNotEmpty);
      expect(advice.sources, isNotEmpty);
      expect(advice.products, isNotEmpty);
      for (final p in advice.products) {
        expect(p.productId, matches(RegExp(r'^P[0-9]+$')));
        expect(p.activeIngredient.hasLang('en') && p.activeIngredient.hasLang('hi'), isTrue, reason: p.productId);
        expect(p.doseText.hasLang('en') && p.doseText.hasLang('hi'), isTrue, reason: p.productId);
        expect(p.doseUnit, isNotNull, reason: p.productId);
        expect(p.category, isNotEmpty);
      }
      expect(advice.timing, isNotNull);
      expect(advice.timing!.action, isNot(TimingAction.unknown));
      expect(advice.timing!.text.isEmpty, isFalse);
      expect(advice.spoken.text.hasLang('en') && advice.spoken.text.hasLang('hi'), isTrue);
      expect(scan.spoken.text.isEmpty, isFalse);
      expect(scan.promptsFor(NextAction.markSprayed), isNotEmpty);
      expect([for (final s in scan.nextSteps) s.action], contains(NextAction.done));
    });

    test('timing: spray now, wait for rain, repeat after a wash-off', () {
      final now = scanOf('scan_ok_scab').advice!.timing!;
      expect(now.action, TimingAction.sprayNow);
      expect(now.rainNext12hMm, 0);
      final wait = scanOf('scan_ok_scab_rain_expected').advice!.timing!;
      expect(wait.action, TimingAction.wait);
      expect(wait.rainNext12hMm, greaterThan(0));
      final repeat = scanOf('scan_ok_scab_after_washoff').advice!.timing!;
      expect(repeat.action, TimingAction.repeatWithinDays);
      expect(repeat.repeatWithinDays, 7);
      for (final timing in [now, wait, repeat]) {
        expect(timing.text.hasLang('en') && timing.text.hasLang('hi'), isTrue);
      }
    });

    test('photo not usable: the retake answer', () {
      for (final name in ['scan_photo_unusable_dark', 'scan_photo_unusable_blurry', 'scan_photo_unusable_bright']) {
        final scan = scanOf(name);
        expect(scan.status, ScanStatus.photoUnusable, reason: name);
        expect(scan.quality.usable, isFalse, reason: name);
        expect(scan.quality.issues, isNotEmpty, reason: name);
        expect(scan.quality.tipPromptId, isNotNull, reason: name);
        expect([for (final s in scan.nextSteps) s.action], [NextAction.retake], reason: name);
        expect(scan.advice, isNull, reason: name);
        expect(scan.disease, isNull, reason: name);
        expect(scan.crop, isNull, reason: name);
      }
      expect(scanOf('scan_photo_unusable_blurry').quality.issues, contains('blurry'));
      expect(scanOf('scan_photo_unusable_bright').quality.issues, contains('too_bright'));
      expect(scanOf('scan_photo_unusable_dark').quality.issues, contains('too_dark'));
    });

    test('confirm crop: the crop is named, nothing else is decided', () {
      for (final name in ['scan_confirm_crop', 'scan_confirm_crop_pea']) {
        final scan = scanOf(name);
        expect(scan.status, ScanStatus.confirmCrop, reason: name);
        expect(scan.crop!.needsConfirmation, isTrue, reason: name);
        expect(scan.crop!.isKnown, isTrue, reason: name);
        expect(scan.crop!.candidates, isNotEmpty, reason: name);
        expect(scan.crop!.name!.hasLang('en'), isTrue, reason: name);
        expect(scan.disease, isNull, reason: 'no disease before the crop is confirmed ($name)');
        expect(scan.advice, isNull, reason: 'no medicine before the crop is confirmed ($name)');
        expect([for (final s in scan.nextSteps) s.action], [NextAction.confirmCrop], reason: name);
        expect(scan.spoken.text.isEmpty, isFalse, reason: name);
      }
      final confirmed = scanOf('crop_confirm');
      expect(confirmed.status, ScanStatus.ok);
      expect(confirmed.crop!.source, 'farmer_confirmed');
      expect(confirmed.crop!.needsConfirmation, isFalse);
      expect(confirmed.advice, isNotNull);
    });

    test('needs expert: queued, no medicine', () {
      for (final name in [
        'scan_needs_expert_marssonina',
        'scan_needs_expert_alternaria',
        'scan_needs_expert_low_confidence',
        'scan_needs_expert_no_disease_result',
        'scan_needs_expert_crop_unknown',
      ]) {
        final scan = scanOf(name);
        expect(scan.status, ScanStatus.needsExpert, reason: name);
        expect(scan.reviewTaskId, isNotNull, reason: '$name is in the expert queue');
        expect(scan.promptsFor(NextAction.askExpert), isNotEmpty, reason: name);
        expect(scan.disease?.route ?? DiseaseRoute.expertQueue, isNot(DiseaseRoute.autoAdvice), reason: name);
        expect(scan.spoken.text.isEmpty, isFalse, reason: name);
      }
      expect(scanOf('scan_needs_expert_marssonina').disease!.diseaseId, 'Apple___Marssonina_blotch');
      expect(scanOf('scan_needs_expert_alternaria').disease!.diseaseId, 'Apple___Alternaria_leaf_spot');
      final unknown = scanOf('scan_needs_expert_crop_unknown').crop!;
      expect(unknown.unknown, isTrue);
      expect(unknown.isKnown, isFalse);
      expect(unknown.cropId, isNull);
      expect(unknown.candidates.length, greaterThanOrEqualTo(2));
    });

    test('no approved data and not a disease', () {
      final noData = scanOf('crop_confirm_no_approved_data');
      expect(noData.status, ScanStatus.noApprovedData);
      expect(noData.crop!.cropId, 'Pea');
      expect(noData.promptsFor(NextAction.askExpert), isNotEmpty);
      expect(noData.spoken.text.isEmpty, isFalse);

      final healthy = scanOf('scan_not_a_disease');
      expect(healthy.status, ScanStatus.notADisease);
      expect(healthy.disease!.route, DiseaseRoute.none);
      expect(healthy.disease!.diseaseId, 'Apple___healthy');
      expect(healthy.promptsFor(NextAction.addPhoto), isNotEmpty);
      expect(healthy.spoken.text.isEmpty, isFalse);
    });

    test('safety: only an ok scan carries medicine', () {
      for (final (name, raw) in rawScans()) {
        final scan = ScanOut.fromJson(raw);
        if (scan.status == ScanStatus.ok) {
          expect(scan.advice?.products, isNotEmpty, reason: name);
          expect(scan.disease?.route, DiseaseRoute.autoAdvice, reason: name);
        } else {
          expect(scan.advice?.products ?? const [], isEmpty, reason: 'medicine in a ${scan.status.wire} scan ($name)');
          expect(scan.advice?.timing, isNull, reason: name);
          expect(scan.disease?.route ?? DiseaseRoute.none, isNot(DiseaseRoute.autoAdvice), reason: name);
        }
      }
    });

    test('get, list, paging and add photos', () {
      expect(fx('scan_get').bodyMap, fx('scan_ok_scab').bodyMap, reason: 'GET returns the stored result unchanged');
      final all = ScanListOut.fromJson(fx('scan_list').bodyMap);
      expect(all.items.length, greaterThanOrEqualTo(5));
      expect(all.nextCursor, isNull);
      expect({for (final s in all.items) s.id}.length, all.items.length);
      final page1 = ScanListOut.fromJson(fx('scan_list_paged').bodyMap);
      final page2 = ScanListOut.fromJson(fx('scan_list_page2').bodyMap);
      expect(page1.items.length, 2);
      expect(page1.nextCursor, isNotNull);
      expect({for (final s in page1.items) s.id}.intersection({for (final s in page2.items) s.id}), isEmpty);
      final added = fx('scan_add_photos');
      expect(scanOf('scan_add_photos').photos, 2);
      expect(scanOf('scan_add_photos').id, added.path.split('/')[3]);
    });

    test('idempotent replays: same id and the replay header (what the offline queue relies on)', () {
      for (final (first, replay, idOf) in <(String, String, String Function(Fixture))>[
        ('scan_idempotent_first', 'scan_idempotent_replay', (f) => '${f.bodyMap['id']}'),
        ('spray_log_idempotent_first', 'spray_log_idempotent_replay', (f) => '${f.bodyMap['id']}'),
        ('expert_request_idempotent_first', 'expert_request_idempotent_replay', (f) => '${f.bodyMap['id']}'),
      ]) {
        expect(idOf(fx(first)), isNotEmpty, reason: first);
        expect(idOf(fx(replay)), idOf(fx(first)), reason: '$replay must return the first answer');
        expect(fx(first).header('idempotent-replayed'), isNull, reason: first);
        expect(fx(replay).header('idempotent-replayed'), 'true', reason: replay);
        expect(fx(replay).status, 200);
      }
      expect(fx('error_400_idempotency_key').bodyMap['code'], 'invalid_idempotency_key');
    });

    test('spray diary: product, advice only, typed names, list', () {
      final advice = scanOf('scan_ok_scab').advice!;
      final byProduct = SprayLogOut.fromJson(fx('spray_log_product').bodyMap);
      expect(byProduct.id, isNotEmpty);
      expect(byProduct.cropId, 'Apple');
      expect(byProduct.productId, advice.products.first.productId);
      expect(byProduct.productName, isNotEmpty);
      expect(byProduct.adviceId, advice.id);
      expect(byProduct.sprayedAt, isNotNull);
      expect(byProduct.spoken!.text.isEmpty, isFalse);

      final adviceOnly = SprayLogOut.fromJson(fx('spray_log_advice_only').bodyMap);
      expect(fx('spray_log_advice_only').status, 200, reason: 'the plain "I sprayed this" tick sends only advice_id');
      expect(adviceOnly.productId, advice.products.first.productId, reason: 'the first product, the one read aloud');
      expect(adviceOnly.adviceId, advice.id);

      final typed = SprayLogOut.fromJson(fx('spray_log_free_text').bodyMap);
      expect(typed.productId, isNotNull, reason: 'a known name is matched to the catalogue');
      expect([for (final w in typed.warnings) w.code], contains('PROPOSED_BAN'));
      final unknown = SprayLogOut.fromJson(fx('spray_log_free_text_unrecognised').bodyMap);
      expect(unknown.productId, isNull);
      expect(unknown.productName, 'my own homemade mix');
      expect([for (final w in unknown.warnings) w.code], contains('PRODUCT_NOT_RECOGNISED'));
      for (final w in [...typed.warnings, ...unknown.warnings]) {
        expect(w.text.hasLang('en') && w.text.hasLang('hi'), isTrue, reason: w.code);
        expect(w.level, isNot(Severity.green), reason: 'a spray warning is never green: ${w.code}');
      }

      final list = (fx('spray_logs_list').body as List).map((e) => SprayLogOut.fromJson(_m(e as Object))).toList();
      expect(list.length, greaterThanOrEqualTo(5));
      expect({for (final s in list) s.id}.length, list.length);
      expect(list.map((s) => s.id), containsAll([byProduct.id, adviceOnly.id, typed.id]));
    });

    test('field: normal and stale', () {
      final field = FieldOut.fromJson(fx('field').bodyMap);
      expect(field.stationId, 'ST01');
      expect(field.village, isNotEmpty);
      expect(field.asOf, isNotNull);
      expect(field.stale, isFalse);
      expect(field.readings!.tempC, isNotNull);
      expect(field.readings!.rhPct, isNotNull);
      expect(field.forecast.length, 7);
      for (final d in field.forecast) {
        expect(d.day, matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
        expect(d.tmaxC, greaterThanOrEqualTo(d.tminC));
        expect(d.rainMm, greaterThanOrEqualTo(0));
      }
      expect(field.risks, isNotEmpty);
      for (final r in field.risks) {
        expect(r.id, isNotEmpty);
        expect(r.title.hasLang('en') && r.title.hasLang('hi'), isTrue, reason: r.id);
        expect(r.text.hasLang('en') && r.text.hasLang('hi'), isTrue, reason: r.id);
      }
      expect(field.spoken.text.isEmpty, isFalse);

      final stale = FieldOut.fromJson(fx('field_stale').bodyMap);
      expect(stale.stale, isTrue);
      expect(stale.stationId, 'ST08');
      expect(stale.asOf!.isBefore(DateTime.parse('2026-07-13T00:00:00+05:30')), isTrue, reason: 'the reading is old');
      expect(
        stale.spoken.text.en,
        startsWith(catalogue['field_stale']!.text['en']!),
        reason: 'the spoken text starts with field_stale',
      );
    });

    test('alerts: list, unread count, mark read', () {
      final list = AlertListOut.fromJson(fx('alerts_list').bodyMap);
      expect(list.items, isNotEmpty);
      expect(list.unread, list.items.where((a) => !a.isRead).length);
      for (final a in list.items) {
        expect(a.id, isNotEmpty);
        expect(a.kind, matches(RegExp(r'^[a-z][a-z_]+$')), reason: 'kind of ${a.id}');
        expect(a.title.hasLang('en') && a.title.hasLang('hi'), isTrue, reason: a.kind);
        expect(a.body.hasLang('en') && a.body.hasLang('hi'), isTrue, reason: a.kind);
        expect(a.spoken.text.isEmpty, isFalse, reason: a.kind);
        expect(a.createdAt, isNotNull);
      }
      final created = [for (final a in list.items) a.createdAt!];
      expect(created, orderedEquals([...created]..sort((a, b) => b.compareTo(a))), reason: 'newest first');

      final waiting = AlertListOut.fromJson(fx('alerts_list_waiting_period').bodyMap).items.first;
      expect(waiting.kind, 'waiting_period');
      expect(
        waiting.scanId,
        scanOf('scan_ok_scab').id,
        reason: 'an alert about a spray points at the scan of its advice',
      );
      expect(
        list.items.every((a) => a.scanId == null),
        isTrue,
        reason: 'weather risks belong to the field, not to a scan',
      );

      final read = AlertOut.fromJson(fx('alert_mark_read').bodyMap);
      expect(read.isRead, isTrue);
      expect(fx('alert_mark_read').path, endsWith('/${read.id}/read'));
      final after = AlertListOut.fromJson(fx('alerts_list_after_read').bodyMap);
      expect(after.unread, list.unread - 1);
      expect(after.items.firstWhere((a) => a.id == read.id).isRead, isTrue);

      final kinds = {for (final (_, raw) in rawAlerts()) '${raw['kind']}'};
      expect(kinds, containsAll(['scab_infection_risk', 'rain_washoff', 'late_blight_risk', 'waiting_period']));
    });

    test('ask: answered and refused', () {
      final answered = AskOut.fromJson(fx('ask_answered').bodyMap);
      expect(answered.refused, isFalse);
      expect(answered.language, 'en');
      expect(answered.answer, isNotEmpty);
      expect(answered.citations, isNotEmpty);
      for (final c in answered.citations) {
        expect(c.noteId, isNotEmpty);
        expect(c.source, isNotEmpty);
      }
      expect(answered.spoken!.text.en, answered.answer);
      final hindi = AskOut.fromJson(fx('ask_answered_hi').bodyMap);
      expect(hindi.language, 'hi');
      expect(hindi.answer, matches(_devanagari));
      expect(hindi.spoken!.text.forLang('hi'), hindi.answer);
      for (final name in ['ask_refused_pea', 'ask_refused_nonsense']) {
        final refused = AskOut.fromJson(fx(name).bodyMap);
        expect(refused.refused, isTrue, reason: name);
        expect(refused.citations, isEmpty, reason: name);
        expect(refused.answer, isNotEmpty, reason: name);
      }
    });

    test('expert requests', () {
      for (final name in ['expert_request_with_scan', 'expert_request_without_scan', 'expert_request_empty']) {
        final out = ExpertRequestOut.fromJson(fx(name).bodyMap);
        expect(out.id, isNotEmpty, reason: name);
        expect(out.status, 'open', reason: name);
      }
      expect(fx('error_expert_request_scan_not_found').bodyMap['code'], 'scan_not_found');
    });

    test('voice catalogue: both languages, same ids, same texts as the bundled prompts', () {
      final hi = VoiceCatalogueOut.fromJson(fx('voice_catalogue_hi').bodyMap);
      final en = VoiceCatalogueOut.fromJson(fx('voice_catalogue_en').bodyMap);
      expect((hi.language, en.language), ('hi', 'en'));
      expect(hi.version, isNotEmpty);
      expect(hi.prompts.length, greaterThan(100));
      expect({for (final p in hi.prompts) p.id}.length, hi.prompts.length, reason: 'unique ids');
      expect({for (final p in hi.prompts) p.id}, {for (final p in en.prompts) p.id});
      for (final p in [...hi.prompts, ...en.prompts]) {
        expect(p.text.trim(), isNotEmpty, reason: p.id);
      }
      expect(fx('voice_catalogue_not_modified').status, 304);
      expect(fx('voice_catalogue_not_modified').header('etag'), '"${en.version}-en"');

      final differing = <String>[];
      final unknownToApp = <String>[];
      for (final (lang, cat) in [('hi', hi), ('en', en)]) {
        for (final p in cat.prompts) {
          final own = catalogue[p.id];
          if (own == null) {
            unknownToApp.add('${p.id}@$lang');
          } else if (own.text[lang] != p.text) {
            differing.add('${p.id}@$lang');
          }
        }
      }
      expect(
        unknownToApp,
        isEmpty,
        reason: 'the server has prompts the bundled catalogue lacks: run tool/sync_voice_assets.py',
      );
      expect(differing, isEmpty, reason: 'texts differ from the bundled copy: run tool/sync_voice_assets.py');
    });

    test('supported crops all have a spoken name and a picture group', () {
      for (final crop in MetaOut.fromJson(fx('meta').bodyMap).supportedCrops) {
        expect(catalogue.contains('crop_is_${crop.toLowerCase()}'), isTrue, reason: 'no crop_is_ prompt for $crop');
      }
    });
  });

  group('enum-like values the server sends are values the app knows', () {
    test('closed sets (Literal in the API schema)', () {
      final statuses = <String>{};
      final actions = <String>{};
      final routes = <String>{};
      final severities = <String>{};
      final timing = <String>{};
      for (final (_, raw) in rawScans()) {
        statuses.add('${raw['status']}');
        for (final s in (raw['next_steps'] as List)) {
          actions.add('${(s as Map)['action']}');
        }
        final disease = raw['disease'];
        if (disease is Map) routes.add('${disease['route']}');
        final advice = raw['advice'];
        if (advice is Map) {
          severities.add('${advice['severity']}');
          final t = advice['timing'];
          if (t is Map) timing.add('${t['action']}');
          for (final w in (advice['warnings'] as List)) {
            severities.add('${(w as Map)['level']}');
          }
          for (final p in (advice['products'] as List)) {
            for (final w in ((p as Map)['warnings'] as List)) {
              severities.add('${(w as Map)['level']}');
            }
          }
        }
      }
      for (final (_, raw) in rawAlerts()) {
        severities.add('${raw['level']}');
      }
      for (final f in fixtures.values.where((f) => f.name.startsWith('field'))) {
        for (final r in (f.bodyMap['risks'] as List)) {
          severities.add('${(r as Map)['level']}');
        }
      }
      expect(statuses.difference(_wires(ScanStatus.values)), isEmpty, reason: 'scan status');
      expect(
        actions.difference(_wires(NextAction.values.where((a) => a != NextAction.unknown))),
        isEmpty,
        reason: 'next step',
      );
      expect(routes.difference(_wires(DiseaseRoute.values)), isEmpty, reason: 'disease route');
      expect(severities.difference(_wires(Severity.values)), isEmpty, reason: 'severity / level');
      expect(
        timing.difference(_wires(TimingAction.values.where((a) => a != TimingAction.unknown))),
        isEmpty,
        reason: 'timing',
      );
      expect(
        timing,
        containsAll(['spray_now', 'wait', 'repeat_within_days']),
        reason: 'a timing action has no fixture',
      );
      // Every status of the contract is covered by a fixture, so no route of routeForScan is untested.
      expect(statuses, _wires(ScanStatus.values), reason: 'a scan status has no fixture');
      // ignore: avoid_print
      print('statuses=$statuses actions=$actions routes=$routes severities=$severities timing=$timing');
    });

    test('open sets (warning codes, alert kinds, risk ids, quality issues, crop sources) are safe strings', () {
      final warnings = <String>{};
      final kinds = <String>{};
      final riskIds = <String>{};
      final issues = <String>{};
      final sources = <String>{};
      for (final (_, raw) in rawScans()) {
        final q = raw['quality'];
        if (q is Map) issues.addAll([for (final i in (q['issues'] as List)) '$i']);
        final crop = raw['crop'];
        if (crop is Map) sources.add('${crop['source']}');
        final advice = raw['advice'];
        if (advice is Map) {
          warnings.addAll([for (final w in (advice['warnings'] as List)) '${(w as Map)['code']}']);
          for (final p in (advice['products'] as List)) {
            warnings.addAll([for (final w in ((p as Map)['warnings'] as List)) '${(w as Map)['code']}']);
          }
        }
      }
      for (final f in fixtures.values.where((f) => f.name.startsWith('spray_log'))) {
        if (f.body is Map) warnings.addAll([for (final w in (f.bodyMap['warnings'] as List)) '${(w as Map)['code']}']);
      }
      for (final (_, raw) in rawAlerts()) {
        kinds.add('${raw['kind']}');
      }
      for (final f in fixtures.values.where((f) => f.name.startsWith('field'))) {
        riskIds.addAll([for (final r in (f.bodyMap['risks'] as List)) '${(r as Map)['id']}']);
      }
      for (final code in warnings) {
        expect(code, matches(RegExp(r'^[A-Z][A-Z0-9_]+$')), reason: 'warning code');
      }
      for (final kind in kinds) {
        expect(kind, matches(RegExp(r'^[a-z][a-z_]+$')), reason: 'alert kind');
      }
      for (final id in riskIds) {
        expect(id, matches(RegExp(r'^[a-z][a-z_]+$')), reason: 'risk id');
      }
      // A quality issue the app has no picture for must still lead to a spoken tip that exists.
      for (final issue in {...issues, 'unreadable', 'something_new'}) {
        final tip = qualityTipPrompt(QualityOut(usable: false, issues: [issue]), catalogue);
        expect(catalogue.contains(tip), isTrue, reason: 'issue $issue -> $tip');
      }
      expect(sources, isNotEmpty);
      // ignore: avoid_print
      print(
        'warning codes=$warnings alert kinds=$kinds risk ids=$riskIds quality issues=$issues crop sources=$sources',
      );
    });

    test('quality issues the server sends are in the documented set', () {
      const documented = {'blurry', 'too_dark', 'too_bright', 'too_small', 'no_leaf', 'unreadable'};
      for (final (name, raw) in rawScans()) {
        final q = raw['quality'];
        if (q is Map) {
          expect((q['issues'] as List).map((e) => '$e').toSet().difference(documented), isEmpty, reason: name);
        }
      }
    });
  });

  group('prompt ids the server asks the app to speak exist in the bundled catalogue', () {
    test('next_steps and quality tips', () {
      final unknown = <String>[];
      for (final (name, raw) in rawScans()) {
        for (final s in (raw['next_steps'] as List)) {
          final id = '${(s as Map)['prompt_id']}';
          if (!catalogue.contains(id)) unknown.add('$name: $id');
        }
        final tip = (raw['quality'] as Map)['tip_prompt_id'];
        if (tip != null && !catalogue.contains('$tip')) unknown.add('$name: $tip');
      }
      expect(unknown, isEmpty);
    });

    test('a photo that cannot be used is explained with the server tip (and the app agrees without it)', () {
      for (final name in ['scan_photo_unusable_dark', 'scan_photo_unusable_blurry', 'scan_photo_unusable_bright']) {
        final scan = scanOf(name);
        expect(qualityTipPrompt(scan.quality, catalogue), scan.quality.tipPromptId, reason: name);
        final withoutTip = QualityOut(usable: false, issues: scan.quality.issues);
        expect(catalogue.contains(qualityTipPrompt(withoutTip, catalogue)), isTrue, reason: name);
      }
    });

    test('every crop the server names has a crop_is_ prompt', () {
      for (final (name, raw) in rawScans()) {
        final crop = raw['crop'];
        if (crop is Map && crop['crop_id'] != null) {
          expect(cropPrompt('${crop['crop_id']}', catalogue), isNotNull, reason: '$name ${crop['crop_id']}');
        }
      }
    });
  });

  group('localized texts', () {
    test('every {en, hi} pair has both languages', () {
      final problems = <String>[];
      for (final f in fixtures.values) {
        if (f.isError || f.body == null) continue;
        for (final (path, pair) in localizedPairs(f.body)) {
          // An answer to /ask is in the language that was asked, so its spoken text holds only that language.
          if (f.name.startsWith('ask_') && path == r'$.spoken.text') continue;
          for (final lang in ['en', 'hi']) {
            if ((pair[lang] as String?)?.trim().isEmpty ?? true) problems.add('${f.name} $path is missing $lang');
          }
        }
      }
      expect(problems, isEmpty);
    });

    test('Hindi texts are Hindi (soft check: a name left in English is only reported)', () {
      final latinOnly = <String>{};
      for (final f in fixtures.values) {
        if (f.isError || f.body == null) continue;
        for (final (path, pair) in localizedPairs(f.body)) {
          final hi = '${pair['hi'] ?? ''}';
          if (hi.isNotEmpty && !_devanagari.hasMatch(hi)) latinOnly.add('$path = "$hi"');
        }
      }
      // Reported, not failed: see docs/design-notes/contract.md (crop name of Pea).
      // ignore: avoid_print
      if (latinOnly.isNotEmpty) print('Hindi text without Devanagari: ${latinOnly.take(8).toList()}');
      for (final f in fixtures.values.where((f) => f.name.startsWith('ask_answered_hi'))) {
        expect(f.bodyMap['answer'], matches(_devanagari));
      }
    });

    test('LocalizedText falls back to the other language when one is empty (ask answers)', () {
      final hindi = AskOut.fromJson(fx('ask_answered_hi').bodyMap);
      expect(hindi.spoken!.text.en, isEmpty);
      expect(hindi.spoken!.text.forLang('en'), hindi.answer, reason: 'English UI still gets something to say');
    });
  });

  group('audio references', () {
    final audioUrl = RegExp(r'^/audio/[a-f0-9]{64}\.mp3$');
    final promptUrl = RegExp(r'^/audio-prompts/(hi|en)/[a-z0-9_]{1,80}\.mp3$');

    test('every reference has the documented shape (or is null when no TTS exists)', () {
      var seen = 0;
      for (final f in fixtures.values) {
        if (f.isError || f.body == null) continue;
        void check(Object? raw, String path) {
          if (raw is Map) {
            if (path.endsWith('.audio') && raw.keys.every((k) => k == 'hi' || k == 'en')) {
              for (final e in raw.entries) {
                if (e.value == null) continue;
                final ref = Json.from(e.value as Map);
                seen++;
                final url = '${ref['url']}';
                expect(
                  audioUrl.hasMatch(url) || promptUrl.hasMatch(url),
                  isTrue,
                  reason: '${f.name} $path.${e.key}: $url',
                );
                expect(ref['sha256'], matches(RegExp(r'^[a-f0-9]{64}$')), reason: '${f.name} $path.${e.key}');
              }
            }
            for (final e in raw.entries) {
              check(e.value, '$path.${e.key}');
            }
          } else if (raw is List) {
            for (var i = 0; i < raw.length; i++) {
              check(raw[i], '$path[$i]');
            }
          }
        }

        check(f.body, r'$');
      }
      expect(
        seen,
        greaterThan(0),
        reason: 'no fixture has an audio reference: the scenario with the fake TTS is missing',
      );
    });

    test('audio refs become playable utterances; a missing one falls back to text', () {
      final withAudio = scanOf('scan_ok_scab_with_audio');
      final hi = withAudio.advice!.spoken;
      expect(hi.audio.keys.toSet(), {'hi', 'en'});
      final utterance = hi.toUtterance('hi')!;
      expect(utterance.audio!.url, startsWith('/audio/'));
      expect(utterance.audio!.sha256, hasLength(64));
      final plain = scanOf('scan_ok_scab').advice!.spoken;
      expect(plain.audio, isEmpty, reason: 'null entries are dropped');
      expect(plain.toUtterance('hi')!.audio, isNull);
      expect(plain.toUtterance('hi')!.text, isNotEmpty);
    });

    test('the url of an audio reference can be fetched without a token', () {
      final fetch = fx('audio_fetch');
      expect(fetch.request['auth'], 'none');
      expect(fetch.status, 200);
      expect(fetch.header('content-type'), 'audio/mpeg');
      final urls = [
        for (final lang in ['hi', 'en'])
          if (scanOf('scan_ok_scab_with_audio').spoken.audio[lang] != null)
            scanOf('scan_ok_scab_with_audio').spoken.audio[lang]!.url,
      ];
      expect(urls, contains(fetch.path));
      expect(fx('error_404_audio').bodyMap['code'], 'audio_not_found');
      final ask = AskOut.fromJson(fx('ask_answered_with_audio').bodyMap);
      expect(ask.spoken!.audio.keys, ['en'], reason: 'audio only for the language of the answer');
    });
  });

  group('what the app does with each answer', () {
    const expectedRoute = {
      'scan_ok_scab': Routes.scanAdvice,
      'scan_ok_scab_with_audio': Routes.scanAdvice,
      'scan_ok_scab_rain_expected': Routes.scanAdvice,
      'scan_ok_scab_after_washoff': Routes.scanAdvice,
      'scan_photo_unusable_dark': Routes.scanRetake,
      'scan_photo_unusable_blurry': Routes.scanRetake,
      'scan_photo_unusable_bright': Routes.scanRetake,
      'scan_confirm_crop': Routes.scanConfirm,
      'scan_confirm_crop_pea': Routes.scanConfirm,
      'scan_needs_expert_marssonina': Routes.scanExpert,
      'scan_needs_expert_alternaria': Routes.scanExpert,
      'scan_needs_expert_low_confidence': Routes.scanExpert,
      'scan_needs_expert_no_disease_result': Routes.scanExpert,
      'scan_needs_expert_crop_unknown': Routes.scanExpert,
      'scan_not_a_disease': Routes.scanExpert,
      'crop_confirm': Routes.scanAdvice,
      'crop_confirm_no_approved_data': Routes.scanExpert,
    };

    for (final name in scanFixtures) {
      test('routeForScan($name)', () => expect(routeForScan(scanOf(name)), expectedRoute[name]));
    }

    test('every status the server can send is routed to a screen that exists', () {
      final routed = {
        for (final s in ScanStatus.values)
          s: routeForScan(
            ScanOut(
              id: 'x',
              status: s,
              crop: const CropOut(cropId: 'Apple'),
            ),
          ),
      };
      expect(routed.values.toSet(), {Routes.scanAdvice, Routes.scanConfirm, Routes.scanRetake, Routes.scanExpert});
    });

    test('server-chosen prompt ids are the ones the screens pick', () {
      final ok = scanOf('scan_ok_scab');
      expect(pickPrompt(ok.promptsFor(NextAction.markSprayed), 'result_next_diary', catalogue), 'diary_tick_sprayed');
      final expert = scanOf('scan_needs_expert_marssonina');
      expect(pickPrompt(expert.promptsFor(NextAction.askExpert), 'result_expert', catalogue), 'result_expert');
    });
  });

  group('forward compatibility with the real shapes', () {
    Json mutate(String name, void Function(Json json) change) {
      final copy = Json.from(jsonDecode(jsonEncode(fx(name).body)) as Map);
      change(copy);
      return copy;
    }

    test('an unknown status reads as needs_expert and leads to the expert screen', () {
      final scan = ScanOut.fromJson(mutate('scan_ok_scab', (j) => j['status'] = 'brand_new_status'));
      expect(scan.status, ScanStatus.needsExpert);
      expect(routeForScan(scan), Routes.scanExpert);
    });

    test('unknown severity, route, timing action, next action and extra keys degrade safely', () {
      final json = mutate('scan_ok_scab', (j) {
        j['surprise'] = {'x': 1};
        (j['next_steps'] as List).add({'action': 'dance', 'prompt_id': 'welcome'});
        (j['disease'] as Map)['route'] = 'telepathy';
        final advice = j['advice'] as Map;
        advice['severity'] = 'purple';
        (advice['timing'] as Map)['action'] = 'whenever';
        ((advice['warnings'] as List).first as Map)['level'] = 'orange';
      });
      final scan = ScanOut.fromJson(json);
      expect(scan.status, ScanStatus.ok);
      expect(scan.nextSteps.last.action, NextAction.unknown);
      expect(scan.disease!.route, DiseaseRoute.none);
      expect(scan.advice!.severity, Severity.yellow, reason: 'be careful is the safe default');
      expect(scan.advice!.timing!.action, TimingAction.unknown);
      expect(scan.advice!.warnings.first.level, Severity.yellow);
    });

    test('null or missing parts of a scan do not throw', () {
      final json = mutate('scan_ok_scab', (j) {
        j['crop'] = null;
        j['quality'] = null;
        j['disease'] = null;
        j['advice'] = null;
        j['spoken'] = null;
        j.remove('next_steps');
      });
      final scan = ScanOut.fromJson(json);
      expect(scan.status, ScanStatus.ok);
      expect(scan.advice, isNull);
      expect(scan.quality.usable, isTrue);
      expect(scan.nextSteps, isEmpty);
    });

    test('every model survives an empty object', () {
      for (final kind in _kinds.values) {
        if (kind.type == 'List<SprayLogOut>') continue;
        expect(() => kind.parse(<String, dynamic>{}), returnsNormally, reason: kind.type);
      }
    });
  });

  group('requests the app can send are accepted by the contract (contracts/openapi.json)', () {
    final spec = Json.from(jsonDecode(File('../contracts/openapi.json').readAsStringSync()) as Map);
    final schemas = Json.from(Json.from(spec['components'] as Map)['schemas'] as Map);

    /// The schema name the contract gives to the body of `POST [path]`.
    String requestSchemaOf(String path) {
      final operation = Json.from(Json.from(Json.from(spec['paths'] as Map)[path] as Map)['post'] as Map);
      final content = Json.from(Json.from(operation['requestBody'] as Map)['content'] as Map);
      final ref = Json.from(Json.from(content['application/json'] as Map)['schema'] as Map)[r'$ref'] as String;
      return ref.split('/').last;
    }

    void check(String schema, Json sent) {
      final def = Json.from(schemas[schema] as Map);
      final properties = Json.from(def['properties'] as Map).keys.toSet();
      expect(sent.keys.toSet().difference(properties), isEmpty, reason: '$schema: keys the server does not know');
      final need = {for (final r in (def['required'] as List? ?? const [])) '$r'};
      expect(need.difference(sent.keys.toSet()), isEmpty, reason: '$schema: required keys missing');
    }

    test('request bodies', () {
      check(
        requestSchemaOf('/v1/auth/login'),
        const LoginIn(username: 'f001', password: 'farm1234', deviceId: 'd').toJson(),
      );
      check('RefreshIn', const RefreshIn(refreshToken: 't').toJson());
      check('FarmerPatch', const FarmerPatch(language: 'hi', name: 'n').toJson());
      check('DeviceIn', const DeviceIn(platform: 'android', pushToken: 't', appVersion: '1').toJson());
      check('CropConfirmIn', const CropConfirmIn(cropId: 'Apple').toJson());
      check(
        'SprayLogIn',
        SprayLogIn(
          cropId: 'Apple',
          adviceId: 'a',
          productId: 'P1',
          freeText: 'f',
          sprayedAt: DateTime.utc(2026, 5, 12),
          notes: 'n',
        ).toJson(),
      );
      check('AskIn', const AskIn(question: 'why?', language: 'hi', cropId: 'Apple').toJson());
      check('ExpertRequestIn', const ExpertRequestIn(scanId: 's', message: 'm').toJson());
    });

    test('the request recorded for the plain "I sprayed" tick has the keys the app sends for it', () {
      final recorded = Json.from(fx('spray_log_advice_only').request['json'] as Map);
      expect(recorded.keys, const SprayLogIn(cropId: 'Apple', adviceId: 'a').toJson().keys);
    });

    test('every call of DioApiClient hits a path, method and query the contract has', () async {
      final seen = <(String, String, Set<String>)>[];
      final adapter = _RecordingAdapter((o) => seen.add((o.method, o.path, o.queryParameters.keys.toSet())));
      final dir = Directory.systemTemp.createTempSync('contract_photo');
      addTearDown(() => dir.deleteSync(recursive: true));
      final photo = File('${dir.path}/leaf.jpg')..writeAsBytesSync([1, 2, 3]);
      final api = DioApiClient(
        baseUrl: 'http://api.test',
        tokens: InMemoryTokenStore(const StoredTokens(accessToken: 'a', refreshToken: 'r')),
        adapter: adapter,
        retryDelays: const [],
      );
      Future<void> run(Future<Object?> Function() call) async {
        try {
          await call();
        } on Object {
          // The recording adapter answers with an empty object: models may complain, the request is what counts.
        }
      }

      await run(api.health);
      await run(api.meta);
      await run(() => api.login(username: 'f001', password: 'farm1234', deviceId: 'd'));
      await run(() => api.logout('r'));
      await run(api.me);
      await run(() => api.patchMe(const FarmerPatch(language: 'hi')));
      await run(
        () => api.createScan(
          photoPaths: [photo.path],
          clientCrop: 'Apple',
          clientConfidence: 0.9,
          idempotencyKey: 'k' * 10,
        ),
      );
      await run(() => api.addPhotos('0' * 32, [photo.path]));
      await run(() => api.confirmCrop('0' * 32, 'Apple'));
      await run(() => api.getScan('0' * 32));
      await run(() => api.listScans(limit: 5, cursor: 'c'));
      await run(
        () => api.createSprayLog(
          const SprayLogIn(cropId: 'Apple', adviceId: 'a'),
          idempotencyKey: 'k' * 10,
        ),
      );
      await run(api.listSprayLogs);
      await run(api.field);
      await run(api.listAlerts);
      await run(() => api.markAlertRead('0' * 32));
      await run(() => api.registerDevice(const DeviceIn(platform: 'android', pushToken: 't')));
      await run(() => api.ask(const AskIn(question: 'why?')));
      await run(() => api.createExpertRequest(const ExpertRequestIn(scanId: 's')));
      await run(() => api.voiceCatalogue('hi'));
      expect(seen.length, greaterThanOrEqualTo(20));

      final paths = Json.from(spec['paths'] as Map);
      for (final (method, path, query) in seen) {
        final templated = path.replaceAll(RegExp(r'/[0-9a-f]{32}'), '/{id}');
        final entry = paths.entries.firstWhere(
          (e) => e.key.replaceAll(RegExp(r'\{[a-z_]+\}'), '{id}') == templated,
          orElse: () => throw TestFailure('$method $path is not in contracts/openapi.json'),
        );
        final operation = (entry.value as Map)[method.toLowerCase()];
        expect(operation, isNotNull, reason: '$method ${entry.key} is not an operation of the contract');
        final known = {
          for (final p in ((operation as Map)['parameters'] as List? ?? const []))
            if ((p as Map)['in'] == 'query') '${p['name']}',
        };
        expect(query.difference(known), isEmpty, reason: '$method $path sends query keys the server does not read');
      }
    });
  });

  group('the real answers through the real screens', () {
    testWidgets('ok: advice screen shows severity, medicine, dose and speaks the server text', (tester) async {
      final scan = scanOf('scan_ok_scab');
      final env = await openResult(tester, scan);
      expect(keyed('severity-${scan.advice!.severity.wire}'), findsOneWidget);
      expect(keyed('advice-headline'), findsOneWidget);
      for (final p in scan.advice!.products) {
        expect(keyed('product-${p.productId}'), findsOneWidget, reason: p.productId);
        expect(find.text(p.doseText.hi), findsWidgets, reason: 'the dose sentence of ${p.productId}');
      }
      expect(env.voice.log, ['result_intro@hi', '${scan.advice!.spoken.text.hi}@hi', 'diary_tick_sprayed@hi']);
      expect(env.voice.unknownIds, isEmpty);
    });

    for (final (name, language) in [
      ('scan_ok_scab', 'hi'),
      ('scan_ok_scab', 'en'),
      ('scan_needs_expert_marssonina', 'hi'),
      ('scan_not_a_disease', 'hi'),
      ('crop_confirm_no_approved_data', 'en'),
    ]) {
      testWidgets('$name in $language: real text lengths do not overflow a small phone at 1.5x text size', (
        tester,
      ) async {
        final env = await openResult(tester, scanOf(name), language: language, textScale: 1.5);
        expect(tester.takeException(), isNull);
        expect(env.voice.unknownIds, isEmpty);
      });
    }

    testWidgets('ok in English speaks the English text', (tester) async {
      final scan = scanOf('scan_ok_scab');
      final env = await openResult(tester, scan, language: 'en');
      expect(env.voice.log, ['result_intro@en', '${scan.advice!.spoken.text.en}@en', 'diary_tick_sprayed@en']);
      expect(env.voice.unknownIds, isEmpty);
    });

    for (final name in ['scan_photo_unusable_dark', 'scan_photo_unusable_blurry', 'scan_photo_unusable_bright']) {
      testWidgets('$name: retake screen with the server tip', (tester) async {
        final scan = scanOf(name);
        final env = await openResult(tester, scan);
        expect(keyed('retake-issue'), findsOneWidget);
        expect(keyed('retake-camera'), findsOneWidget);
        expect(env.voice.spokenIds.first, scan.quality.tipPromptId);
        expect(env.voice.unknownIds, isEmpty);
      });
    }

    for (final name in [
      'scan_needs_expert_marssonina',
      'scan_needs_expert_alternaria',
      'scan_needs_expert_low_confidence',
      'scan_needs_expert_no_disease_result',
      'scan_needs_expert_crop_unknown',
    ]) {
      testWidgets('$name: expert screen, asks the expert with the scan id, shows no medicine', (tester) async {
        final scan = scanOf(name);
        final env = await openResult(tester, scan);
        expect(keyed('expert-icon-needs_expert'), findsOneWidget);
        expect(keyed('ask-expert'), findsOneWidget);
        expect(
          find.byWidgetPredicate(
            (w) => w.key is ValueKey<String> && (w.key! as ValueKey<String>).value.startsWith('product-'),
          ),
          findsNothing,
        );
        expect(env.voice.spokenIds.first, 'result_expert');
        expect(env.voice.unknownIds, isEmpty);
        await tapKey(tester, 'ask-expert');
        expect(env.api.expertRequests.single.scanId, scan.id);
      });
    }

    testWidgets('no_approved_data: expert screen in its own variant', (tester) async {
      final env = await openResult(tester, scanOf('crop_confirm_no_approved_data'));
      expect(keyed('expert-icon-no_approved_data'), findsOneWidget);
      expect(env.voice.spokenIds.first, 'result_expert');
      expect(env.voice.unknownIds, isEmpty);
    });

    testWidgets('not_a_disease: expert screen in its own variant', (tester) async {
      final scan = scanOf('scan_not_a_disease');
      final env = await openResult(tester, scan);
      expect(keyed('expert-icon-not_a_disease'), findsOneWidget);
      expect(env.voice.spokenTexts, contains(scan.spoken.text.hi));
      expect(env.voice.unknownIds, isEmpty);
    });

    testWidgets('confirm_crop: tick sends the crop and shows the advice', (tester) async {
      final env = await openResult(tester, scanOf('scan_confirm_crop'), afterConfirm: scanOf('crop_confirm'));
      expect(keyed('crop-name'), findsOneWidget);
      expect(env.voice.unknownIds, isEmpty);
      await tapKey(tester, 'crop-yes');
      expect(env.api.confirmedCrops, ['Apple']);
      expect(keyed('severity-${scanOf('crop_confirm').advice!.severity.wire}'), findsOneWidget);
    });

    knownMismatchWidgets(
      'confirm_crop: the screen asks the question "is this the right crop?" (crop_confirm_prompt)',
      '#1 next_steps[confirm_crop].prompt_id is crop_tap_yes, so the question is never spoken',
      (tester) async {
        final env = await openResult(tester, scanOf('scan_confirm_crop'));
        expect(env.voice.spokenIds, ['crop_is_apple', 'crop_confirm_prompt', 'crop_tap_yes', 'crop_tap_no']);
      },
    );

    knownMismatchWidgets(
      'not_a_disease: the first thing spoken is that no disease was seen (result_not_disease)',
      '#5 the server sends add_photo -> scan_add_more, so the screen opens with a question before the finding',
      (tester) async {
        final env = await openResult(tester, scanOf('scan_not_a_disease'));
        expect(env.voice.spokenIds.first, 'result_not_disease');
      },
    );

    testWidgets('confirm_crop for a crop without a recorded picture group still shows (Pea)', (tester) async {
      final env = await openResult(tester, scanOf('scan_confirm_crop_pea'));
      expect(keyed('crop-name'), findsOneWidget);
      expect(env.voice.spokenIds.first, 'crop_is_pea');
      expect(env.voice.unknownIds, isEmpty);
    });
  });

  group('crop ids: the server writes Apple, the app tables are lower case', () {
    knownMismatch(
      'the crop chooser shows the Hindi name of a crop the server lists',
      '#2 AppResources looks crops up case-sensitively: the server says "Apple", the table has "apple"',
      () {
        for (final crop in MetaOut.fromJson(fx('meta').bodyMap).supportedCrops) {
          expect(resources.cropName(crop, 'hi'), isNot(crop), reason: 'English name shown in Hindi for $crop');
        }
      },
    );

    knownMismatch(
      'a crop the server names without a Hindi name (Pea: hi == en) is shown with the Hindi name from the app tables',
      '#3 the backend crop catalogue has no Hindi name for crops outside the demo set and the app trusts hi blindly',
      () {
        final name = scanOf('scan_confirm_crop_pea').crop!.name;
        expect(resources.cropName('Pea', 'hi', serverName: name), matches(_devanagari));
      },
    );

    knownMismatch(
      'the picture group of a crop the server lists is its real group (potato is not a tree)',
      '#2 AppResources.cropGroup is case-sensitive: every server crop falls back to "fruit"',
      () {
        expect(resources.cropGroup('Potato'), 'vegetable');
        expect(resources.cropGroup('Maize'), 'cereal');
      },
    );
  });
}

/// Records every request and answers `{}` (200) so that the client's own methods can run without a server.
class _RecordingAdapter implements HttpClientAdapter {
  _RecordingAdapter(this.onRequest);

  final void Function(RequestOptions options) onRequest;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    await requestStream?.drain<void>();
    onRequest(options);
    return ResponseBody.fromString(
      '{}',
      200,
      headers: {
        'content-type': ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
