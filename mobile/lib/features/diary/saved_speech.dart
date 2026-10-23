import '../../core/models/models.dart';
import '../../core/voice/utterance.dart';

/// What to say after an entry was saved: "Done", and then every warning, one after the other.
///
/// Without warnings it is only the fixed prompt `diary_saved` (it works offline and sounds like the other prompts).
/// With warnings the server's `spoken` text is used when it already holds the first warning (it comes with
/// generated audio and starts with the same "Done" sentence); the server reads only that first warning, so the others
/// are added here, from their own text. When the server sent nothing usable, the prompts `diary_saved` and
/// `diary_warning` and each warning's text are spoken instead.
List<Utterance> savedScript(SprayLogOut entry, String lang) {
  final warnings = [
    for (final w in entry.warnings)
      if (!w.text.isEmpty) w,
  ];
  if (warnings.isEmpty) return [const PromptUtterance('diary_saved')];

  Utterance? say(LocalizedText text) => SpokenOut(text: text).toUtterance(lang);
  final rest = [for (final w in warnings.skip(1)) ?say(w.text)];

  final spoken = entry.spoken?.toUtterance(lang);
  final first = warnings.first.text.forLang(lang);
  if (spoken != null && spoken.text.contains(first)) return [spoken, ...rest];

  return [
    const PromptUtterance('diary_saved'),
    const PromptUtterance('diary_warning'),
    ?say(warnings.first.text),
    ...rest,
  ];
}

/// The sentence to say for one warning (its card's speaker button).
Utterance? warningUtterance(WarningOut warning, String lang) => SpokenOut(text: warning.text).toUtterance(lang);
