import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/connectivity/connectivity_service.dart';
import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/settings/app_settings.dart';
import 'package:farmtrack/core/voice/audio_cache.dart';
import 'package:farmtrack/core/voice/catalogue_sync.dart';
import 'package:farmtrack/core/voice/device_voice_service.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';
import 'package:farmtrack/core/voice/utterance.dart';

import 'support/fakes.dart';
import 'support/harness.dart';

String _sha(List<int> bytes) => sha256.convert(bytes).toString();

/// A server that serves a voice catalogue and audio bytes, and counts what the phone asks for.
class _Server extends MockApiClient {
  _Server(this.files) : super(latency: Duration.zero);

  /// url -> bytes
  final Map<String, List<int>> files;
  bool down = false;
  final List<String> downloads = [];
  int catalogueCalls = 0;

  @override
  Future<VoiceCatalogueOut> voiceCatalogue(String lang) async {
    catalogueCalls++;
    if (down) throw const ApiException.network('down');
    return VoiceCatalogueOut(
      version: 'v1',
      language: lang,
      prompts: [
        for (final e in files.entries)
          if (e.key.contains('/$lang/'))
            PromptOut(
              id: e.key.split('/').last.replaceAll('.mp3', ''),
              text: 'x',
              audio: AudioRef(url: e.key, sha256: _sha(e.value)),
            ),
      ],
    );
  }

  @override
  Future<List<int>> downloadBytes(String url) async {
    downloads.add(url);
    if (down) throw const ApiException.network('down');
    final bytes = files[url];
    if (bytes == null) throw const ApiException.network('missing');
    return bytes;
  }
}

class _Rig {
  _Rig({
    _Server? server,
    bool online = true,
    bool wifi = true,
    Set<String>? ttsLocales,
    Set<String> bundled = const {},
  }) {
    this.server =
        server ??
        _Server({
          '/audio-prompts/hi/welcome.mp3': utf8.encode('hindi welcome'),
          '/audio-prompts/hi/scan_send.mp3': utf8.encode('hindi send'),
          '/audio-prompts/en/welcome.mp3': utf8.encode('english welcome'),
        });
    connectivity = FakeConnectivity(online: online, unmetered: wifi);
    support = Directory.systemTemp.createTempSync('voice_pkg');
    addTearDown(() => support.deleteSync(recursive: true));
    catalogue = loadCatalogue(bundledAudio: bundled);
    cache = AudioCache(directory: Directory('${support.path}/voice_cache'), download: this.server.downloadBytes);
    sync = CatalogueSync(api: this.server, catalogue: catalogue, directory: support);
    package = VoicePackage(
      sync: sync,
      cache: cache,
      catalogue: catalogue,
      connectivity: connectivity,
      languages: const ['hi', 'en'],
      preferredLanguage: () => 'hi',
    );
    addTearDown(package.dispose);
    log = SoundLog();
    tts = FakeTts(log, locales: ttsLocales);
    audio = FakeAudio(log);
    voice = voiceWith(cache);
  }

  late final _Server server;
  late final FakeConnectivity connectivity;
  late final Directory support;
  late final PromptCatalogue catalogue;
  late final AudioCache cache;
  late final CatalogueSync sync;
  late final VoicePackage package;
  late final SoundLog log;
  late final FakeTts tts;
  late final FakeAudio audio;
  late final DeviceVoiceService voice;

  DeviceVoiceService voiceWith(AudioCache cache, {Duration downloadTimeout = const Duration(seconds: 6)}) =>
      DeviceVoiceService(
        catalogue: catalogue,
        resources: loadResources(),
        tts: tts,
        audio: audio,
        cache: cache,
        isOnline: connectivity.isOnline,
        downloadTimeout: downloadTimeout,
        readingTime: (_) => Duration.zero,
        engineWarmUp: Duration.zero,
        settings: () => const VoiceSettings(language: 'hi', speed: SpeechSpeed.normal, volume: VolumeLevel.high),
      );

  AudioRef refOf(String id, String lang) => catalogue.serverAudio(id, lang)!;
}

