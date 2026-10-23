import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/settings/app_settings.dart';
import 'package:farmtrack/core/voice/audio_cache.dart';
import 'package:farmtrack/core/voice/device_voice_service.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';
import 'package:farmtrack/core/voice/utterance.dart';
import 'package:farmtrack/core/voice/voice_service.dart';

import 'support/fakes.dart';
import 'support/harness.dart';

class _Rig {
  _Rig({Set<String> bundled = const {}, Set<String>? ttsLocales, this.downloads = const {}}) {
    catalogue = loadCatalogue(bundledAudio: bundled);
    log = SoundLog();
    tts = FakeTts(log, locales: ttsLocales);
    audio = FakeAudio(log);
    dir = Directory.systemTemp.createTempSync('voice_cache');
    cache = AudioCache(
      directory: dir,
      download: (url) async {
        downloaded.add(url);
        final bytes = downloads[url];
        if (bytes == null) throw StateError('offline');
        return bytes;
      },
    );
    service = DeviceVoiceService(
      catalogue: catalogue,
      resources: loadResources(),
      tts: tts,
      audio: audio,
      cache: cache,
      readingTime: (_) => Duration.zero,
      engineWarmUp: Duration.zero,
      settings: () => VoiceSettings(language: language, speed: speed, volume: volume),
    );
  }

  late final PromptCatalogue catalogue;
  late final SoundLog log;
  late final FakeTts tts;
  late final FakeAudio audio;
  late final Directory dir;
  late final AudioCache cache;
  late final DeviceVoiceService service;
  final Map<String, List<int>> downloads;
  final List<String> downloaded = [];
  String language = 'hi';
  SpeechSpeed speed = SpeechSpeed.normal;
  VolumeLevel volume = VolumeLevel.high;
}

String _sha(List<int> bytes) => sha256.convert(bytes).toString();

