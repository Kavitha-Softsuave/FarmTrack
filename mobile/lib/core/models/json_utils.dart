/// Tolerant JSON readers: unknown fields are ignored, wrong types fall back to defaults instead of throwing.
library;

typedef Json = Map<String, dynamic>;

extension JsonReader on Json {
  String str(String key, [String fallback = '']) {
    final v = this[key];
    return v is String ? v : fallback;
  }

  String? strOrNull(String key) {
    final v = this[key];
    return v is String ? v : null;
  }

  int intOr(String key, [int fallback = 0]) {
    final v = this[key];
    return v is num ? v.toInt() : fallback;
  }

  int? intOrNull(String key) {
    final v = this[key];
    return v is num ? v.toInt() : null;
  }

  double doubleOr(String key, [double fallback = 0]) {
    final v = this[key];
    return v is num ? v.toDouble() : fallback;
  }

  double? doubleOrNull(String key) {
    final v = this[key];
    return v is num ? v.toDouble() : null;
  }

  bool boolOr(String key, [bool fallback = false]) {
    final v = this[key];
    return v is bool ? v : fallback;
  }

  DateTime? dateOrNull(String key) {
    final v = this[key];
    return v is String ? DateTime.tryParse(v) : null;
  }

  DateTime dateOr(String key, DateTime fallback) => dateOrNull(key) ?? fallback;

  Json? objOrNull(String key) {
    final v = this[key];
    if (v is Map) return Json.from(v);
    return null;
  }

  T? obj<T>(String key, T Function(Json) parse) {
    final v = objOrNull(key);
    return v == null ? null : parse(v);
  }

  List<T> list<T>(String key, T Function(Json) parse) {
    final v = this[key];
    if (v is! List) return const [];
    return [
      for (final e in v)
        if (e is Map) parse(Json.from(e)),
    ];
  }

  List<String> strList(String key) {
    final v = this[key];
    if (v is! List) return const [];
    return [
      for (final e in v)
        if (e is String) e,
    ];
  }
}

/// An enum whose JSON representation is a fixed string (snake_case in the API).
abstract interface class WireEnum {
  String get wire;
}

/// Parses a wire value, returning [fallback] for null or unknown values.
T parseWire<T extends WireEnum>(List<T> values, Object? raw, T fallback) {
  if (raw is! String) return fallback;
  for (final v in values) {
    if (v.wire == raw) return v;
  }
  return fallback;
}

/// Removes null entries so that optional fields are left out of request bodies.
Json compact(Json json) => {
  for (final e in json.entries)
    if (e.value != null) e.key: e.value,
};
