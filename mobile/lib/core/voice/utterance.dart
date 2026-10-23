import '../models/models.dart';

/// One thing to say. [lang] null means "the farmer's current language".
sealed class Utterance {
  const Utterance({this.lang});

  final String? lang;
}

/// A fixed prompt from the catalogue (`welcome`, `scan_send`, ...).
final class PromptUtterance extends Utterance {
  const PromptUtterance(this.id, {super.lang});

  final String id;

  @override
  String toString() => 'Prompt($id${lang == null ? '' : ', $lang'})';
}

/// Dynamic text from the API (advice, alerts, answers), with generated audio when the server made it.
final class TextUtterance extends Utterance {
  const TextUtterance(this.text, {super.lang, this.audio});

  final String text;
  final AudioRef? audio;

  @override
  String toString() => 'Text("$text"${lang == null ? '' : ', $lang'})';
}

/// Turns prompt ids into utterances, skipping empty ids and repeats.
List<Utterance> promptList(Iterable<String> ids, {String? lang}) {
  final seen = <String>{};
  return [
    for (final id in ids)
      if (id.isNotEmpty && seen.add(id)) PromptUtterance(id, lang: lang),
  ];
}

extension SpokenOutUtterance on SpokenOut {
  /// The spoken text for [lang] with its audio, or null when the server sent nothing to say.
  TextUtterance? toUtterance(String lang) {
    final text = this.text.forLang(lang).trim();
    final ref = audio[lang];
    if (text.isEmpty && ref == null) return null;
    // If the text had to fall back to another language, speak it in that language, without the audio of [lang].
    final spokenLang = this.text.hasLang(lang) || text.isEmpty ? lang : _fallbackLang();
    return TextUtterance(text, lang: spokenLang, audio: spokenLang == lang ? ref : audio[spokenLang]);
  }

  String _fallbackLang() {
    for (final l in const ['en', 'hi']) {
      if (text.hasLang(l)) return l;
    }
    return text.values.keys.first;
  }
}
