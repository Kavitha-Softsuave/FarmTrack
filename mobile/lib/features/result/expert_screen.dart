import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/errors/api_exception.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/redirect.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../scan/result_prompts.dart';
import '../scan/scan_flow.dart';
import '../scan/scan_scope.dart';
import 'advice_widgets.dart';

/// `needs_expert`, `no_approved_data` and `not_a_disease`: says so plainly, adds the server's own spoken text and
/// offers one button that asks a farm expert (POST /v1/expert-requests).
class ExpertScreen extends ConsumerStatefulWidget {
  const ExpertScreen({super.key});

  @override
  ConsumerState<ExpertScreen> createState() => _ExpertScreenState();
}

class _ExpertScreenState extends ConsumerState<ExpertScreen> {
  final Object _owner = Object();
  bool _sending = false;
  bool _sent = false;

  static const _variantPrompt = {
    ScanStatus.needsExpert: 'result_expert',
    ScanStatus.noApprovedData: 'result_no_data',
    ScanStatus.notADisease: 'result_not_disease',
  };

  Future<void> _askExpert(ScanOut scan) async {
    if (_sending || _sent) return;
    final voice = ref.read(voiceServiceProvider);
    setState(() => _sending = true);
    try {
      await ref.read(apiClientProvider).createExpertRequest(ExpertRequestIn(scanId: scan.id));
      Haptics.success();
      if (mounted) setState(() => _sent = true);
      // "Done. Your photos are saved." (the case is kept in the database; nobody calls back, owner decision)
      await voice.speak(promptList(const ['expert_photos_saved']), owner: _owner);
    } on ApiException catch (e) {
      Haptics.error();
      await voice.speak(promptList([errorPromptFor(e)]), owner: _owner);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) => ScanScope(builder: _content);

  Widget _content(BuildContext context, WidgetRef ref, ScanOut scan) {
    if (!_variantPrompt.containsKey(scan.status)) return const Redirect(to: Routes.home);

    final lang = ref.watch(languageProvider);
    final catalogue = ref.watch(promptCatalogueProvider);
    final t = ref.watch(stringsProvider);
    final fallback = _variantPrompt[scan.status]!;
    final stepAction = scan.status == ScanStatus.notADisease ? NextAction.addPhoto : NextAction.askExpert;
    // "No disease seen" always opens with its own fixed sentence: the server's step prompt for it is the add-photo
    // question ("take one more photo?"), which would come before the finding.
    final variant = scan.status == ScanStatus.notADisease
        ? fallback
        : pickPrompt(scan.promptsFor(stepAction), fallback, catalogue);

    final (icon, color, labelKey) = switch (scan.status) {
      ScanStatus.needsExpert => (AppIcons.expert, AppColors.amberDark, 'expert_variant_expert'),
      ScanStatus.noApprovedData => (AppIcons.info, AppColors.blue, 'expert_variant_no_data'),
      _ => (AppIcons.noDisease, AppColors.inkSoft, 'expert_variant_not_disease'),
    };
    final advice = scan.advice;
    final script = <Utterance>[PromptUtterance(variant), ?scan.spoken.toUtterance(lang)];

    return VoiceScaffold(
      owner: _owner,
      script: script,
      onBack: () => context.go(Routes.home),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Icon(icon, size: 96, color: color, key: ValueKey('expert-icon-${scan.status.wire}')),
          const SizedBox(height: 8),
          Text(t(labelKey), textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineMedium),
          if (advice != null) ...[const SizedBox(height: 16), AdviceCards(advice: advice)],
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              BigIconButton(
                key: const ValueKey('expert-camera'),
                icon: AppIcons.camera,
                semanticLabel: t('a11y_camera'),
                size: Dimens.minTouch + 8,
                onPressed: () {
                  ref.read(scanFlowProvider.notifier).reset();
                  context.go(Routes.scan);
                },
              ),
              const SizedBox(width: 20),
              BigIconButton(
                key: const ValueKey('expert-home'),
                icon: AppIcons.house,
                semanticLabel: t('a11y_home'),
                color: AppColors.card,
                foreground: AppColors.ink,
                size: Dimens.minTouch + 8,
                onPressed: () => context.go(Routes.home),
              ),
            ],
          ),
        ],
      ),
      bottomRight: _sent
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  key: const ValueKey('expert-sent'),
                  width: 96,
                  height: 96,
                  decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
                  child: const Icon(AppIcons.tick, size: 56, color: Colors.white),
                ),
                SizedBox(
                  width: 128,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(t('expert_sent'), style: Theme.of(context).textTheme.labelLarge),
                  ),
                ),
              ],
            )
          : BigIconButton(
              key: const ValueKey('ask-expert'),
              icon: AppIcons.expert,
              color: AppColors.blue,
              size: 104,
              semanticLabel: t('a11y_expert'),
              onPressed: _sending ? null : () => _askExpert(scan),
            ),
    );
  }
}
