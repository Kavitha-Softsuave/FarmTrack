import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/api_exception.dart';
import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/redirect.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../diary/date_words.dart';
import '../result/advice_widgets.dart';
import 'alerts_providers.dart';
import 'open_scan.dart';

/// One alert, opened from the list or from a push message: the level as colour, picture and word, the title and
/// text, and the spoken version, which starts by itself. An alert that is about a photo check has a big green arrow
/// that opens that scan's result. Opening an alert marks it as read.
class AlertDetailScreen extends ConsumerStatefulWidget {
  const AlertDetailScreen({super.key, required this.alertId});

  final String? alertId;

  @override
  ConsumerState<AlertDetailScreen> createState() => _AlertDetailScreenState();
}

class _AlertDetailScreenState extends ConsumerState<AlertDetailScreen> {
  final Object _owner = Object();
  bool _markedRead = false;
  bool _opening = false;

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.alerts);
    }
  }

  /// Marks the alert as read once, after the first frame that shows it.
  void _markRead(AlertOut alert) {
    if (_markedRead || alert.isRead) return;
    _markedRead = true;
    final container = ProviderScope.containerOf(context, listen: false);
    WidgetsBinding.instance.addPostFrameCallback((_) => markAlertRead(container, alert));
  }

  Future<void> _openScan(AlertOut alert) async {
    final scanId = alert.scanId;
    if (scanId == null || _opening) return;
    final voice = ref.read(voiceServiceProvider);
    setState(() => _opening = true);
    try {
      final scan = await ref.read(apiClientProvider).getScan(scanId);
      final route = resultRouteFor(scan);
      if (!mounted) return;
      if (route == null) {
        await voice.speak(promptList(const ['error_try_again']), owner: _owner);
        return;
      }
      showScanResult(ref, scan);
      await context.push<void>(route);
    } on ApiException catch (e) {
      Haptics.error();
      await voice.speak(promptList([errorPromptFor(e)]), owner: _owner);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final id = widget.alertId;
    if (id == null || id.isEmpty) return const Redirect(to: Routes.alerts);

    final alerts = ref.watch(alertsProvider);
    if (alerts.hasError && !alerts.hasValue) {
      return ErrorRetryScreen(error: alerts.error!, onRetry: () => ref.invalidate(alertsProvider), onBack: _back);
    }
    final items = alerts.value?.items;
    if (items == null) {
      return VoiceScaffold(
        script: const [],
        speakEnabled: false,
        onBack: _back,
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final found = items.where((a) => a.id == id);
    // The alert is not in the list any more (very old, or a wrong link): show the list instead.
    if (found.isEmpty) return const Redirect(to: Routes.alerts);
    final alert = found.first;
    _markRead(alert);

    final lang = ref.watch(languageProvider);
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final now = ref.watch(clockProvider)();
    final theme = Theme.of(context).textTheme;
    final body = alert.body.forLang(lang);
    final created = alert.createdAt;
    final date = created == null
        ? ''
        : [words.relative(created, now), words.written(created)].whereType<String>().join(', ');
    final hasScan = alert.scanId != null && alert.scanId!.isNotEmpty;

    final spoken = alert.spoken.toUtterance(lang) ?? (body.isEmpty ? null : TextUtterance(body, lang: lang));
    return VoiceScaffold(
      owner: _owner,
      script: [?spoken, if (hasScan) const PromptUtterance('alert_see_scan')],
      onBack: _back,
      bottomRight: hasScan
          ? (_opening
                ? const SizedBox(width: 96, height: 96, child: Center(child: CircularProgressIndicator()))
                : BigIconButton(
                    key: const ValueKey('alert-open-scan'),
                    icon: AppIcons.greenArrow,
                    size: 96,
                    semanticLabel: t('alerts_open_scan_label'),
                    onPressed: () => _openScan(alert),
                  ))
          : null,
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SeverityBand(severity: alert.level, headline: alert.title.forLang(lang)),
          if (body.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(body, key: const ValueKey('alert-body'), style: theme.bodyLarge),
          ],
          if (date.isNotEmpty) ...[const SizedBox(height: 12), Text(date, style: theme.bodyMedium)],
        ],
      ),
    );
  }
}
