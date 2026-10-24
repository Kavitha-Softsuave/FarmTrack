import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';

/// True in a release build. Tests override it.
final releaseBuildProvider = Provider<bool>((ref) => kReleaseMode);

/// Whether the app asks the server (`GET /v1/meta`) for the demo date at all. Off under `flutter test`, so the extra
/// request cannot take a failure that a test queued for another call; the banner tests turn it on.
final demoBannerFetchProvider = Provider<bool>((ref) => !Platform.environment.containsKey('FLUTTER_TEST'));

/// The date the server pretends it is (`MetaOut.demo_clock`), or null when it uses the real clock, the answer is
/// unavailable (offline) or this is a release build talking to a production server.
///
/// It is fetched again when the phone comes back online; the app invalidates it when it is resumed.
final demoClockProvider = FutureProvider<DateTime?>((ref) async {
  if (!ref.watch(demoBannerFetchProvider)) return null;
  final meta = await ref.watch(serverMetaProvider.future);
  final clock = meta?.demoClock;
  if (meta == null || clock == null) return null;
  if (ref.watch(releaseBuildProvider) && meta.env == 'prod') return null;
  return clock;
});

/// The farmer (or the tester) tapped the demo strip away: it stays away until the app is started again.
final demoBannerDismissedProvider = NotifierProvider<DemoBannerDismissed, bool>(DemoBannerDismissed.new);

class DemoBannerDismissed extends Notifier<bool> {
  @override
  bool build() => false;

  void dismiss() => state = true;
}

/// "12 May 2026" (or the Hindi month name) for the demo clock, in Indian time. Only ever shown, never spoken.
String formatDemoDate(DateTime clock, List<String> monthNames) {
  final ist = clock.toUtc().add(const Duration(hours: 5, minutes: 30));
  final month = ist.month >= 1 && ist.month <= monthNames.length ? monthNames[ist.month - 1] : '${ist.month}';
  return '${ist.day} $month ${ist.year}';
}

/// A thin, high-contrast strip at the top of every screen while the server runs on a demo clock: "Demo date: 12 May
/// 2026". It is text only (the voice never reads it), a tap on it hides it until the app is started again, and it does
/// not exist in a release build against production.
class DemoClockBanner extends ConsumerWidget {
  const DemoClockBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clock = ref.watch(demoClockProvider).value;
    if (clock == null || ref.watch(demoBannerDismissedProvider)) return const SizedBox.shrink();
    final t = ref.watch(stringsProvider);
    final months = t('demo_month_words').split(',');
    final text = t('demo_banner', args: {'date': formatDemoDate(clock, months)});
    return Semantics(
      container: true,
      label: text,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => ref.read(demoBannerDismissedProvider.notifier).dismiss(),
        child: Container(
          key: const ValueKey('demo-banner'),
          width: double.infinity,
          color: AppColors.ink,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
          child: FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              text,
              maxLines: 1,
              style: const TextStyle(color: AppColors.amber, fontSize: 14, fontWeight: FontWeight.w800, height: 1.2),
            ),
          ),
        ),
      ),
    );
  }
}
