import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../diary/date_words.dart';
import '../diary/diary_widgets.dart';

/// One alert in the list. An unread alert has a coloured background, a thick border, bold words and a "New" label,
/// so it stands out without relying on colour; the level is a picture and a word as well as a colour.
class AlertCard extends ConsumerWidget {
  const AlertCard({super.key, required this.alert, required this.onTap});

  final AlertOut alert;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider);
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final now = ref.watch(clockProvider)();
    final theme = Theme.of(context).textTheme;
    final unread = !alert.isRead;
    final color = AppColors.severity(alert.level);
    final created = alert.createdAt;
    final title = alert.title.forLang(lang);
    final date = created == null
        ? ''
        : [words.relative(created, now), words.written(created)].whereType<String>().join(', ');
    return Material(
      key: ValueKey('alert-${alert.id}'),
      color: unread ? AppColors.severitySoft(alert.level) : AppColors.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: unread ? AppColors.severityAccent(alert.level) : AppColors.line, width: unread ? 4 : 2),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          Haptics.tap();
          onTap();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 96),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                  child: Icon(AppIcons.bell, size: 34, color: AppColors.onSeverity(alert.level)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: theme.titleMedium?.copyWith(fontWeight: unread ? FontWeight.w800 : FontWeight.w500),
                      ),
                      if (date.isNotEmpty) Text(date, style: theme.bodyMedium),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        children: [
                          SeverityPill(severity: alert.level),
                          if (unread)
                            StatusPill(
                              key: ValueKey('alert-new-${alert.id}'),
                              icon: Icons.fiber_manual_record_rounded,
                              label: t('alerts_new'),
                              color: AppColors.blue,
                              background: AppColors.blueSoft,
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(AppIcons.greenArrow, size: 32, color: AppColors.green),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
