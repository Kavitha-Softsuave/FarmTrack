import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'result_prompts.dart';
import 'scan_flow.dart';

/// The photo was not usable: speaks what was wrong (blurry, dark, far, no leaf) and offers the camera again.
class RetakeScreen extends ConsumerWidget {
  const RetakeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scan = ref.watch(scanFlowProvider).scan;
    final catalogue = ref.watch(promptCatalogueProvider);
    final t = ref.watch(stringsProvider);
    final issues = scan?.quality.issues ?? const <String>[];
    final tip = qualityTipPrompt(scan?.quality, catalogue);
    final retake = pickPrompt(scan?.promptsFor(NextAction.retake) ?? const [], 'scan_retake_tap', catalogue);

    return VoiceScaffold(
      script: promptList([tip, retake]),
      onBack: () => context.go(Routes.home),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_issueIcon(issues), size: 72, color: AppColors.amberDark, key: const ValueKey('retake-issue')),
          const SizedBox(height: 16),
          BigIconButton(
            key: const ValueKey('retake-camera'),
            icon: AppIcons.camera,
            semanticLabel: t('a11y_camera'),
            size: 180,
            onPressed: () {
              ref.read(scanFlowProvider.notifier).reset();
              context.go(Routes.scan);
            },
          ),
        ],
      ),
    );
  }

  IconData _issueIcon(List<String> issues) {
    if (issues.contains('blurry')) return Icons.blur_on_rounded;
    if (issues.contains('too_dark')) return Icons.brightness_low_rounded;
    if (issues.contains('too_bright')) return Icons.brightness_high_rounded;
    if (issues.contains('too_small')) return Icons.zoom_in_rounded;
    if (issues.contains('no_leaf')) return AppIcons.leaf;
    return AppIcons.warning;
  }
}
