import 'dart:convert';
import 'dart:io';

import '../models/models.dart';
import '../network/api_client.dart';
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
