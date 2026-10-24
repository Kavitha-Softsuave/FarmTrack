import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Whether the phone has a network connection. A connection is not proof that the server is reachable, so
/// callers treat this as a hint and still try the request.
abstract interface class ConnectivityService {
  Future<bool> isOnline();

  /// Online over Wi-Fi or a cable (not mobile data): the moment for big downloads such as the voice package.
  Future<bool> isUnmetered();

  /// Emits when the phone gets on (true) or off (false) Wi-Fi or a cable.
  Stream<bool> get unmeteredChanges;

  /// Emits whenever the connection appears or disappears.
  Stream<bool> get onlineChanges;
}

class ConnectivityPlusService implements ConnectivityService {
  ConnectivityPlusService([Connectivity? connectivity]) : _connectivity = connectivity ?? Connectivity();

  final Connectivity _connectivity;

  static bool _online(List<ConnectivityResult> results) => results.any((r) => r != ConnectivityResult.none);

  @override
  Future<bool> isOnline() async {
    try {
      return _online(await _connectivity.checkConnectivity());
    } catch (_) {
      return true; // Unknown: let the request itself decide.
    }
  }

  @override
  Future<bool> isUnmetered() async {
    try {
      return _unmetered(await _connectivity.checkConnectivity());
    } catch (_) {
      return false; // Unknown: do not spend the farmer's data.
    }
  }

  static bool _unmetered(List<ConnectivityResult> results) =>
      results.contains(ConnectivityResult.wifi) || results.contains(ConnectivityResult.ethernet);

  @override
  Stream<bool> get onlineChanges => _connectivity.onConnectivityChanged.map(_online).distinct();

  @override
  Stream<bool> get unmeteredChanges => _connectivity.onConnectivityChanged.map(_unmetered).distinct();
}

/// A controllable connection for tests.
class FakeConnectivity implements ConnectivityService {
  FakeConnectivity({this._online = true, this.unmetered = true});

  bool _online;

  /// Whether the fake connection counts as Wi-Fi (default) or mobile data.
  bool unmetered;
  final StreamController<bool> _controller = StreamController<bool>.broadcast();

  final StreamController<bool> _unmeteredController = StreamController<bool>.broadcast();

  set online(bool value) {
    if (value == _online) return;
    _online = value;
    _controller.add(value);
    _unmeteredController.add(value && unmetered);
  }

  /// Simulates a switch between Wi-Fi and mobile data while online.
  void switchNetwork({required bool wifi}) {
    unmetered = wifi;
    _unmeteredController.add(_online && wifi);
  }

  @override
  Future<bool> isOnline() async => _online;

  @override
  Future<bool> isUnmetered() async => _online && unmetered;

  @override
  Stream<bool> get onlineChanges => _controller.stream;

  @override
  Stream<bool> get unmeteredChanges => _unmeteredController.stream;
}
