import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/api_client.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/offline/persistent_offline_queue.dart';
import 'package:farmtrack/core/offline/queue_clock.dart';

/// A clock that only moves when the test says so. [advance] runs every timer that falls due on the way.
class FakeQueueClock implements QueueClock {
  FakeQueueClock([DateTime? start]) : _now = start ?? DateTime.utc(2026, 5, 12, 8);

  DateTime _now;
  final List<_FakeTimer> _timers = [];

  /// Every delay a timer was ever scheduled with, in order.
  final List<Duration> scheduled = [];

  @override
  DateTime now() => _now;

  @override
  Timer schedule(Duration delay, void Function() callback) {
    scheduled.add(delay);
    final timer = _FakeTimer(_now.add(delay), callback);
    _timers.add(timer);
    return timer;
  }

  int get activeTimers => _timers.where((t) => t.isActive).length;

  /// The wait of the timer that is armed now (null if none).
  Duration? get armedFor {
    final active = _timers.where((t) => t.isActive).toList();
    return active.isEmpty ? null : active.first.due.difference(_now);
  }

  void advance(Duration by) {
    final target = _now.add(by);
    while (true) {
      final due = _timers.where((t) => t.isActive && !t.due.isAfter(target)).toList()
        ..sort((a, b) => a.due.compareTo(b.due));
      if (due.isEmpty) break;
      _now = due.first.due;
      due.first.fire();
    }
    _now = target;
  }
}

class _FakeTimer implements Timer {
  _FakeTimer(this.due, this._callback);

  final DateTime due;
  final void Function() _callback;
  bool _cancelled = false;
  bool _fired = false;

  void fire() {
    _fired = true;
    _callback();
  }

  @override
  bool get isActive => !_cancelled && !_fired;

  @override
  int get tick => _fired ? 1 : 0;

  @override
  void cancel() => _cancelled = true;
}

/// The server processes the request but the answer never arrives (the phone lost the network just then).
class LossyApi extends MockApiClient {
  LossyApi({super.scanScript}) : super(latency: Duration.zero);

  /// How many of the next answers get lost (after the server stored the scan).
  int loseAnswers = 0;

  /// The idempotency key of every attempt, also of those that failed before the server saw them.
  final List<String?> attemptedKeys = [];

  @override
  Future<ScanOut> createScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
    String? idempotencyKey,
    UploadProgressCallback? onProgress,
    CancelHandle? cancel,
  }) async {
    attemptedKeys.add(idempotencyKey);
    final out = await super.createScan(
      photoPaths: photoPaths,
      clientCrop: clientCrop,
      clientConfidence: clientConfidence,
      takenAt: takenAt,
      lat: lat,
      lon: lon,
      idempotencyKey: idempotencyKey,
      onProgress: onProgress,
      cancel: cancel,
    );
    if (loseAnswers > 0) {
      loseAnswers--;
      throw const ApiException.timeout();
    }
    return out;
  }
}

const serverError = ApiException(kind: ApiErrorKind.server, code: 'internal_error', statusCode: 500);
const unprocessable = ApiException(
  kind: ApiErrorKind.validation,
  code: 'validation_error',
  statusCode: 422,
  message: 'bad photo',
);
const notAuthenticated = ApiException(kind: ApiErrorKind.unauthorized, code: 'not_authenticated', statusCode: 401);
const tooManyRequests = ApiException(kind: ApiErrorKind.rateLimited, code: 'rate_limited', statusCode: 429);

/// Everything a queue test needs: a temp folder for the queue, another one standing in for the camera cache,
/// a fake clock and a mock API with no latency.
class QueueRig {
  QueueRig({this.limits = const OfflineQueueLimits(), MockApiClient? api, this.farmer})
    : api = api ?? MockApiClient(latency: Duration.zero) {
    root = Directory.systemTemp.createTempSync('farmtrack_queue');
    queueDir = Directory('${root.path}${Platform.pathSeparator}pending');
    cameraDir = Directory('${root.path}${Platform.pathSeparator}camera')..createSync();
  }

  final OfflineQueueLimits limits;
  final MockApiClient api;
  final FakeQueueClock clock = FakeQueueClock();
  String? farmer;

  /// False: nobody is logged in, so the queue must not send anything.
  bool signedIn = true;
  late final Directory root;
  late final Directory queueDir;
  late final Directory cameraDir;
  final List<PersistentOfflineQueue> _made = [];
  int _photoSerial = 0;

  /// A queue on the same folder, like the app after a restart.
  PersistentOfflineQueue make() {
    final queue = PersistentOfflineQueue(
      directory: queueDir,
      api: () => api,
      clock: clock,
      farmerId: () => farmer,
      canSend: () => signedIn,
      limits: limits,
    );
    _made.add(queue);
    return queue;
  }

  /// Creates [count] photo files in the camera folder.
  List<String> photos(int count, {int bytes = 64}) => [
    for (var i = 0; i < count; i++)
      (File(
        '${cameraDir.path}${Platform.pathSeparator}leaf_${_photoSerial++}.jpg',
      )..writeAsBytesSync(List<int>.filled(bytes, i + 1))).path,
  ];

  /// Files and folders in the queue folder (names only).
  List<String> get filesOnDisk =>
      queueDir.existsSync() ? [for (final e in queueDir.listSync()) e.path.split(Platform.pathSeparator).last] : [];

  void dispose() {
    for (final q in _made) {
      q.dispose();
    }
    if (root.existsSync()) root.deleteSync(recursive: true);
  }
}

/// Collects the events and the pending counts of a queue.
class QueueWatcher {
  QueueWatcher(OfflineQueue queue) {
    _subs = [queue.events.listen(events.add), queue.pendingChanges.listen(counts.add)];
  }

  final List<QueueEvent> events = [];
  final List<int> counts = [];
  late final List<StreamSubscription<Object?>> _subs;

  List<QueueEvent> of(QueueEventType type) => [
    for (final e in events)
      if (e.type == type) e,
  ];

  Future<void> settle() => pumpEventQueue();

  Future<void> close() async {
    for (final s in _subs) {
      await s.cancel();
    }
  }
}
