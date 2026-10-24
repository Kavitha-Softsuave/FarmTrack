import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart' show debugPrint, visibleForTesting;

import '../errors/api_exception.dart';
import '../models/models.dart';
import '../network/api_client.dart';
import 'offline_queue.dart';
import 'queue_clock.dart';

/// Limits and timings of [PersistentOfflineQueue].
class OfflineQueueLimits {
  const OfflineQueueLimits({
    this.maxItems = 20,
    this.maxBytes = 100 * 1024 * 1024,
    this.maxAge = const Duration(days: 7),
    this.firstRetry = const Duration(seconds: 30),
    this.maxRetry = const Duration(minutes: 15),
  });

  /// A new item is refused when this many are already waiting.
  final int maxItems;

  /// ... or when the photos and files on disk would pass this size (about 100 MB).
  final int maxBytes;

  /// An item older than this is dropped (the advice would be too old to matter).
  final Duration maxAge;

  /// The timer's first wait; it doubles after every failed round up to [maxRetry].
  final Duration firstRetry;
  final Duration maxRetry;
}

enum OfflineRejectReason {
  /// [OfflineQueueLimits.maxItems] items are already waiting.
  tooManyItems,

  /// The photos would not fit in [OfflineQueueLimits.maxBytes].
  tooMuchData,
  noPhotos,

  /// A photo file is gone (the system cleared the camera cache) or cannot be read.
  photoMissing,

  /// The phone could not write the files (storage full).
  storage,

  /// Only used in [QueueEvent.error]: the item waited longer than [OfflineQueueLimits.maxAge].
  expired,
}

/// Why the queue refused (or gave up) an item. The screens show the `error_try_again` prompt for it.
class OfflineQueueException implements Exception {
  const OfflineQueueException(this.reason);

  final OfflineRejectReason reason;

  @override
  String toString() => 'OfflineQueueException(${reason.name})';
}

/// A queue that can reuse the idempotency key of a live attempt.
///
/// A screen first tries the request for real, with a key. If that fails with a timeout the server may still have
/// processed it, so the queued retry must carry the SAME key: the server then returns the first answer instead of
/// creating a second scan or diary entry.
abstract interface class KeyedOfflineQueue implements OfflineQueue {
  Future<String> enqueueScanWithKey(
    String key, {
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  });

  Future<String> enqueueSprayLogWithKey(String key, SprayLogIn log);
}

/// [OfflineQueue] that survives restarts: one JSON file per item in [directory] (`<key>.json`), scan photos copied
/// into `<key>/`.
///
/// Rules: oldest first, one request at a time, the same idempotency key on every attempt. A connection problem, a
/// timeout, a 401 or a 429 stops the round and keeps everything; a 5xx or an unexpected error keeps that item and
/// moves on to the next; any other error (400, 404, 422 ...) drops the item and emits a `dropped` event. Retries run
/// from a timer (30 s doubling to 15 min) while the app is open, and from the triggers that call [flush]: phone back
/// online, app start after login, app resume.
///
/// Files are handled with the synchronous `dart:io` calls on purpose: an item is a few small files, the work takes
/// milliseconds, the check of the limits and the write cannot interleave with another enqueue, and it behaves the same
/// under the fake clock of widget tests. Logs never contain farmer data, only counts.
class PersistentOfflineQueue implements KeyedOfflineQueue {
  PersistentOfflineQueue({
    required this.directory,
    required this._api,
    this._clock = const SystemQueueClock(),
    String? Function()? farmerId,
    bool Function()? canSend,
    this.limits = const OfflineQueueLimits(),
  }) : _farmerId = farmerId ?? (() => null),
       _canSend = canSend ?? (() => true),
       _delay = limits.firstRetry;

  final Directory directory;
  final OfflineQueueLimits limits;
  final ApiClient Function() _api;
  final QueueClock _clock;

  /// The farmer who is logged in. Items remember who queued them: on a shared phone one farmer's photo is never sent
  /// under another farmer's login (it waits until the owner logs in again, or ages out).
  final String? Function() _farmerId;

  /// False while nobody is logged in: a round then sends nothing (the login triggers the next flush).
  final bool Function() _canSend;

