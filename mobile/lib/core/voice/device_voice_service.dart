import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../l10n/app_resources.dart';
import '../models/models.dart';
import '../settings/app_settings.dart';
import 'audio_cache.dart';
import 'audio_port.dart';
import 'prompt_catalogue.dart';
import 'tts_port.dart';
import 'utterance.dart';
import 'voice_service.dart';

/// The settings the voice reads at the moment it speaks (so a change applies to the very next sentence).
class VoiceSettings {
  const VoiceSettings({required this.language, required this.speed, required this.volume});

  final String language;
  final SpeechSpeed speed;
  final VolumeLevel volume;
}

/// How long a caption stays when nothing could be spoken, so the sentence can still be read.
Duration defaultReadingTime(String text) => Duration(milliseconds: (text.length * 60).clamp(1500, 8000));

/// Plays prompts and dynamic text through one queue.
///
/// Fixed prompt: bundled mp3, else cached server audio, else on-device TTS of the text.
/// Dynamic text: audio url for the language (cached by sha256; downloaded when online), else on-device TTS.
/// If nothing can be spoken the caption stays on screen for a reading time and the queue moves on (caption only).
class DeviceVoiceService implements VoiceService {
  DeviceVoiceService({
    required this.catalogue,
    required this.resources,
    required this.tts,
    required this.audio,
    required this.cache,
    required this.settings,
    this.readingTime = defaultReadingTime,
    this.engineWarmUp = const Duration(milliseconds: 700),
    this.isOnline,
    this.downloadTimeout = const Duration(seconds: 6),
  });

  final PromptCatalogue catalogue;
  final AppResources resources;
  final TtsPort tts;
  final AudioPort audio;
  final AudioCache cache;
  final VoiceSettings Function() settings;
  final Duration Function(String text) readingTime;

  /// The Android speech engine starts in the background and may say "no voice" in its first moments. If no voice
  /// is found the very first time, wait this long once and ask again before reporting a missing voice.
  final Duration engineWarmUp;

  /// Whether the phone has a network (null: assume yes). Offline, a sentence that is not cached is not even tried
  /// from the server: the phone's own voice speaks at once.
  final Future<bool> Function()? isOnline;

  /// A server audio file that takes longer than this to arrive is given up for this sentence (the phone's voice
  /// speaks instead); the download goes on and the file is cached for the next time.
  final Duration downloadTimeout;

  final ValueNotifier<VoiceState> _state = ValueNotifier(const VoiceState());
  final Map<String, String> _locales = {};
  bool _warmedUp = false;
  Completer<void> _cut = Completer<void>();
  Future<void> _tail = Future.value();
  int _epoch = 0;
  int _pending = 0;
  List<Utterance> _last = const [];
  Object? _lastOwner;

  @override
  ValueListenable<VoiceState> get state => _state;

  void _update(VoiceState Function(VoiceState) change) => _state.value = change(_state.value);

  @override
  Future<void> speak(List<Utterance> items, {Object? owner, bool interrupt = true}) {
    if (items.isEmpty) return Future.value();
    if (interrupt) {
      _epoch++;
      _cutCurrent();
    }
    _last = List.of(items);
    _lastOwner = owner;
    final epoch = _epoch;
    final previous = _tail;
    final done = Completer<void>();
    _tail = done.future;
    _pending++;
    _update((s) => s.copyWith(speaking: true, owner: owner, caption: interrupt ? null : s.caption));
    return _run(items, owner, epoch, previous, done);
  }

  Future<void> _run(
    List<Utterance> items,
    Object? owner,
    int epoch,
    Future<void> previous,
    Completer<void> done,
  ) async {
    try {
      await previous;
      for (final item in items) {
        if (epoch != _epoch) break;
        await _speakOne(item, owner, epoch);
      }
    } catch (_) {
      // Speaking must never crash a screen.
    } finally {
      _pending--;
      if (_pending == 0) _update((s) => s.copyWith(speaking: false));
      done.complete();
    }
  }

  void _cutCurrent() {
    if (!_cut.isCompleted) _cut.complete();
    _cut = Completer<void>();
    unawaited(audio.stop().catchError((Object _) {}));
    unawaited(tts.stop().catchError((Object _) {}));
  }

