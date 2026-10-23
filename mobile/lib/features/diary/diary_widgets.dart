import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/widgets/big_buttons.dart';
import '../result/advice_widgets.dart';
import '../scan/crop_picture.dart';
import 'date_words.dart';
import 'diary_providers.dart';

/// A small label with a picture and words: never colour alone.
class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.icon, required this.label, required this.color, required this.background});

  final IconData icon;
  final String label;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: background,
      borderRadius: BorderRadius.circular(999),
      border: Border.all(color: color, width: 2),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 22, color: color),
        const SizedBox(width: 6),
        Flexible(
          child: Text(label, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
        ),
      ],
    ),
  );
}

/// The pill of a warning level: picture and word ("Be careful" / "Serious").
class SeverityPill extends ConsumerWidget {
  const SeverityPill({super.key, required this.severity});

  final Severity severity;

  @override
  Widget build(BuildContext context, WidgetRef ref) => StatusPill(
    icon: severityIcon(severity),
    label: ref.watch(stringsProvider)('severity_${severity.wire}'),
    color: severity == Severity.red ? AppColors.red : AppColors.amberDark,
    background: AppColors.severitySoft(severity),
  );
}

/// One line of the diary list: crop picture, medicine, date in words, and the warning and waiting badges.
class DiaryEntryCard extends ConsumerWidget {
  const DiaryEntryCard({super.key, required this.entry, required this.onTap});

  final DiaryEntry entry;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final now = ref.watch(clockProvider)();
    final theme = Theme.of(context).textTheme;
    final worst = entry.worst;
    final relative = words.relative(entry.date, now);
    final date = relative == null ? words.written(entry.date) : '$relative, ${words.written(entry.date)}';
    return Material(
      key: ValueKey('diary-entry-${entry.id}'),
      color: AppColors.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: entry.pending ? AppColors.inkSoft : AppColors.line, width: 2),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          Haptics.tap();
          onTap();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 88),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                CropPicture(cropId: entry.cropId.toLowerCase(), size: 56),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        entry.name.isEmpty ? t('diary_no_name') : entry.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.titleMedium,
                      ),
                      Text(date, style: theme.bodyLarge),
                      if (worst != null || entry.pending) ...[
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            if (entry.pending)
                              StatusPill(
                                icon: AppIcons.clock,
                                label: t('diary_waiting_label'),
                                color: AppColors.inkSoft,
                                background: AppColors.line.withValues(alpha: 0.5),
                              ),
                            if (worst != null) SeverityPill(severity: worst),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(AppIcons.speaker, size: 28, color: AppColors.blue),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A warning of a saved entry: colour, picture and words together, with its own speaker button.
class DiaryWarningCard extends ConsumerWidget {
  const DiaryWarningCard({super.key, required this.warning, required this.onSpeak});

  final WarningOut warning;
  final VoidCallback onSpeak;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final lang = ref.watch(languageProvider);
    final theme = Theme.of(context).textTheme;
    final level = warning.level == Severity.red ? Severity.red : Severity.yellow;
    final color = AppColors.severity(level);
    return Container(
      key: ValueKey('warning-${warning.code}'),
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
                Text(t('severity_${level.wire}'), style: theme.titleMedium),
                Text(warning.text.forLang(lang), style: theme.bodyLarge),
              ],
            ),
          ),
          const SizedBox(width: 8),
          BigIconButton(
            key: ValueKey('warning-speak-${warning.code}'),
            icon: AppIcons.speaker,
            semanticLabel: t('diary_listen_warning'),
            color: AppColors.blue,
            size: Dimens.minTouch,
            onPressed: onSpeak,
          ),
        ],
      ),
    );
  }
}

/// A medicine of an advice: name, brand and dose, big enough to tap. Tapping says its name and dose.
class MedicineCard extends ConsumerWidget {
  const MedicineCard({super.key, required this.product, required this.onTap, this.selected = false});