  final List<_Item> _items = [];
  final StreamController<int> _pendingChanges = StreamController<int>.broadcast();
  final StreamController<QueueEvent> _events = StreamController<QueueEvent>.broadcast();
  bool _loaded = false;
  bool _disposed = false;
  bool _foreground = true;
  Future<void>? _flushing;
  Timer? _timer;
  Duration _delay;

  // ------------------------------------------------------------------ OfflineQueue

  @override
  int get pending {
    _ensureLoaded();
    return _items.length;
  }

  @override
  Stream<int> get pendingChanges => _pendingChanges.stream;

  @override
  Stream<QueueEvent> get events => _events.stream;

  /// Keys of the waiting items, oldest first.
  @visibleForTesting
  List<String> get keys {
    _ensureLoaded();
    return [for (final i in _items) i.key];
  }

  /// The diary entries that wait to be sent, oldest first, so the diary can show them as "waiting" after a restart.
  /// With [owner] only that farmer's entries (and entries of nobody) are returned.
  List<({String key, SprayLogIn log})> waitingSprayLogs({String? owner}) {
    _ensureLoaded();
    return [
      for (final i in _items)
        if (i.kind == QueueKind.sprayLog && (owner == null || i.owner == null || i.owner == owner))
          (key: i.key, log: i.log!),
    ];
  }

  /// The photos and files of waiting items together, in bytes.
  int get usedBytes {
    _ensureLoaded();
    return _totalBytes;
  }

  /// False while the app is in the background: the retry timer then stays off (the resume trigger flushes).
  set foreground(bool value) {
    _foreground = value;
    if (!value) _cancelTimer();
  }

