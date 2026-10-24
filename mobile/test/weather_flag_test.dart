import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/features/diary/date_words.dart';

import 'support/feature_fakes.dart';
import 'support/finders.dart';
import 'support/harness.dart';

/// A server whose `/v1/meta` says [weatherEnabled] (null: the old answer without the field), or is unreachable.
class _MetaApi extends MockApiClient {
  _MetaApi({this.weatherEnabled, this.unreachable = false}) : super(latency: Duration.zero);

  bool? weatherEnabled;
  bool unreachable;

  @override
  Future<MetaOut> meta() async {
    if (unreachable) throw const ApiException.network('offline');
    return MetaOut.fromJson({
      'app_version': '1',
      'supported_languages': ['hi', 'en'],
      if (weatherEnabled != null) 'weather_enabled': weatherEnabled,
    });
  }
}

Future<TestEnv> _env(MockApiClient api) =>
    TestEnv.create(loggedIn: true, api: api, extraOverrides: [clockProvider.overrideWithValue(() => fixedNow)]);

Future<void> _openField(WidgetTester tester, TestEnv env) async {
  useSmallPhone(tester);
  await pumpApp(tester, env, location: '/home');
  await tapKey(tester, 'home-field');
}

void main() {
  test('MetaOut: weather_enabled is read, and a missing field means true', () {
    expect(MetaOut.fromJson({'weather_enabled': false}).weatherEnabled, isFalse);
    expect(MetaOut.fromJson({'weather_enabled': true}).weatherEnabled, isTrue);
    expect(MetaOut.fromJson({'app_version': '1'}).weatherEnabled, isTrue);
    expect(MetaOut.fromJson({'weather_enabled': 'no'}).weatherEnabled, isTrue, reason: 'only a real boolean counts');
    expect(MetaOut.fromJson(MetaOut.fromJson({'weather_enabled': false}).toJson()).weatherEnabled, isFalse);
  });

  group('My field with weather switched off on the server', () {
    testWidgets('weather tiles and the forecast are hidden, the soil sensor and the risks stay', (tester) async {
      final env = await _env(_MetaApi(weatherEnabled: false));
      await _openField(tester, env);
      expect(keyed('reading-temp'), findsNothing);
      expect(keyed('reading-humidity'), findsNothing);
      expect(keyed('reading-rain'), findsNothing);
      expect(keyed('reading-leaf'), findsNothing);
      expect(keyed('reading-soil'), findsOneWidget);
      expect(keyed('forecast-strip'), findsNothing);
      expect(env.prefs.getBool('weather_enabled'), isFalse, reason: 'remembered for the next time offline');
    });

    testWidgets('weather on (or a server that does not know the field) shows everything', (tester) async {
      for (final enabled in [true, null]) {
        final env = await _env(_MetaApi(weatherEnabled: enabled));
        await _openField(tester, env);
        expect(keyed('reading-temp'), findsOneWidget, reason: 'weather_enabled=$enabled');
        expect(keyed('reading-rain'), findsOneWidget);
        expect(keyed('forecast-strip'), findsOneWidget);
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('offline, the last answer of the server is used; with none, weather is shown', (tester) async {
      final api = _MetaApi(unreachable: true);
      var env = await _env(api);
      await _openField(tester, env);
      expect(keyed('reading-temp'), findsOneWidget, reason: 'never heard: shown');
      await tester.pumpWidget(const SizedBox());

      env = await _env(api);
      await env.prefs.setBool('weather_enabled', false);
      await _openField(tester, env);
      expect(keyed('reading-temp'), findsNothing, reason: 'the server said off the last time');
      expect(keyed('reading-soil'), findsOneWidget);
    });
  });
}
