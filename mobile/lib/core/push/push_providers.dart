import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/alerts/alerts_providers.dart';
import '../providers.dart';
import 'notification_permission.dart';
import 'push_service.dart';
import 'push_token_source.dart';

const _permissionAskedKey = 'push_permission_asked';

/// Replace with the real implementation when push is switched on (see `docs/design-notes/mobile2a.md`).
final pushTokenSourceProvider = Provider<PushTokenSource>((ref) => const NoopPushTokenSource());

final notificationPermissionPortProvider = Provider<NotificationPermissionPort>(
  (ref) => const UnsupportedNotificationPermissionPort(),
);

final pushServiceProvider = Provider<PushService>((ref) {
  final prefs = ref.watch(sharedPreferencesProvider);
  final service = PushService(
    tokens: ref.watch(pushTokenSourceProvider),
    permission: ref.watch(notificationPermissionPortProvider),
    registerDevice: (device) => ref.read(apiClientProvider).registerDevice(device),
    speak: (items) => ref.read(voiceServiceProvider).speak(items, interrupt: false),
    isLoggedIn: () => ref.read(sessionProvider).isLoggedIn,
    wasPermissionAsked: () => prefs.getBool(_permissionAskedKey) ?? false,
    markPermissionAsked: () => prefs.setBool(_permissionAskedKey, true),
    platform: Platform.isIOS ? 'ios' : 'android',
    onAlertArrived: () => refreshAlerts(ref),
  );
  ref.listen(sessionProvider, (previous, next) {
    final was = previous?.isLoggedIn ?? false;
    if (next.isLoggedIn && !was) unawaited(service.onLoggedIn());
    if (!next.isLoggedIn && was) service.onLoggedOut();
  });
  ref.onDispose(service.dispose);
  return service;
});

/// Wraps the Home screen (which only exists for a logged-in farmer): connects the push service to the router,
/// starts it, and asks the notification permission once.
class PushBootstrap extends ConsumerStatefulWidget {
  const PushBootstrap({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<PushBootstrap> createState() => _PushBootstrapState();
}

class _PushBootstrapState extends ConsumerState<PushBootstrap> {
  @override
  void initState() {
    super.initState();
    final service = ref.read(pushServiceProvider);
    final router = GoRouter.of(context);
    service.attachNavigator((location) => unawaited(router.push<void>(location)));
    unawaited(service.start());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(service.ensurePermission());
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