  @override
  Future<String> enqueueScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  }) => enqueueScanWithKey(
    newIdempotencyKey(),
    photoPaths: photoPaths,
    clientCrop: clientCrop,
    clientConfidence: clientConfidence,
    takenAt: takenAt,
    lat: lat,
    lon: lon,
  );

  @override
  Future<String> enqueueSprayLog(SprayLogIn log) => enqueueSprayLogWithKey(newIdempotencyKey(), log);

  @override
  Future<String> enqueueScanWithKey(
    String key, {
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  }) async {
    _checkKey(key);
    _ensureLoaded();
    if (_find(key) != null) return key; // the same request queued twice (a double tap)
    if (photoPaths.isEmpty) throw const OfflineQueueException(OfflineRejectReason.noPhotos);
    _checkCount();
    var photoBytes = 0;
    for (final path in photoPaths) {
      final file = File(path);
      try {
        photoBytes += file.lengthSync();
      } on FileSystemException {
        throw const OfflineQueueException(OfflineRejectReason.photoMissing);
      }
    }
    if (_totalBytes + photoBytes > limits.maxBytes) {
      throw const OfflineQueueException(OfflineRejectReason.tooMuchData);
    }

    final names = <String>[];
    final folder = Directory(_join(directory.path, key));
    try {
      folder.createSync(recursive: true);
      for (var i = 0; i < photoPaths.length; i++) {
        final name = 'p$i${_extension(photoPaths[i])}';
        File(photoPaths[i]).copySync(_join(folder.path, name));
        names.add(name);
      }
    } on FileSystemException {
      _deleteQuietly(folder);
      throw const OfflineQueueException(OfflineRejectReason.storage);
    }

    final item = _Item(
      key: key,
      kind: QueueKind.scan,
      createdAt: _clock.now().toUtc(),
      owner: _farmerId(),
      photoNames: names,
      clientCrop: clientCrop,
      clientConfidence: clientConfidence,
      takenAt: takenAt,
      lat: lat,
      lon: lon,
    );
    return _store(item, extraBytes: photoBytes);
  }

  @override
  Future<String> enqueueSprayLogWithKey(String key, SprayLogIn log) async {
    _checkKey(key);
    _ensureLoaded();
    if (_find(key) != null) return key;
    _checkCount();
    final item = _Item(
      key: key,
      kind: QueueKind.sprayLog,
      createdAt: _clock.now().toUtc(),
      owner: _farmerId(),
      log: log,
    );
    return _store(item);
  }

  /// Writes the item's JSON file (through a temporary file, so a crash never leaves half a file) and adds it.
  String _store(_Item item, {int extraBytes = 0}) {
    final text = jsonEncode(item.toJson());
    final target = File(_jsonPath(item.key));
    final temp = File('${target.path}.tmp');
    try {
      temp.writeAsStringSync(text, flush: true);
      temp.renameSync(target.path);
    } on FileSystemException {
      _deleteKey(item.key);
      throw const OfflineQueueException(OfflineRejectReason.storage);
    }
    item.bytes = extraBytes + utf8.encode(text).length;
    _items.add(item);
    _pendingChanged();
    if (_timer == null) _scheduleRetry();
    return item.key;
  }

  @override
  Future<void> flush() {
    if (_disposed) return Future<void>.value();
    final running = _flushing;
    if (running != null) return running;
    final round = _flushRound();
    _flushing = round;
    // Block body on purpose: an arrow returning a value would make `whenComplete` wait for it (see docs/design-notes/mobile1.md).
    unawaited(
      round.whenComplete(() {
        _flushing = null;
      }),
    );
    return round;
  }

  /// Stops the timer and closes the streams.
  void dispose() {
    _disposed = true;
    _cancelTimer();
    unawaited(_pendingChanges.close());
    unawaited(_events.close());
  }

  // ------------------------------------------------------------------ sending

  Future<void> _flushRound() async {
    try {
      _ensureLoaded();
      _cancelTimer();
      if (!_canSend()) return;
      var retry = false;
      final tried = <String>{};
      while (!_disposed) {
        _dropExpired();
        final item = _nextToSend(tried);
        if (item == null) break;
        tried.add(item.key);
        final outcome = await _send(item);
        if (outcome == _Outcome.sent) {
          _delay = limits.firstRetry;
        } else if (outcome == _Outcome.retryItem) {
          retry = true;
        } else if (outcome == _Outcome.stopRound) {
          retry = true;
          break;
        }
      }
      if (retry) _scheduleRetry();
    } on Object catch (e) {
      // flush() never throws: whatever happened, the files are still there for the next round.
      debugPrint('offline queue: round failed (${e.runtimeType})');
      _scheduleRetry();
    }
  }

  _Item? _nextToSend(Set<String> tried) {
    final me = _farmerId();
    for (final item in _items) {
      if (tried.contains(item.key)) continue;
      if (item.owner != null && me != null && item.owner != me) continue;
      return item;
    }
    return null;
  }

  Future<_Outcome> _send(_Item item) async {
    try {
      switch (item.kind) {
        case QueueKind.scan:
          final paths = [for (final name in item.photoNames) _join(_join(directory.path, item.key), name)];
          if (paths.any((p) => !File(p).existsSync())) {
            _drop(item, const OfflineQueueException(OfflineRejectReason.photoMissing));
            return _Outcome.dropped;
          }
          final scan = await _api().createScan(
            photoPaths: paths,
            clientCrop: item.clientCrop,
            clientConfidence: item.clientConfidence,
            takenAt: item.takenAt,
            lat: item.lat,
            lon: item.lon,
            idempotencyKey: item.key,
          );
          _finish(item, QueueEvent(type: QueueEventType.sent, kind: QueueKind.scan, key: item.key, scan: scan));
        case QueueKind.sprayLog:
          final log = await _api().createSprayLog(item.log!, idempotencyKey: item.key);
          _finish(item, QueueEvent(type: QueueEventType.sent, kind: QueueKind.sprayLog, key: item.key, sprayLog: log));
      }
      return _Outcome.sent;
    } on ApiException catch (e) {
      return _afterApiError(item, e);
    } on Object catch (e) {
      debugPrint('offline queue: unexpected error while sending (${e.runtimeType})');
      return _Outcome.retryItem;
    }
  }

  _Outcome _afterApiError(_Item item, ApiException e) {
    if (e.isConnectionProblem || e.kind == ApiErrorKind.unauthorized || e.kind == ApiErrorKind.rateLimited) {
      // Nothing is wrong with the item: the phone has no network, the login ran out, or the server asks us to slow down.
      return _Outcome.stopRound;
    }
    if (e.kind == ApiErrorKind.validation || e.kind == ApiErrorKind.client) {
      _drop(item, e); // the server will never accept this request
      return _Outcome.dropped;
    }
    return _Outcome.retryItem; // 5xx, cancelled, unknown: keep it
  }

  void _finish(_Item item, QueueEvent event) {
    _remove(item);
    _emit(event);
  }

  void _drop(_Item item, Object error) {
    _remove(item);
    _emit(QueueEvent(type: QueueEventType.dropped, kind: item.kind, key: item.key, error: error));
  }

  void _dropExpired() {
    final limit = _clock.now().toUtc().subtract(limits.maxAge);
    for (final item in List.of(_items)) {
      if (item.createdAt.isBefore(limit)) {
        _drop(item, const OfflineQueueException(OfflineRejectReason.expired));
      }
    }
  }

  void _remove(_Item item) {
    _items.remove(item);
    _deleteKey(item.key);
    _pendingChanged();
  }

  // ------------------------------------------------------------------ timer

  void _scheduleRetry() {
    if (_disposed || !_foreground || _items.isEmpty) return;
    _cancelTimer();
    final wait = _delay;
    final doubled = _delay * 2;
    _delay = doubled > limits.maxRetry ? limits.maxRetry : doubled;
    _timer = _clock.schedule(wait, () {
      _timer = null;
      unawaited(flush());
    });
  }

  void _cancelTimer() {
    _timer?.cancel();
    _timer = null;
  }

  // ------------------------------------------------------------------ files

  static final RegExp _keyPattern = RegExp(r'^[A-Za-z0-9_-]{8,64}$');
  static final RegExp _photoPattern = RegExp(r'^p\d{1,2}\.[a-z0-9]{2,5}$');

  void _checkKey(String key) {
    if (!_keyPattern.hasMatch(key)) throw ArgumentError.value(key, 'key', 'not a valid idempotency key');
  }

  void _checkCount() {
    if (_items.length >= limits.maxItems) throw const OfflineQueueException(OfflineRejectReason.tooManyItems);
  }

  int get _totalBytes => _items.fold(0, (sum, i) => sum + i.bytes);

  _Item? _find(String key) {
    for (final item in _items) {
      if (item.key == key) return item;
    }
    return null;
  }

  String _jsonPath(String key) => _join(directory.path, '$key.json');

  static String _join(String a, String b) => '$a${Platform.pathSeparator}$b';

  static String _basename(String path) => path.substring(path.lastIndexOf(RegExp(r'[\\/]')) + 1);

  static String _extension(String path) {
    final name = _basename(path);
    final dot = name.lastIndexOf('.');
    final ext = dot < 0 ? '' : name.substring(dot).toLowerCase();
    return RegExp(r'^\.[a-z0-9]{2,5}$').hasMatch(ext) ? ext : '.jpg';
  }

  void _ensureLoaded() {
    if (_loaded) return;
    _loaded = true;
    try {
      directory.createSync(recursive: true);
      final entries = directory.listSync(followLinks: false);
      final withJson = <String>{};
      for (final entity in entries) {
        final name = _basename(entity.path);
        if (entity is! File) continue;
        if (!name.endsWith('.json')) {
          _deleteQuietly(entity); // a temporary file of a write that was cut short
          continue;
        }
        final key = name.substring(0, name.length - '.json'.length);
        final item = _readItem(key, entity);
        if (item == null) {
          debugPrint('offline queue: removed a damaged item');
          _deleteKey(key);
        } else {
          _items.add(item);
          withJson.add(key);
        }
      }
      for (final entity in entries) {
        if (entity is Directory && !withJson.contains(_basename(entity.path))) _deleteQuietly(entity);
      }
    } on FileSystemException catch (e) {
      debugPrint('offline queue: cannot read the folder (${e.runtimeType})');
    }
    _items.sort((a, b) {
      final byTime = a.createdAt.compareTo(b.createdAt);
      return byTime != 0 ? byTime : a.key.compareTo(b.key);
    });
    _dropExpired();
  }

  /// Reads one item; null when the file is damaged or its photos are gone.
  _Item? _readItem(String key, File file) {
    if (!_keyPattern.hasMatch(key)) return null;
    try {
      final text = file.readAsStringSync();
      final raw = jsonDecode(text);
      if (raw is! Map) return null;
      final j = Json.from(raw);
      if (j.str('key') != key) return null;
      final createdAt = j.dateOrNull('created_at');
      if (createdAt == null) return null;
      var bytes = utf8.encode(text).length;
      switch (j.str('kind')) {
        case 'scan':
          final scan = j.objOrNull('scan');
          if (scan == null) return null;
          final names = scan.strList('photos');
          if (names.isEmpty || names.any((n) => !_photoPattern.hasMatch(n))) return null;
          for (final name in names) {
            final photo = File(_join(_join(directory.path, key), name));
            if (!photo.existsSync()) return null;
            bytes += photo.lengthSync();
          }
          return _Item(
            key: key,
            kind: QueueKind.scan,
            createdAt: createdAt.toUtc(),
            owner: j.strOrNull('owner'),
            photoNames: names,
            clientCrop: scan.strOrNull('client_crop'),
            clientConfidence: scan.doubleOrNull('client_confidence'),
            takenAt: scan.dateOrNull('taken_at'),
            lat: scan.doubleOrNull('lat'),
            lon: scan.doubleOrNull('lon'),
          )..bytes = bytes;
        case 'spray_log':
          final log = j.objOrNull('spray_log');
          if (log == null || log.str('crop_id').isEmpty) return null;
          return _Item(
            key: key,
            kind: QueueKind.sprayLog,
            createdAt: createdAt.toUtc(),
            owner: j.strOrNull('owner'),
            log: SprayLogIn(
              cropId: log.str('crop_id'),
              adviceId: log.strOrNull('advice_id'),
              productId: log.strOrNull('product_id'),
              freeText: log.strOrNull('free_text'),
              sprayedAt: log.dateOrNull('sprayed_at'),
              notes: log.strOrNull('notes'),
            ),
          )..bytes = bytes;
        default:
          return null;
      }
    } on Object {
      return null;
    }
  }

  void _deleteKey(String key) {
    _deleteQuietly(File(_jsonPath(key)));
    _deleteQuietly(File('${_jsonPath(key)}.tmp'));
    _deleteQuietly(Directory(_join(directory.path, key)));
  }

  static void _deleteQuietly(FileSystemEntity entity) {
    try {
      if (entity is Directory) {
        if (entity.existsSync()) entity.deleteSync(recursive: true);
      } else if (entity.existsSync()) {
        entity.deleteSync();
      }
    } on FileSystemException {
      // Nothing more to do: the next start tries again.
    }
  }

  void _pendingChanged() {
    if (!_disposed && !_pendingChanges.isClosed) _pendingChanges.add(_items.length);
  }

  void _emit(QueueEvent event) {
    if (!_disposed && !_events.isClosed) _events.add(event);
  }
}

enum _Outcome { sent, dropped, retryItem, stopRound }

class _Item {
  _Item({
    required this.key,
    required this.kind,
    required this.createdAt,
    this.owner,
    this.photoNames = const [],
    this.clientCrop,
    this.clientConfidence,
    this.takenAt,
    this.lat,
    this.lon,
    this.log,
  });

  final String key;
  final QueueKind kind;
  final DateTime createdAt;
  final String? owner;
  final List<String> photoNames;
  final String? clientCrop;
  final double? clientConfidence;
  final DateTime? takenAt;
  final double? lat;
  final double? lon;
  final SprayLogIn? log;

  /// The size of the JSON file plus the photos.
  int bytes = 0;

  Json toJson() => {
    'v': 1,
    'key': key,
    'kind': kind == QueueKind.scan ? 'scan' : 'spray_log',
    'created_at': createdAt.toIso8601String(),
    'owner': owner,
    if (kind == QueueKind.scan)
      'scan': {
        'photos': photoNames,
        'client_crop': clientCrop,
        'client_confidence': clientConfidence,
        'taken_at': takenAt?.toIso8601String(),
        'lat': lat,
        'lon': lon,
      }
    else
      'spray_log': log!.toJson(),
  };
}
