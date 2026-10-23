import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';

/// Speaks the welcome in the chosen language; the green tick moves on to the login screen.
class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      script: promptList(const ['welcome', 'tap_green_tick']),
      onBack: () => context.go(Routes.language),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 160,
            height: 160,
            decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
            child: const Icon(AppIcons.leaf, size: 100, color: Colors.white),
          ),
          const SizedBox(height: 24),
          Text(t('app_name'), style: Theme.of(context).textTheme.displaySmall),
        ],
      ),
      bottomRight: TickButton(
        key: const ValueKey('welcome-continue'),
        size: 112,
        semanticLabel: t('a11y_yes'),
        onPressed: () async {
          await ref.read(settingsProvider.notifier).markOnboardingDone();
          if (context.mounted) context.go(Routes.login);
        },
      ),
    );
  }
}
