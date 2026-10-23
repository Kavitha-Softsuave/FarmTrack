import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'config/app_config.dart';
import 'connectivity/connectivity_service.dart';
import 'l10n/app_resources.dart';
import 'models/models.dart';
import 'network/api_client.dart';
import 'errors/api_exception.dart';
import 'network/dio_api_client.dart';
import 'network/mock_api_client.dart';
import 'settings/app_settings.dart';
import 'storage/token_store.dart';
import 'vision/on_device_detector.dart';
import 'voice/audio_cache.dart';
import 'voice/audio_port.dart';
import 'voice/catalogue_sync.dart';
import 'voice/device_voice_service.dart';
import 'voice/prompt_catalogue.dart';
import 'voice/tts_port.dart';
import 'voice/voice_service.dart';

// ---------------------------------------------------------------------------- bootstrap data
// These are overridden in main() (and in tests) with values loaded before the app starts.

final resourcesProvider = Provider<AppResources>((ref) => throw UnimplementedError('resourcesProvider'));
final promptCatalogueProvider = Provider<PromptCatalogue>((ref) => throw UnimplementedError('promptCatalogueProvider'));
final sharedPreferencesProvider = Provider<SharedPreferences>((ref) => throw UnimplementedError('sharedPreferences'));

/// A random id made once per install and sent at login: the server revokes sessions per device when a refresh token is
/// replayed (for example after a lost answer on a bad network), so without it one phone's retry logs out every session.
final deviceIdProvider = Provider<String>((ref) {
  final prefs = ref.watch(sharedPreferencesProvider);
  const key = 'device_id';
  final saved = prefs.getString(key);
  if (saved != null && saved.length >= 8) return saved;
  final random = Random.secure();
  final id = List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  unawaited(prefs.setString(key, id));
  return id;
});

/// A folder for files that must survive restarts (audio cache, saved voice catalogue).
final supportDirectoryProvider = Provider<Directory>((ref) => throw UnimplementedError('supportDirectory'));

final appConfigProvider = Provider<AppConfig>((ref) => AppConfig.fromEnvironment());

// ---------------------------------------------------------------------------- settings

final settingsStoreProvider = Provider<SettingsStore>((ref) => SettingsStore(ref.watch(sharedPreferencesProvider)));

final settingsProvider = NotifierProvider<SettingsNotifier, AppSettings>(SettingsNotifier.new);

class SettingsNotifier extends Notifier<AppSettings> {
  @override
  AppSettings build() => ref.watch(settingsStoreProvider).load();

  Future<void> _set(AppSettings next) async {
    state = next;
    await ref.read(settingsStoreProvider).save(next);
  }

  Future<void> setLanguage(String code) => _set(state.copyWith(language: code));
  Future<void> setSpeed(SpeechSpeed speed) => _set(state.copyWith(speed: speed));
  Future<void> setVolume(VolumeLevel volume) => _set(state.copyWith(volume: volume));
  Future<void> setCaptions({required bool on}) => _set(state.copyWith(captions: on));
  Future<void> markOnboardingDone() => _set(state.copyWith(onboardingDone: true));
  Future<void> markHomeTourDone() => _set(state.copyWith(homeTourDone: true));
  Future<void> markCameraExplained() => _set(state.copyWith(cameraExplained: true));
}

/// The farmer's language code (the default language until one is chosen).
final languageProvider = Provider<String>(
  (ref) => ref.watch(settingsProvider.select((s) => s.language)) ?? ref.watch(resourcesProvider).defaultLanguage,
);

/// Looks up an interface word in the current language: `ref.watch(stringsProvider)('home_scan_label')`.
final stringsProvider = Provider<String Function(String key, {Map<String, Object> args})>((ref) {
  final resources = ref.watch(resourcesProvider);
  final lang = ref.watch(languageProvider);
  return (key, {args = const {}}) => resources.t(key, lang, args: args);
});

// ---------------------------------------------------------------------------- network

final tokenStoreProvider = Provider<TokenStore>((ref) => SecureTokenStore());

/// SharedPreferences key of a server address typed into the app.
const serverOverrideKey = 'api_base_url_override';

/// The server the app talks to: an address typed on the login screen (so a test phone can follow the PC from one Wi-Fi to
/// another without a rebuild), else the build setting `API_BASE_URL`.
final apiBaseUrlProvider = Provider<String>((ref) {
  final saved = ref.watch(sharedPreferencesProvider).getString(serverOverrideKey)?.trim();
  return (saved != null && saved.isNotEmpty) ? saved : ref.watch(appConfigProvider).apiBaseUrl;
});

final apiClientProvider = Provider<ApiClient>((ref) {
  final config = ref.watch(appConfigProvider);
  if (config.useMockApi) return MockApiClient(latency: config.mockLatency, baseUrl: config.apiBaseUrl);
  return DioApiClient(
    baseUrl: ref.watch(apiBaseUrlProvider),
    tokens: ref.watch(tokenStoreProvider),
    onSessionExpired: () => ref.read(sessionProvider.notifier).expire(),
  );
});

final metaProvider = FutureProvider<MetaOut>((ref) => ref.watch(apiClientProvider).meta());

/// Crop ids for the "choose your crop" grid: the server's list, or the app's own table when offline.
final supportedCropsProvider = FutureProvider<List<String>>((ref) async {
  try {
    final meta = await ref.watch(apiClientProvider).meta();
    if (meta.supportedCrops.isNotEmpty) return meta.supportedCrops;
  } on ApiException {
    // Offline: use what the app knows.
  }
  return ref.watch(resourcesProvider).cropIds;
});

// ---------------------------------------------------------------------------- session

enum SessionStatus { unknown, loggedOut, loggedIn }

class SessionState {
  const SessionState(this.status, [this.farmer]);

