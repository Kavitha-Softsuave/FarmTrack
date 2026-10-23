import 'dart:async';

import 'package:flutter/services.dart';

/// Vibration feedback: a short tick on success, a longer buzz on errors. Fire and forget; never throws.
class Haptics {
  const Haptics._();

  static void success() => _run(HapticFeedback.mediumImpact);

  static void error() => _run(HapticFeedback.heavyImpact);

  static void tap() => _run(HapticFeedback.selectionClick);

  static void _run(Future<void> Function() feedback) {
    unawaited(() async {
      try {
        await feedback();
      } catch (_) {
        // Phones without a vibration motor ignore it.
      }
    }());
  }
}
