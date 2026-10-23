import 'dart:async';

import 'package:farmtrack/core/errors/api_exception.dart';
import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_api_client.dart';
import 'package:farmtrack/core/offline/offline_queue.dart';
import 'package:farmtrack/core/offline/persistent_offline_queue.dart' show KeyedOfflineQueue;
import 'package:farmtrack/core/push/notification_permission.dart';
import 'package:farmtrack/core/push/push_token_source.dart';

/// The phone's clock in the diary tests: noon on the demo day of the mock server (12 May 2026).
final DateTime fixedNow = DateTime(2026, 5, 12, 12);

/// An offline queue that remembers what was queued and lets a test say what happened to it.
class FakeOfflineQueue implements KeyedOfflineQueue {
  final List<({String key, SprayLogIn log})> sprayLogs = [];
  final StreamController<QueueEvent> _events = StreamController<QueueEvent>.broadcast();
  int _serial = 0;

  @override
  int get pending => sprayLogs.length;

  @override
  Stream<int> get pendingChanges => const Stream<int>.empty();

  @override
  Stream<QueueEvent> get events => _events.stream;

  @override
  Future<String> enqueueScan({
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  }) async => 'scan-key-${_serial++}';

  @override
  Future<String> enqueueSprayLog(SprayLogIn log) => enqueueSprayLogWithKey('spray-key-${_serial++}', log);

  @override
  Future<String> enqueueSprayLogWithKey(String key, SprayLogIn log) async {
    sprayLogs.add((key: key, log: log));
    return key;
  }

  @override
  Future<String> enqueueScanWithKey(
    String key, {
    required List<String> photoPaths,
    String? clientCrop,
    double? clientConfidence,
    DateTime? takenAt,
    double? lat,
    double? lon,
  }) async => key;

  @override
  Future<void> flush() async {}

  /// The queue sent [key] to the server.
  void emitSent(String key, {SprayLogOut? answer}) =>
      _events.add(QueueEvent(type: QueueEventType.sent, kind: QueueKind.sprayLog, key: key, sprayLog: answer));

  /// The server refused [key]; the queue dropped it.
  void emitDropped(String key) => _events.add(
    QueueEvent(type: QueueEventType.dropped, kind: QueueKind.sprayLog, key: key, error: const ApiException.timeout()),
  );
}

/// A push plugin stand-in: a token, and messages the test sends.
class FakePushSource implements PushTokenSource {
  FakePushSource({this.token});

  String? token;
  PushData? initial;
  final StreamController<String> refresh = StreamController<String>.broadcast();
  final StreamController<PushData> foreground = StreamController<PushData>.broadcast();
  final StreamController<PushData> taps = StreamController<PushData>.broadcast();

  @override
  Future<String?> getToken() async => token;

  @override
  Stream<String> get onTokenRefresh => refresh.stream;

  @override
  Stream<PushData> get onForegroundMessage => foreground.stream;

  @override
  Stream<PushData> get onNotificationTap => taps.stream;

  @override
  Future<PushData?> getInitialMessage() async => initial;
}

class FakePermissionPort implements NotificationPermissionPort {
  FakePermissionPort(this.current, {this.answer = NotificationPermission.granted});

  NotificationPermission current;

  /// What the system dialog returns.
  NotificationPermission answer;
  int requests = 0;
  final List<String> events = [];

  @override
  Future<NotificationPermission> status() async => current;

  @override
  Future<NotificationPermission> request() async {
    requests++;
    events.add('request');
    return current = answer;
  }
}

/// A mock server that answers `createSprayLog` with whatever the test builds.
class ScriptedSprayApi extends MockApiClient {
  ScriptedSprayApi(this.build) : super(latency: Duration.zero, scanScript: [MockScanScenario.ok]);

  final SprayLogOut Function(SprayLogIn log) build;

  @override
  Future<SprayLogOut> createSprayLog(SprayLogIn log, {String? idempotencyKey}) async {
    calls.add('createSprayLog');
    idempotencyKeys.add(idempotencyKey);
    sprayLogsIn.add(log);
    return build(log);
  }
}
