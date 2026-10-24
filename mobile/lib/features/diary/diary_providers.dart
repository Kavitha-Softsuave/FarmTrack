import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/errors/api_exception.dart';
import '../../core/models/models.dart';
import '../../core/offline/offline_queue.dart';
import '../../core/offline/persistent_offline_queue.dart' show KeyedOfflineQueue, PersistentOfflineQueue;
import '../../core/providers.dart';
import 'date_words.dart';

/// The last diary list of one farmer, in the phone's preferences, so the diary can still be read without internet.
/// One entry per farmer id: another farmer on the same phone never sees it.
class DiaryCache {
  const DiaryCache(this._prefs, this._farmerId);

  final SharedPreferences _prefs;
  final String? _farmerId;

  String? get _key => _farmerId == null || _farmerId.isEmpty ? null : 'diary_cache_$_farmerId';

  Future<void> save(List<SprayLogOut> entries) async {
    final key = _key;
    if (key == null) return;
    await _prefs.setString(key, jsonEncode([for (final e in entries) e.toJson()]));
  }

  /// The saved list, or null when there is none (or it is damaged).
  List<SprayLogOut>? load() {
    final key = _key;
    final raw = key == null ? null : _prefs.getString(key);
    if (raw == null) return null;
    try {
      return [for (final e in jsonDecode(raw) as List) SprayLogOut.fromJson(Json.from(e as Map))];
    } on Object {
      return null;
    }
  }
}

/// The diary entries the server has, newest first. Every good answer is kept on the phone ([DiaryCache]); the list
/// screen reads it when the server cannot be reached.
final sprayLogsProvider = FutureProvider.autoDispose<List<SprayLogOut>>((ref) async {
  final farmerId = ref.watch(sessionProvider.select((s) => s.farmer?.id));
  final entries = await ref.watch(apiClientProvider).listSprayLogs(limit: 50);
  try {
    await DiaryCache(ref.read(sharedPreferencesProvider), farmerId).save(entries);
  } on Object {
    // Keeping a copy is a convenience.
  }
  return entries;
});

/// What the phone remembers of the diary for the logged-in farmer (null when nothing).
final cachedSprayLogsProvider = Provider.autoDispose<List<SprayLogOut>?>((ref) {
  final farmerId = ref.watch(sessionProvider.select((s) => s.farmer?.id));
  return DiaryCache(ref.watch(sharedPreferencesProvider), farmerId).load();
});

// ------------------------------------------------------------------------------------------ is this advice sprayed?

/// Where the "I sprayed" of one advice stands. Green = done, grey = saved on the phone and waiting for the internet
/// (never yellow: yellow is only for warnings), nothing = not written yet.
enum SprayState { none, waiting, done }

/// The advice ids whose spray the server has accepted, remembered on the phone (newest last, at most 50) so the advice
/// still shows "sprayed" after the app was closed. Written by [SpraySaver] and when a waiting entry is finally sent.
final sprayedAdvicesProvider = NotifierProvider<SprayedAdvicesNotifier, Set<String>>(SprayedAdvicesNotifier.new);

class SprayedAdvicesNotifier extends Notifier<Set<String>> {
  static const _limit = 50;

  String? get _key {
    final id = ref.read(sessionProvider).farmer?.id;
    return id == null || id.isEmpty ? null : 'sprayed_advices_$id';
  }

  @override
  Set<String> build() {
    final farmerId = ref.watch(sessionProvider.select((s) => s.farmer?.id));
    if (farmerId == null || farmerId.isEmpty) return {};
    final saved = ref.read(sharedPreferencesProvider).getStringList('sprayed_advices_$farmerId');
    return {...?saved};
  }

  Future<void> add(String adviceId) async {
    if (adviceId.isEmpty || state.contains(adviceId)) return;
    final all = [...state, adviceId];
    final kept = all.length > _limit ? all.sublist(all.length - _limit) : all;
    state = {...kept};
    final key = _key;
    if (key == null) return;
    try {
      await ref.read(sharedPreferencesProvider).setStringList(key, kept);
    } on Object {
      // Remembering is a convenience: the diary list on the server has the entry anyway.
    }
  }
}

/// [SprayState] of one advice, from what is on the phone only (no request): the remembered ids, the saved diary list
/// and the entries waiting in the offline queue.
final sprayStateProvider = Provider.autoDispose.family<SprayState, String>((ref, adviceId) {
  if (adviceId.isEmpty) return SprayState.none;
  if (ref.watch(sprayedAdvicesProvider).contains(adviceId)) return SprayState.done;
  final cached = ref.watch(cachedSprayLogsProvider) ?? const <SprayLogOut>[];
  if (cached.any((e) => e.adviceId == adviceId)) return SprayState.done;
  if (ref.watch(pendingSpraysProvider).items.any((p) => p.log.adviceId == adviceId)) return SprayState.waiting;
  return SprayState.none;
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
/// The queue is persistent, and so is this list: after an app restart it is read back from the queue's files.
final pendingSpraysProvider = NotifierProvider<PendingSpraysNotifier, PendingSprays>(PendingSpraysNotifier.new);

class PendingSpraysNotifier extends Notifier<PendingSprays> {
  @override
  PendingSprays build() {
    final queue = ref.watch(offlineQueueProvider);
    final subscription = queue.events.listen(_onEvent);
    ref.onDispose(subscription.cancel);
    final me = ref.read(sessionProvider).farmer?.id;
    return PendingSprays(
      items: queue is PersistentOfflineQueue
          ? [
              for (final waiting in queue.waitingSprayLogs(owner: me).reversed)
                PendingSpray(
                  key: waiting.key,
                  log: waiting.log,
                  name: (waiting.log.freeText ?? waiting.log.productId ?? '').trim(),
                ),
            ]
          : const [],
    );
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
    if (sent) {
      // The waiting entry reached the server: its advice turns from grey "waiting" to green "sprayed".
      final adviceId = state.items.firstWhere((p) => p.key == event.key).log.adviceId;
      if (adviceId != null) unawaited(ref.read(sprayedAdvicesProvider.notifier).add(adviceId));
    }
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
      final adviceId = log.adviceId;
      if (adviceId != null) unawaited(_ref.read(sprayedAdvicesProvider.notifier).add(adviceId));
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
