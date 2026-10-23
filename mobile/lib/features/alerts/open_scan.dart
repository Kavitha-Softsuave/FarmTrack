import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/router/routes.dart';
import '../scan/scan_flow.dart';

/// The result screen for a scan the farmer did earlier (an alert is about it), or null when the scan has no result
/// to show (still waiting for the crop tick, or the photo was unusable).
String? resultRouteFor(ScanOut scan) => switch (scan.status) {
  ScanStatus.ok => Routes.scanAdvice,
  ScanStatus.needsExpert || ScanStatus.noApprovedData || ScanStatus.notADisease => Routes.scanExpert,
  ScanStatus.confirmCrop || ScanStatus.photoUnusable => null,
};

/// Puts [scan] where the advice and expert screens look for it (the scan flow), so they show it exactly like a
/// scan that was just done: the same cards, the same speech, and the "I sprayed" button with this advice.
void showScanResult(WidgetRef ref, ScanOut scan) => ref.read(scanFlowProvider.notifier).showResult(scan);
