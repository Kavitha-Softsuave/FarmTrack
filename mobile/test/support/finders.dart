import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Finder keyed(String key) => find.byKey(ValueKey(key));

/// Taps a widget that may be below the fold of a scroll view.
Future<void> tapKey(WidgetTester tester, String key) async {
  final finder = keyed(key);
  expect(finder, findsOneWidget, reason: 'no widget with key $key');
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

/// Types into the login screen's two fields (only the ones given). Does not tap the green tick.
Future<void> enterLogin(WidgetTester tester, {String? username, String? password}) async {
  if (username != null) await tester.enterText(keyed('login-username'), username);
  if (password != null) await tester.enterText(keyed('login-password'), password);
  await tester.pump();
}

/// Types the user name and password and taps the green tick of the login screen.
Future<void> logInWith(WidgetTester tester, {String username = 'f001', String password = 'farm1234'}) async {
  await enterLogin(tester, username: username, password: password);
  await tapKey(tester, 'login-submit');
}

/// Every tappable area must be at least 64 x 64 dp.
void expectBigTouchTargets(WidgetTester tester) {
  final small = <String>[];
  for (final element in find.byType(InkWell).evaluate()) {
    final widget = element.widget as InkWell;
    if (widget.onTap == null) continue;
    final size = tester.getSize(find.byWidget(widget));
    if (size.width < 63.9 || size.height < 63.9) small.add('${size.width}x${size.height} ${widget.key ?? ''}');
  }
  expect(small, isEmpty, reason: 'touch targets below 64 dp: $small');
}
