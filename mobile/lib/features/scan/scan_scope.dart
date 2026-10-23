import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/router/routes.dart';
import '../../core/widgets/redirect.dart';
import 'scan_flow.dart';

/// Builds a result screen from the scan the farmer is looking at.
///
/// It remembers the last scan it saw: starting a new scan clears the flow before the old screen has left the
/// stage, and the old screen must not jump to Home because of that. With no scan at all (the app was restarted
/// on a result route) it sends the farmer Home.
class ScanScope extends ConsumerStatefulWidget {
  const ScanScope({super.key, required this.builder});

  /// [ref] belongs to this widget, so `ref.watch` inside [builder] is valid.
  final Widget Function(BuildContext context, WidgetRef ref, ScanOut scan) builder;

  @override
  ConsumerState<ScanScope> createState() => _ScanScopeState();
}

class _ScanScopeState extends ConsumerState<ScanScope> {
  ScanOut? _last;

  @override
  Widget build(BuildContext context) {
    final current = ref.watch(scanFlowProvider.select((s) => s.scan));
    if (current != null) _last = current;
    final scan = _last;
    if (scan == null) return const Redirect(to: Routes.home);
    return widget.builder(context, ref, scan);
  }
}
