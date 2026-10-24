import 'dart:async';
import 'dart:io' show Directory;

import 'package:flutter/foundation.dart' show debugPrint, kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'core/l10n/app_resources.dart';
import 'core/providers.dart';
import 'core/voice/prompt_catalogue.dart';

/// Everything that runs before the first frame, in one place: two small JSON assets (interface words and voice
/// prompts, about 50 KB together), the saved settings and the app folder. They do not depend on each other, so they
/// run side by side and the start costs the slowest of them, not the sum. Nothing else is done before [runApp]: the
/// offline queue, the voice catalogue refresh, push and the demo date all start after the first frame. In debug
/// builds each step prints how long it took.
/// The start-up steps that have not finished yet, and whether the first screen is up.
final Set<String> _pendingSteps = {};
bool _firstScreenShown = false;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // A step that never finishes would leave the phone on the launch picture for ever: say which one it is.
  final watchdog = Timer(const Duration(seconds: 8), () {
    if (!_firstScreenShown) {
      runApp(_StartupErrorApp('Still starting after 8 seconds.\nWaiting for: ${_pendingSteps.join(', ')}'));
    }
  });
  try {
    await _start();
  } on Object catch (error, stack) {
    // A start that fails must say why on the screen; otherwise the phone just shows the launch picture for ever.
    runApp(_StartupErrorApp('$error\n\n$stack'));
  } finally {
    watchdog.cancel();
  }
}

Future<void> _start() async {
  final startup = Stopwatch()..start();
  Future<T> timed<T>(String what, Future<T> step) async {
    _pendingSteps.add(what);
    final result = await step;
    _pendingSteps.remove(what);
    if (kDebugMode) debugPrint('startup: $what ready after ${startup.elapsedMilliseconds} ms');
    return result;
  }

  final (_, resources, catalogue, prefs, support) = await (
    timed(
      'orientation',
      SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp, DeviceOrientation.portraitDown]),
    ),
    timed('words', AppResources.load(rootBundle)),
    timed('prompts', PromptCatalogue.load(rootBundle)),
    timed('settings', SharedPreferences.getInstance()),
    timed('app folder', _appFolder()),
  ).wait;

  final container = ProviderContainer(
    // A failed request must show our error screen at once, not retry silently in the background.
    retry: (_, _) => null,
    overrides: [
      resourcesProvider.overrideWithValue(resources),
      promptCatalogueProvider.overrideWithValue(catalogue),
      sharedPreferencesProvider.overrideWithValue(prefs),
      supportDirectoryProvider.overrideWithValue(support),
    ],
  );
  unawaited(_syncVoiceCatalogue(container));
  _firstScreenShown = true;
  runApp(UncontrolledProviderScope(container: container, child: const FarmTrackApp()));
  if (kDebugMode) debugPrint('startup: runApp called after ${startup.elapsedMilliseconds} ms');
}

/// Loads the saved server voice catalogue, refreshes it and (over Wi-Fi) downloads the prompt audio. Best effort,
/// never blocks the first screen.
Future<void> _syncVoiceCatalogue(ProviderContainer container) => container.read(voicePackageProvider).start();

/// The app's own folder; if the phone does not give one in time, a temporary folder keeps the app usable (the offline
/// queue and the audio cache then only last until the app is closed).
Future<Directory> _appFolder() async {
  try {
    return await getApplicationSupportDirectory().timeout(const Duration(seconds: 5));
  } on Object {
    return Directory.systemTemp.createTemp('farmtrack');
  }
}

/// Shown only when the start itself failed: the error as text that can be read and photographed.
class _StartupErrorApp extends StatelessWidget {
  const _StartupErrorApp(this.message);

  final String message;

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    home: Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: SelectableText('FarmTrack could not start.\n\n$message', style: const TextStyle(fontSize: 14)),
        ),
      ),
    ),
  );
}
