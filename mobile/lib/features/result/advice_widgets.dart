import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';

IconData severityIcon(Severity s) => switch (s) {
  Severity.green => AppIcons.tick,
  Severity.yellow => AppIcons.warning,
  Severity.red => AppIcons.danger,
};

/// The coloured band at the top of an advice: colour and picture carry the urgency before any word is read.
class SeverityBand extends ConsumerWidget {
  const SeverityBand({super.key, required this.severity, required this.headline});

  final Severity severity;
  final String headline;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final fg = AppColors.onSeverity(severity);
    return Container(
      key: ValueKey('severity-${severity.wire}'),
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.severity(severity),
        borderRadius: BorderRadius.circular(Dimens.radius),
      ),
      child: Row(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(color: fg.withValues(alpha: 0.18), shape: BoxShape.circle),
            child: Icon(severityIcon(severity), size: 44, color: fg),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  t('severity_${severity.wire}'),
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(color: fg),
                ),
                Text(
                  headline,
                  key: const ValueKey('advice-headline'),
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: fg),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class WarningTile extends StatelessWidget {
  const WarningTile({super.key, required this.level, required this.text});

  final Severity level;
  final String text;

  @override
  Widget build(BuildContext context) {
    final color = level == Severity.red ? AppColors.red : AppColors.amberDark;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.severitySoft(level == Severity.red ? Severity.red : Severity.yellow),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color, width: 2),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(level == Severity.red ? AppIcons.danger : AppIcons.warning, size: 36, color: color),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyLarge)),
        ],
      ),
    );
  }
}

class _IconLine extends StatelessWidget {
  const _IconLine({required this.icon, required this.text, this.bold = false, this.color = AppColors.inkSoft});

  final IconData icon;
  final String text;
  final bool bold;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(icon, size: 32, color: color),
      const SizedBox(width: 12),
      Expanded(
        child: Text(
          text,
          style: Theme.of(context).textTheme.bodyLarge?.copyWith(fontWeight: bold ? FontWeight.w700 : FontWeight.w400),
        ),
      ),
    ],
  );
}

/// One approved medicine: the active ingredient, a brand example, the dose as a sentence and the waiting period.
class ProductCard extends ConsumerWidget {
  const ProductCard({super.key, required this.product});

  final ProductOut product;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final lang = ref.watch(languageProvider);
    final brand = [
      product.brandExamples.take(2).join(' / '),
      ?product.formulation,
    ].where((s) => s.isNotEmpty).join(' · ');
    final dose = product.doseText.forLang(lang);
    final waiting = product.waitingPeriodDays;
    return Container(
      key: ValueKey('product-${product.productId}'),
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.blue, width: 2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
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
                    Text(
                      t('advice_medicine'),
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: AppColors.inkSoft),
                    ),
                    Text(product.activeIngredient.forLang(lang), style: Theme.of(context).textTheme.titleLarge),
                    if (brand.isNotEmpty) Text(brand, style: Theme.of(context).textTheme.bodyLarge),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _IconLine(
            icon: Icons.water_drop_rounded,
            text: dose.isNotEmpty
                ? dose
                : [if (product.doseMin != null) '${product.doseMin}', ?product.doseUnit].join(' '),
            bold: true,
            color: AppColors.blue,
          ),
          if (waiting != null) ...[
            const SizedBox(height: 10),
            _IconLine(
              icon: AppIcons.clock,
              text: t('advice_wait_days', args: {'n': waiting}),
            ),
          ],
          for (final w in product.warnings) ...[
            const SizedBox(height: 10),
            WarningTile(level: w.level, text: w.text.forLang(lang)),
          ],
        ],
      ),
    );
  }
}

IconData timingIcon(TimingAction a) => switch (a) {
  TimingAction.sprayNow => AppIcons.tick,
  TimingAction.wait => Icons.hourglass_top_rounded,
  TimingAction.repeatWithinDays => AppIcons.roundArrow,
  TimingAction.notNeeded => AppIcons.cross,
  TimingAction.unknown => AppIcons.clock,
};

/// Everything of an advice except the actions. Order: severity band, medicines, timing, warnings, the summary
/// sentence, safety notes, steps: what to buy and do comes before the explanation.
class AdviceCards extends ConsumerWidget {
  const AdviceCards({super.key, required this.advice});

  final AdviceOut advice;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(languageProvider);
    final t = ref.watch(stringsProvider);
    final timing = advice.timing;
    final summary = advice.summary.forLang(lang);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SeverityBand(severity: advice.severity, headline: advice.headline.forLang(lang)),
        for (final p in advice.products) ...[const SizedBox(height: 14), ProductCard(product: p)],
        if (timing != null && !timing.text.isEmpty) ...[
          const SizedBox(height: 14),
          Container(
            key: const ValueKey('advice-timing'),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.greenSoft,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.green, width: 2),
            ),
            child: _IconLine(
              icon: timingIcon(timing.action),
              text: '${t('advice_when')}: ${timing.text.forLang(lang)}',
              bold: true,
              color: AppColors.green,
            ),
          ),
        ],
        for (final w in advice.warnings) ...[
          const SizedBox(height: 12),
          WarningTile(level: w.level, text: w.text.forLang(lang)),
        ],
        if (summary.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text(summary, key: const ValueKey('advice-summary'), style: Theme.of(context).textTheme.bodyLarge),
        ],
        for (final s in advice.safety) ...[
          const SizedBox(height: 12),
          WarningTile(level: Severity.yellow, text: s.forLang(lang)),
        ],
        if (advice.steps.isNotEmpty) ...[
          const SizedBox(height: 14),
          Text(t('advice_steps'), style: Theme.of(context).textTheme.titleLarge),
          for (var i = 0; i < advice.steps.length; i++) ...[
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                  decoration: const BoxDecoration(color: AppColors.ink, shape: BoxShape.circle),
                  child: Text(
                    '${i + 1}',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 20),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(child: Text(advice.steps[i].forLang(lang), style: Theme.of(context).textTheme.bodyLarge)),
              ],
            ),
          ],
        ],
        const SizedBox(height: 8),
      ],
    );
  }
}
