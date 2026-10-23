enum NotificationPermission {
  granted,
  denied,

  /// The system has not asked the farmer yet.
  notDetermined,

  /// This build cannot show notifications (no plugin): nothing is asked and nothing is spoken about it.
  unsupported,
}

/// The phone's notification permission. The default implementation reports [NotificationPermission.unsupported];
/// implement this interface with `firebase_messaging` or `permission_handler` when real push is switched on.
abstract interface class NotificationPermissionPort {
  Future<NotificationPermission> status();

  /// Shows the system dialog. Returns the farmer's answer.
  Future<NotificationPermission> request();
}

class UnsupportedNotificationPermissionPort implements NotificationPermissionPort {
  const UnsupportedNotificationPermissionPort();

  @override
  Future<NotificationPermission> status() async => NotificationPermission.unsupported;

  @override
  Future<NotificationPermission> request() async => NotificationPermission.unsupported;
}
