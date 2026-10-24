import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// The two tokens of a login. Refresh tokens rotate: a new pair replaces the old one at every refresh.
class StoredTokens {
  const StoredTokens({required this.accessToken, required this.refreshToken});

  final String accessToken;
  final String refreshToken;
}

/// Where the login lives on the phone. Implementations never keep the password (the app never stores it).
abstract interface class TokenStore {
  /// The saved tokens, or null when nobody is logged in.
  Future<StoredTokens?> read();

  Future<void> write(StoredTokens tokens);

  Future<void> clear();
}

/// Keeps the tokens in memory only. For tests and for a phone whose key store cannot be used.
class InMemoryTokenStore implements TokenStore {
  InMemoryTokenStore([this._tokens]);

  StoredTokens? _tokens;

  @override
  Future<StoredTokens?> read() async => _tokens;

  @override
  Future<void> write(StoredTokens tokens) async => _tokens = tokens;

  @override
  Future<void> clear() async => _tokens = null;
}

/// Android Keystore / iOS Keychain through `flutter_secure_storage`.
///
/// Some phones (old Android builds, a broken key store after a restore) throw from the plugin. That must never stop
/// the app: the login is then kept in memory for this run, and the store never throws.
class SecureTokenStore implements TokenStore {
  SecureTokenStore([FlutterSecureStorage? storage]) : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _storage;

  /// What this run knows when the phone's storage does not work (and a copy of what it holds when it does).
  StoredTokens? _memory;
  bool _storageFailed = false;

  @override
  Future<StoredTokens?> read() async {
    if (!_storageFailed) {
      try {
        final access = await _storage.read(key: _accessKey);
        final refresh = await _storage.read(key: _refreshKey);
        if (access != null && refresh != null && access.isNotEmpty && refresh.isNotEmpty) {
          return _memory = StoredTokens(accessToken: access, refreshToken: refresh);
        }
        return null;
      } on Object catch (e) {
        _storageFailed = true;
        debugPrint('token store: phone storage failed (${e.runtimeType}); keeping the login in memory');
      }
    }
    return _memory;
  }

  @override
  Future<void> write(StoredTokens tokens) async {
    _memory = tokens;
    if (_storageFailed) return;
    try {
      await _storage.write(key: _accessKey, value: tokens.accessToken);
      await _storage.write(key: _refreshKey, value: tokens.refreshToken);
    } on Object catch (e) {
      _storageFailed = true;
      debugPrint('token store: phone storage failed (${e.runtimeType}); keeping the login in memory');
    }
  }

  @override
  Future<void> clear() async {
    _memory = null;
    if (_storageFailed) return;
    try {
      await _storage.delete(key: _accessKey);
      await _storage.delete(key: _refreshKey);
    } on Object catch (e) {
      _storageFailed = true;
      debugPrint('token store: phone storage failed (${e.runtimeType})');
    }
  }
}
