import 'package:shared_preferences/shared_preferences.dart';

/// How fast the voice speaks. [ttsRate] is the flutter_tts rate (0.5 = normal), [audioSpeed] the mp3 playback speed.
enum SpeechSpeed {
  slow(0.35, 0.85),
  normal(0.5, 1.0),
  fast(0.65, 1.15);

  const SpeechSpeed(this.ttsRate, this.audioSpeed);

  final double ttsRate;
  final double audioSpeed;
}

enum VolumeLevel {
  low(0.4),
  medium(0.7),
  high(1.0);

  const VolumeLevel(this.value);

  final double value;
}

class AppSettings {
  const AppSettings({
    this.language,
    this.speed = SpeechSpeed.normal,
    this.volume = VolumeLevel.high,
    this.captions = true,
    this.onboardingDone = false,
    this.homeTourDone = false,
    this.cameraExplained = false,
  });

  /// `null` until the farmer picks a language on the first screen.
  final String? language;
  final SpeechSpeed speed;
  final VolumeLevel volume;

  /// Show the spoken sentence as a large caption (default on).
  final bool captions;
  final bool onboardingDone;

  /// The long first-visit speech on Home (intro plus every button) has been played once.
  final bool homeTourDone;

  /// The "the phone will ask for the camera" prompt has been played once.
  final bool cameraExplained;

  AppSettings copyWith({
    String? language,
    SpeechSpeed? speed,
    VolumeLevel? volume,
    bool? captions,
    bool? onboardingDone,
    bool? homeTourDone,
    bool? cameraExplained,
  }) => AppSettings(
    language: language ?? this.language,
    speed: speed ?? this.speed,
    volume: volume ?? this.volume,
    captions: captions ?? this.captions,
    onboardingDone: onboardingDone ?? this.onboardingDone,
    homeTourDone: homeTourDone ?? this.homeTourDone,
    cameraExplained: cameraExplained ?? this.cameraExplained,
  );
}

/// Persists [AppSettings] in SharedPreferences.
class SettingsStore {
  SettingsStore(this._prefs);

  final SharedPreferences _prefs;

  static const _language = 'language';
  static const _speed = 'speech_speed';
  static const _volume = 'volume';
  static const _captions = 'captions';
  static const _onboardingDone = 'onboarding_done';
  static const _homeTourDone = 'home_tour_done';
  static const _cameraExplained = 'camera_explained';

  AppSettings load() => AppSettings(
    language: _prefs.getString(_language),
    speed: _enum(SpeechSpeed.values, _prefs.getString(_speed), SpeechSpeed.normal),
    volume: _enum(VolumeLevel.values, _prefs.getString(_volume), VolumeLevel.high),
    captions: _prefs.getBool(_captions) ?? true,
    onboardingDone: _prefs.getBool(_onboardingDone) ?? false,
    homeTourDone: _prefs.getBool(_homeTourDone) ?? false,
    cameraExplained: _prefs.getBool(_cameraExplained) ?? false,
  );

  Future<void> save(AppSettings s) async {
    final language = s.language;
    if (language == null) {
      await _prefs.remove(_language);
    } else {
      await _prefs.setString(_language, language);
    }
    await _prefs.setString(_speed, s.speed.name);
    await _prefs.setString(_volume, s.volume.name);
    await _prefs.setBool(_captions, s.captions);
    await _prefs.setBool(_onboardingDone, s.onboardingDone);
    await _prefs.setBool(_homeTourDone, s.homeTourDone);
    await _prefs.setBool(_cameraExplained, s.cameraExplained);
  }

  static const _lastUsername = 'last_username';

  /// The user name typed at the last successful login (prefilled on the login screen). The password is never stored here:
  /// the login itself stays in the secure token store.
  String? loadLastUsername() => _prefs.getString(_lastUsername);

  Future<void> saveLastUsername(String username) => _prefs.setString(_lastUsername, username);

  static const _farmer = 'farmer_json';

  /// The last known farmer profile (name, crops; the phone is masked), so the app starts offline.
  String? loadFarmerJson() => _prefs.getString(_farmer);

  Future<void> saveFarmerJson(String? json) => json == null ? _prefs.remove(_farmer) : _prefs.setString(_farmer, json);

  static T _enum<T extends Enum>(List<T> values, String? name, T fallback) {
    for (final v in values) {
      if (v.name == name) return v;
    }
    return fallback;
  }
}