void main() {
  group('voice package download', () {
    test('on Wi-Fi the catalogue and every audio file are downloaded and kept', () async {
      final rig = _Rig();
      await rig.package.start();
      expect(rig.server.downloads, hasLength(3));
      expect(await rig.cache.peek(rig.refOf('welcome', 'hi')), isNotNull);
      expect(await rig.cache.peek(rig.refOf('scan_send', 'hi')), isNotNull);
      expect(await rig.cache.peek(rig.refOf('welcome', 'en')), isNotNull);
    });

    test('on mobile data the catalogue is fetched but no audio is downloaded', () async {
      final rig = _Rig(wifi: false);
      await rig.package.start();
      expect(rig.server.catalogueCalls, 2);
      expect(rig.server.downloads, isEmpty);
      expect(rig.catalogue.serverAudio('welcome', 'hi'), isNotNull);
    });

    test('the audio is fetched when the phone reaches Wi-Fi later', () async {
      final rig = _Rig(wifi: false);
      await rig.package.start();
      expect(rig.server.downloads, isEmpty);
      rig.connectivity.switchNetwork(wifi: true);
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(rig.server.downloads, hasLength(3));
    });

    test('files already on the phone are not downloaded again', () async {
      final rig = _Rig();
      await rig.package.start();
      rig.server.downloads.clear();
      await rig.package.refresh();
      expect(rig.server.downloads, isEmpty);
    });

    test('offline start: nothing is requested, and the saved catalogue still points at the cached audio', () async {
      final first = _Rig();
      await first.package.start();
      // The app is started again with no network, with the same folders.
      final offline = _Rig(online: false);
      final reopened = CatalogueSync(api: offline.server, catalogue: offline.catalogue, directory: first.support);
      await reopened.loadCached(const ['hi', 'en']);
      final sameCache = AudioCache(
        directory: Directory('${first.support.path}/voice_cache'),
        download: offline.server.downloadBytes,
      );
      expect(await sameCache.peek(offline.refOf('welcome', 'hi')), isNotNull);
      await offline.package.start();
      expect(offline.server.catalogueCalls, 0);
      expect(offline.server.downloads, isEmpty);
    });

    test('a server that is down keeps what was loaded and does not throw', () async {
      final rig = _Rig();
      await rig.package.start();
      rig.server.down = true;
      await rig.package.refresh();
      expect(rig.catalogue.serverAudio('welcome', 'hi'), isNotNull);
    });

    test("the farmer's language is downloaded first", () async {
      final rig = _Rig();
      await rig.package.start();
      expect(rig.server.downloads.take(2), everyElement(contains('/hi/')));
    });
  });

  group('fallback order: bundled or cached audio, device voice, caption only', () {
    test('cached server audio plays offline, without a request and without the device voice', () async {
      final rig = _Rig();
      await rig.package.start();
      rig.server.downloads.clear();
      rig.connectivity.online = false;
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played.single.path, endsWith('${_sha(utf8.encode('hindi welcome'))}.mp3'));
      expect(rig.tts.spoken, isEmpty);
      expect(rig.server.downloads, isEmpty);
    });

    test('bundled audio wins over cached audio', () async {
      final rig = _Rig(bundled: {PromptCatalogue.assetPath('hi', 'welcome')});
      await rig.package.start();
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played.single.asset, isTrue);
      expect(rig.tts.spoken, isEmpty);
    });

    test('offline and not cached: the device voice speaks at once, no download is tried', () async {
      final rig = _Rig(wifi: false);
      await rig.package.start(); // catalogue only, no audio on the phone
      rig.connectivity.online = false;
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.server.downloads, isEmpty);
      expect(rig.audio.played, isEmpty);
      expect(rig.tts.spoken.single.locale, 'hi-IN');
    });

    test('online and not cached: downloaded and played, then cached for the next time', () async {
      final rig = _Rig(wifi: false);
      await rig.package.start();
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.server.downloads, ['/audio-prompts/hi/welcome.mp3']);
      expect(rig.audio.played, hasLength(1));
      rig.connectivity.online = false;
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played, hasLength(2));
      expect(rig.tts.spoken, isEmpty);
    });

    test('a download that hangs is given up after the timeout and the device voice speaks', () async {
      final rig = _Rig(wifi: false);
      await rig.package.start();
      final slow = AudioCache(
        directory: Directory('${rig.support.path}/slow'),
        download: (_) => Completer<List<int>>().future,
      );
      final voice = rig.voiceWith(slow, downloadTimeout: const Duration(milliseconds: 30));
      await voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.audio.played, isEmpty);
      expect(rig.tts.spoken, hasLength(1));
    });

    test('no audio and no device voice for the language: caption only, the queue still moves on', () async {
      final rig = _Rig(ttsLocales: {'en-IN'}, wifi: false);
      await rig.package.start();
      rig.connectivity.online = false;
      await rig.voice.speak(const [PromptUtterance('welcome'), PromptUtterance('choose_language', lang: 'en')]);
      expect(rig.audio.played, isEmpty);
      expect(rig.tts.spoken.map((s) => s.locale), ['en-IN'], reason: 'only the English sentence has a voice');
      expect(rig.voice.state.value.missingVoices, {'hi'});
    });

    test('a cached file that cannot be played falls through to the device voice', () async {
      final rig = _Rig();
      await rig.package.start();
      final file = await rig.cache.peek(rig.refOf('welcome', 'hi'));
      rig.audio.failing.add(file!.path);
      await rig.voice.speak(const [PromptUtterance('welcome')]);
      expect(rig.tts.spoken, hasLength(1));
    });
  });
}
