import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../../core/theme/app_theme.dart';
import 'scan_flow.dart';

/// Sends the photos (or the confirmed crop) and waits for the server's answer, then routes by its status.
///
/// With [confirmCropId] null it uploads the photos; otherwise it posts the crop the farmer ticked or chose.
class ProcessingScreen extends ConsumerStatefulWidget {
  const ProcessingScreen({super.key, this.confirmCropId});

  final String? confirmCropId;

  @override
  ConsumerState<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends ConsumerState<ProcessingScreen> {
  bool _started = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _run());
  }

  Future<void> _run() async {
    if (!mounted) return;
    _started = true;
    final flow = ref.read(scanFlowProvider.notifier);
    final cropId = widget.confirmCropId;
    final current = ref.read(scanFlowProvider);
    if (cropId == null ? current.photos.isEmpty : current.scan == null) {
      // Opened without anything to send (for example after the app restarted): start from the beginning.
      context.go(cropId == null ? Routes.scan : Routes.home);
      return;
    }
    final scan = cropId == null ? await flow.submit() : await flow.confirmCrop(cropId);
    if (!mounted) return;
    if (scan == null) {
      if (ref.read(scanFlowProvider).phase == ScanPhase.queued) {
        // No internet: the photos are saved in the offline queue and will be sent later.
        Haptics.success();
        context.go(Routes.scanSaved);
        return;
      }
      // Failed or cancelled: the build method shows the error screen or the cancel already navigated.
      Haptics.error();
      return;
    }
    Haptics.success();
    context.go(routeForScan(scan));
  }

  void _cancel() {
    ref.read(scanFlowProvider.notifier).cancel();
    context.go(widget.confirmCropId == null ? Routes.scanReview : Routes.scanConfirm);
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(scanFlowProvider);
    final t = ref.watch(stringsProvider);
    final uploading = widget.confirmCropId == null;

    if (_started && flow.phase == ScanPhase.failed && flow.error != null) {
      return ErrorRetryScreen(error: flow.error!, onRetry: _run, onBack: _cancel);
    }
    return VoiceScaffold(
      showBack: false,
      onBack: _cancel,
      script: promptList(uploading ? const ['scan_uploading', 'scan_wait'] : const ['scan_wait']),
      body: ProcessingBody(
        icon: uploading && flow.phase != ScanPhase.analysing ? AppIcons.camera : AppIcons.leaf,
        label: t(uploading && flow.phase != ScanPhase.analysing ? 'uploading' : 'analysing'),
        progress: uploading && flow.phase == ScanPhase.uploading && flow.progress > 0 ? flow.progress : null,
        onCancel: _cancel,
        cancelLabel: t('a11y_cancel'),
      ),
    );
  }
}
