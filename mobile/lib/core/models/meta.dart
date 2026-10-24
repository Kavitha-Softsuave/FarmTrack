import 'json_utils.dart';
import 'localized.dart';

class HealthOut {
  const HealthOut({this.status = '', this.db = false});

  factory HealthOut.fromJson(Json json) => HealthOut(status: json.str('status'), db: json.boolOr('db'));

  final String status;
  final bool db;

  Json toJson() => {'status': status, 'db': db};
}

class MetaOut {
  const MetaOut({
    this.appVersion = '',
    this.env = '',
    this.demoClock,
    this.supportedLanguages = const ['hi', 'en'],
    this.supportedCrops = const [],
    this.providers = const {},
    this.weatherEnabled = true,
  });

  factory MetaOut.fromJson(Json json) {
    final providers = <String, String>{};
    final raw = json['providers'];
    if (raw is Map) {
      for (final e in raw.entries) {
        if (e.key is String && e.value is String) providers[e.key as String] = e.value as String;
      }
    }
    final langs = json.strList('supported_languages');
    return MetaOut(
      appVersion: json.str('app_version'),
      env: json.str('env'),
      demoClock: json.dateOrNull('demo_clock'),
      supportedLanguages: langs.isEmpty ? const ['hi', 'en'] : langs,
      supportedCrops: json.strList('supported_crops'),
      providers: providers,
      // An older server has no such field: weather is then on.
      weatherEnabled: json.boolOr('weather_enabled', true),
    );
  }

  final String appVersion;
  final String env;
  final DateTime? demoClock;
  final List<String> supportedLanguages;
  final List<String> supportedCrops;
  final Map<String, String> providers;

  /// `weather_enabled` of `/v1/meta`: false when the operator switched weather off (then the app shows no weather).
  final bool weatherEnabled;

  Json toJson() => {
    'app_version': appVersion,
    'env': env,
    'demo_clock': demoClock?.toIso8601String(),
    'supported_languages': supportedLanguages,
    'supported_crops': supportedCrops,
    'providers': providers,
    'weather_enabled': weatherEnabled,
  };
}

class PromptOut {
  const PromptOut({required this.id, this.text = '', this.audio});

  factory PromptOut.fromJson(Json json) =>
      PromptOut(id: json.str('id'), text: json.str('text'), audio: json.obj('audio', AudioRef.fromJson));

  final String id;
  final String text;
  final AudioRef? audio;

  Json toJson() => compact({'id': id, 'text': text, 'audio': audio?.toJson()});
}

class VoiceCatalogueOut {
  const VoiceCatalogueOut({this.version = '', this.language = 'hi', this.prompts = const []});

  factory VoiceCatalogueOut.fromJson(Json json) => VoiceCatalogueOut(
    version: json.str('version'),
    language: json.str('language', 'hi'),
    prompts: json.list('prompts', PromptOut.fromJson),
  );

  final String version;
  final String language;
  final List<PromptOut> prompts;

  Json toJson() => {
    'version': version,
    'language': language,
    'prompts': [for (final p in prompts) p.toJson()],
  };
}
