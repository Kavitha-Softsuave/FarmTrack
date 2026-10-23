import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';

/// Route `/settings/logout`: "Do you want to log out?" with the red cross (stay) and the green tick (log out).
/// Logging out forgets the login on this phone at once and tells the server in the background.
class LogoutConfirmScreen extends ConsumerWidget {
  const LogoutConfirmScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      script: promptList(const ['settings_logout_confirm']),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(AppIcons.logout, size: 96, color: AppColors.inkSoft),
          const SizedBox(height: 12),
          Text(
            t('settings_logout_question'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CrossButton(
                key: const ValueKey('logout-no'),
                size: 112,
                semanticLabel: t('a11y_no'),
                onPressed: () => context.pop(),
              ),
              const SizedBox(width: 28),
              TickButton(
                key: const ValueKey('logout-yes'),
                size: 112,
                semanticLabel: t('a11y_yes'),
                onPressed: () async {
                  await ref.read(sessionProvider.notifier).logout();
                  if (context.mounted) context.go(Routes.login);
                },
              ),
            ],
          ),
        ],
      ),
    );
  }
}
