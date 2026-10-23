import 'package:flutter/foundation.dart';

import 'utterance.dart';

/// What the screen needs to know about the voice: the caption, whether it is speaking, and which languages
/// had no voice on this phone.
@immutable
class VoiceState {
  const VoiceState({this.caption, this.captionLang, this.owner, this.speaking = false, this.missingVoices = const {}});

  /// The sentence being (or last) spoken, shown as a large caption.
  final String? caption;
  final String? captionLang;

  /// The screen that started the current speech; captions are only shown by their owner.
  final Object? owner;
  final bool speaking;

  /// Languages for which neither audio nor an on-device voice was available.
  final Set<String> missingVoices;

  VoiceState copyWith({
    Object? caption = _keep,
    Object? captionLang = _keep,
    Object? owner = _keep,
    bool? speaking,
    Set<String>? missingVoices,
  }) => VoiceState(
    caption: identical(caption, _keep) ? this.caption : caption as String?,
    captionLang: identical(captionLang, _keep) ? this.captionLang : captionLang as String?,
    owner: identical(owner, _keep) ? this.owner : owner,
    speaking: speaking ?? this.speaking,
    missingVoices: missingVoices ?? this.missingVoices,
  );

  static const Object _keep = Object();
}

/// The only way the app makes sound. One speech queue: two voices never overlap.
abstract interface class VoiceService {
  ValueListenable<VoiceState> get state;

  /// Speaks [items] in order. Completes when everything was spoken, or when the speech was cut off by a newer
  /// [speak] with `interrupt: true` or by [stop]. Never throws: a missing voice shows the caption and moves on.
  ///
  /// With `interrupt: false` the items are appended to what is already being spoken.
  Future<void> speak(List<Utterance> items, {Object? owner, bool interrupt = true});

  /// Speaks the last [speak] call again.
  Future<void> replay();

  /// Stops speaking. If [owner] is given, only when that owner is the one speaking (a screen that closes must
  /// not cut off the screen that replaced it).
  Future<void> stop({Object? owner});

  /// True when this language can be spoken on this phone: bundled audio or an installed on-device voice.
  Future<bool> isLanguageAvailable(String lang);
}

extension VoiceServicePrompts on VoiceService {
  /// Speaks catalogue prompts one after another.
  Future<void> speakPrompts(Iterable<String> ids, {String? lang, Object? owner, bool interrupt = true}) => speak(
    promptList(ids, lang: lang),
    owner: owner,
    interrupt: interrupt,
  );
}
