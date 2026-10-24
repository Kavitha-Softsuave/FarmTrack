import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/redirect.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../scan/crop_picture.dart';
import '../diary/diary_providers.dart';
import '../scan/scan_scope.dart';
import 'advice_widgets.dart';

/// The result for an `ok` scan: severity band, medicines with dose sentences, timing, warnings and steps.
/// It says `result_intro`, then the advice's spoken version and "if you have sprayed, tap the green tick". The green
/// tick opens the spray diary's confirm screen for this advice; once the spray is written the tick is replaced by a
/// green "sprayed" mark (grey "waiting" while the entry still waits for the internet).
class AdviceScreen extends StatelessWidget {
  const AdviceScreen({super.key});

  @override
  Widget build(BuildContext context) => ScanScope(builder: _content);

  Widget _content(BuildContext context, WidgetRef ref, ScanOut scan) {
    final advice = scan.advice;
    if (advice == null) return const Redirect(to: Routes.home);

    final lang = ref.watch(languageProvider);
    final resources = ref.watch(resourcesProvider);
    final t = ref.watch(stringsProvider);
    final cropId = advice.cropId.isNotEmpty ? advice.cropId : (scan.crop?.cropId ?? '');
    final cropName = resources.cropName(cropId, lang, serverName: scan.crop?.name);

    final spoken = (advice.spoken.isEmpty ? scan.spoken : advice.spoken).toUtterance(lang);
    final sprayed = ref.watch(sprayStateProvider(advice.id));
    // The sentence names the green tick, so the button that opens the diary is the green tick. The app picks the
    // sentence itself (whatever prompt the server names for this step, the picture on the button is the app's).
    final script = <Utterance>[
      const PromptUtterance('result_intro'),
      ?spoken,
      if (sprayed == SprayState.none) const PromptUtterance('diary_tick_sprayed'),
    ];

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
      bottomRight: switch (sprayed) {
        SprayState.none => TickButton(
          key: const ValueKey('i-sprayed'),
          size: 88,
          semanticLabel: t('a11y_sprayed'),
          onPressed: () => context.push(
            Routes.diaryFor(
              adviceId: advice.id,
              cropId: cropId.isEmpty ? null : cropId,
              productId: advice.products.isEmpty ? null : advice.products.first.productId,
            ),
          ),
        ),
        SprayState.waiting => SprayStatusChip(waiting: true, label: t('diary_waiting_label')),
        SprayState.done => SprayStatusChip(waiting: false, label: t('advice_sprayed_done')),
      },
    );
  }
}
