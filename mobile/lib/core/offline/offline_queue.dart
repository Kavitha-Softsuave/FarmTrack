import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../providers.dart';
import 'persistent_offline_queue.dart';
import 'queue_clock.dart';

/// Things the farmer did without a network that must still reach the server.
///
/// This file is the shared contract between the screens (they only call `enqueue*`) and the queue implementation.
/// [offlineQueueProvider] builds the persistent implementation ([PersistentOfflineQueue]); [InMemoryOfflineQueue]
/// stays for tests that need a queue without files.
///
/// Rules every implementation follows:
/// * Every item gets an idempotency key when it is queued and sends the SAME key on every attempt
///   (`ApiClient.createScan/createSprayLog(idempotencyKey: ...)`), so a lost response never makes a duplicate.
/// * Only connection problems (`ApiException.isConnectionProblem`) are retried; any other error drops the item and is
///   reported through [OfflineQueue.events] so the farmer is told once.
/// * Nothing here speaks or shows UI; the screens listen to [events] and [pending].
abstract interface class OfflineQueue {
  /// How many items still wait to be sent.
  int get pending;

  /// Emits the new count whenever it changes.
  Stream<int> get pendingChanges;

  /// What happened to queued items (sent, dropped). The UI speaks `back_online_sent` etc. from these.
  Stream<QueueEvent> get events;

  /// Saves the photos (they must be copied to a folder of the app, the camera cache can be cleared) and returns the key.
  Future<String> enqueueScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  });

  Future<String> enqueueSprayLog(SprayLogIn log);

  /// Tries to send everything now (called when the phone is back online, on app start and on resume). Never throws.
  Future<void> flush();
}

enum QueueKind { scan, sprayLog }

enum QueueEventType { sent, dropped }

class QueueEvent {
  const QueueEvent({required this.type, required this.kind, required this.key, this.scan, this.sprayLog, this.error});

  final QueueEventType type;
  final QueueKind kind;
  final String key;

  /// The server answer for a sent scan (so the app can open the result).
  final ScanOut? scan;
  final SprayLogOut? sprayLog;

  /// Why an item was dropped.
  final Object? error;
}

/// A random 128-bit key as 32 hex characters (no package needed).
String newIdempotencyKey([Random? random]) {
  final r = random ?? Random.secure();
  final buffer = StringBuffer();
  for (var i = 0; i < 16; i++) {
    buffer.write(r.nextInt(256).toRadixString(16).padLeft(2, '0'));
  }
  return buffer.toString();
}

/// Remembers nothing across restarts and never sends. Only for tests that do not want files.
class InMemoryOfflineQueue implements OfflineQueue {
  final List<({String key, QueueKind kind, Object payload})> items = [];

  @override
  int get pending => items.length;

  @override
  Stream<int> get pendingChanges => const Stream<int>.empty();

  @override
  Stream<QueueEvent> get events => const Stream<QueueEvent>.empty();

  @override
  Future<String> enqueueScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  }) async {
    final key = newIdempotencyKey();
    items.add((key: key, kind: QueueKind.scan, payload: List<String>.of(photoPaths)));
    return key;
  }

  @override
  Future<String> enqueueSprayLog(SprayLogIn log) async {
    final key = newIdempotencyKey();
    items.add((key: key, kind: QueueKind.sprayLog, payload: log));
    return key;
  }

  @override
  Future<void> flush() async {}
}

/// Time for the queue (retry timer, age limit). Tests replace it with a clock they move by hand.
final queueClockProvider = Provider<QueueClock>((ref) => const SystemQueueClock());

/// The queue of the app: items live in `<support folder>/pending`, so they survive restarts.
final offlineQueueProvider = Provider<OfflineQueue>((ref) {
  final queue = PersistentOfflineQueue(
    directory: Directory('${ref.watch(supportDirectoryProvider).path}${Platform.pathSeparator}pending'),
    api: () => ref.read(apiClientProvider),
    clock: ref.watch(queueClockProvider),
    farmerId: () => ref.read(sessionProvider).farmer?.id,
    canSend: () => ref.read(sessionProvider).isLoggedIn,
  );
  ref.onDispose(queue.dispose);
  return queue;
});
