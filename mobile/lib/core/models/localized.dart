import 'json_utils.dart';

/// Text in several languages. The API sends `{en, hi}`; keeping every string entry means a future language
/// arrives as data without a code change.
class LocalizedText {
  const LocalizedText([this.values = const {}]);

  factory LocalizedText.fromJson(Object? json) {
    if (json is! Map) return const LocalizedText();
    return LocalizedText({
      for (final e in json.entries)
        if (e.key is String && e.value is String) e.key as String: e.value as String,
    });
  }

  factory LocalizedText.pair({String en = '', String hi = ''}) =>
      LocalizedText({if (en.isNotEmpty) 'en': en, if (hi.isNotEmpty) 'hi': hi});

  final Map<String, String> values;

  String get en => values['en'] ?? '';
  String get hi => values['hi'] ?? '';

  bool get isEmpty => values.values.every((v) => v.trim().isEmpty);

  /// The text for [lang]; falls back to English, then Hindi, then any other language, then ''.
  String forLang(String lang) {
    final exact = values[lang];
    if (exact != null && exact.trim().isNotEmpty) return exact;
    for (final fallback in const ['en', 'hi']) {
      final v = values[fallback];
      if (v != null && v.trim().isNotEmpty) return v;
    }
    for (final v in values.values) {
      if (v.trim().isNotEmpty) return v;
    }
    return '';
  }

  /// True when there is real text for exactly [lang] (no fallback).
  bool hasLang(String lang) => (values[lang] ?? '').trim().isNotEmpty;

  Json toJson() => Map<String, dynamic>.from(values);

  @override
  bool operator ==(Object other) =>
      other is LocalizedText &&
      other.values.length == values.length &&
      values.entries.every((e) => other.values[e.key] == e.value);

  @override
  int get hashCode => Object.hashAllUnordered(values.entries.map((e) => Object.hash(e.key, e.value)));

  @override
  String toString() => 'LocalizedText($values)';
}

/// A reference to a generated audio file (an mp3 on the server, cached on the phone by [sha256]).
class AudioRef {
  const AudioRef({required this.url, this.sha256, this.durationS});

  factory AudioRef.fromJson(Json json) =>
      AudioRef(url: json.str('url'), sha256: json.strOrNull('sha256'), durationS: json.doubleOrNull('duration_s'));

  final String url;
  final String? sha256;
  final double? durationS;

  Json toJson() => compact({'url': url, 'sha256': sha256, 'duration_s': durationS});
}

/// What the app should say aloud: the text in every language plus optional generated audio per language.
class SpokenOut {
  const SpokenOut({this.text = const LocalizedText(), this.audio = const {}});

  factory SpokenOut.fromJson(Object? json) {
    if (json is! Map) return const SpokenOut();
    final j = Json.from(json);
    final audio = <String, AudioRef>{};
    final raw = j['audio'];
    if (raw is Map) {
      for (final e in raw.entries) {
        final v = e.value;
        if (e.key is String && v is Map) {
          final ref = AudioRef.fromJson(Json.from(v));
          if (ref.url.isNotEmpty) audio[e.key as String] = ref;
        }
      }
    }
    return SpokenOut(text: LocalizedText.fromJson(j['text']), audio: audio);
  }

  final LocalizedText text;
  final Map<String, AudioRef> audio;

  bool get isEmpty => text.isEmpty && audio.isEmpty;

  Json toJson() => {
    'text': text.toJson(),
    'audio': {for (final e in audio.entries) e.key: e.value.toJson()},
  };
}

enum Severity implements WireEnum {
  green('green'),
  yellow('yellow'),
  red('red');

  const Severity(this.wire);

  @override
  final String wire;

  /// Unknown values read as yellow: "be careful" is the safe default.
  static Severity parse(Object? raw) => parseWire(values, raw, Severity.yellow);
}
