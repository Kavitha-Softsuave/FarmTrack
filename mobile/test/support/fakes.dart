import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:farmtrack/core/voice/audio_port.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';
import 'package:farmtrack/core/voice/tts_port.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/voice/voice_service.dart';
import 'package:farmtrack/features/scan/photo_picker.dart';

/// A [VoiceService] that records what was spoken and finishes instantly.
///
/// Use it in widget tests: `voice.spokenIds` is every prompt id in order, `voice.calls` the speak calls.
class FakeVoice implements VoiceService {
  FakeVoice(this.catalogue, {this.language = 'hi'});

  final PromptCatalogue catalogue;

  /// The language used for utterances that do not name one (set [languageOf] to follow the app settings).
  String language;
  String Function()? languageOf;

  String get _lang => languageOf?.call() ?? language;

  final List<List<Utterance>> calls = [];
  final List<Utterance> spoken = [];

  /// Ids spoken that the catalogue does not know (a typo in the app would show up here).
  final List<String> unknownIds = [];
  final Set<String> availableLanguages = {'hi', 'en'};
  int stopCalls = 0;
  final ValueNotifier<VoiceState> _state = ValueNotifier(const VoiceState());

  @override
  ValueListenable<VoiceState> get state => _state;

  /// Prompt ids spoken, in order.
  List<String> get spokenIds => [
    for (final u in spoken)
      if (u is PromptUtterance) u.id,
  ];

  /// Texts of dynamic utterances, in order.
  List<String> get spokenTexts => [
    for (final u in spoken)
      if (u is TextUtterance) u.text,
  ];

  /// `id@lang` for prompts and `text@lang` for dynamic text, with the effective language.
  List<String> get log => [
    for (final u in spoken)
      switch (u) {
        PromptUtterance(:final id) => '$id@${u.lang ?? _lang}',
        TextUtterance(:final text) => '$text@${u.lang ?? _lang}',
      },
  ];

  /// Pretends the phone has no voice for [lang] (shows the "voice missing" banner).
  void markVoiceMissing(String lang) {
    _state.value = _state.value.copyWith(missingVoices: {..._state.value.missingVoices, lang});
  }

  /// Forgets everything except the last speak call (the script of the screen that is showing now).
  void keepLastCall() {
    if (calls.isEmpty) return;
    final last = calls.last;
    clear();
    calls.add(last);
    spoken.addAll(last);
  }

  void clear() {
    calls.clear();
    spoken.clear();
    unknownIds.clear();
    stopCalls = 0;
  }

  @override
  Future<void> speak(List<Utterance> items, {Object? owner, bool interrupt = true}) async {
    if (items.isEmpty) return;
    calls.add(List.of(items));
    for (final item in items) {
      spoken.add(item);
      final lang = item.lang ?? _lang;
      final caption = switch (item) {
        PromptUtterance(:final id) => _promptText(id, lang),
        TextUtterance(:final text) => text,
      };
      _state.value = _state.value.copyWith(caption: caption, captionLang: lang, owner: owner, speaking: false);
    }
  }

  String _promptText(String id, String lang) {
    if (!catalogue.contains(id)) {
      unknownIds.add(id);
      return '';
    }
    return catalogue.text(id, lang);
  }

  @override
  Future<void> replay() async {
    if (calls.isNotEmpty) await speak(calls.last, owner: _state.value.owner);
  }

  @override
  Future<void> stop({Object? owner}) async {
    if (owner != null && owner != _state.value.owner) return;
    stopCalls++;
    _state.value = _state.value.copyWith(caption: null, captionLang: null, owner: null);
  }

  @override
  Future<bool> isLanguageAvailable(String lang) async => availableLanguages.contains(lang);
}

/// Shared log of what makes sound, to prove two voices never overlap.
class SoundLog {
  final List<String> events = [];
  int active = 0;
  int maxActive = 0;

  void start(String what) {
    active++;
    if (active > maxActive) maxActive = active;
    events.add('start $what');
  }

