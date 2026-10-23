import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'scan_flow.dart';

const _countPrompts = [
  'scan_photo_count_one',
  'scan_photo_count_two',
  'scan_photo_count_three',
  'scan_photo_count_four',
];

/// Thumbnails of the photos taken (up to four) with a red cross on each; a big plus adds one more and the big
/// green tick sends them.
class PhotoReviewScreen extends ConsumerStatefulWidget {
  const PhotoReviewScreen({super.key});

  @override
  ConsumerState<PhotoReviewScreen> createState() => _PhotoReviewScreenState();
}

class _PhotoReviewScreenState extends ConsumerState<PhotoReviewScreen> {
  final Object _owner = Object();

  List<Utterance> _script(ScanFlowState flow, int max) {
    final count = flow.photos.length;
    if (count == 0) return const []; // the screen is about to close: nothing to say
    final justAdded = ref.read(scanFlowProvider.notifier).hasUnannouncedPhoto;
    return promptList([
      if (justAdded) 'scan_photo_taken',
      _countPrompts[(count - 1).clamp(0, _countPrompts.length - 1)],
      if (count < max) 'scan_add_more' else 'scan_photo_limit',
      'scan_send',
    ]);
  }

  void _remove(int index) {
    final flow = ref.read(scanFlowProvider.notifier);
    flow.removePhotoAt(index);
    if (ref.read(scanFlowProvider).photos.isEmpty) context.go(Routes.scan);
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(scanFlowProvider);
    final max = ref.watch(appConfigProvider).maxPhotos;
    final t = ref.watch(stringsProvider);
    final script = _script(flow, max);
    // Remember what was announced, so a removal or a return to this screen does not say "photo taken" again.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) ref.read(scanFlowProvider.notifier).markAnnounced();
    });

    return VoiceScaffold(
      owner: _owner,
      script: script,
      restartKey: (flow.photos.length, flow.added),
      onBack: () => context.go(Routes.scan),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 14,
            runSpacing: 14,
            children: [
              for (var i = 0; i < flow.photos.length; i++)
                _Thumbnail(
                  key: ValueKey('photo-$i'),
                  path: flow.photos[i],
                  removeLabel: t('a11y_remove_photo'),
                  onRemove: () => _remove(i),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            t('photo_count', args: {'n': flow.photos.length, 'max': max}),
            style: Theme.of(context).textTheme.titleLarge,
          ),
        ],
      ),
      bottomRight: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          BigIconButton(
            key: const ValueKey('add-photo'),
            icon: AppIcons.plus,
            semanticLabel: t('a11y_plus'),
            color: AppColors.blue,
            size: 80,
            onPressed: flow.photos.length >= max ? null : () => context.go(Routes.scan),
          ),
          const SizedBox(width: 8),
          TickButton(
            key: const ValueKey('send-photos'),
            size: 96,
            semanticLabel: t('a11y_send'),
            onPressed: flow.photos.isEmpty ? null : () => context.go(Routes.scanUploading),
          ),
        ],
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({super.key, required this.path, required this.onRemove, required this.removeLabel});

  final String path;
  final VoidCallback onRemove;
  final String removeLabel;

  @override
  Widget build(BuildContext context) {
    final side = (MediaQuery.sizeOf(context).width - 32 - 14) / 2 - 20;
    final size = side.clamp(100.0, 150.0);
    return SizedBox(
      width: size + 20,
      height: size + 20,
      child: Stack(
        children: [
          Positioned(
            left: 0,
            bottom: 0,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: SizedBox(
                width: size,
                height: size,
                child: Image.file(
                  File(path),
                  fit: BoxFit.cover,
                  cacheWidth: 400,
                  errorBuilder: (_, _, _) => const ColoredBox(
                    color: AppColors.line,
                    child: Icon(AppIcons.leaf, size: 56, color: AppColors.inkSoft),
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            right: 0,
            top: 0,
            child: CrossButton(
              key: const ValueKey('remove-photo'),
              size: Dimens.minTouch,
              semanticLabel: removeLabel,
              onPressed: onRemove,
            ),
          ),
        ],
      ),
    );
  }
}
