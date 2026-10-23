import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/config/app_config.dart';
import 'package:farmtrack/core/providers.dart';

import 'support/finders.dart';
import 'support/harness.dart';

void main() {
  const realServer = AppConfig(apiBaseUrl: 'http://10.0.2.2:8000', useMockApi: false, mockLatency: Duration.zero);

  testWidgets('with the demo mock there is no server link on the login screen', (tester) async {
    final env = await TestEnv.create(onboardingDone: true);
    await pumpApp(tester, env);
    expect(keyed('login-username'), findsOneWidget);
    expect(keyed('server-link'), findsNothing);
  });

  testWidgets('against a real server the link shows the address; a typed address is kept and used', (tester) async {
    final env = await TestEnv.create(onboardingDone: true, config: realServer);
    final container = await pumpApp(tester, env);
    expect(find.textContaining('http://10.0.2.2:8000'), findsOneWidget);

    await tapKey(tester, 'server-link');
    await tester.enterText(keyed('server-field'), 'http://192.168.1.5:8000/');
    await tapKey(tester, 'server-save');
    expect(container.read(apiBaseUrlProvider), 'http://192.168.1.5:8000');
    expect(env.prefs.getString(serverOverrideKey), 'http://192.168.1.5:8000');
    expect(find.textContaining('http://192.168.1.5:8000'), findsOneWidget);
  });

  testWidgets('an address that is not http(s)://host is refused and nothing is saved', (tester) async {
    final env = await TestEnv.create(onboardingDone: true, config: realServer);
    final container = await pumpApp(tester, env);
    await tapKey(tester, 'server-link');
    await tester.enterText(keyed('server-field'), '192.168.1.5');
    await tapKey(tester, 'server-save');
    expect(keyed('server-field'), findsOneWidget, reason: 'the dialog stays open');
    expect(env.prefs.getString(serverOverrideKey), isNull);
    expect(container.read(apiBaseUrlProvider), 'http://10.0.2.2:8000');
  });

  testWidgets('reset goes back to the build setting', (tester) async {
    final env = await TestEnv.create(onboardingDone: true, config: realServer);
    final container = await pumpApp(tester, env);
    await tapKey(tester, 'server-link');
    await tester.enterText(keyed('server-field'), 'https://farm.example.org');
    await tapKey(tester, 'server-save');
    expect(container.read(apiBaseUrlProvider), 'https://farm.example.org');
    await tapKey(tester, 'server-link');
    await tapKey(tester, 'server-reset');
    expect(container.read(apiBaseUrlProvider), 'http://10.0.2.2:8000');
    expect(env.prefs.getString(serverOverrideKey), isNull);
  });

  testWidgets('Settings: with the demo mock there is no Server row', (tester) async {
    useSmallPhone(tester);
    final mock = await TestEnv.create(loggedIn: true);
    await pumpApp(tester, mock, location: '/home');
    await tapKey(tester, 'home-settings');
    expect(keyed('settings-about'), findsOneWidget, reason: 'the settings screen is open');
    expect(keyed('settings-server-link'), findsNothing);
  });

  testWidgets('Settings: against a real server the Server row changes the address', (tester) async {
    useSmallPhone(tester);
    final env = await TestEnv.create(loggedIn: true, config: realServer);
    final container = await pumpApp(tester, env, location: '/home');
    await tapKey(tester, 'home-settings');
    await tester.ensureVisible(keyed('settings-server-link'));
    await tapKey(tester, 'settings-server-link');
    await tester.enterText(keyed('server-field'), 'http://192.168.12.246:8000');
    await tapKey(tester, 'server-save');
    expect(container.read(apiBaseUrlProvider), 'http://192.168.12.246:8000');
    expect(env.prefs.getString(serverOverrideKey), 'http://192.168.12.246:8000');
  });
}