  void end(String what) {
    active--;
    events.add('end $what');
  }
}

class FakeTts implements TtsPort {
  FakeTts(this.log, {Set<String>? locales}) : locales = locales ?? {'hi-IN', 'en-IN'};

  final SoundLog log;
  Set<String> locales;
  bool failSpeak = false;

  /// While set, [speak] waits for it (or for [stop]).
  Completer<void>? gate;
  final List<({String text, String locale, double rate, double volume})> spoken = [];
  Completer<void>? _current;

  @override
  Future<bool> isLocaleAvailable(String locale) async => locales.contains(locale);

  @override
  Future<void> speak(String text, {required String locale, required double rate, required double volume}) async {
    if (failSpeak) throw StateError('tts failed');
    spoken.add((text: text, locale: locale, rate: rate, volume: volume));
    log.start('tts:$text');
    final g = gate;
    if (g != null) {
      _current = Completer<void>();
      await Future.any([g.future, _current!.future]);
    } else {
      await Future<void>.delayed(Duration.zero);
    }
    log.end('tts:$text');
  }

  @override
  Future<void> stop() async {
    log.events.add('stop tts');
    final c = _current;
    if (c != null && !c.isCompleted) c.complete();
  }
}

class FakeAudio implements AudioPort {
  FakeAudio(this.log);

  final SoundLog log;

  /// Paths (assets or files) that fail to play.
  final Set<String> failing = {};
  Completer<void>? gate;
  final List<({String path, bool asset, double volume, double speed})> played = [];
  Completer<void>? _current;

  Future<void> _play(String path, bool asset, double volume, double speed) async {
    if (failing.contains(path)) throw StateError('cannot play $path');
    played.add((path: path, asset: asset, volume: volume, speed: speed));
    log.start('audio:$path');
    final g = gate;
    if (g != null) {
      _current = Completer<void>();
      await Future.any([g.future, _current!.future]);
    } else {
      await Future<void>.delayed(Duration.zero);
    }
    log.end('audio:$path');
  }

  @override
  Future<void> playAsset(String assetPath, {required double volume, required double speed}) =>
      _play(assetPath, true, volume, speed);

  @override
  Future<void> playFile(String path, {required double volume, required double speed}) =>
      _play(path, false, volume, speed);

  @override
  Future<void> stop() async {
    log.events.add('stop audio');
    final c = _current;
    if (c != null && !c.isCompleted) c.complete();
  }
}

/// A camera that returns what the test queued: a path, null (came back without a photo) or an exception.
class FakePhotoPicker implements PhotoPicker {
  FakePhotoPicker([List<Object?> script = const []]) : script = List.of(script);

  final List<Object?> script;
  int opened = 0;
  String? lost;

  /// What the gallery returns, one list per opening (a Exception in the list throws).
  final List<Object> gallery = [];
  int galleryOpened = 0;
  int? lastGalleryLimit;

  int _serial = 0;

  /// Queues [count] photos with generated paths.
  void queuePhotos(int count) {
    for (var i = 0; i < count; i++) {
      script.add('/tmp/leaf_${_serial++}.jpg');
    }
  }

  @override
  Future<String?> takePhoto() async {
    opened++;
    if (script.isEmpty) return null;
    final next = script.removeAt(0);
    if (next is Exception) throw next;
    return next as String?;
  }

  /// Queues one gallery answer with [count] generated photo paths.
  void queueGallery(int count) {
    gallery.add([for (var i = 0; i < count; i++) '/tmp/gallery_${_serial++}.jpg']);
  }

  @override
  Future<List<String>> pickFromGallery({int limit = 1}) async {
    galleryOpened++;
    lastGalleryLimit = limit;
    if (gallery.isEmpty) return const [];
    final next = gallery.removeAt(0);
    if (next is Exception) throw next;
    return List<String>.of(next as List<String>).take(limit).toList();
  }

  @override
  Future<String?> recoverLostPhoto() async {
    final path = lost;
    lost = null;
    return path;
  }
}
