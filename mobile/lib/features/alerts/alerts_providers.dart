import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/api_exception.dart';
import '../../core/models/models.dart';
import '../../core/providers.dart';

/// The alert list, newest first. Reloaded by [refreshAlerts] (resume, timer, push, after reading an alert).
final alertsProvider = FutureProvider<AlertListOut>((ref) {
  // A new login (maybe another farmer on this phone) starts with a fresh list.
  ref.watch(sessionProvider.select((s) => s.farmer?.id));
  return ref.watch(apiClientProvider).listAlerts(limit: 30);
});

/// Newest first (the server already sends them that way; an alert without a date goes last). The order of alerts
/// with the same time is kept.
List<AlertOut> newestFirst(List<AlertOut> alerts) {
  final indexed = [for (var i = 0; i < alerts.length; i++) (i, alerts[i])];
  indexed.sort((a, b) {
    final x = a.$2.createdAt;
    final y = b.$2.createdAt;
    if (x == null || y == null) return x == y ? a.$1.compareTo(b.$1) : (x == null ? 1 : -1);
    final byTime = y.compareTo(x);
    return byTime != 0 ? byTime : a.$1.compareTo(b.$1);
  });
  return [for (final e in indexed) e.$2];
}

/// Makes the alert list and the bell badge on Home load again.
void refreshAlerts(Ref ref) {
  ref.invalidate(alertsProvider);
  ref.invalidate(unreadAlertsProvider);
}

/// Same as [refreshAlerts] for widgets: use `ProviderScope.containerOf(context)`, which stays valid after the
/// widget is gone (a `WidgetRef` does not).
void refreshAlertsIn(ProviderContainer container) {
  container.invalidate(alertsProvider);
  container.invalidate(unreadAlertsProvider);
}

/// Tells the server that an alert was opened, then reloads the list and the badge. A failure (no internet) is
/// silent: the alert simply stays unread until the next time.
Future<void> markAlertRead(ProviderContainer container, AlertOut alert) async {
  if (alert.isRead) return;
  try {
    await container.read(apiClientProvider).markAlertRead(alert.id);
  } on ApiException {
    return;
  }
  refreshAlertsIn(container);
}

/// How often the open Home or alert screen asks for new alerts.
final alertsRefreshIntervalProvider = Provider<Duration>((ref) => const Duration(minutes: 5));

/// Keeps the bell badge and the alert list fresh while its child (Home or the alert screen) is on screen: when the
/// app comes back from the background and every [alertsRefreshIntervalProvider].
class AlertsAutoRefresh extends ConsumerStatefulWidget {
  const AlertsAutoRefresh({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AlertsAutoRefresh> createState() => _AlertsAutoRefreshState();
}

class _AlertsAutoRefreshState extends ConsumerState<AlertsAutoRefresh> with WidgetsBindingObserver {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _timer = Timer.periodic(ref.read(alertsRefreshIntervalProvider), (_) => _refresh());
  }

  void _refresh() {
    if (!mounted || !ref.read(sessionProvider).isLoggedIn) return;
    refreshAlertsIn(ProviderScope.containerOf(context, listen: false));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
