import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../errors/api_exception.dart';
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
  ref.watch(onlineProvider.select((online) => online.value ?? true));
  try {
    final meta = await ref.watch(apiClientProvider).meta();
    final clock = meta.demoClock;
    if (clock == null) return null;
    if (ref.watch(releaseBuildProvider) && meta.env == 'prod') return null;
    return clock;
  } on ApiException {
    return null;
  }
});

/// "12 May 2026" (or the Hindi month name) for the demo clock, in Indian time. Only ever shown, never spoken.
String formatDemoDate(DateTime clock, List<String> monthNames) {
  final ist = clock.toUtc().add(const Duration(hours: 5, minutes: 30));
  final month = ist.month >= 1 && ist.month <= monthNames.length ? monthNames[ist.month - 1] : '${ist.month}';
  return '${ist.day} $month ${ist.year}';
}

/// A thin, high-contrast strip at the top of every screen while the server runs on a demo clock: "Demo date: 12 May
/// 2026". It is text only (the voice never reads it) and does not exist in a release build against production.
class DemoClockBanner extends ConsumerWidget {
  const DemoClockBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clock = ref.watch(demoClockProvider).value;
    if (clock == null) return const SizedBox.shrink();
    final t = ref.watch(stringsProvider);
    final months = t('demo_month_words').split(',');
    final text = t('demo_banner', args: {'date': formatDemoDate(clock, months)});
    return Semantics(
      container: true,
      label: text,
      excludeSemantics: true,
      child: Container(
        key: const ValueKey('demo-banner'),
        width: double.infinity,
        color: AppColors.ink,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            text,
            maxLines: 1,
            style: const TextStyle(color: AppColors.amber, fontSize: 15, fontWeight: FontWeight.w800, height: 1.2),
          ),
        ),
      ),
    );
  }
}
