import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:farmtrack/app.dart';
import 'package:farmtrack/core/config/app_config.dart';
import 'package:farmtrack/core/connectivity/connectivity_service.dart';
import 'package:farmtrack/core/l10n/app_resources.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/providers.dart';
import 'package:farmtrack/core/router/app_router.dart';
import 'package:farmtrack/core/storage/token_store.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';
import 'package:farmtrack/features/scan/photo_picker.dart';

import 'fakes.dart';

AppResources loadResources() => AppResources.fromJson(
  languagesJson: File('assets/l10n/languages.json').readAsStringSync(),
  stringsJson: File('assets/l10n/strings.json').readAsStringSync(),
);

PromptCatalogue loadCatalogue({Set<String> bundledAudio = const {}}) =>
    PromptCatalogue.fromJson(File('assets/voice/prompts.json').readAsStringSync(), bundledAudioAssets: bundledAudio);

/// Everything a widget test needs: fake voice, mock API with zero latency, in-memory storage.
class TestEnv {
  TestEnv._({
    required this.resources,
    required this.catalogue,
    required this.voice,
    required this.api,
    required this.picker,
    required this.connectivity,
    required this.tokens,
    required this.prefs,
    required this.config,
    required this.supportDir,
    required this.extraOverrides,
  });

  final AppResources resources;
  final PromptCatalogue catalogue;
  final FakeVoice voice;
  final MockApiClient api;
  final FakePhotoPicker picker;
  final FakeConnectivity connectivity;
  final TokenStore tokens;
  final SharedPreferences prefs;
  final AppConfig config;
  final Directory supportDir;
  final List<Override> extraOverrides;

  static Future<TestEnv> create({
    String? language = 'hi',
    bool loggedIn = false,
    bool onboardingDone = false,
    bool homeTourDone = true,
    bool cameraExplained = true,
    AppConfig config = const AppConfig.test(),
    List<MockScanScenario>? scanScript,
    MockApiClient? api,
    TokenStore? tokenStore,
    List<Override> extraOverrides = const [],
  }) async {
    SharedPreferences.setMockInitialValues({
      'language': ?language,
      'onboarding_done': onboardingDone || loggedIn,
      'home_tour_done': homeTourDone,
      'camera_explained': cameraExplained,
    });
    final prefs = await SharedPreferences.getInstance();
    final catalogue = loadCatalogue();
    return TestEnv._(
      resources: loadResources(),
      catalogue: catalogue,
      voice: FakeVoice(catalogue, language: language ?? 'hi'),
      api: api ?? MockApiClient(latency: Duration.zero, scanScript: scanScript),
      picker: FakePhotoPicker(),
      connectivity: FakeConnectivity(),
      tokens:
          tokenStore ??
          (loggedIn
              ? InMemoryTokenStore(const StoredTokens(accessToken: 'a', refreshToken: 'r'))
              : InMemoryTokenStore()),
      prefs: prefs,
      config: config,
      supportDir: Directory.systemTemp.createTempSync('farmtrack_test'),
      extraOverrides: extraOverrides,
    );
  }

  List<Override> get overrides => [
    resourcesProvider.overrideWithValue(resources),
    promptCatalogueProvider.overrideWithValue(catalogue),
    sharedPreferencesProvider.overrideWithValue(prefs),
    supportDirectoryProvider.overrideWithValue(supportDir),
    appConfigProvider.overrideWithValue(config),
    apiClientProvider.overrideWithValue(api),
    tokenStoreProvider.overrideWithValue(tokens),
    voiceServiceProvider.overrideWith((ref) {
      voice.languageOf = () => ref.read(languageProvider);
      return voice;
    }),
    photoPickerProvider.overrideWithValue(picker),
    connectivityServiceProvider.overrideWithValue(connectivity),
    ...extraOverrides,
  ];

  /// The whole app, opened at [location] (the splash screen by default).
  Widget app({String location = '/'}) => ProviderScope(
    retry: (_, _) => null,
    overrides: [...overrides, initialLocationProvider.overrideWithValue(location)],
    child: const FarmTrackApp(),
  );

  /// One widget under the real theme and providers (no router).
  Widget wrap(Widget child) => ProviderScope(
    retry: (_, _) => null,
    overrides: overrides,
    child: MaterialApp(home: child),
  );
}

/// Pumps the whole app at [location] with a login already stored, and settles.
Future<ProviderContainer> pumpApp(WidgetTester tester, TestEnv env, {String location = '/'}) async {
  await tester.pumpWidget(env.app(location: location));
  await tester.pumpAndSettle();
  return containerOf(tester);
}

/// The provider container of the app under test.
ProviderContainer containerOf(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));

/// A farmer who is logged in without going through the login screens (session state and stored tokens).
Future<void> signIn(ProviderContainer container) async {
  await container.read(sessionProvider.notifier).login(MockData.tokens(1));
}

/// A phone-sized screen (360 x 640 dp) so layout problems show up in tests.
void useSmallPhone(WidgetTester tester, {double textScale = 1.0, Size size = const Size(360, 640)}) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
    tester.platformDispatcher.clearTextScaleFactorTestValue();
  });
}
