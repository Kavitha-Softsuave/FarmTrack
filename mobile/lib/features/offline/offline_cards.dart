import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/api_exception.dart';
import '../../core/offline/offline_status.dart';
import '../../core/providers.dart';
import '../../core/utils/haptics.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/speak_on_enter.dart';
import '../../core/voice/voice_service.dart';
import '../../core/widgets/status_views.dart';
import '../scan/scan_flow.dart';

/// The cards at the top of Home about the offline queue: a green "Result ready: tap to see" card for a saved photo
/// that was sent, and a "Waiting to send: N" card while items still wait for the internet. Nothing shows otherwise.
class OfflineCards extends ConsumerStatefulWidget {
  const OfflineCards({super.key});

  @override
  ConsumerState<OfflineCards> createState() => _OfflineCardsState();
}

class _OfflineCardsState extends ConsumerState<OfflineCards> {
  bool _opening = false;

  Future<void> _openResult(ReadyResult result) async {
    if (_opening) return;
    final notifier = ref.read(offlineStatusProvider.notifier);
    final voice = ref.read(voiceServiceProvider);
    final owner = VoiceSession.maybeOf(context)?.owner;
    setState(() => _opening = true);
    try {
      final scan = await notifier.open(result);
      if (!mounted) return;
      ref.read(scanFlowProvider.notifier).showResult(scan);
      notifier.dismiss(result.scanId);
      Haptics.success();
      context.go(routeForScan(scan));
    } on ApiException catch (e) {
      Haptics.error();
      // A result the server does not know any more can never be opened: take the card away.
      if (e.kind == ApiErrorKind.client) notifier.dismiss(result.scanId);
      await voice.speakPrompts([errorPromptFor(e)], owner: owner);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  void _speakWaiting() {
    final owner = VoiceSession.maybeOf(context)?.owner;
    unawaited(ref.read(voiceServiceProvider).speakPrompts(const ['offline_waiting'], owner: owner));
  }

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(offlineStatusProvider);
    final t = ref.watch(stringsProvider);
    if (status.ready.isEmpty && status.pending == 0) return const SizedBox.shrink();
    final text = Theme.of(context).textTheme.titleMedium;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (status.ready.isNotEmpty)
          _Card(
            key: const ValueKey('offline-result-card'),
            label: t('offline_result_card'),
            background: AppColors.greenSoft,
            border: AppColors.green,
            icon: const Icon(Icons.check_circle_rounded, size: 44, color: AppColors.green),
            badge: status.ready.length > 1 ? status.ready.length : 0,
            style: text,
            onTap: _opening ? null : () => _openResult(status.ready.first),
          ),
        if (status.pending > 0)
          _Card(
            key: const ValueKey('offline-waiting-card'),
            label: t('offline_waiting_card', args: {'n': status.pending}),
            background: AppColors.amberSoft,
            border: AppColors.amberDark,
            icon: const Icon(Icons.cloud_upload_rounded, size: 44, color: AppColors.inkSoft),
            style: text,
            onTap: _speakWaiting,
          ),
      ],
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({
    super.key,
    required this.label,
    required this.background,
    required this.border,
    required this.icon,
    required this.style,
    required this.onTap,
    this.badge = 0,
  });

  final String label;
  final Color background;
  final Color border;
  final Widget icon;
  final TextStyle? style;
  final VoidCallback? onTap;
  final int badge;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: background,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Dimens.radius),
          side: BorderSide(color: border, width: 3),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(Dimens.radius),
          onTap: onTap == null
              ? null
              : () {
                  Haptics.tap();
                  onTap!();
                },
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: Dimens.minTouch),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                children: [
                  icon,
                  const SizedBox(width: 12),
                  Expanded(child: Text(label, style: style)),
                  if (badge > 0)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
                      child: Text(
                        '$badge',
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 18),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
