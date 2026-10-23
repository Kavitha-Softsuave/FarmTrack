import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/widgets/big_buttons.dart';
import '../diary/date_words.dart';
import '../diary/diary_widgets.dart';
import '../result/advice_widgets.dart';
import 'field_words.dart';

/// "This information is old": shown when the server says the sensor is quiet or the answer comes from the phone's memory.
class OldInfoBanner extends ConsumerWidget {
  const OldInfoBanner({super.key, this.since});

  /// When the information is from.
  final DateTime? since;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final theme = Theme.of(context).textTheme;
    return Container(
      key: const ValueKey('field-old'),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.amberSoft,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.amberDark, width: 3),
      ),
      child: Row(
        children: [
          const Icon(Icons.history_rounded, size: 40, color: Color(0xFF8A5A00)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(t('field_old_title'), style: theme.titleMedium),
                if (since != null) Text(words.written(since!), style: theme.bodyMedium),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Nothing is known about this farmer's field yet.
class NoFieldData extends ConsumerWidget {
  const NoFieldData({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return Column(
      key: const ValueKey('field-no-data'),
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(AppIcons.offline, size: Dimens.hero, color: AppColors.inkSoft),
        const SizedBox(height: 12),
        Text(t('field_no_data_title'), textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
      ],
    );
  }
}

/// The readings as big tiles: a picture, one word, the number small. Tapping a tile says its title and word.
class ReadingTiles extends ConsumerWidget {
  const ReadingTiles({super.key, required this.tiles, required this.onSpeak});

  final List<ReadingTile> tiles;

  /// Called with the sentence to say (title and word, no number).
  final void Function(String sentence) onSpeak;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final theme = Theme.of(context).textTheme;
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = (constraints.maxWidth - 12) / 2;
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final tile in tiles)
              SizedBox(
                width: width,
                child: Material(
                  key: ValueKey('reading-${tile.id}'),
                  color: AppColors.card,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(20),
                    side: BorderSide(color: tile.color, width: 3),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(20),
                    onTap: () {
                      Haptics.tap();
                      onSpeak('${t(tile.labelKey)}, ${t(tile.wordKey)}');
                    },
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(minHeight: 132),
                      child: Padding(
                        padding: const EdgeInsets.all(10),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(tile.icon, size: 48, color: tile.color),
                            const SizedBox(height: 4),
                            FittedBox(
                              fit: BoxFit.scaleDown,
                              child: Text(
                                t(tile.wordKey),
                                key: ValueKey('reading-word-${tile.id}'),
                                style: theme.titleLarge,
                              ),
                            ),
                            FittedBox(
                              fit: BoxFit.scaleDown,
                              child: Text(
                                t(tile.labelKey),
                                style: theme.bodyMedium?.copyWith(color: AppColors.inkSoft),
                              ),
                            ),
                            FittedBox(
                              fit: BoxFit.scaleDown,
                              child: Text(
                                tile.digits,
                                key: ValueKey('reading-digits-${tile.id}'),
                                style: theme.bodyMedium?.copyWith(fontSize: 14, color: AppColors.inkSoft),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

/// A weather risk: colour, picture and words together, with its own speaker button.
class RiskCard extends ConsumerWidget {
  const RiskCard({super.key, required this.risk, required this.onSpeak});

  final RiskOut risk;
  final VoidCallback onSpeak;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final lang = ref.watch(languageProvider);
    final theme = Theme.of(context).textTheme;
    final level = risk.level;
    final color = AppColors.severity(level);
    final title = risk.title.forLang(lang);
    final text = risk.text.forLang(lang);
    return Container(
      key: ValueKey('risk-${risk.id}'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.severitySoft(level),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.severityAccent(level), width: 3),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            child: Icon(severityIcon(level), size: 32, color: AppColors.onSeverity(level)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title.isNotEmpty) Text(title, style: theme.titleMedium),
                const SizedBox(height: 4),
                SeverityPill(severity: level),
                if (text.isNotEmpty) ...[const SizedBox(height: 6), Text(text, style: theme.bodyLarge)],
              ],
            ),
          ),
          const SizedBox(width: 8),
          BigIconButton(
            key: ValueKey('risk-speak-${risk.id}'),
            icon: AppIcons.speaker,
            semanticLabel: t('field_listen_card'),
            color: AppColors.blue,
            size: Dimens.minTouch,
            onPressed: onSpeak,
          ),
        ],
      ),
    );
  }
}

/// Seven days in a row: the day's name, a weather picture, and the temperatures small. Scrolls sideways.
class ForecastStrip extends ConsumerWidget {
  const ForecastStrip({super.key, required this.days});

  final List<ForecastDayOut> days;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final now = ref.watch(clockProvider)();
    final theme = Theme.of(context).textTheme;
    return SingleChildScrollView(
      key: const ValueKey('forecast-strip'),
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final day in days)
            Builder(
              builder: (context) {
                final date = DateTime.tryParse(day.day);
                final name = date == null ? '' : (daysAgo(date, now) == 0 ? words.today : words.shortWeekday(date));
                final rainWord = t(forecastWordKey(day.rainMm));
                return Semantics(
                  container: true,
                  label: '$name, $rainWord',
                  excludeSemantics: true,
                  child: Container(
                    key: ValueKey('forecast-${day.day}'),
                    width: 84,
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.card,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppColors.line, width: 2),
                    ),
                    child: Column(
                      children: [
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(name, style: theme.labelLarge),
                        ),
                        const SizedBox(height: 6),
                        Icon(forecastIcon(day.rainMm), size: 40, color: forecastColor(day.rainMm)),
                        const SizedBox(height: 6),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(rainWord, style: theme.bodyMedium?.copyWith(fontSize: 14)),
                        ),
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            '${day.tmaxC.round()}° / ${day.tminC.round()}°',
                            style: theme.bodyMedium?.copyWith(fontSize: 14, color: AppColors.inkSoft),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
        ],
      ),
    );
  }
}
