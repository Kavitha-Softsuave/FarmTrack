import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/redirect.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../scan/crop_picture.dart';
import '../scan/result_prompts.dart';
import '../scan/scan_scope.dart';
import 'advice_widgets.dart';

/// The result for an `ok` scan: severity band, medicines with dose sentences, timing, warnings and steps.
/// It says `result_intro`, then the advice's spoken version; the speaker button plays it again and the
/// notebook button opens the spray diary with this advice preselected.
class AdviceScreen extends StatelessWidget {
  const AdviceScreen({super.key});

  @override
  Widget build(BuildContext context) => ScanScope(builder: _content);

  Widget _content(BuildContext context, WidgetRef ref, ScanOut scan) {
    final advice = scan.advice;
    if (advice == null) return const Redirect(to: Routes.home);

    final lang = ref.watch(languageProvider);
    final resources = ref.watch(resourcesProvider);
    final catalogue = ref.watch(promptCatalogueProvider);
    final t = ref.watch(stringsProvider);
    final cropId = advice.cropId.isNotEmpty ? advice.cropId : (scan.crop?.cropId ?? '');
    final cropName = resources.cropName(cropId, lang, serverName: scan.crop?.name);

    final spoken = (advice.spoken.isEmpty ? scan.spoken : advice.spoken).toUtterance(lang);
    final next = pickPrompt(scan.promptsFor(NextAction.markSprayed), 'result_next_diary', catalogue);
    final script = <Utterance>[const PromptUtterance('result_intro'), ?spoken, PromptUtterance(next)];

    return VoiceScaffold(
      script: script,
      onBack: () => context.go(Routes.home),
      // The crop the advice is for stays visible next to the back arrow, so a wrong crop is noticed.
      topRight: [
        if (cropId.isNotEmpty)
          Row(
            key: const ValueKey('advice-crop'),
            mainAxisSize: MainAxisSize.min,
            children: [
              CropPicture(cropId: cropId, size: 48),
              const SizedBox(width: 8),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 150),
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(cropName, style: Theme.of(context).textTheme.titleLarge),
                ),
              ),
            ],
          ),
      ],
      body: Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: AdviceCards(advice: advice),
      ),
      bottomRight: BigIconButton(
        key: const ValueKey('i-sprayed'),
        icon: AppIcons.notebook,
        color: AppColors.amber,
        foreground: AppColors.ink,
        size: 104,
        label: t('a11y_sprayed'),
        semanticLabel: t('a11y_sprayed'),
        onPressed: () => context.push(
          Routes.diaryFor(
            adviceId: advice.id,
            cropId: cropId.isEmpty ? null : cropId,
            productId: advice.products.isEmpty ? null : advice.products.first.productId,
          ),
        ),
      ),
    );
  }
}
