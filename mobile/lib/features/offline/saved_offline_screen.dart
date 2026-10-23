import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../scan/scan_flow.dart';

/// Calm confirmation after a photo was saved because there was no internet: "Your photo is saved and will be sent
/// later." One big house button leads back to the first page.
class SavedOfflineScreen extends ConsumerWidget {
  const SavedOfflineScreen({super.key});

  void _home(BuildContext context, WidgetRef ref) {
    ref.read(scanFlowProvider.notifier).reset();
    context.go(Routes.home);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      onBack: () => _home(context, ref),
      script: promptList(const ['offline_saved']),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 140,
            height: 120,
            child: Stack(
              alignment: Alignment.center,
              children: [
                const Icon(AppIcons.offline, size: 110, color: AppColors.inkSoft),
                Positioned(
                  right: 4,
                  bottom: 0,
                  child: Container(
                    key: const ValueKey('saved-tick'),
                    width: 52,
                    height: 52,
                    decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
                    child: const Icon(AppIcons.tick, size: 36, color: Colors.white),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            t('offline_saved_title'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 8),
          Text(t('offline_saved_hint'), textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
      bottomRight: BigIconButton(
        key: const ValueKey('saved-home'),
        icon: AppIcons.house,
        semanticLabel: t('a11y_home'),
        size: 104,
        onPressed: () => _home(context, ref),
      ),
    );
  }
}
