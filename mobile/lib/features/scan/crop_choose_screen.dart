import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'crop_picture.dart';
import 'scan_flow.dart';

/// "Tap the picture of your crop": the likely crops first, then every crop the server supports, six per page
/// with big arrows (no scrolling or swiping needed).
class CropChooseScreen extends ConsumerStatefulWidget {
  const CropChooseScreen({super.key});

  @override
  ConsumerState<CropChooseScreen> createState() => _CropChooseScreenState();
}

class _CropChooseScreenState extends ConsumerState<CropChooseScreen> {
  static const _perPage = 6;
  int _page = 0;

  List<String> _cropIds(List<String> supported) {
    final candidates = ref.read(scanFlowProvider).scan?.crop?.candidates ?? const [];
    final seen = <String>{};
    return [
      for (final id in [for (final c in candidates) c.cropId, ...supported])
        if (id.isNotEmpty && seen.add(id)) id,
    ];
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final lang = ref.watch(languageProvider);
    final resources = ref.watch(resourcesProvider);
    final supported = ref.watch(supportedCropsProvider);
    final ids = _cropIds(supported.value ?? const []);
    final pages = (ids.length / _perPage).ceil().clamp(1, 99);
    final page = _page.clamp(0, pages - 1);
    final shown = ids.skip(page * _perPage).take(_perPage).toList();

    return VoiceScaffold(
      script: promptList(const ['crop_choose_other']),
      scrollable: false,
      onBack: () => context.go(ref.read(scanFlowProvider).scan == null ? Routes.home : Routes.scanConfirm),
      bottomRight: pages <= 1
          ? null
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (page > 0)
                  BigIconButton(
                    key: const ValueKey('crops-prev'),
                    icon: AppIcons.back,
                    semanticLabel: t('a11y_prev_page'),
                    color: AppColors.card,
                    foreground: AppColors.ink,
                    size: 80,
                    onPressed: () => setState(() => _page = page - 1),
                  ),
                const SizedBox(width: 12),
                if (page < pages - 1)
                  BigIconButton(
                    key: const ValueKey('crops-next'),
                    icon: AppIcons.greenArrow,
                    semanticLabel: t('a11y_next_page'),
                    size: 80,
                    onPressed: () => setState(() => _page = page + 1),
                  ),
              ],
            ),
      body: supported.isLoading && ids.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : LayoutBuilder(
              builder: (context, constraints) {
                final rows = (shown.length / 2).ceil().clamp(1, 3);
                final tileHeight = ((constraints.maxHeight - (rows - 1) * 12) / rows).clamp(110.0, 200.0);
                return SingleChildScrollView(
                  child: Wrap(
                    alignment: WrapAlignment.center,
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      for (final id in shown)
                        SizedBox(
                          width: (constraints.maxWidth - 12) / 2,
                          height: tileHeight,
                          child: PictureTile(
                            key: ValueKey('crop-$id'),
                            semanticLabel: resources.cropName(id, lang),
                            label: resources.cropName(id, lang),
                            minHeight: 110,
                            onPressed: () => context.go(Routes.analysingFor(id)),
                            child: CropPicture(cropId: id, size: 84),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
    );
  }
}
