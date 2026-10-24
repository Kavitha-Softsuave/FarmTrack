import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../connectivity/connectivity_service.dart';
import '../models/models.dart';
import '../network/api_client.dart';
import 'audio_cache.dart';
import 'prompt_catalogue.dart';

/// Keeps the server's voice catalogue (audio references for fixed prompts) on disk, so server audio still
/// plays offline. Best effort: a failure never reaches the farmer.
class CatalogueSync {
  CatalogueSync({required this.api, required this.catalogue, required this.directory});

  final ApiClient api;
  final PromptCatalogue catalogue;
  final Directory directory;

  File _file(String lang) => File('${directory.path}${Platform.pathSeparator}voice_catalogue_$lang.json');

  /// Applies the catalogues saved by an earlier run.
  Future<void> loadCached(Iterable<String> languages) async {
    for (final lang in languages) {
      try {
        final file = _file(lang);
        if (!await file.exists()) continue;
        final json = jsonDecode(await file.readAsString());
        if (json is Map) catalogue.applyServer(VoiceCatalogueOut.fromJson(Json.from(json)));
      } catch (_) {
        // A damaged cache file is simply ignored.
      }
    }
  }

  /// Fetches every language from the server, applies it and saves it.
  Future<void> refresh(Iterable<String> languages) async {
    for (final lang in languages) {
      try {
        final out = await api.voiceCatalogue(lang);
        catalogue.applyServer(out);
        await directory.create(recursive: true);
        await _file(lang).writeAsString(jsonEncode(out.toJson()));
      } catch (_) {
        // Offline or server down: the bundled prompts and any cached catalogue keep working.
      }
    }
  }
}

/// The voice package: the server's prompt audio, kept on the phone so it plays without a network.
///
/// What it does: loads the catalogue saved by an earlier run (so cached audio plays at once, offline), asks the server
/// for a fresh catalogue, and downloads the audio files that are not on the phone yet, but only over Wi-Fi or a cable
/// (mobile data is the farmer's money; on mobile data a sentence is fetched only when it is about to be spoken). A
/// download that stops halfway when the Wi-Fi goes is simply resumed the next time the phone is on Wi-Fi.
class VoicePackage {
  VoicePackage({
    required this.sync,
    required this.cache,
    required this.catalogue,
    required this.connectivity,
    required this.languages,
    this.preferredLanguage,
  });

  final CatalogueSync sync;
  final AudioCache cache;
  final PromptCatalogue catalogue;
  final ConnectivityService connectivity;
  final List<String> languages;

  /// The farmer's language is downloaded first (null: the order of [languages]).
  final String? Function()? preferredLanguage;

  StreamSubscription<bool>? _watch;
  Future<void>? _running;

  /// Start-up: saved catalogue, fresh catalogue (when online), audio (when on Wi-Fi), then watch the network.
  Future<void> start() async {
    await sync.loadCached(languages);
    await refresh();
    _watch ??= connectivity.unmeteredChanges.listen((wifi) {
      if (wifi) unawaited(refresh());
    });
  }

  /// Fetches the catalogue and, on Wi-Fi, the missing audio. One run at a time; never throws.
  Future<void> refresh() => _running ??= _refresh().whenComplete(() {
    _running = null;
  });

  Future<void> _refresh() async {
    try {
      if (!await connectivity.isOnline()) return;
      await sync.refresh(languages);
      if (!await connectivity.isUnmetered()) return;
      final first = preferredLanguage?.call();
      final ordered = [if (first != null && languages.contains(first)) first, ...languages.where((l) => l != first)];
      for (final lang in ordered) {
        await prefetchAudio(lang);
      }
    } catch (_) {
      // The voice package is a convenience; the phone's own voice always remains.
    }
  }

  /// Downloads every prompt audio of [lang] that is not cached. Stops as soon as the phone leaves Wi-Fi.
  /// Returns the number of files fetched.
  Future<int> prefetchAudio(String lang) async {
    var fetched = 0;
    for (final id in catalogue.ids.toList()) {
      final audio = catalogue.serverAudio(id, lang);
      if (audio == null) continue;
      if (await cache.peek(audio) != null) continue;
      if (!await connectivity.isUnmetered()) break;
      if (await cache.fetch(audio) != null) fetched++;
    }
    return fetched;
  }

  Future<void> dispose() async {
    await _watch?.cancel();
    _watch = null;
  }
}