void main() {
  group('fixed prompts: bundled audio, then server audio, then on-device speech', () {
    test('bundled audio is played and speech is not used', () async {
      final rig = _Rig(bundled: {PromptCatalogue.assetPath('hi', 'welcome')});
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played.single.path, 'assets/voice/hi/welcome.mp3');
      expect(rig.audio.played.single.asset, isTrue);
      expect(rig.tts.spoken, isEmpty);
    });

    test('without bundled audio the server audio is downloaded once, cached on disk and replayed from there', () async {
      final bytes = utf8.encode('mp3 bytes');
      final rig = _Rig(downloads: {'/audio/w.mp3': bytes});
      rig.catalogue.applyServer(
        VoiceCatalogueOut(
          language: 'hi',
          prompts: [
            PromptOut(
              id: 'welcome',
              text: 'x',
              audio: AudioRef(url: '/audio/w.mp3', sha256: _sha(bytes)),
            ),
          ],
        ),
      );
      await rig.service.speak(const [PromptUtterance('welcome')]);
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.downloaded, ['/audio/w.mp3']);
      expect(rig.audio.played, hasLength(2));
      expect(rig.audio.played.first.asset, isFalse);
      expect(rig.audio.played.first.path, endsWith('${_sha(bytes)}.mp3'));
      expect(File(rig.audio.played.first.path).existsSync(), isTrue);
      expect(rig.tts.spoken, isEmpty);
    });

    test('with no audio at all the text is spoken by the on-device voice with the settings speed and volume', () async {
      final rig = _Rig()
        ..speed = SpeechSpeed.slow
        ..volume = VolumeLevel.medium;
      await rig.service.speak(const [PromptUtterance('scan_send')]);
      final spoken = rig.tts.spoken.single;
      expect(spoken.text, contains('हरा सही का निशान'));
      expect(spoken.locale, 'hi-IN');
      expect(spoken.rate, SpeechSpeed.slow.ttsRate);
      expect(spoken.volume, VolumeLevel.medium.value);
      expect(rig.audio.played, isEmpty);
    });

    test('a failing bundled file falls through to server audio, then to speech', () async {
      final bytes = utf8.encode('b');
      final rig = _Rig(bundled: {PromptCatalogue.assetPath('hi', 'welcome')}, downloads: {'/audio/w.mp3': bytes});
      rig.catalogue.applyServer(
        VoiceCatalogueOut(
          language: 'hi',
          prompts: [
            PromptOut(
              id: 'welcome',
              text: 'x',
              audio: AudioRef(url: '/audio/w.mp3', sha256: _sha(bytes)),
            ),
          ],
        ),
      );
      rig.audio.failing.add('assets/voice/hi/welcome.mp3');
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played.single.asset, isFalse, reason: 'the server copy plays when the bundled file cannot');
      expect(rig.audio.played.single.path, endsWith('${_sha(bytes)}.mp3'));
      expect(rig.tts.spoken, isEmpty);
    });

    test('when the bundled file and the server audio both fail, the sentence is spoken', () async {
      final rig = _Rig(bundled: {PromptCatalogue.assetPath('hi', 'welcome')});
      rig.audio.failing.add('assets/voice/hi/welcome.mp3');
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.tts.spoken.single.text, contains('फार्मट्रैक'));
    });

    test('server audio that cannot be downloaded (offline) falls back to speech', () async {
      final rig = _Rig();
      rig.catalogue.applyServer(
        const VoiceCatalogueOut(
          language: 'hi',
          prompts: [
            PromptOut(
              id: 'welcome',
              text: 'x',
              audio: AudioRef(url: '/audio/missing.mp3'),
            ),
          ],
        ),
      );
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.tts.spoken, hasLength(1));
      expect(rig.audio.played, isEmpty);
    });

    test('english utterances use the English voice, whatever the current language', () async {
      final rig = _Rig();
      await rig.service.speak(const [
        PromptUtterance('choose_language', lang: 'hi'),
        PromptUtterance('choose_language', lang: 'en'),
      ]);
      expect(rig.tts.spoken.map((s) => s.locale), ['hi-IN', 'en-IN']);
      expect(rig.tts.spoken.first.text, contains('कृपया'));
      expect(rig.tts.spoken.last.text, contains('Please choose your language'));
    });

    test('an unknown prompt id is skipped without breaking the chain', () async {
      final rig = _Rig();
      await rig.service.speak(const [PromptUtterance('no_such_prompt'), PromptUtterance('scan_send')]);
      expect(rig.tts.spoken, hasLength(1));
    });
  });

  group('dynamic text', () {
    test('uses the audio url of the language: downloads, caches by sha256, resolves a relative url', () async {
      final bytes = utf8.encode('advice mp3');
      final rig = _Rig(downloads: {'/audio/a.mp3': bytes});
      final spoken = SpokenOut(
        text: LocalizedText.pair(en: 'Spray Score', hi: 'स्कोर छिड़किए'),
        audio: {'hi': AudioRef(url: '/audio/a.mp3', sha256: _sha(bytes))},
      );
      await rig.service.speak([spoken.toUtterance('hi')!]);
      expect(rig.audio.played.single.path, endsWith('${_sha(bytes)}.mp3'));
      expect(rig.tts.spoken, isEmpty);
      expect(await rig.cache.peek(const AudioRef(url: '/x', sha256: null)), isNull);
      expect(await rig.cache.peek(AudioRef(url: '/audio/a.mp3', sha256: _sha(bytes))), isNotNull);
    });

    test('speaks the text with the on-device voice when the language has no audio', () async {
      final rig = _Rig();
      final spoken = SpokenOut(
        text: LocalizedText.pair(en: 'Spray Score', hi: 'स्कोर छिड़किए'),
        audio: {'en': const AudioRef(url: '/audio/en.mp3')},
      );
      await rig.service.speak([spoken.toUtterance('hi')!]);
      expect(rig.tts.spoken.single.text, 'स्कोर छिड़किए');
      expect(rig.tts.spoken.single.locale, 'hi-IN');
    });

    test('a corrupt download (wrong sha256) is rejected and the text is spoken instead', () async {
      final rig = _Rig(downloads: {'/audio/a.mp3': utf8.encode('tampered')});
      final spoken = SpokenOut(
        text: LocalizedText.pair(en: 'Hello', hi: 'नमस्ते'),
        audio: {'hi': const AudioRef(url: '/audio/a.mp3', sha256: 'deadbeef')},
      );
      await rig.service.speak([spoken.toUtterance('hi')!]);
      expect(rig.audio.played, isEmpty);
      expect(rig.tts.spoken.single.text, 'नमस्ते');
      expect(rig.dir.listSync().where((f) => f.path.endsWith('.mp3')), isEmpty);
    });

    test('text in a language with no translation is spoken in the fallback language', () {
      final spoken = SpokenOut(text: LocalizedText.pair(en: 'Only English'));
      final u = spoken.toUtterance('hi')!;
      expect(u.lang, 'en');
      expect(u.text, 'Only English');
      expect(const SpokenOut().toUtterance('hi'), isNull);
    });
  });

  group('one queue', () {
    test('prompts are spoken in the order given and speak() completes at the end', () async {
      final rig = _Rig();
      final done = rig.service.speak(const [
        PromptUtterance('welcome'),
        PromptUtterance('scan_send'),
        PromptUtterance('home_intro'),
      ]);
      expect(rig.tts.spoken, isEmpty);
      await done;
      expect(rig.tts.spoken, hasLength(3));
      expect(rig.log.maxActive, 1);
      expect(rig.service.state.value.speaking, isFalse);
    });

    test('a new speak interrupts the old one and two voices never overlap', () async {
      final rig = _Rig();
      rig.tts.gate = Completer<void>(); // the first sentence "plays" until stopped
      final first = rig.service.speak(const [PromptUtterance('welcome'), PromptUtterance('scan_send')]);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(rig.tts.spoken, hasLength(1));
      expect(rig.service.state.value.speaking, isTrue);

      rig.tts.gate = null;
      final second = rig.service.speak(const [PromptUtterance('home_intro')]);
      await Future.wait([first, second]);

      expect(rig.tts.spoken.map((s) => s.text), hasLength(2)); // welcome, then home_intro (scan_send was cut off)
      expect(rig.tts.spoken.last.text, contains('पहला पन्ना'));
      expect(rig.log.maxActive, 1, reason: 'sounds overlapped: ${rig.log.events}');
      expect(
        rig.log.events.indexOf('stop tts'),
        lessThan(rig.log.events.lastIndexWhere((e) => e.startsWith('start tts'))),
      );
    });

    test('speak with interrupt: false appends to the queue', () async {
      final rig = _Rig();
      rig.tts.gate = Completer<void>();
      final first = rig.service.speak(const [PromptUtterance('welcome')]);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      final second = rig.service.speak(const [PromptUtterance('scan_send')], interrupt: false);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(rig.tts.spoken, hasLength(1), reason: 'the second one waits its turn');
      rig.tts.gate!.complete();
      await Future.wait([first, second]);
      expect(rig.tts.spoken, hasLength(2));
      expect(rig.log.maxActive, 1);
    });

    test('stop() silences and clears the caption; stop(owner:) only stops its own speech', () async {
      final rig = _Rig();
      final ownerA = Object();
      final ownerB = Object();
      rig.tts.gate = Completer<void>();
      final speaking = rig.service.speak(const [
        PromptUtterance('welcome'),
        PromptUtterance('scan_send'),
      ], owner: ownerA);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(rig.service.state.value.owner, ownerA);
      expect(rig.service.state.value.caption, isNotEmpty);

      await rig.service.stop(owner: ownerB);
      expect(rig.service.state.value.speaking, isTrue, reason: 'B does not own the speech');

      await rig.service.stop(owner: ownerA);
      await speaking;
      expect(rig.tts.spoken, hasLength(1), reason: 'the second sentence never started');
      expect(rig.service.state.value.speaking, isFalse);
      expect(rig.service.state.value.caption, isNull);
      expect(rig.service.state.value.owner, isNull);
    });

    test('replay speaks the last call again', () async {
      final rig = _Rig();
      await rig.service.speak(const [PromptUtterance('welcome')]);
      await rig.service.replay();
      expect(rig.tts.spoken, hasLength(2));
      expect(rig.tts.spoken.first.text, rig.tts.spoken.last.text);
    });

    test('speed and volume settings apply to the very next sentence, for audio files too', () async {
      final rig = _Rig(bundled: {PromptCatalogue.assetPath('hi', 'welcome')});
      rig.speed = SpeechSpeed.fast;
      rig.volume = VolumeLevel.low;
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played.single.speed, SpeechSpeed.fast.audioSpeed);
      expect(rig.audio.played.single.volume, VolumeLevel.low.value);
    });

    test('speech failures never throw to the caller', () async {
      final rig = _Rig();
      rig.tts.failSpeak = true;
      await rig.service.speak(const [PromptUtterance('welcome'), PromptUtterance('scan_send')]);
      expect(rig.service.state.value.speaking, isFalse);
    });
  });

  group('missing on-device voice', () {
    test('shows the caption, remembers that the voice is missing and carries on with the next sentence', () async {
      final rig = _Rig(ttsLocales: {'en-IN'}); // no Hindi voice installed
      await rig.service.speak(const [
        PromptUtterance('welcome'),
        PromptUtterance('choose_language', lang: 'en'),
      ], owner: 'screen');
      expect(rig.service.state.value.missingVoices, {'hi'});
      expect(rig.tts.spoken.map((s) => s.locale), ['en-IN'], reason: 'only the English sentence could be spoken');
      expect(rig.service.state.value.caption, contains('Please choose your language'));
      expect(await rig.service.isLanguageAvailable('hi'), isFalse);
      expect(await rig.service.isLanguageAvailable('en'), isTrue);
    });

    test('the caption of a sentence that cannot be spoken stays for a reading time', () async {
      final rig = _Rig(ttsLocales: <String>{});
      final slow = DeviceVoiceService(
        catalogue: rig.catalogue,
        resources: loadResources(),
        tts: rig.tts,
        audio: rig.audio,
        cache: rig.cache,
        readingTime: (_) => const Duration(milliseconds: 80),
        engineWarmUp: Duration.zero,
        settings: () => const VoiceSettings(language: 'hi', speed: SpeechSpeed.normal, volume: VolumeLevel.high),
      );
      final started = DateTime.now();
      await slow.speak(const [PromptUtterance('welcome')]);
      expect(DateTime.now().difference(started).inMilliseconds, greaterThanOrEqualTo(70));
      expect(slow.state.value.missingVoices, contains('hi'));
    });

    test('a language is available when audio is bundled even without an on-device voice', () async {
      final rig = _Rig(ttsLocales: <String>{}, bundled: {PromptCatalogue.assetPath('hi', 'welcome')});
      expect(await rig.service.isLanguageAvailable('hi'), isTrue);
      expect(await rig.service.isLanguageAvailable('en'), isFalse);
    });

    test('the first lookup waits once for the speech engine to start before it reports a missing voice', () async {
      final rig = _Rig(ttsLocales: <String>{});
      final service = DeviceVoiceService(
        catalogue: rig.catalogue,
        resources: loadResources(),
        tts: rig.tts,
        audio: rig.audio,
        cache: rig.cache,
        readingTime: (_) => Duration.zero,
        engineWarmUp: const Duration(milliseconds: 50),
        settings: () => const VoiceSettings(language: 'hi', speed: SpeechSpeed.normal, volume: VolumeLevel.high),
      );
      // The engine becomes ready while we wait.
      Timer(const Duration(milliseconds: 20), () => rig.tts.locales = {'hi-IN'});
      await service.speak(const [PromptUtterance('welcome')]);
      expect(rig.tts.spoken, hasLength(1));
      expect(service.state.value.missingVoices, isEmpty);
    });

    test('the missing flag clears once a voice is installed', () async {
      final rig = _Rig(ttsLocales: <String>{});
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.service.state.value.missingVoices, {'hi'});
      rig.tts.locales = {'hi-IN'};
      await rig.service.speak(const [PromptUtterance('welcome')]);
      expect(rig.service.state.value.missingVoices, isEmpty);
    });
  });

  group('AudioCache', () {
    test('trims the oldest files when it grows past its limit', () async {
      final dir = Directory.systemTemp.createTempSync('trim');
      final cache = AudioCache(
        directory: dir,
        maxBytes: 25,
        download: (url) async => List.filled(10, url.codeUnitAt(url.length - 1)),
      );
      for (final n in ['a', 'b', 'c', 'd']) {
        await cache.fetch(AudioRef(url: '/$n'));
        await Future<void>.delayed(const Duration(milliseconds: 30));
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
      final left = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.mp3')).length;
      expect(left, lessThanOrEqualTo(2));
      expect(left, greaterThanOrEqualTo(1));
    });

    test('concurrent requests for the same audio download it once', () async {
      var calls = 0;
      final cache = AudioCache(
        directory: Directory.systemTemp.createTempSync('dedupe'),
        download: (url) async {
          calls++;
          await Future<void>.delayed(const Duration(milliseconds: 20));
          return [1, 2, 3];
        },
      );
      final results = await Future.wait([
        cache.fetch(const AudioRef(url: '/x')),
        cache.fetch(const AudioRef(url: '/x')),
      ]);
      expect(calls, 1);
      expect(results.every((f) => f != null), isTrue);
    });
  });

  test('VoiceState copyWith keeps untouched fields and can clear nullable ones', () {
    const s = VoiceState(caption: 'a', captionLang: 'hi', owner: 'o', speaking: true);
    final t = s.copyWith(speaking: false);
    expect(t.caption, 'a');
    expect(t.owner, 'o');
    final u = s.copyWith(caption: null, owner: null);
    expect(u.caption, isNull);
    expect(u.owner, isNull);
    expect(u.captionLang, 'hi');
  });
}
