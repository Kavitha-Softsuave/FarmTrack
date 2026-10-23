/// The `data` map of a push message, as the messaging plugin hands it over (`{alert_id, kind, level}`).
typedef PushData = Map<Object?, Object?>;

/// Where the phone's push token and the incoming messages come from.
///
/// The app has no push plugin yet ([NoopPushTokenSource]). To switch FCM on, implement this interface on top of
/// `firebase_messaging` (see `docs/design-notes/mobile2a.md`, section "Switching real push on"); nothing else changes.
abstract interface class PushTokenSource {
  /// The device's push token, or null while there is none (no plugin, no permission, no network).
  Future<String?> getToken();

  /// A new token after the plugin rotated it; register it again.
  Stream<String> get onTokenRefresh;

  /// A message that arrived while the app is open (the system shows no notification then).
  Stream<PushData> get onForegroundMessage;

  /// The farmer tapped a notification while the app was in the background.
  Stream<PushData> get onNotificationTap;

  /// The notification the farmer tapped to start the app from closed, if the app was started that way.
  Future<PushData?> getInitialMessage();
}

/// The default until a real plugin is added: no token, no messages.
class NoopPushTokenSource implements PushTokenSource {
  const NoopPushTokenSource();

  @override
  Future<String?> getToken() async => null;

  @override
  Stream<String> get onTokenRefresh => const Stream<String>.empty();

  @override
  Stream<PushData> get onForegroundMessage => const Stream<PushData>.empty();

  @override
  Stream<PushData> get onNotificationTap => const Stream<PushData>.empty();

  @override
  Future<PushData?> getInitialMessage() async => null;
}
