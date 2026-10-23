import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../models/models.dart';

typedef AudioDownloader = Future<List<int>> Function(String url);

/// Disk cache of server audio, keyed by the sha256 of the file (so identical sentences are stored once).
class AudioCache {
  AudioCache({required this.directory, required this.download, this.maxBytes = 40 * 1024 * 1024});

  final Directory directory;
  final AudioDownloader download;

  /// Oldest files are deleted when the cache grows past this size.
  final int maxBytes;
  final Map<String, Future<File?>> _inFlight = {};

  /// The cached file for [ref], downloading it first if needed. Null when it cannot be had (offline, bad hash).
  Future<File?> fetch(AudioRef ref) {
    final key = ref.sha256 ?? sha256.convert(ref.url.codeUnits).toString();
    return _inFlight[key] ??= _fetch(ref, key).whenComplete(() {
      _inFlight.remove(key);
    });
  }

  /// A file already on disk, without downloading.
  Future<File?> peek(AudioRef ref) async {
    final key = ref.sha256 ?? sha256.convert(ref.url.codeUnits).toString();
    final file = _file(key);
    return await file.exists() ? file : null;
  }

  File _file(String key) => File('${directory.path}${Platform.pathSeparator}$key.mp3');

  Future<File?> _fetch(AudioRef ref, String key) async {
    try {
      final file = _file(key);
      if (await file.exists() && await file.length() > 0) {
        unawaited(file.setLastModified(DateTime.now()).catchError((Object _) {}));
        return file;
      }
      final bytes = await download(ref.url);
      if (bytes.isEmpty) return null;
      final expected = ref.sha256;
      if (expected != null && sha256.convert(bytes).toString() != expected.toLowerCase()) return null;
      await directory.create(recursive: true);
      final tmp = File('${file.path}.part');
      await tmp.writeAsBytes(bytes, flush: true);
      await tmp.rename(file.path);
      unawaited(_trim());
      return file;
    } catch (_) {
      return null;
    }
  }

  Future<void> _trim() async {
    try {
      final files = <File>[
        await for (final e in directory.list())
          if (e is File && e.path.endsWith('.mp3')) e,
      ];
      var total = 0;
      final sizes = <File, int>{};
      for (final f in files) {
        final len = await f.length();
        sizes[f] = len;
        total += len;
      }
      if (total <= maxBytes) return;
      final stats = {for (final f in files) f: (await f.stat()).modified};
      files.sort((a, b) => stats[a]!.compareTo(stats[b]!));
      for (final f in files) {
        if (total <= maxBytes) break;
        total -= sizes[f]!;
        await f.delete();
      }
    } catch (_) {
      // Trimming is housekeeping only.
    }
  }
}
