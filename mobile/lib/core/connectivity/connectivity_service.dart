import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Whether the phone has a network connection. A connection is not proof that the server is reachable, so
/// callers treat this as a hint and still try the request.
abstract interface class ConnectivityService {
  Future<bool> isOnline();

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
  Stream<bool> get onlineChanges => _connectivity.onConnectivityChanged.map(_online).distinct();
}

/// A controllable connection for tests.
class FakeConnectivity implements ConnectivityService {
  FakeConnectivity({this._online = true});

  bool _online;
  final StreamController<bool> _controller = StreamController<bool>.broadcast();

  set online(bool value) {
    if (value == _online) return;
    _online = value;
    _controller.add(value);
  }

  @override
  Future<bool> isOnline() async => _online;

  @override
  Stream<bool> get onlineChanges => _controller.stream;
}
