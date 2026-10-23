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
import 'crop_picture.dart';
import 'result_prompts.dart';
import 'scan_scope.dart';

/// "This looks like apple. Is this the right crop?" The green tick confirms, the red cross opens the crop grid.
class CropConfirmScreen extends StatelessWidget {
  const CropConfirmScreen({super.key});

  @override
  Widget build(BuildContext context) => ScanScope(builder: _content);

  Widget _content(BuildContext context, WidgetRef ref, ScanOut scan) {
    final crop = scan.crop;
    if (crop == null || !crop.isKnown) return const Redirect(to: Routes.scanCrops);
    final cropId = crop.cropId!;
    final lang = ref.watch(languageProvider);
    final resources = ref.watch(resourcesProvider);
    final catalogue = ref.watch(promptCatalogueProvider);
    final t = ref.watch(stringsProvider);
    final name = resources.cropName(cropId, lang, serverName: crop.name);

    final named = cropPrompt(cropId, catalogue);
    final ask = pickPrompt(scan.promptsFor(NextAction.confirmCrop), 'crop_confirm_prompt', catalogue);
    final script = <Utterance>[
      if (named != null) PromptUtterance(named) else TextUtterance(name, lang: lang),
      ...promptList([ask, 'crop_tap_yes', 'crop_tap_no']),
    ];

    return VoiceScaffold(
      script: script,
      onBack: () => context.go(Routes.home),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CropPicture(cropId: cropId, size: 130),
          const SizedBox(height: 10),
          Text(
            name,
            key: const ValueKey('crop-name'),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.displaySmall,
          ),
          const SizedBox(height: 4),
          Text(t('crop_is_this'), style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CrossButton(
                key: const ValueKey('crop-no'),
                size: 112,
                semanticLabel: t('a11y_no'),
                onPressed: () => context.go(Routes.scanCrops),
              ),
              const SizedBox(width: 28),
              TickButton(
                key: const ValueKey('crop-yes'),
                size: 112,
                semanticLabel: t('a11y_yes'),
                onPressed: () => context.go(Routes.analysingFor(cropId)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
