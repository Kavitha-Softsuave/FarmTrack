import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/errors/api_exception.dart';
import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../diary/date_words.dart';

/// What "My field" shows: the server's answer, or the last one kept on the phone when there is no internet.
class FieldView {
  const FieldView(this.field, {this.fromCache = false, this.savedAt});

  final FieldOut field;

  /// The answer was read from the phone's memory, so it is old: say so.
  final bool fromCache;

  /// When this answer was kept (only for cached answers).
  final DateTime? savedAt;

  /// The server sent no readings, no forecast and no risks: nothing to show.
  bool get hasNoData => field.readings == null && field.forecast.isEmpty && field.risks.isEmpty;

  /// Old, either because the server says so (a sensor went quiet) or because it comes from the cache.
  bool get isOld => fromCache || field.stale;
}

/// The last field answer of one farmer, in the phone's preferences. One entry per farmer id, so another farmer who logs
/// in on the same phone never sees it.
class FieldCache {
  const FieldCache(this._prefs, this._farmerId);

  final SharedPreferences _prefs;
  final String? _farmerId;

  String? get _key => _farmerId == null || _farmerId.isEmpty ? null : 'field_cache_$_farmerId';

  Future<void> save(FieldOut field, DateTime at) async {
    final key = _key;
    if (key == null) return;
    await _prefs.setString(key, jsonEncode({'saved_at': at.toUtc().toIso8601String(), 'field': field.toJson()}));
  }

  FieldView? load() {
    final key = _key;
    final raw = key == null ? null : _prefs.getString(key);
    if (raw == null) return null;
    try {
      final json = Json.from(jsonDecode(raw) as Map);
      return FieldView(
        FieldOut.fromJson(Json.from(json['field'] as Map)),
        fromCache: true,
        savedAt: json.dateOrNull('saved_at'),
      );
    } on Object {
      return null; // A damaged entry is the same as none.
    }
  }
}

/// `GET /v1/field`. Without internet it answers with the cached last answer when there is one (marked as old),
/// otherwise the error reaches the screen.
final fieldProvider = FutureProvider.autoDispose<FieldView>((ref) async {
  final farmerId = ref.watch(sessionProvider.select((s) => s.farmer?.id));
  final api = ref.watch(apiClientProvider);
  final cache = FieldCache(ref.watch(sharedPreferencesProvider), farmerId);
  try {
    final field = await api.field();
    await cache.save(field, ref.read(clockProvider)());
    return FieldView(field);
  } on ApiException catch (e) {
    if (e.isConnectionProblem) {
      final cached = cache.load();
      if (cached != null) return cached;
    }
    rethrow;
  }
});
