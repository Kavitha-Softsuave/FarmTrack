import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show AssetBundle, rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/theme/app_theme.dart';

/// One suggestion card of the Ask screen (`assets/l10n/ask_suggestions.json`).
class AskSuggestion {
  const AskSuggestion({
    required this.id,
    required this.icon,
    required this.label,
    required this.question,
    this.promptId,
  });

  factory AskSuggestion.fromJson(Json json) => AskSuggestion(
    id: json.str('id'),
    icon: askIcon(json.str('icon')),
    promptId: json.strOrNull('prompt_id'),
    label: LocalizedText.fromJson(json['label']),
    question: LocalizedText.fromJson(json['question']),
  );

  final String id;
  final IconData icon;

  /// The voice prompt that says the question (same text), so bundled audio is used when it exists.
  final String? promptId;

  /// Two or three words under the picture.
  final LocalizedText label;

  /// The question that is spoken and sent to `POST /v1/ask`.
  final LocalizedText question;

  /// Cards without a question or a label in any language are skipped.
  bool get isUsable => id.isNotEmpty && !question.isEmpty && !label.isEmpty;
}

/// Picture names used in the data file. A name that is not here shows the question-mark picture.
const Map<String, IconData> _icons = {
  'water_drop': Icons.water_drop_rounded,
  'hourglass': Icons.hourglass_bottom_rounded,
  'science': AppIcons.medicine,
  'safety': Icons.health_and_safety_rounded,
  'leaf': AppIcons.leaf,
  'forest': Icons.forest_rounded,
  'calendar': Icons.date_range_rounded,
  'repeat': Icons.repeat_rounded,
  'sun': Icons.wb_sunny_rounded,
  'spa': Icons.spa_rounded,
};

IconData askIcon(String name) => _icons[name] ?? AppIcons.question;

/// The names `ask_suggestions.json` may use.
Set<String> get askIconNames => _icons.keys.toSet();

List<AskSuggestion> parseAskSuggestions(String jsonText) {
  final raw = jsonDecode(jsonText);
  if (raw is! Map) return const [];
  return [
    for (final e in Json.from(raw).list('suggestions', AskSuggestion.fromJson))
      if (e.isUsable) e,
  ];
}

Future<List<AskSuggestion>> loadAskSuggestions(AssetBundle bundle) async =>
    parseAskSuggestions(await bundle.loadString('assets/l10n/ask_suggestions.json'));

/// The ten suggestion cards. Loaded on the first visit of the Ask screen (a few kilobytes).
final askSuggestionsProvider = FutureProvider<List<AskSuggestion>>((ref) => loadAskSuggestions(rootBundle));
