import 'dart:async';

import '../models/models.dart';
import '../router/routes.dart';
import '../voice/utterance.dart';
import 'notification_permission.dart';
import 'push_token_source.dart';

/// What a push message says: which alert was sent. Every field is optional because the data is not under our control.
class PushTap {
  const PushTap({this.alertId, this.kind = '', this.level = Severity.yellow});

  /// Reads `{alert_id, kind, level}`; anything else is ignored.
  factory PushTap.fromData(PushData data) {
    String? text(String key) {
      final v = data[key];
      return v is String && v.trim().isNotEmpty ? v.trim() : null;
    }

    return PushTap(alertId: text('alert_id'), kind: text('kind') ?? '', level: Severity.parse(text('level')));
  }

  final String? alertId;
  final String kind;
  final Severity level;

  /// The screen this message leads to: that alert, or the alert list when the message names none.
  String get location => alertId == null ? Routes.alerts : Routes.alertDetailFor(alertId!);
}

/// Push for the app: registers the device with the server, asks the notification permission with spoken
/// explanations, and turns an incoming message into speech or navigation.
///
/// Plain Dart with injected functions, so it is tested with fakes. The plugin side is [PushTokenSource] and
/// [NotificationPermissionPort] (both are no-ops until a real plugin is added).
class PushService {
  PushService({
    required this.tokens,
    required this.permission,
    required this.registerDevice,
    required this.speak,
    required this.isLoggedIn,
    required this.wasPermissionAsked,
    required this.markPermissionAsked,
    required this.platform,
    this.appVersion,
    this.onAlertArrived,
  });

  final PushTokenSource tokens;
  final NotificationPermissionPort permission;
  final Future<void> Function(DeviceIn device) registerDevice;

  /// Speaks after whatever is being said now (it must not cut off the screen's own speech).
  final Future<void> Function(List<Utterance> items) speak;
  final bool Function() isLoggedIn;
  final bool Function() wasPermissionAsked;
  final Future<void> Function() markPermissionAsked;

  /// `android` or `ios`.
  final String platform;
  final String? appVersion;

  /// A message arrived while the app is open: refresh the alert badge and list.
  final void Function()? onAlertArrived;

  void Function(String location)? _navigate;
  String? _pendingLocation;
  String? _registeredToken;
  Future<bool>? _registering;
  bool _started = false;
  final List<StreamSubscription<Object?>> _subscriptions = [];

  /// Where taps on a message go (the app's router). Anything that arrived before is delivered now.
  void attachNavigator(void Function(String location) navigate) {
    _navigate = navigate;
    _deliverPending();
  }

  /// Starts listening to the token source. Safe to call again.
  Future<void> start() async {
    if (_started) return;
    _started = true;
    _subscriptions
      ..add(tokens.onTokenRefresh.listen((_) => unawaited(_registerQuietly(force: true))))
      ..add(tokens.onForegroundMessage.listen(handleForegroundMessage))
      ..add(tokens.onNotificationTap.listen(handleNotificationTap));
    try {
      final initial = await tokens.getInitialMessage();
      if (initial != null) handleNotificationTap(initial);
    } on Exception {
      // The app simply starts normally.
    }
    await _registerQuietly();
  }

  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
    _subscriptions.clear();
  }

  /// The farmer logged in: this phone now belongs to them, so register it again, and open the alert a notification
  /// was waiting to show.
  Future<void> onLoggedIn() async {
    _registeredToken = null;
    await _registerQuietly();
    _deliverPending();
  }

  /// The farmer logged out. Nothing can be sent without a login, so only forget what was registered: the next login
  /// (maybe another farmer on the same phone) registers the token again and the server moves it.
  void onLoggedOut() {
    _registeredToken = null;
  }

  /// Registers the device when there is a token. True when the server has the current token.
  Future<bool> syncRegistration({bool force = false}) {
    final running = _registering;
    if (running != null) return running;
    final run = _register(force: force);
    _registering = run;
    return run.whenComplete(() {
      _registering = null;
    });
  }

  Future<void> _registerQuietly({bool force = false}) async {
    try {
      await syncRegistration(force: force);
    } on Object {
      // Best effort: the next login, resume or token change tries again.
    }
  }

  Future<bool> _register({required bool force}) async {
    if (!isLoggedIn()) return false;
    final token = await tokens.getToken();
    if (token == null || token.isEmpty) return false;
    if (!force && token == _registeredToken) return true;
    try {
      await registerDevice(DeviceIn(platform: platform, pushToken: token, appVersion: appVersion));
    } on Exception {
      return false;
    }
    _registeredToken = token;
    return true;
  }

  /// Asks the notification permission once, with the voice prompts. Does nothing when this build cannot show
  /// notifications or the farmer already answered. Returns the permission after the question.
  Future<NotificationPermission> ensurePermission() async {
    var status = await permission.status();
    if (status == NotificationPermission.unsupported) return status;
    if (status == NotificationPermission.granted) {
      await _registerQuietly();
      return status;
    }
    if (wasPermissionAsked()) return status;
    if (status == NotificationPermission.notDetermined) {
      // The prompt is spoken to the end first: the system dialog covers the screen.
      await speak(promptList(const ['notification_permission']));
      status = await permission.request();
    }
    await markPermissionAsked();
    if (status == NotificationPermission.denied) {
      await speak(promptList(const ['permission_denied_notifications']));
    } else if (status == NotificationPermission.granted) {
      await _registerQuietly();
    }
    return status;
  }

  /// The farmer tapped a notification (or the app was started by one): open its alert.
  void handleNotificationTap(PushData data) {
    _pendingLocation = PushTap.fromData(data).location;
    _deliverPending();
  }

  /// A message arrived while the app is open: say so and refresh the badge.
  void handleForegroundMessage(PushData data) {
    if (!isLoggedIn()) return;
    unawaited(speak(promptList(const ['alert_new', 'alert_open'])));
    onAlertArrived?.call();
  }

  void _deliverPending() {
    final location = _pendingLocation;
    final navigate = _navigate;
    // Waits for a login (the router would throw the farmer to the login screen and forget the target) and a router.
    if (location == null || navigate == null || !isLoggedIn()) return;
    _pendingLocation = null;
    navigate(location);
  }
}
