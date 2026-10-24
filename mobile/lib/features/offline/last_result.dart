import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../diary/date_words.dart';

/// The last advice the farmer was given, kept on the phone so it can be read (and listened to) again with no internet.
class LastResult {
  const LastResult({required this.scan, required this.savedAt});

  final ScanOut scan;
  final DateTime savedAt;
}

/// One entry per farmer id in the phone's preferences, so another farmer on the same phone never sees it.
class LastResultCache {
  const LastResultCache(this._prefs, this._farmerId);

  /// Older advice is not offered any more: a spray advice from last month would mislead.
  static const maxAge = Duration(days: 7);

  final SharedPreferences _prefs;
  final String? _farmerId;

  String? get _key => _farmerId == null || _farmerId.isEmpty ? null : 'last_result_$_farmerId';

  /// Results worth reading again: a finished answer, not a question about the crop or a photo that must be retaken.
  static bool keeps(ScanOut scan) =>
      scan.status == ScanStatus.ok ||
      scan.status == ScanStatus.needsExpert ||
      scan.status == ScanStatus.noApprovedData ||
      scan.status == ScanStatus.notADisease;

  Future<void> save(ScanOut scan, DateTime at) async {
    final key = _key;
    if (key == null || !keeps(scan)) return;
    await _prefs.setString(key, jsonEncode({'saved_at': at.toUtc().toIso8601String(), 'scan': scan.toJson()}));
  }

  LastResult? load(DateTime now) {
    final key = _key;
    final raw = key == null ? null : _prefs.getString(key);
    if (raw == null) return null;
    try {
      final json = Json.from(jsonDecode(raw) as Map);
      final savedAt = json.dateOrNull('saved_at');
      if (savedAt == null || now.difference(savedAt) > maxAge) return null;
      return LastResult(scan: ScanOut.fromJson(Json.from(json['scan'] as Map)), savedAt: savedAt);
    } on Object {
      return null; // A damaged entry is the same as none.
    }
  }
}

/// The last advice of the logged-in farmer (null when there is none), and the way to remember a new one.
final lastResultProvider = NotifierProvider<LastResultNotifier, LastResult?>(LastResultNotifier.new);

class LastResultNotifier extends Notifier<LastResult?> {
  LastResultCache get _cache =>
      LastResultCache(ref.read(sharedPreferencesProvider), ref.read(sessionProvider).farmer?.id);

  @override
  LastResult? build() {
    ref.watch(sessionProvider.select((s) => s.farmer?.id));
    return _cache.load(ref.read(clockProvider)());
  }

  /// Remembers [scan] as the last advice (only finished answers are kept).
  Future<void> remember(ScanOut scan) async {
    if (!LastResultCache.keeps(scan)) return;
    final now = ref.read(clockProvider)();
    state = LastResult(scan: scan, savedAt: now);
    try {
      await _cache.save(scan, now);
    } on Object {
      // Remembering is a convenience: the answer on the screen is what counts.
    }
  }
}
