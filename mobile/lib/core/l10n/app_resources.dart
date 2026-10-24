import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/models.dart';

class LanguageInfo {
  const LanguageInfo({
    required this.code,
    required this.nativeName,
    required this.ttsLocales,
    this.promptId = '',
    this.badge = '',
  });

  final String code;

  /// The voice prompt that names this language (`language_hindi`), played when its button is tapped.
  final String promptId;

  /// The language's name written in its own script, shown on the language buttons.
  final String nativeName;

  /// On-device TTS locales to try, best first.
  final List<String> ttsLocales;

  /// One letter (or a short sign) in the language's own script, drawn in a circle next to the name so a farmer who
  /// cannot read the name still recognises the button (`"badge"` in `languages.json`; the first letter of the name
  /// when missing).
  final String badge;

  String get badgeText =>
      badge.isNotEmpty ? badge : (nativeName.isEmpty ? code : String.fromCharCode(nativeName.runes.first));
}

class CropInfo {
  const CropInfo({required this.id, required this.name, required this.group});

  final String id;
  final LocalizedText name;

  /// `fruit`, `vegetable` or `cereal`: picks the generic picture until real crop pictures exist.
  final String group;
}

/// Data-driven languages, interface words and crop names (`assets/l10n/*.json`).
/// A new language is a new entry in `languages.json`, a new key in `strings.json`, and its voice prompts.
class AppResources {
  AppResources({required this.languages, required this.defaultLanguage, required this._ui, required this._crops});

  factory AppResources.fromJson({required String languagesJson, required String stringsJson}) {
    final langs = Json.from(jsonDecode(languagesJson) as Map);
    final strings = Json.from(jsonDecode(stringsJson) as Map);
    final languages = <LanguageInfo>[
      for (final l in (langs['languages'] as List? ?? const []).whereType<Map>())
        LanguageInfo(
          code: l['code'] as String,
          nativeName: l['native_name'] as String? ?? l['code'] as String,
          promptId: l['prompt_id'] as String? ?? '',
          badge: l['badge'] as String? ?? '',
          ttsLocales: [for (final t in (l['tts_locales'] as List? ?? const [])) '$t'],
        ),
    ];
    final ui = <String, LocalizedText>{
      for (final e in (strings['ui'] as Map? ?? const {}).entries) '${e.key}': LocalizedText.fromJson(e.value),
    };
    final crops = <String, CropInfo>{
      for (final e in (strings['crops'] as Map? ?? const {}).entries)
        '${e.key}': CropInfo(
          id: '${e.key}',
          name: LocalizedText.fromJson(e.value),
          group: (e.value as Map)['group'] as String? ?? 'fruit',
        ),
    };
    return AppResources(
      languages: languages,
      defaultLanguage: langs['default_language'] as String? ?? languages.first.code,
      ui: ui,
      crops: crops,
    );
  }

  static Future<AppResources> load(AssetBundle bundle) async => AppResources.fromJson(
    languagesJson: await bundle.loadString('assets/l10n/languages.json'),
    stringsJson: await bundle.loadString('assets/l10n/strings.json'),
  );

  final List<LanguageInfo> languages;
  final String defaultLanguage;
  final Map<String, LocalizedText> _ui;
  final Map<String, CropInfo> _crops;

  LanguageInfo language(String code) => languages.firstWhere(
    (l) => l.code == code,
    orElse: () => LanguageInfo(code: code, nativeName: code, ttsLocales: [code]),
  );

  bool supports(String code) => languages.any((l) => l.code == code);

  /// An interface word in [lang]; `{n}`-style placeholders are replaced from [args].
  String t(String key, String lang, {Map<String, Object> args = const {}}) {
    var text = _ui[key]?.forLang(lang) ?? key;
    for (final e in args.entries) {
      text = text.replaceAll('{${e.key}}', '${e.value}');
    }
    return text;
  }

  /// The localized crop name: the server's name if given, else our table, else the id.
  ///
  /// The server writes ids like `Apple`, our table keys are lower case, so both spellings are tried. A server name that
  /// has no Devanagari in Hindi mode (the backend repeats the English name for crops it has no Hindi word for) loses to
  /// our own table when that has the crop.
  String cropName(String id, String lang, {LocalizedText? serverName}) {
    final known = _crop(id);
    if (serverName != null && !serverName.isEmpty) {
      final name = serverName.forLang(lang);
      final needsOwnHindi = lang == 'hi' && known != null && !_devanagari.hasMatch(name);
      return needsOwnHindi ? known.name.forLang(lang) : name;
    }
    if (known != null) return known.name.forLang(lang);
    return id.isEmpty ? id : '${id[0].toUpperCase()}${id.substring(1)}';
  }

  String cropGroup(String id) => _crop(id)?.group ?? 'fruit';

  static final _devanagari = RegExp('[ऀ-ॿ]');

  CropInfo? _crop(String id) => _crops[id] ?? _crops[id.toLowerCase()];

  /// Every crop id this app knows a name for.
  List<String> get cropIds => _crops.keys.toList();
}
