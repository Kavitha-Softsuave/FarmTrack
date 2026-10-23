import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/api_exception.dart';
import '../../core/models/models.dart';
import '../../core/offline/offline_queue.dart';
import '../../core/offline/persistent_offline_queue.dart' show KeyedOfflineQueue;
import '../../core/providers.dart';
import 'date_words.dart';

/// The diary entries the server has, newest first.
final sprayLogsProvider = FutureProvider.autoDispose<List<SprayLogOut>>((ref) {
  ref.watch(sessionProvider.select((s) => s.farmer?.id));
  return ref.watch(apiClientProvider).listSprayLogs(limit: 50);
});

// ------------------------------------------------------------------------------------------ entries shown in the list

/// One line of the diary, whether the server has it or it still waits for the internet.
class DiaryEntry {
  const DiaryEntry({
    required this.id,
    required this.cropId,
    required this.name,
    required this.date,
    this.warnings = const [],
    this.pending = false,
  });

  final String id;
  final String cropId;

  /// The medicine's name as the server or the farmer wrote it (empty when nobody named it).
  final String name;
  final DateTime date;
  final List<WarningOut> warnings;

  /// Saved on the phone, not sent yet.
  final bool pending;

  /// The most serious warning level, or null without warnings.
  Severity? get worst {
    if (warnings.isEmpty) return null;
    return warnings.any((w) => w.level == Severity.red) ? Severity.red : Severity.yellow;
  }
}

/// Server entries and waiting ones in one list, newest day first (waiting ones first within a day: they are newer).
List<DiaryEntry> mergeDiaryEntries(List<SprayLogOut> server, List<PendingSpray> pending, DateTime now) {
  final all = <DiaryEntry>[
    for (final p in pending)
      DiaryEntry(id: p.key, cropId: p.log.cropId, name: p.name, date: p.log.sprayedAt ?? now, pending: true),
    for (final s in server)
      DiaryEntry(
        id: s.id,
        cropId: s.cropId,
        name: (s.productName ?? s.productId ?? '').trim(),
        date: s.sprayedAt ?? now,
        warnings: s.warnings,
      ),
  ];
  // Stable sort: equal days keep the order above.
  final indexed = [for (var i = 0; i < all.length; i++) (i, all[i])];
  indexed.sort((a, b) {
    final byDay = dayOnly(b.$2.date).compareTo(dayOnly(a.$2.date));
    return byDay != 0 ? byDay : a.$1.compareTo(b.$1);
  });
  return [for (final e in indexed) e.$2];
}

/// Names used before, newest first, without repeats (ignoring case), at most [limit].
List<String> recentMedicineNames(List<DiaryEntry> entries, {int limit = 6}) {
  final seen = <String>{};
  final names = <String>[];
  for (final e in entries) {
    final name = e.name.trim();
    if (name.isNotEmpty && seen.add(name.toLowerCase())) names.add(name);
    if (names.length == limit) break;
  }
  return names;
}

// ------------------------------------------------------------------------------------------ waiting for the internet

/// A diary entry that was saved on the phone because there was no internet.
class PendingSpray {
  const PendingSpray({required this.key, required this.log, required this.name});

  /// The offline queue's key for this entry.
  final String key;
  final SprayLogIn log;

  /// What to show for the medicine (the typed name or the advice's medicine).
  final String name;
}

class PendingSprays {
  const PendingSprays({this.items = const [], this.sent = 0});

  final List<PendingSpray> items;

  /// How many waiting entries reached the server since the app started; screens speak when it grows.
  final int sent;

  PendingSprays copyWith({List<PendingSpray>? items, int? sent}) =>
      PendingSprays(items: items ?? this.items, sent: sent ?? this.sent);
}

/// The diary entries that wait in the offline queue (the queue only counts them), and what happens to them.
///
/// The queue is persistent but this list is not: after an app restart the entries are still sent, they just no
/// longer show as "waiting" in the diary until the server has them.
final pendingSpraysProvider = NotifierProvider<PendingSpraysNotifier, PendingSprays>(PendingSpraysNotifier.new);

class PendingSpraysNotifier extends Notifier<PendingSprays> {
  @override
  PendingSprays build() {
    final subscription = ref.watch(offlineQueueProvider).events.listen(_onEvent);
    ref.onDispose(subscription.cancel);
    return const PendingSprays();
  }

  void add(PendingSpray entry) => state = state.copyWith(items: [entry, ...state.items]);

  void _onEvent(QueueEvent event) {
    if (event.kind != QueueKind.sprayLog) return;
    final remaining = [
      for (final p in state.items)
        if (p.key != event.key) p,
    ];
    if (remaining.length == state.items.length) return; // not an entry of ours
    final sent = event.type == QueueEventType.sent;
    state = state.copyWith(items: remaining, sent: sent ? state.sent + 1 : state.sent);
    if (sent) ref.invalidate(sprayLogsProvider);
  }
}

// ------------------------------------------------------------------------------------------ saving

sealed class SaveOutcome {
  const SaveOutcome();
}

/// The server saved it.
final class SavedOnline extends SaveOutcome {
  const SavedOnline(this.entry);

  final SprayLogOut entry;
}

/// No internet: the entry waits in the offline queue.
final class SavedOffline extends SaveOutcome {
  const SavedOffline(this.key);

  final String key;
}

/// The server (or the phone) refused: nothing was saved.
final class SaveFailed extends SaveOutcome {
  const SaveFailed(this.error);

  final Object error;
}

/// Saves a diary entry: to the server, or into the offline queue when the phone cannot reach it.
final spraySaverProvider = Provider<SpraySaver>((ref) => SpraySaver(ref));

class SpraySaver {
  SpraySaver(this._ref);

  final Ref _ref;

  /// [name] is only for the list on the phone. [idempotencyKey] stays the same on a retry of the same entry, so a
  /// lost answer never makes two entries.
  Future<SaveOutcome> save(SprayLogIn log, {required String name, String? idempotencyKey}) async {
    final key = idempotencyKey ?? newIdempotencyKey();
    try {
      final entry = await _ref.read(apiClientProvider).createSprayLog(log, idempotencyKey: key);
      _ref.invalidate(sprayLogsProvider);
      return SavedOnline(entry);
    } on ApiException catch (e) {
      if (!e.isConnectionProblem) return SaveFailed(e);
      return _queue(log, name, key);
    } on Object catch (e) {
      return SaveFailed(e);
    }
  }

  /// Queues the entry with the key of the live attempt: if that attempt timed out after the server had processed it,
  /// the queued retry gets the first answer back instead of making a second entry.
  Future<SaveOutcome> _queue(SprayLogIn log, String name, String idempotencyKey) async {
    // Without a date the server would stamp the day the entry is finally sent, not the day it was sprayed.
    final stamped = log.sprayedAt != null
        ? log
        : SprayLogIn(
            cropId: log.cropId,
            adviceId: log.adviceId,
            productId: log.productId,
            freeText: log.freeText,
            sprayedAt: _ref.read(clockProvider)().toUtc(),
            notes: log.notes,
          );
    try {
      final queue = _ref.read(offlineQueueProvider);
      final key = queue is KeyedOfflineQueue
          ? await queue.enqueueSprayLogWithKey(idempotencyKey, stamped)
          : await queue.enqueueSprayLog(stamped);
      _ref.read(pendingSpraysProvider.notifier).add(PendingSpray(key: key, log: stamped, name: name));
      return SavedOffline(key);
    } on Object catch (e) {
      return SaveFailed(e);
    }
  }
}
