import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';

/// Checks the saved login and the onboarding flag, then moves on. Silent: no language is known yet.
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  /// What the start is doing now: shown (small) if it takes long, so a stuck start can be read off the screen.
  String _step = 'starting';
  String? _error;
  bool _slow = false;
  Timer? _watchdog;

  @override
  void initState() {
    super.initState();
    _watchdog = Timer(const Duration(seconds: 6), () {
      if (mounted) setState(() => _slow = true);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    _watchdog?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    if (mounted && _error != null) setState(() => _error = null);
    try {
      _step = 'reading the saved login';
      try {
        // Never wait for ever on the phone's key store: no answer means "not logged in".
        await ref.read(sessionProvider.notifier).restore().timeout(const Duration(seconds: 8));
      } on Object {
        // Continue as logged out; the farmer simply logs in again.
        ref.read(sessionProvider.notifier).assumeLoggedOut();
      }
      if (!mounted) return;
      _step = 'choosing the first screen';
      final settings = ref.read(settingsProvider);
      final session = ref.read(sessionProvider);
      final String target;
      if (settings.language == null) {
        target = Routes.language;
      } else if (!session.isLoggedIn) {
        target = settings.onboardingDone ? Routes.login : Routes.welcome;
      } else {
        target = Routes.home;
      }
      _step = 'opening $target';
      context.go(target);
    } on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final small = Theme.of(context).textTheme.bodyMedium;
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 140,
                height: 140,
                decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
                child: const Icon(AppIcons.leaf, size: 88, color: Colors.white),
              ),
              const SizedBox(height: 24),
              Text(t('app_name'), style: Theme.of(context).textTheme.displaySmall),
              if (_error != null) ...[
                const SizedBox(height: 24),
                SelectableText('Start problem: $_error', key: const ValueKey('splash-error'), style: small),
                const SizedBox(height: 16),
                FilledButton(
                  key: const ValueKey('splash-retry'),
                  style: FilledButton.styleFrom(minimumSize: const Size(120, 64)),
                  onPressed: _start,
                  child: const Icon(AppIcons.roundArrow, size: 32),
                ),
              ] else if (_slow) ...[
                const SizedBox(height: 24),
                Text('Still starting… ($_step)', key: const ValueKey('splash-slow'), style: small),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