  final SessionStatus status;
  final FarmerOut? farmer;

  bool get isLoggedIn => status == SessionStatus.loggedIn;
}

final sessionProvider = NotifierProvider<SessionNotifier, SessionState>(SessionNotifier.new);

class SessionNotifier extends Notifier<SessionState> {
  @override
  SessionState build() => const SessionState(SessionStatus.unknown);

  /// Reads the saved tokens and returns at once; the profile is refreshed in the background, so the app starts
  /// instantly even with no network.
  Future<void> restore() async {
    StoredTokens? tokens;
    try {
      tokens = await ref.read(tokenStoreProvider).read();
    } on Object {
      tokens = null; // a store that fails counts as "no saved login"
    }
    if (tokens == null) {
      state = const SessionState(SessionStatus.loggedOut);
      return;
    }
    state = SessionState(SessionStatus.loggedIn, _cachedFarmer());
    unawaited(refreshProfile());
  }

  /// When reading the saved login took too long or failed: carry on as logged out instead of staying "unknown" (the
  /// router keeps an unknown session on the logo screen).
  void assumeLoggedOut() {
    if (state.status == SessionStatus.unknown) state = const SessionState(SessionStatus.loggedOut);
  }

  /// Fetches the farmer's profile. Offline or server trouble keeps the saved one; a rejected refresh token ends
  /// the session by itself ([expire]).
  Future<void> refreshProfile() async {
    try {
      final farmer = await ref.read(apiClientProvider).me();
      if (state.isLoggedIn) await _setFarmer(farmer);
    } on ApiException {
      // Keep what we have.
    }
  }

  Future<void> login(TokenOut token) async {
    await ref
        .read(tokenStoreProvider)
        .write(StoredTokens(accessToken: token.accessToken, refreshToken: token.refreshToken));
    await _setFarmer(token.farmer);
  }

  /// Forgets the login on this phone at once (works offline) and tells the server in the background, which
  /// revokes the refresh token.
  Future<void> logout() async {
    final store = ref.read(tokenStoreProvider);
    final tokens = await store.read();
    final api = ref.read(apiClientProvider);
    await store.clear();
    await ref.read(settingsStoreProvider).saveFarmerJson(null);
    state = const SessionState(SessionStatus.loggedOut);
    if (tokens != null) {
      unawaited(api.logout(tokens.refreshToken).catchError((Object _) {}));
    }
  }

  /// The server refused our refresh token: back to the login screen.
  void expire() {
    ref.read(settingsStoreProvider).saveFarmerJson(null);
    state = const SessionState(SessionStatus.loggedOut);
  }

  /// Tells the server which language the farmer chose (alerts and spoken advice follow it). Best effort.
  Future<void> syncLanguage(String code) async {
    final farmer = state.farmer;
    if (!state.isLoggedIn || farmer == null || farmer.language == code) return;
    try {
      await _setFarmer(await ref.read(apiClientProvider).patchMe(FarmerPatch(language: code)));
    } on ApiException {
      // The next login or settings change retries.
    }
  }

  Future<void> _setFarmer(FarmerOut farmer) async {
    await ref.read(settingsStoreProvider).saveFarmerJson(jsonEncode(farmer.toJson()));
    state = SessionState(SessionStatus.loggedIn, farmer);
  }

  FarmerOut? _cachedFarmer() {
    final raw = ref.read(settingsStoreProvider).loadFarmerJson();
    if (raw == null) return null;
    try {
      return FarmerOut.fromJson(Json.from(jsonDecode(raw) as Map));
    } catch (_) {
      return null;
    }
  }
}

/// Number of unread alerts for the bell badge; 0 when unknown.
final unreadAlertsProvider = FutureProvider<int>((ref) async {
  if (!ref.watch(sessionProvider).isLoggedIn) return 0;
  try {
    return (await ref.watch(apiClientProvider).listAlerts(limit: 10)).unread;
  } on ApiException {
    return 0;
  }
});

// ---------------------------------------------------------------------------- voice

final ttsPortProvider = Provider<TtsPort>((ref) => FlutterTtsPort());
final audioPortProvider = Provider<AudioPort>((ref) => JustAudioPort());

final audioCacheProvider = Provider<AudioCache>((ref) {
  final api = ref.watch(apiClientProvider);
  return AudioCache(
    directory: Directory('${ref.watch(supportDirectoryProvider).path}${Platform.pathSeparator}voice_cache'),
    download: api.downloadBytes,
  );
});

final catalogueSyncProvider = Provider<CatalogueSync>(
  (ref) => CatalogueSync(
    api: ref.watch(apiClientProvider),
    catalogue: ref.watch(promptCatalogueProvider),
    directory: ref.watch(supportDirectoryProvider),
  ),
);

final voiceServiceProvider = Provider<VoiceService>((ref) {
  final resources = ref.watch(resourcesProvider);
  return DeviceVoiceService(
    catalogue: ref.watch(promptCatalogueProvider),
    resources: resources,
    tts: ref.watch(ttsPortProvider),
    audio: ref.watch(audioPortProvider),
    cache: ref.watch(audioCacheProvider),
    settings: () {
      final s = ref.read(settingsProvider);
      return VoiceSettings(language: s.language ?? resources.defaultLanguage, speed: s.speed, volume: s.volume);
    },
  );
});

// ---------------------------------------------------------------------------- device helpers

final connectivityServiceProvider = Provider<ConnectivityService>((ref) => ConnectivityPlusService());

final onlineProvider = StreamProvider<bool>((ref) async* {
  final service = ref.watch(connectivityServiceProvider);
  yield await service.isOnline();
  yield* service.onlineChanges;
});

final onDeviceDetectorProvider = Provider<OnDeviceDetector>((ref) => const StubOnDeviceDetector());
