import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'alert_widgets.dart';
import 'alerts_providers.dart';

/// Route `/alerts`: newest first, unread ones highlighted. Tapping an alert opens it (and marks it as read).
/// Reloads when the app comes back and every five minutes (see [AlertsAutoRefresh] in the router).
class AlertsScreen extends ConsumerStatefulWidget {
  const AlertsScreen({super.key});

  @override
  ConsumerState<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends ConsumerState<AlertsScreen> {
  final Object _owner = Object();

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.home);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final alerts = ref.watch(alertsProvider);

    final failed = alerts.hasError && !alerts.hasValue;
    if (failed) {
      return ErrorRetryScreen(error: alerts.error!, onRetry: () => ref.invalidate(alertsProvider), onBack: _back);
    }
    final loading = !alerts.hasValue;
    final items = newestFirst(alerts.value?.items ?? const []);

    return VoiceScaffold(
      owner: _owner,
      script: promptList([items.isEmpty ? 'alert_none' : 'alert_open']),
      speakEnabled: !loading,
      onBack: _back,
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : items.isEmpty
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(AppIcons.bell, size: Dimens.hero, color: AppColors.inkSoft),
                const SizedBox(height: 12),
                Text(
                  t('alerts_empty_title'),
                  key: const ValueKey('alerts-empty'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ],
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final alert in items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: AlertCard(alert: alert, onTap: () => context.push(Routes.alertDetailFor(alert.id))),
                  ),
              ],
            ),
    );
  }
}
