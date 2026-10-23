import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/offline/offline_status.dart';
import 'core/providers.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';
import 'core/widgets/demo_clock_banner.dart';

/// The whole app: theme, router, text scaling, "stop talking when the app goes to the background" and the root of
/// the offline queue (it is started here, after the first frame, and reacts to resume and pause).
class FarmTrackApp extends ConsumerStatefulWidget {
  const FarmTrackApp({super.key});

  @override
  ConsumerState<FarmTrackApp> createState() => _FarmTrackAppState();
}

class _FarmTrackAppState extends ConsumerState<FarmTrackApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // After the first frame: nothing of the offline queue runs before the first screen is on the glass.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(offlineStatusProvider);
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // `paused` only: the camera and permission dialogs make the app `inactive` while we still want to talk.
    if (state == AppLifecycleState.paused) ref.read(voiceServiceProvider).stop();
    // Back in the app: send what waits, and ask the server again whether it runs on a demo clock.
    ref.read(offlineStatusProvider.notifier).onLifecycle(state);
    if (state == AppLifecycleState.resumed) ref.invalidate(demoClockProvider);
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'FarmTrack',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      routerConfig: router,
      builder: (context, child) {
        // Respect the phone's large-text setting, but cap it so the big buttons still fit.
        final scaler = MediaQuery.textScalerOf(context).clamp(minScaleFactor: 1.0, maxScaleFactor: 2.0);
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: scaler),
          child: child ?? const SizedBox.shrink(),
        );
      },
    );
  }
}
