import 'dart:async';

/// Time as the offline queue sees it: the current moment (age limit) and a one-shot timer (retry back-off).
/// Tests replace it with a clock they can move by hand.
abstract interface class QueueClock {
  DateTime now();

  /// Runs [callback] once after [delay]. Cancel the returned timer to stop it.
  Timer schedule(Duration delay, void Function() callback);
}

class SystemQueueClock implements QueueClock {
  const SystemQueueClock();

  @override
  DateTime now() => DateTime.now();

  @override
  Timer schedule(Duration delay, void Function() callback) => Timer(delay, callback);
}
