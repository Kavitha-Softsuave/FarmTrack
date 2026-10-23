import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/alerts/alert_detail_screen.dart';
import '../../features/alerts/alerts_providers.dart';
import '../../features/alerts/alerts_screen.dart';
import '../../features/ask/ask_answer_screen.dart';
import '../../features/ask/ask_screen.dart';
import '../../features/ask/ask_type_screen.dart';
import '../../features/auth/login_screen.dart';
import '../../features/diary/diary_screen.dart';
import '../../features/field/field_screen.dart';
import '../../features/home/home_screen.dart';
import '../../features/offline/saved_offline_screen.dart';
import '../../features/onboarding/language_screen.dart';
import '../../features/onboarding/welcome_screen.dart';
import '../../features/result/advice_screen.dart';
import '../../features/result/expert_screen.dart';
import '../../features/scan/crop_choose_screen.dart';
import '../../features/scan/crop_confirm_screen.dart';
import '../../features/scan/photo_review_screen.dart';
import '../../features/scan/processing_screen.dart';
import '../../features/scan/retake_screen.dart';
import '../../features/scan/scan_capture_screen.dart';
import '../../features/settings/logout_confirm_screen.dart';
import '../../features/settings/settings_screen.dart';
import '../../features/splash/splash_screen.dart';
import '../providers.dart';
import '../push/push_providers.dart';
import 'routes.dart';

/// Where the app starts. Tests override it to open a screen directly.
final initialLocationProvider = Provider<String>((ref) => Routes.splash);

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier<int>(0);
  ref.listen(sessionProvider, (_, _) => refresh.value++);
  final router = GoRouter(
    initialLocation: ref.read(initialLocationProvider),
    refreshListenable: refresh,
    redirect: (context, state) => _redirect(ref, state.matchedLocation),
    routes: _buildRoutes(),
  );
  ref.onDispose(() {
    router.dispose();
    refresh.dispose();
  });
  return router;
});

/// Keeps logged-out farmers on the public screens and sends everyone through the splash screen first.
String? _redirect(Ref ref, String location) {
  final session = ref.read(sessionProvider);
  switch (session.status) {
    case SessionStatus.unknown:
      return location == Routes.splash ? null : Routes.splash;
    case SessionStatus.loggedOut:
      if (Routes.publicRoutes.contains(location)) return null;
      return ref.read(settingsProvider).language == null ? Routes.language : Routes.login;
    case SessionStatus.loggedIn:
      return null;
  }
}

/// A short fade between screens; none when the phone asks for no animations (`MediaQuery.disableAnimations`).
Page<void> _page(GoRouterState state, Widget child) => CustomTransitionPage<void>(
  key: state.pageKey,
  child: child,
  transitionDuration: const Duration(milliseconds: 160),
  reverseTransitionDuration: const Duration(milliseconds: 120),
  transitionsBuilder: (context, animation, secondary, child) =>
      MediaQuery.disableAnimationsOf(context) ? child : FadeTransition(opacity: animation, child: child),
);

GoRoute _route(String path, Widget Function(GoRouterState state) build) =>
    GoRoute(path: path, pageBuilder: (context, state) => _page(state, build(state)));

List<RouteBase> _buildRoutes() => [
  _route(Routes.splash, (_) => const SplashScreen()),
  _route(Routes.language, (_) => const LanguageScreen()),
  _route(Routes.welcome, (_) => const WelcomeScreen()),
  _route(Routes.login, (_) => const LoginScreen()),
  // Home only exists for a logged-in farmer: it starts push and keeps the bell badge fresh.
  _route(
    Routes.home,
    (s) => PushBootstrap(
      child: AlertsAutoRefresh(child: HomeScreen(fresh: s.uri.queryParameters['fresh'] == '1')),
    ),
  ),
  _route(Routes.scan, (_) => const ScanCaptureScreen()),
  _route(Routes.scanReview, (_) => const PhotoReviewScreen()),
  _route(Routes.scanUploading, (_) => const ProcessingScreen()),
  _route(Routes.scanAnalysing, (s) => ProcessingScreen(confirmCropId: s.uri.queryParameters['crop'])),
  _route(Routes.scanRetake, (_) => const RetakeScreen()),
  _route(Routes.scanConfirm, (_) => const CropConfirmScreen()),
  _route(Routes.scanCrops, (_) => const CropChooseScreen()),
  _route(Routes.scanAdvice, (_) => const AdviceScreen()),
  _route(Routes.scanExpert, (_) => const ExpertScreen()),
  _route(Routes.scanSaved, (_) => const SavedOfflineScreen()),
  _route(
    Routes.diary,
    (s) => DiaryScreen(
      adviceId: s.uri.queryParameters['advice'],
      cropId: s.uri.queryParameters['crop'],
      productId: s.uri.queryParameters['product'],
    ),
  ),
  _route(Routes.diaryAdd, (_) => const DiaryAddScreen()),
  _route(Routes.field, (_) => const FieldScreen()),
  _route(Routes.alerts, (_) => const AlertsAutoRefresh(child: AlertsScreen())),
  _route(Routes.alertDetail, (s) => AlertDetailScreen(alertId: s.uri.queryParameters['id'])),
  _route(Routes.ask, (_) => const AskScreen()),
  _route(Routes.askType, (_) => const AskTypeScreen()),
  _route(Routes.askAnswer, (_) => const AskAnswerScreen()),
  _route(Routes.settings, (_) => const SettingsScreen()),
  _route(Routes.settingsLogout, (_) => const LogoutConfirmScreen()),
];
