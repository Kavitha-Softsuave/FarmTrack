import 'package:flutter/material.dart';

import '../../core/models/models.dart';
import '../../core/theme/app_theme.dart';

/// Turns the numbers of a reading into the plain words a farmer uses. The limits only choose the word (they match the
/// words the server speaks); the weather rules that decide risks live on the server.
enum TempBand { cold, cool, pleasant, warm, hot }

TempBand tempBand(double celsius) {
  if (celsius < 5) return TempBand.cold;
  if (celsius < 15) return TempBand.cool;
  if (celsius < 25) return TempBand.pleasant;
  if (celsius < 32) return TempBand.warm;
  return TempBand.hot;
}

enum RainBand { none, light, heavy }

RainBand rainBand(double mm) {
  if (mm < 1) return RainBand.none;
  return mm < 10 ? RainBand.light : RainBand.heavy;
}

enum HumidityBand { dry, ok, damp }

HumidityBand humidityBand(double percent) {
  if (percent < 50) return HumidityBand.dry;
  return percent < 80 ? HumidityBand.ok : HumidityBand.damp;
}

enum LeafBand { dry, damp, wet }

/// [minutes] of leaf wetness.
LeafBand leafBand(int minutes) {
  if (minutes < 60) return LeafBand.dry;
  return minutes < 240 ? LeafBand.damp : LeafBand.wet;
}

enum SoilBand { dry, ok, wet }

SoilBand soilBand(double percent) {
  if (percent < 15) return SoilBand.dry;
  return percent < 40 ? SoilBand.ok : SoilBand.wet;
}

/// One big tile of "My field": a picture, one word, and the number small.
class ReadingTile {
  const ReadingTile({
    required this.id,
    required this.icon,
    required this.color,
    required this.labelKey,
    required this.wordKey,
    required this.digits,
  });

  final String id;
  final IconData icon;
  final Color color;

  /// Interface string keys (strings.json) of the tile's title and of the word for its state.
  final String labelKey;
  final String wordKey;

  /// The measured value, written small ("17 °C"). Never spoken.
  final String digits;
}

String _number(double value) {
  final rounded = value.roundToDouble() == value ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
  return rounded;
}

/// The tiles for the readings the server sent (a missing reading has no tile).
List<ReadingTile> readingTiles(ReadingsOut? readings) {
  if (readings == null) return const [];
  final temp = readings.tempC;
  final humidity = readings.rhPct;
  final rain = readings.rain24hMm;
  final leaf = readings.leafWetnessMin;
  final soil = readings.soilMoisturePct;
  return [
    if (temp != null)
      ReadingTile(
        id: 'temp',
        icon: Icons.thermostat_rounded,
        color: AppColors.red,
        labelKey: 'field_label_temp',
        wordKey: 'field_temp_${tempBand(temp).name}',
        digits: '${temp.round()} °C',
      ),
    if (humidity != null)
      ReadingTile(
        id: 'humidity',
        icon: Icons.water_drop_rounded,
        color: AppColors.blue,
        labelKey: 'field_label_humidity',
        wordKey: 'field_humid_${humidityBand(humidity).name}',
        digits: '${humidity.round()} %',
      ),
    if (rain != null)
      ReadingTile(
        id: 'rain',
        icon: Icons.umbrella_rounded,
        color: AppColors.blue,
        labelKey: 'field_label_rain',
        wordKey: 'field_rain_${rainBand(rain).name}',
        digits: '${_number(rain)} mm',
      ),
    if (leaf != null)
      ReadingTile(
        id: 'leaf',
        icon: AppIcons.leaf,
        color: AppColors.green,
        labelKey: 'field_label_leaf',
        wordKey: 'field_leaf_${leafBand(leaf).name}',
        digits: '$leaf min',
      ),
    if (soil != null)
      ReadingTile(
        id: 'soil',
        icon: Icons.landscape_rounded,
        color: const Color(0xFF8A5A2B),
        labelKey: 'field_label_soil',
        wordKey: 'field_soil_${soilBand(soil).name}',
        digits: '${soil.round()} %',
      ),
  ];
}

/// The picture of a forecast day, from its rain: sun, rain drop, storm.
IconData forecastIcon(double rainMm) => switch (rainBand(rainMm)) {
  RainBand.none => Icons.wb_sunny_rounded,
  RainBand.light => Icons.water_drop_rounded,
  RainBand.heavy => Icons.thunderstorm_rounded,
};

Color forecastColor(double rainMm) => switch (rainBand(rainMm)) {
  RainBand.none => AppColors.amberDark,
  RainBand.light => AppColors.blue,
  RainBand.heavy => const Color(0xFF3B2F8F),
};

/// The words of a forecast day's rain (a string key).
String forecastWordKey(double rainMm) => 'field_rain_${rainBand(rainMm).name}';

/// Risks in the order a farmer needs them: scab first (the one disease the app advises on), then red, yellow, green.
List<RiskOut> sortedRisks(List<RiskOut> risks) {
  int rank(RiskOut r) => switch (r.level) {
    Severity.red => 0,
    Severity.yellow => 1,
    Severity.green => 2,
  };
  final indexed = [for (var i = 0; i < risks.length; i++) (i, risks[i])];
  indexed.sort((a, b) {
    final scab = (b.$2.id.contains('scab') ? 1 : 0).compareTo(a.$2.id.contains('scab') ? 1 : 0);
    if (scab != 0) return scab;
    final level = rank(a.$2).compareTo(rank(b.$2));
    return level != 0 ? level : a.$1.compareTo(b.$1);
  });
  return [for (final e in indexed) e.$2];
}
