import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter_tts/flutter_tts.dart';

/// The on-device speech engine as the voice service needs it. Tests use a fake.
abstract interface class TtsPort {
  /// True when the phone has a voice for [locale] (for example `hi-IN`).
  Future<bool> isLocaleAvailable(String locale);

  /// Speaks [text] and completes when it has finished, was stopped, or failed.
  Future<void> speak(String text, {required String locale, required double rate, required double volume});

  Future<void> stop();
}

/// `flutter_tts` (Android TextToSpeech, iOS AVSpeechSynthesizer).
class FlutterTtsPort implements TtsPort {
  FlutterTtsPort([FlutterTts? tts]) : _tts = tts ?? FlutterTts();

  final FlutterTts _tts;
  Completer<void>? _current;
  bool _ready = false;
  int _expectedCancels = 0;

  Future<void> _init() async {
    if (_ready) return;
    _ready = true;
    void onDone([Object? _]) {
      final c = _current;
      if (c != null && !c.isCompleted) c.complete();
    }

    // Android reports the stop of the sentence we cut off a moment later, when the next sentence may already be
    // running: that late "cancel" must not end the new sentence early.
    void onCancel() {
      if (_expectedCancels > 0) {
        _expectedCancels--;
        return;
      }
      onDone();
    }

    _tts.setCompletionHandler(onDone);
    _tts.setCancelHandler(onCancel);
    _tts.setErrorHandler(onDone);
    try {
      if (Platform.isIOS) {
        // Speak even when the ring/silent switch is on: this app is audio first.
        await _tts.setSharedInstance(true);
        await _tts.setIosAudioCategory(IosTextToSpeechAudioCategory.playback, const []);
      }
      await _tts.setPitch(1.0);
    } catch (_) {
      // Optional tuning only.
    }
  }

  @override
  Future<bool> isLocaleAvailable(String locale) async {
    try {
      await _init();
      final result = await _tts.isLanguageAvailable(locale);
      return result == true || result == 1;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> speak(String text, {required String locale, required double rate, required double volume}) async {
    await _init();
    final completer = Completer<void>();
    _current = completer;
    try {
      await _tts.setLanguage(locale);
      await _tts.setSpeechRate(rate);
      await _tts.setVolume(volume);
      final started = await _tts.speak(text);
      if (started != 1 && started != true) finish(completer);
    } catch (_) {
      finish(completer);
      rethrow;
    }
    // Safety net: if the engine never reports the end (a lost callback), do not block the queue forever.
    final longest = Duration(seconds: 8, milliseconds: text.length * 200);
    await completer.future.timeout(longest, onTimeout: () {});
  }

  void finish(Completer<void> c) {
    if (!c.isCompleted) c.complete();
  }

  @override
  Future<void> stop() async {
    final c = _current;
    if (c != null && !c.isCompleted) _expectedCancels++;
    try {
      await _tts.stop();
    } catch (_) {
      // Stopping is best effort.
    }
    if (c != null) finish(c);
  }
}
