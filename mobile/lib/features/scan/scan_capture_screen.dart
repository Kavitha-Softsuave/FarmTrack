import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/voice/voice_service.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'photo_picker.dart';
import 'scan_flow.dart';

/// One huge camera button. Speaks how to hold the phone, then opens the system camera.
class ScanCaptureScreen extends ConsumerStatefulWidget {
  const ScanCaptureScreen({super.key});

  @override
  ConsumerState<ScanCaptureScreen> createState() => _ScanCaptureScreenState();
}

class _ScanCaptureScreenState extends ConsumerState<ScanCaptureScreen> {
  final Object _owner = Object();
  bool _denied = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _recoverLostPhoto());
  }

  Future<void> _say(List<String> ids) => ref.read(voiceServiceProvider).speakPrompts(ids, owner: _owner);

  Future<void> _recoverLostPhoto() async {
    final path = await ref.read(photoPickerProvider).recoverLostPhoto();
    if (path == null || !mounted) return;
    ref.read(scanFlowProvider.notifier).addPhoto(path);
    context.go(Routes.scanReview);
  }

  Future<void> _openCamera() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final settings = ref.read(settingsProvider);
      if (!settings.cameraExplained) {
        // "The phone will ask to use the camera: tap the button that allows it."
        await ref.read(settingsProvider.notifier).markCameraExplained();
        await _say(const ['camera_permission']);
      }
      final path = await ref.read(photoPickerProvider).takePhoto();
      if (!mounted) return;
      if (_denied) setState(() => _denied = false);
      if (path == null) return;
      if (ref.read(scanFlowProvider.notifier).addPhoto(path)) Haptics.success();
      if (mounted) context.go(Routes.scanReview);
    } on CameraPermissionDenied {
      Haptics.error();
      if (mounted) setState(() => _denied = true);
    } catch (_) {
      Haptics.error();
      await _say(const ['error_try_again']);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Photos that are already in the phone: the system picker, as many as still fit in this scan.
  Future<void> _openGallery() async {
    if (_busy) return;
    final flow = ref.read(scanFlowProvider.notifier);
    final room = flow.maxPhotos - ref.read(scanFlowProvider).photos.length;
    if (room <= 0) {
      await _say(const ['scan_photo_limit']);
      return;
    }
    setState(() => _busy = true);
    try {
      final paths = await ref.read(photoPickerProvider).pickFromGallery(limit: room);
      if (!mounted) return;
      if (_denied) setState(() => _denied = false);
      if (paths.isEmpty) return;
      var added = false;
      for (final path in paths) {
        added = flow.addPhoto(path) || added;
      }
      if (added) Haptics.success();
      if (mounted) context.go(Routes.scanReview);
    } catch (_) {
      Haptics.error();
      await _say(const ['error_try_again']);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      owner: _owner,
      script: promptList(
        _denied
            ? const ['permission_denied_camera']
            : const ['scan_open_camera', 'scan_or_gallery', 'scan_hold_close', 'scan_one_leaf', 'scan_daylight'],
      ),
      restartKey: _denied,
      onBack: () => context.go(ref.read(scanFlowProvider).photos.isEmpty ? Routes.home : Routes.scanReview),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_denied) ...[
            const Icon(Icons.no_photography_rounded, size: 72, color: AppColors.red, key: ValueKey('camera-denied')),
            const SizedBox(height: 16),
          ],
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                BigIconButton(
                  key: const ValueKey('camera-button'),
                  icon: AppIcons.camera,
                  semanticLabel: t('a11y_camera'),
                  size: 152,
                  onPressed: _busy ? null : _openCamera,
                ),
                const SizedBox(width: 20),
                BigIconButton(
                  key: const ValueKey('gallery-button'),
                  icon: AppIcons.gallery,
                  semanticLabel: t('a11y_gallery'),
                  size: 112,
                  color: AppColors.card,
                  foreground: AppColors.ink,
                  onPressed: _busy ? null : _openGallery,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
