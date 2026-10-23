import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/offline/offline_status.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../offline/offline_cards.dart';
import '../scan/scan_flow.dart';

/// The four big picture buttons. Speaks `home_intro`; on the very first visit it also says what each button does.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key, this.fresh = false});

  /// Arrived straight from login: greet first.
  final bool fresh;

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  static const _tour = ['home_intro', 'home_scan', 'home_field', 'home_diary', 'home_ask', 'home_settings'];

  /// Decided once, so the speaker button keeps replaying the whole tour after it was marked as heard.
  late final bool _firstVisit = !ref.read(settingsProvider).homeTourDone;

  @override
  void initState() {
    super.initState();
    if (_firstVisit) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) ref.read(settingsProvider.notifier).markHomeTourDone();
      });
    }
  }

  void _openScan() {
    ref.read(scanFlowProvider.notifier).reset();
    context.go(Routes.scan);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final online = ref.watch(onlineProvider).value ?? true;
    final unread = ref.watch(unreadAlertsProvider).value ?? 0;
    final resultReady = ref.watch(offlineStatusProvider.select((s) => s.ready.isNotEmpty));
    final tileHeight = (MediaQuery.sizeOf(context).height * 0.27).clamp(140.0, 230.0);

    Widget tile(String key, Widget picture, String label, String semantic, VoidCallback onTap, Color border) =>
        Expanded(
          child: SizedBox(
            height: tileHeight,
            child: PictureTile(
              key: ValueKey(key),
              semanticLabel: semantic,
              label: label,
              borderColor: border,
              onPressed: onTap,
              child: picture,
            ),
          ),
        );

    const picture = 88.0;
    return VoiceScaffold(
      showBack: false,
      script: promptList([
        if (widget.fresh) 'login_ok',
        ..._firstVisit ? _tour : const ['home_intro'],
        if (resultReady) 'offline_result_ready',
      ]),
      replayScript: promptList([..._tour, if (resultReady) 'offline_result_ready']),
      topRight: [
        if (!online)
          Semantics(
            label: t('a11y_offline'),
            child: const Icon(AppIcons.offline, size: 40, color: AppColors.inkSoft),
          ),
        _TopIcon(
          key: const ValueKey('home-alerts'),
          icon: AppIcons.bell,
          semanticLabel: t('a11y_alerts'),
          badge: unread,
          onPressed: () => context.push(Routes.alerts),
        ),
        _TopIcon(
          key: const ValueKey('home-settings'),
          icon: AppIcons.gear,
          semanticLabel: t('a11y_settings'),
          onPressed: () => context.push(Routes.settings),
        ),
      ],
      body: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const OfflineCards(),
            Row(
              children: [
                tile(
                  'home-scan',
                  const Icon(AppIcons.camera, size: picture, color: AppColors.green),
                  t('home_scan_label'),
                  t('a11y_camera'),
                  _openScan,
                  AppColors.green,
                ),
                const SizedBox(width: 16),
                tile(
                  'home-field',
                  const _FieldPicture(size: picture),
                  t('home_field_label'),
                  t('home_field_label'),
                  () => context.push(Routes.field),
                  AppColors.blue,
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                tile(
                  'home-diary',
                  const Icon(AppIcons.notebook, size: picture, color: AppColors.amberDark),
                  t('home_diary_label'),
                  t('home_diary_label'),
                  () => context.push(Routes.diary),
                  AppColors.amberDark,
                ),
                const SizedBox(width: 16),
                tile(
                  'home-ask',
                  const Icon(AppIcons.question, size: picture, color: AppColors.inkSoft),
                  t('home_ask_label'),
                  t('home_ask_label'),
                  () => context.push(Routes.ask),
                  AppColors.inkSoft,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// The "My field" picture: a cloud over a patch of grass, so both "the field picture" and "the cloud picture"
/// of the voice prompts match what is on screen.
class _FieldPicture extends StatelessWidget {
  const _FieldPicture({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: size,
    height: size,
    child: Stack(
      children: [
        Positioned(
          left: 0,
          bottom: 0,
          child: Icon(AppIcons.field, size: size * 0.7, color: AppColors.green),
        ),
        Positioned(
          right: 0,
          top: 0,
          child: Icon(AppIcons.cloud, size: size * 0.75, color: AppColors.blue),
        ),
      ],
    ),
  );
}

class _TopIcon extends StatelessWidget {
  const _TopIcon({super.key, required this.icon, required this.semanticLabel, required this.onPressed, this.badge = 0});

  final IconData icon;
  final String semanticLabel;
  final VoidCallback onPressed;
  final int badge;

  @override
  Widget build(BuildContext context) {
    final button = BigIconButton(
      icon: icon,
      semanticLabel: semanticLabel,
      color: AppColors.card,
      foreground: AppColors.ink,
      size: Dimens.minTouch,
      onPressed: onPressed,
    );
    if (badge <= 0) return button;
    return Stack(
      clipBehavior: Clip.none,
      children: [
        button,
        Positioned(
          right: -2,
          top: -2,
          child: Container(
            key: const ValueKey('alert-badge'),
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
            decoration: const BoxDecoration(color: AppColors.red, shape: BoxShape.circle),
            child: Text(
              '$badge',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16),
            ),
          ),
        ),
      ],
    );
  }
}
