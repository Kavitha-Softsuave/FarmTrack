import 'json_utils.dart';
import 'localized.dart';

class ReadingsOut {
  const ReadingsOut({this.tempC, this.rhPct, this.rain24hMm, this.leafWetnessMin, this.soilMoisturePct});

  factory ReadingsOut.fromJson(Json json) => ReadingsOut(
    tempC: json.doubleOrNull('temp_c'),
    rhPct: json.doubleOrNull('rh_pct'),
    rain24hMm: json.doubleOrNull('rain_24h_mm'),
    leafWetnessMin: json.intOrNull('leaf_wetness_min'),
    soilMoisturePct: json.doubleOrNull('soil_moisture_pct'),
  );

  final double? tempC;
  final double? rhPct;
  final double? rain24hMm;
  final int? leafWetnessMin;
  final double? soilMoisturePct;

  Json toJson() => {
    'temp_c': tempC,
    'rh_pct': rhPct,
    'rain_24h_mm': rain24hMm,
    'leaf_wetness_min': leafWetnessMin,
    'soil_moisture_pct': soilMoisturePct,
  };
}

class ForecastDayOut {
  const ForecastDayOut({required this.day, this.tminC = 0, this.tmaxC = 0, this.rainMm = 0});

  factory ForecastDayOut.fromJson(Json json) => ForecastDayOut(
    day: json.str('day'),
    tminC: json.doubleOr('tmin_c'),
    tmaxC: json.doubleOr('tmax_c'),
    rainMm: json.doubleOr('rain_mm'),
  );

  /// ISO date, `2026-05-12`.
  final String day;
  final double tminC;
  final double tmaxC;
  final double rainMm;

  Json toJson() => {'day': day, 'tmin_c': tminC, 'tmax_c': tmaxC, 'rain_mm': rainMm};
}

class RiskOut {
  const RiskOut({
    required this.id,
    this.level = Severity.yellow,
    this.title = const LocalizedText(),
    this.text = const LocalizedText(),
  });

  factory RiskOut.fromJson(Json json) => RiskOut(
    id: json.str('id'),
    level: Severity.parse(json['level']),
    title: LocalizedText.fromJson(json['title']),
    text: LocalizedText.fromJson(json['text']),
  );

  final String id;
  final Severity level;
  final LocalizedText title;
  final LocalizedText text;

  Json toJson() => {'id': id, 'level': level.wire, 'title': title.toJson(), 'text': text.toJson()};
}

class FieldOut {
  const FieldOut({
    this.stationId,
    this.village,
    this.asOf,
    this.stale = false,
    this.readings,
    this.forecast = const [],
    this.risks = const [],
    this.spoken = const SpokenOut(),
  });

  factory FieldOut.fromJson(Json json) => FieldOut(
    stationId: json.strOrNull('station_id'),
    village: json.strOrNull('village'),
    asOf: json.dateOrNull('as_of'),
    stale: json.boolOr('stale'),
    readings: json.obj('readings', ReadingsOut.fromJson),
    forecast: json.list('forecast', ForecastDayOut.fromJson),
    risks: json.list('risks', RiskOut.fromJson),
    spoken: SpokenOut.fromJson(json['spoken']),
  );

  final String? stationId;
  final String? village;
  final DateTime? asOf;
  final bool stale;
  final ReadingsOut? readings;
  final List<ForecastDayOut> forecast;
  final List<RiskOut> risks;
  final SpokenOut spoken;

  Json toJson() => {
    'station_id': stationId,
    'village': village,
    'as_of': asOf?.toIso8601String(),
    'stale': stale,
    'readings': readings?.toJson(),
    'forecast': [for (final f in forecast) f.toJson()],
    'risks': [for (final r in risks) r.toJson()],
    'spoken': spoken.toJson(),
  };
}
