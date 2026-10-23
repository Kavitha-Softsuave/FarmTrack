import 'dart:convert';

import 'package:flutter/services.dart';

import '../models/models.dart';

class VoicePrompt {
  const VoicePrompt({required this.id, this.screen = '', this.text = const {}});

  final String id;
  final String screen;

  /// The sentence per language code.
  final Map<String, String> text;
}

/// A prompt ready to play: what to show, and where its audio could come from (best source first).
class ResolvedPrompt {
  const ResolvedPrompt({required this.id, required this.lang, required this.text, this.bundledAsset, this.remote});

  final String id;

  /// The language actually spoken (English when the requested language has no text for this prompt).
  final String lang;
  final String text;
  final String? bundledAsset;
  final AudioRef? remote;
}

/// The fixed prompts (`assets/voice/prompts.json`, written by the VOICE agent) plus audio availability.
///
/// Audio comes from, in order: the bundled mp3 (`assets/voice/<lang>/<id>.mp3`), the server audio reference of
/// `GET /v1/voice/catalogue` (cached on disk by the audio cache), then on-device speech of the text.
class PromptCatalogue {
  PromptCatalogue._(this.version, this.languages, this._prompts, this._bundledAudio);

  factory PromptCatalogue.fromJson(String source, {Set<String> bundledAudioAssets = const {}}) {
    final json = Json.from(jsonDecode(source) as Map);
    final languages = json.strList('languages');
    final prompts = <String, VoicePrompt>{};
    for (final raw in json['prompts'] as List? ?? const []) {
      if (raw is! Map) continue;
      final p = Json.from(raw);
      final id = p.str('id');
      if (id.isEmpty) continue;
      prompts[id] = VoicePrompt(
        id: id,
        screen: p.str('screen'),
        text: {
          for (final lang in languages)
            if (p.str(lang).trim().isNotEmpty) lang: p.str(lang),
        },
      );
    }
    return PromptCatalogue._(json.str('version'), languages, prompts, bundledAudioAssets);
  }

  /// Loads the catalogue from the asset bundle and finds which mp3 files were bundled.
  static Future<PromptCatalogue> load(AssetBundle bundle, {String path = 'assets/voice/prompts.json'}) async {
    final source = await bundle.loadString(path);
    var audio = <String>{};
    try {
      final manifest = await AssetManifest.loadFromAssetBundle(bundle);
      audio = manifest.listAssets().where((a) => a.startsWith('assets/voice/') && a.endsWith('.mp3')).toSet();
    } catch (_) {
      // No manifest (some test setups): behave as if no audio is bundled.
    }
    return PromptCatalogue.fromJson(source, bundledAudioAssets: audio);
  }

  final String version;
  final List<String> languages;
  final Map<String, VoicePrompt> _prompts;
  final Set<String> _bundledAudio;
  final Map<String, Map<String, PromptOut>> _server = {};

  Iterable<String> get ids => _prompts.keys;

  int get length => _prompts.length;

  bool contains(String id) => _prompts.containsKey(id);

  VoicePrompt? operator [](String id) => _prompts[id];

  static String assetPath(String lang, String id) => 'assets/voice/$lang/$id.mp3';

  bool hasBundledAudio(String lang, String id) => _bundledAudio.contains(assetPath(lang, id));

  bool hasAnyBundledAudio(String lang) => _bundledAudio.any((a) => a.startsWith('assets/voice/$lang/'));

  /// The sentence for [id] in [lang], or '' when the id is unknown. Falls back to English.
  String text(String id, String lang) {
    final p = _prompts[id];
    if (p == null) return '';
    return p.text[lang] ?? p.text['en'] ?? p.text.values.firstOrNull ?? '';
  }

  /// Adds the server's audio references (and the text of prompts the app does not know yet).
  void applyServer(VoiceCatalogueOut catalogue) {
    _server[catalogue.language] = {for (final p in catalogue.prompts) p.id: p};
  }

  AudioRef? serverAudio(String id, String lang) => _server[lang]?[id]?.audio;

  ResolvedPrompt? resolve(String id, String lang) {
    final known = _prompts[id];
    final server = _server[lang]?[id];
    if (known == null && (server == null || server.text.isEmpty)) return null;

    final ownText = known?.text[lang];
    if (ownText != null) {
      final asset = hasBundledAudio(lang, id) ? assetPath(lang, id) : null;
      final remote = server?.audio;
      // The caption must match the audio that plays: the bundled sentence for the bundled mp3, the server's
      // sentence for the server mp3. If the bundled file fails to play, the server copy is the next source.
      final serverText = server?.text.trim() ?? '';
      final text = asset == null && remote != null && serverText.isNotEmpty ? serverText : ownText;
      return ResolvedPrompt(id: id, lang: lang, text: text, bundledAsset: asset, remote: remote);
    }
    if (server != null && server.text.trim().isNotEmpty) {
      return ResolvedPrompt(id: id, lang: lang, text: server.text, remote: server.audio);
    }
    // No translation yet: speak the English text with the English voice rather than staying silent.
    final fallback = known?.text['en'] ?? known?.text.values.firstOrNull;
    if (fallback == null) return null;
    final fallbackLang = known!.text.containsKey('en') ? 'en' : known.text.keys.first;
    return ResolvedPrompt(
      id: id,
      lang: fallbackLang,
      text: fallback,
      bundledAsset: hasBundledAudio(fallbackLang, id) ? assetPath(fallbackLang, id) : null,
    );
  }
}
