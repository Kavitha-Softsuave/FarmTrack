import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/app_theme.dart';

/// Crop pictures that exist as assets (`assets/crops/<crop_id>.png`). Add a file there and it is used.
final cropImageAssetsProvider = FutureProvider<Set<String>>((ref) async {
  try {
    final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
    return manifest.listAssets().where((a) => a.startsWith('assets/crops/') && !a.endsWith('.gitkeep')).toSet();
  } catch (_) {
    return const {};
  }
});

/// A round picture of a crop. Until real crop illustrations are added to `assets/crops/`, each crop shows the
/// generic picture of its group (tree for fruit, leaf for vegetables, grass for cereals). Always blue (information):
/// green, red and yellow are kept for done, stop and warning.
class CropPicture extends ConsumerWidget {
  const CropPicture({super.key, required this.cropId, this.size = 120});

  final String cropId;
  final double size;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final group = ref.watch(resourcesProvider).cropGroup(cropId);
    final assets = ref.watch(cropImageAssetsProvider).value ?? const <String>{};
    final path = 'assets/crops/${cropId.toLowerCase()}.png';
    final icon = switch (group) {
      'vegetable' => AppIcons.leaf,
      'cereal' => AppIcons.grass,
      _ => AppIcons.tree,
    };
    const color = AppColors.blue;
    const soft = AppColors.blueSoft;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: soft,
        shape: BoxShape.circle,
        border: Border.all(color: color, width: 3),
      ),
      clipBehavior: Clip.antiAlias,
      child: assets.contains(path) ? Image.asset(path, fit: BoxFit.cover) : Icon(icon, size: size * 0.55, color: color),
    );
  }
}