  @override
  Future<void> replay() => speak(_last, owner: _lastOwner);

  @override
  Future<void> stop({Object? owner}) async {
    if (owner != null && owner != _state.value.owner) return;
    _epoch++;
    _cutCurrent();
    _update((s) => s.copyWith(caption: null, captionLang: null, owner: null));
    await _tail;
  }

  @override
  Future<bool> isLanguageAvailable(String lang) async =>
      catalogue.hasAnyBundledAudio(lang) || await _ttsLocale(lang) != null;

  Future<String?> _ttsLocale(String lang) async {
    final cached = _locales[lang];
    if (cached != null) return cached;
    var found = await _findLocale(lang);
    if (found == null && !_warmedUp) {
      _warmedUp = true;
      if (engineWarmUp > Duration.zero) await Future<void>.delayed(engineWarmUp);
      found = await _findLocale(lang);
    }
    if (found != null) {
      _warmedUp = true;
      _locales[lang] = found;
    }
    return found;
  }

  Future<String?> _findLocale(String lang) async {
    for (final locale in resources.language(lang).ttsLocales) {
      if (await tts.isLocaleAvailable(locale)) return locale;
    }
    return null;
  }

  Future<void> _speakOne(Utterance item, Object? owner, int epoch) async {
    final current = settings();
    final lang = item.lang ?? current.language;
    final String text;
    String spokenLang = lang;
    String? asset;
    AudioRef? remote;
    switch (item) {
      case PromptUtterance(:final id):
        final resolved = catalogue.resolve(id, lang);
        if (resolved == null) {
          debugPrint('Unknown voice prompt "$id"');
          return;
        }
        text = resolved.text;
        spokenLang = resolved.lang;
        asset = resolved.bundledAsset;
        remote = resolved.remote;
      case TextUtterance(text: final t, audio: final a):
        if (t.trim().isEmpty && a == null) return;
        text = t;
        remote = a;
    }

    final cut = _cut.future;
    _update((s) => s.copyWith(caption: text, captionLang: spokenLang, owner: owner));

    if (asset != null) {
      final path = asset;
      if (await _tryAudio(() => audio.playAsset(path, volume: current.volume.value, speed: current.speed.audioSpeed))) {
        return;
      }
    }
    if (epoch != _epoch) return;
    if (remote != null) {
      final file = await _serverAudio(remote);
      if (epoch != _epoch) return;
      if (file != null &&
          await _tryAudio(
            () => audio.playFile(file.path, volume: current.volume.value, speed: current.speed.audioSpeed),
          )) {
        return;
      }
    }
    if (epoch != _epoch || text.trim().isEmpty) return;
    await _speakWithTts(text, spokenLang, current, cut);
  }

  /// The server audio file: the cached copy first (works offline), else a download when online, within
  /// [downloadTimeout]. Null when there is none, and the next source is used.
  Future<File?> _serverAudio(AudioRef remote) async {
    final cached = await cache.peek(remote);
    if (cached != null) return cached;
    if (isOnline != null && !await isOnline!()) return null;
    return cache.fetch(remote).timeout(downloadTimeout, onTimeout: () => null);
  }

  /// Plays audio; false if it could not be played (the caller then falls back to the next source).
  Future<bool> _tryAudio(Future<void> Function() play) async {
    try {
      await play();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _speakWithTts(String text, String lang, VoiceSettings current, Future<void> cut) async {
    final locale = await _ttsLocale(lang);
    if (locale == null) {
      _update((s) => s.copyWith(missingVoices: {...s.missingVoices, lang}));
      await _hold(text, cut);
      return;
    }
    if (_state.value.missingVoices.contains(lang)) {
      _update((s) => s.copyWith(missingVoices: {...s.missingVoices}..remove(lang)));
    }
    try {
      await tts.speak(text, locale: locale, rate: current.speed.ttsRate, volume: current.volume.value);
    } catch (_) {
      await _hold(text, cut);
    }
  }

  Future<void> _hold(String text, Future<void> cut) async {
    final wait = readingTime(text);
    if (wait <= Duration.zero) return;
    await Future.any([Future<void>.delayed(wait), cut]);
  }
}
