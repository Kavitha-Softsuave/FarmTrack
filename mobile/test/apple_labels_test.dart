import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// The apple classifier of the server has four labels (apple scab, Marssonina blotch, Alternaria leaf spot, healthy).
/// The app only shows what the server decides, so these tests feed the four label ids through every result path:
/// automatic advice, healthy ("no disease seen"), and a low-confidence answer that goes to the expert queue.
class _Api extends MockApiClient {
  _Api(this.build) : super(latency: Duration.zero);

  final ScanOut Function(String id) build;

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
    final scan = build('scan-1');
    scans[scan.id] = scan;
    return scan;
  }
}

class _Label {
  const _Label(this.id, this.en, this.hi);

  final String id;
  final String en;
  final String hi;
}

const _scab = _Label('Apple___Apple_scab', 'Apple scab', 'सेब का स्कैब (पपड़ी रोग)');
const _marssonina = _Label(
  'Apple___Marssonina_blotch',
  'Marssonina leaf blotch',
  'मार्सोनिना पत्ती धब्बा (समय से पहले पत्ते झड़ना)',
);
const _alternaria = _Label('Apple___Alternaria_leaf_spot', 'Alternaria leaf spot', 'आल्टरनेरिया पत्ती धब्बा');
const _healthy = _Label('Apple___healthy', 'Healthy apple leaf', 'स्वस्थ सेब की पत्ती');

/// An `ok` scan for [label]: the scab advice with the label's id and names (the server writes the real text).
ScanOut _advisedScan(String id, _Label label) {
  final base = MockData.okScan(id).toJson();
  final advice = Map<String, Object?>.from(base['advice']! as Map);
  advice['disease_id'] = label.id;
  advice['headline'] = LocalizedText.pair(en: label.en, hi: label.hi).toJson();
  final disease = Map<String, Object?>.from(base['disease']! as Map)
    ..['disease_id'] = label.id
    ..['name'] = LocalizedText.pair(en: label.en, hi: label.hi).toJson();
  return ScanOut.fromJson({...base, 'advice': advice, 'disease': disease});
}

/// The confident "healthy" answer: status `not_a_disease`, no advice, the label kept in `disease`.
ScanOut _healthyScan(String id) => ScanOut.fromJson({
  ...MockData.notADiseaseScan(id).toJson(),
  'disease': DiseaseOut(
    diseaseId: _healthy.id,
    name: LocalizedText.pair(en: _healthy.en, hi: _healthy.hi),
    confidence: 0.93,
    route: DiseaseRoute.none,
  ).toJson(),
});

/// A low-confidence answer for [label]: expert queue, no advice.
ScanOut _unsureScan(String id, _Label label, double confidence) => ScanOut.fromJson({
  ...MockData.needsExpertScan(id).toJson(),
  'disease': DiseaseOut(
    diseaseId: label.id,
    name: LocalizedText.pair(en: label.en, hi: label.hi),
    confidence: confidence,
    route: DiseaseRoute.expertQueue,
  ).toJson(),
});

Future<TestEnv> _scan(WidgetTester tester, ScanOut Function(String id) build, {String language = 'hi'}) async {
  useSmallPhone(tester);
  final env = await TestEnv.create(loggedIn: true, language: language, api: _Api(build));
  env.picker.queuePhotos(1);
  await pumpApp(tester, env, location: '/home');
  await tapKey(tester, 'home-scan');
  await tapKey(tester, 'camera-button');
  await tapKey(tester, 'send-photos');
  env.voice.keepLastCall();
  return env;
}

void main() {
  group('labels are real data of the repository', () {
    // The reference files live next to the app in the repository; a lone checkout of mobile/ skips this group.
    final glossary = File('../data/reference/hindi_glossary.json');
    final catalogue = File('../data/reference/disease_catalogue.csv');
    final present = glossary.existsSync() && catalogue.existsSync();

    test('every label of the apple model has a Hindi name in the glossary and the disease catalogue', () {
      final lines = <String>[];
      void walk(Object? node) {
        if (node is! Map) return;
        node.forEach((key, value) => value is String ? lines.add('$key=$value') : walk(value));
      }

      walk(jsonDecode(glossary.readAsStringSync()));
      final glossaryText = lines.join('\n');
      final rows = catalogue.readAsLinesSync();
      for (final label in [_scab, _marssonina, _alternaria, _healthy]) {
        expect(glossaryText, contains('${label.id}=${label.hi}'), reason: label.id);
        expect(rows.where((r) => r.startsWith('${label.id},')), isNotEmpty, reason: label.id);
      }
    }, skip: present ? false : 'repository data folder not found');
  });

  group('the four labels through the result screens', () {
    for (final label in [_scab, _marssonina, _alternaria]) {
      testWidgets('${label.id}: automatic advice shows the label name in Hindi and speaks the advice', (tester) async {
        final env = await _scan(tester, (id) => _advisedScan(id, label));
        expect(keyed('severity-yellow'), findsOneWidget);
        expect(find.text(label.hi), findsWidgets);
        expect(keyed('product-P007'), findsOneWidget);
        expect(env.voice.unknownIds, isEmpty);
        expect(env.voice.spokenIds.first, 'result_intro');
        expect(env.voice.spokenTexts, hasLength(1));
      });

      testWidgets('${label.id}: in English', (tester) async {
        await _scan(tester, (id) => _advisedScan(id, label), language: 'en');
        expect(find.text(label.en), findsWidgets);
      });
    }

    testWidgets('healthy: "no disease seen" screen, no medicine, camera and home buttons, photo can be repeated', (
      tester,
    ) async {
      final env = await _scan(tester, _healthyScan);
      expect(keyed('expert-icon-not_a_disease'), findsOneWidget);
      expect(keyed('product-P007'), findsNothing);
      expect(env.voice.spokenIds, ['result_not_disease']);
      expect(env.voice.unknownIds, isEmpty);
      expect(keyed('expert-camera'), findsOneWidget);
      expect(keyed('expert-home'), findsOneWidget);
    });

    for (final label in [_marssonina, _alternaria, _scab]) {
      testWidgets('${label.id} at low confidence goes to the expert queue and the expert can be asked', (tester) async {
        final env = await _scan(tester, (id) => _unsureScan(id, label, 0.42));
        expect(keyed('expert-icon-needs_expert'), findsOneWidget);
        expect(keyed('product-P007'), findsNothing, reason: 'never a medicine for an unsure answer');
        expect(env.voice.spokenIds.first, 'result_expert');
        await tapKey(tester, 'ask-expert');
        expect(env.api.expertRequests.single.scanId, 'scan-1');
        expect(keyed('expert-sent'), findsOneWidget);
      });
    }

    testWidgets('a label the app has never heard of is shown by the name the server sent, not an error', (
      tester,
    ) async {
      final env = await _scan(
        tester,
        (id) => _advisedScan(id, const _Label('Apple___Some_new_class', 'Some new disease', 'कोई नई बीमारी')),
      );
      expect(find.text('कोई नई बीमारी'), findsWidgets);
      expect(env.voice.unknownIds, isEmpty);
    });
  });
}
