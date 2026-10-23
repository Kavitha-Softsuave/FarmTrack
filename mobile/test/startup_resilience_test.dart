import 'dart:async';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/storage/token_store.dart';

import 'support/finders.dart';
import 'support/harness.dart';

/// A phone key store that never answers.
class _HangingStore implements TokenStore {
  @override
  Future<StoredTokens?> read() => Completer<StoredTokens?>().future;

  @override
  Future<void> write(StoredTokens tokens) => Completer<void>().future;

  @override
  Future<void> clear() => Completer<void>().future;
}

class _ThrowingStore implements TokenStore {
  @override
  Future<StoredTokens?> read() async => throw StateError('keystore is broken');

  @override
  Future<void> write(StoredTokens tokens) async => throw StateError('keystore is broken');

  @override
  Future<void> clear() async => throw StateError('keystore is broken');
}

/// The plugin as it behaves on a phone whose key store fails.
class _BrokenSecureStorage extends FlutterSecureStorage {
  const _BrokenSecureStorage();

  @override
  Future<String?> read({
    required String key,
    dynamic iOptions,
    dynamic aOptions,
    dynamic lOptions,
    dynamic webOptions,
    dynamic mOptions,
    dynamic wOptions,
  }) async => throw StateError('keystore is broken');

  @override
  Future<void> write({
    required String key,
    required String? value,
    dynamic iOptions,
    dynamic aOptions,
    dynamic lOptions,
    dynamic webOptions,
    dynamic mOptions,
    dynamic wOptions,
  }) async => throw StateError('keystore is broken');

  @override
  Future<void> delete({
    required String key,
    dynamic iOptions,
    dynamic aOptions,
    dynamic lOptions,
    dynamic webOptions,
    dynamic mOptions,
    dynamic wOptions,
  }) async => throw StateError('keystore is broken');
}

void main() {
  testWidgets('a key store that never answers does not keep the app on the logo: it goes on as logged out', (
    tester,
  ) async {
    final env = await TestEnv.create(language: null, tokenStore: _HangingStore());
    await tester.pumpWidget(env.app());
    await tester.pump(const Duration(seconds: 7));
    expect(
      keyed('splash-slow'),
      findsOneWidget,
      reason: 'after a few seconds the logo screen says what it is waiting for',
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
    expect(keyed('language-hi'), findsOneWidget);
  });

  testWidgets('a key store that throws does not keep the app on the logo either', (tester) async {
    final env = await TestEnv.create(onboardingDone: true, tokenStore: _ThrowingStore());
    await tester.pumpWidget(env.app());
    await tester.pumpAndSettle();
    expect(keyed('login-username'), findsOneWidget);
  });

  test('the secure token store keeps a login in memory when the phone storage fails, and never throws', () async {
    final store = SecureTokenStore(const _BrokenSecureStorage());
    expect(await store.read(), isNull);
    await store.write(const StoredTokens(accessToken: 'a', refreshToken: 'r'));
    final back = await store.read();
    expect(back?.accessToken, 'a');
    expect(back?.refreshToken, 'r');
    await store.clear();
    expect(await store.read(), isNull);
  });
}
