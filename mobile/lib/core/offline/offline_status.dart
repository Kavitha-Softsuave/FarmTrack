import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart' show AppLifecycleState;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/models.dart';
import '../providers.dart';
import '../voice/voice_service.dart';
import 'offline_queue.dart';
import 'persistent_offline_queue.dart';

/// A queued scan that was sent: the farmer has not looked at the result yet.
class ReadyResult {
  const ReadyResult({required this.scanId, required this.at, this.owner});

  factory ReadyResult.fromJson(Json json) => ReadyResult(
    scanId: json.str('id'),
    at: json.dateOrNull('at') ?? DateTime.fromMillisecondsSinceEpoch(0),
    owner: json.strOrNull('owner'),
  );

  final String scanId;
  final DateTime at;

  /// The farmer whose scan it is: on a shared phone the card shows only for its owner.
  final String? owner;

  Json toJson() => {'id': scanId, 'at': at.toIso8601String(), 'owner': owner};
}

/// What Home shows about the offline queue: how many items wait, and which results are ready to open.
class OfflineStatus {
  const OfflineStatus({this.pending = 0, this.ready = const []});

  final int pending;

  /// Oldest first.
  final List<ReadyResult> ready;

  OfflineStatus copyWith({int? pending, List<ReadyResult>? ready}) =>
      OfflineStatus(pending: pending ?? this.pending, ready: ready ?? this.ready);
}

final offlineStatusProvider = NotifierProvider<OfflineStatusNotifier, OfflineStatus>(OfflineStatusNotifier.new);

/// Drives the offline queue for the whole app and tells the screens what happened.
///
/// * Flush triggers: logged in (app start after login), the phone is back online, the app is resumed. The queue's own
///   timer covers the rest.
/// * `sent` scan: remembers the result for a Home card ("Result ready: tap to see"), speaks `back_online_sent` and
///   `offline_result_ready` while the app is open. The list is saved, so the card survives a restart (the result is then
///   fetched with `GET /v1/scans/{id}`).
/// * `dropped`: speaks `error_try_again` once.
/// * Spray logs that were sent are announced by the diary screen (`diary_sent`), not here.
class OfflineStatusNotifier extends Notifier<OfflineStatus> {
  /// The saved ids of results that wait to be opened (SharedPreferences).
  static const prefsKey = 'offline_ready_scans';
  static const maxReady = 5;
  static const maxReadyAge = Duration(days: 7);

  final Map<String, ScanOut> _scans = {};

  /// Every saved result, of every farmer who used this phone; [OfflineStatus.ready] is the part for the farmer who is
  /// logged in.
  List<ReadyResult> _all = [];
  final Object _voiceOwner = Object();
  late OfflineQueue _queue;
  bool _foreground = true;

  @override
  OfflineStatus build() {
    final queue = _queue = ref.watch(offlineQueueProvider);
    final subscriptions = [
      queue.pendingChanges.listen((n) => state = state.copyWith(pending: n)),
      queue.events.listen(_onEvent),
    ];
    ref.onDispose(() {
      for (final s in subscriptions) {
        unawaited(s.cancel());
      }
    });
    ref.listen<SessionState>(sessionProvider, (previous, next) {
      if (next.isLoggedIn && !(previous?.isLoggedIn ?? false)) unawaited(queue.flush());
    }, fireImmediately: true);
    // Another farmer sees other cards: filter the saved results again whenever the login changes.
    ref.listen<String?>(sessionProvider.select((s) => s.farmer?.id), (_, _) {
      state = state.copyWith(ready: _visible());
    });
    ref.listen<AsyncValue<bool>>(onlineProvider, (previous, next) {
      if (next.value == true && previous?.value != true) unawaited(queue.flush());
    });
    _all = _loadReady();
    return OfflineStatus(pending: queue.pending, ready: _visible());
  }

  String? get _me => ref.read(sessionProvider).farmer?.id;

  List<ReadyResult> _visible() => [
    for (final r in _all)
      if (r.owner == null || _me == null || r.owner == _me) r,
  ];

  /// The app went to the background or came back. The retry timer only runs while the app is open.
  void onLifecycle(AppLifecycleState lifecycle) {
    final foreground = lifecycle == AppLifecycleState.resumed || lifecycle == AppLifecycleState.inactive;
    _foreground = foreground;
    final queue = _queue;
    if (queue is PersistentOfflineQueue) queue.foreground = foreground;
    if (lifecycle == AppLifecycleState.resumed && ref.read(sessionProvider).isLoggedIn) unawaited(queue.flush());
  }

  /// The scan answer for [result]: from memory, else from the server (throws `ApiException`).
  Future<ScanOut> open(ReadyResult result) async =>
      _scans[result.scanId] ?? await ref.read(apiClientProvider).getScan(result.scanId);

  /// The farmer has seen (or can no longer get) this result: take the card away.
  void dismiss(String scanId) {
    _scans.remove(scanId);
    _all = [
      for (final r in _all)
        if (r.scanId != scanId) r,
    ];
    state = state.copyWith(ready: _visible());
    _saveReady(_all);
  }

  void _onEvent(QueueEvent event) {
    switch (event.type) {
      case QueueEventType.sent:
        final scan = event.scan;
        if (event.kind == QueueKind.scan && scan != null) {
          _addReady(scan);
          _announce(const ['back_online_sent', 'offline_result_ready']);
        }
      case QueueEventType.dropped:
        _announce(const ['error_try_again']);
    }
  }

  void _addReady(ScanOut scan) {
    _scans[scan.id] = scan;
    if (_all.any((r) => r.scanId == scan.id)) return;
    _all = [..._all, ReadyResult(scanId: scan.id, at: DateTime.now(), owner: _me)];
    while (_all.length > maxReady) {
      _scans.remove(_all.first.scanId);
      _all = _all.sublist(1);
    }
    state = state.copyWith(ready: _visible());
    _saveReady(_all);
  }

  /// Speaks after whatever is being said; silent while the app is in the background.
  void _announce(List<String> promptIds) {
    if (!_foreground) return;
    unawaited(ref.read(voiceServiceProvider).speakPrompts(promptIds, interrupt: false, owner: _voiceOwner));
  }

  List<ReadyResult> _loadReady() {
    try {
      final raw = ref.read(sharedPreferencesProvider).getString(prefsKey);
      if (raw == null) return const [];
      final oldest = DateTime.now().subtract(maxReadyAge);
      return [
        for (final e in (jsonDecode(raw) as List).whereType<Map>())
          if (ReadyResult.fromJson(Json.from(e)) case final r when r.scanId.isNotEmpty && r.at.isAfter(oldest)) r,
      ];
    } on Object {
      return const [];
    }
  }

  void _saveReady(List<ReadyResult> list) {
    try {
      final prefs = ref.read(sharedPreferencesProvider);
      unawaited(prefs.setString(prefsKey, jsonEncode([for (final r in list) r.toJson()])));
    } on Object {
      // The card is a convenience; losing it only costs one tap in the history that does not exist yet.
    }
  }
}