  final ProductOut product;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider);
    final theme = Theme.of(context).textTheme;
    final brand = product.brandExamples.take(2).join(' / ');
    final dose = product.doseText.forLang(lang);
    return Material(
      key: ValueKey('diary-product-${product.productId}'),
      color: selected ? AppColors.greenSoft : AppColors.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: selected ? AppColors.green : AppColors.blue, width: selected ? 4 : 2),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          Haptics.tap();
          onTap();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 88),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: const BoxDecoration(color: AppColors.blueSoft, shape: BoxShape.circle),
                  child: const Icon(AppIcons.medicine, size: 34, color: AppColors.blue),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(product.activeIngredient.forLang(lang), style: theme.titleLarge),
                      if (brand.isNotEmpty) Text(brand, style: theme.bodyLarge),
                      if (dose.isNotEmpty) Text(dose, style: theme.bodyMedium),
                    ],
                  ),
                ),
                if (selected) ...[
                  const SizedBox(width: 8),
                  const Icon(AppIcons.tick, size: 36, color: AppColors.green),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------------------------------------------------- day choice

/// Which day the farmer sprayed: today (the default), yesterday, or another day of the last two weeks.
enum DayChoice { today, yesterday, other }

class DateChoiceRow extends ConsumerWidget {
  const DateChoiceRow({
    super.key,
    required this.choice,
    required this.otherDay,
    required this.onToday,
    required this.onYesterday,
    required this.onOther,
  });

  final DayChoice choice;

  /// The day picked with "other day", shown on that button once it is chosen.
  final DateTime? otherDay;
  final VoidCallback onToday;
  final VoidCallback onYesterday;
  final VoidCallback onOther;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final other = choice == DayChoice.other && otherDay != null ? words.written(otherDay!) : t('diary_other_day');
    final buttons = [
      _DayButton(
        key: const ValueKey('day-today'),
        icon: Icons.today_rounded,
        label: t('diary_today'),
        selected: choice == DayChoice.today,
        onTap: onToday,
      ),
      _DayButton(
        key: const ValueKey('day-yesterday'),
        icon: Icons.history_rounded,
        label: t('diary_yesterday'),
        selected: choice == DayChoice.yesterday,
        onTap: onYesterday,
      ),
      _DayButton(
        key: const ValueKey('day-other'),
        icon: Icons.calendar_month_rounded,
        label: other,
        selected: choice == DayChoice.other,
        onTap: onOther,
      ),
    ];
    // At large text sizes three buttons side by side would squeeze the words: stack them.
    final stacked = MediaQuery.textScalerOf(context).scale(20) > 26;
    if (stacked) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [for (final b in buttons) Padding(padding: const EdgeInsets.only(bottom: 8), child: b)],
      );
    }
    return Row(
      children: [
        for (var i = 0; i < buttons.length; i++) ...[if (i > 0) const SizedBox(width: 8), Expanded(child: buttons[i])],
      ],
    );
  }
}

class _DayButton extends StatelessWidget {
  const _DayButton({super.key, required this.icon, required this.label, required this.selected, required this.onTap});

  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? Colors.white : AppColors.ink;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: selected ? AppColors.green : AppColors.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: AppColors.green, width: 3),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: () {
            Haptics.tap();
            onTap();
          },
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 80),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(selected ? AppIcons.tick : icon, size: 30, color: foreground),
                  const SizedBox(height: 4),
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      label,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(color: foreground),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The last fourteen days as big buttons, today first.
class DayChooser extends ConsumerWidget {
  const DayChooser({super.key, required this.onPick, this.days = 14});

  /// [daysBack] is 0 for today, 1 for yesterday, up to `days - 1`.
  final void Function(int daysBack) onPick;
  final int days;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final words = ref.watch(dateWordsProvider);
    final now = dayOnly(ref.watch(clockProvider)());
    final theme = Theme.of(context).textTheme;
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = (constraints.maxWidth - 12) / 2;
        return Wrap(
          alignment: WrapAlignment.center,
          spacing: 12,
          runSpacing: 12,
          children: [
            for (var back = 0; back < days; back++)
              SizedBox(
                width: width,
                child: Builder(
                  builder: (context) {
                    final day = DateTime(now.year, now.month, now.day - back);
                    final relative = words.relative(day, now) ?? words.weekday(day);
                    return Material(
                      key: ValueKey('day-option-$back'),
                      color: back == 0 ? AppColors.greenSoft : AppColors.card,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                        side: const BorderSide(color: AppColors.green, width: 3),
                      ),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(20),
                        onTap: () {
                          Haptics.tap();
                          onPick(back);
                        },
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(minHeight: 80),
                          child: Padding(
                            padding: const EdgeInsets.all(8),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                FittedBox(
                                  fit: BoxFit.scaleDown,
                                  child: Text(words.written(day), style: theme.titleLarge),
                                ),
                                FittedBox(
                                  fit: BoxFit.scaleDown,
                                  child: Text(relative, style: theme.bodyMedium),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
        );
      },
    );
  }
}

// ------------------------------------------------------------------------------------------------------- crops

/// Crop pictures to tap, as many as fit (the screen pages them with big arrows, six at a time).
///
/// The server writes crop ids with a capital (`Apple`), the app's names and pictures are keyed in lower case: the
/// lookups here use the lower case id, while [onPick] gives the id as it was listed (the server accepts any case).
class CropGrid extends ConsumerWidget {
  const CropGrid({super.key, required this.cropIds, required this.onPick});

  final List<String> cropIds;
  final void Function(String cropId) onPick;

  /// Crops per page of the grid.
  static const perPage = 6;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider);
    final resources = ref.watch(resourcesProvider);
    return LayoutBuilder(
      builder: (context, constraints) {
        final rows = (cropIds.length / 2).ceil().clamp(1, 3);
        final tileHeight = ((constraints.maxHeight - (rows - 1) * 12) / rows).clamp(110.0, 200.0);
        return SingleChildScrollView(
          child: Wrap(
            alignment: WrapAlignment.center,
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final id in cropIds)
                SizedBox(
                  width: (constraints.maxWidth - 12) / 2,
                  height: tileHeight,
                  child: PictureTile(
                    key: ValueKey('crop-$id'),
                    semanticLabel: resources.cropName(id.toLowerCase(), lang),
                    label: resources.cropName(id.toLowerCase(), lang),
                    minHeight: 110,
                    onPressed: () => onPick(id),
                    child: CropPicture(cropId: id.toLowerCase(), size: 84),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
