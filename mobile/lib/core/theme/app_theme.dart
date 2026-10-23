import 'package:flutter/material.dart';

import '../models/models.dart';

/// High-contrast colours that carry meaning: green = yes / safe, red = no / danger, amber = be careful.
class AppColors {
  const AppColors._();

  static const green = Color(0xFF1B7F3A);
  static const greenSoft = Color(0xFFDDF3E2);
  static const red = Color(0xFFC62828);
  static const redSoft = Color(0xFFFBE0DE);
  static const amber = Color(0xFFF2A900);

  /// Amber for icons, borders and text drawn ON light backgrounds (paper, white, [amberSoft]): 4.7 to 5.3 against
  /// them. [amber] itself is a fill that carries ink text (8.9:1); drawn as an icon on a light panel it is only
  /// 1.8 to 2.0:1.
  static const amberDark = Color(0xFF946100);
  static const amberSoft = Color(0xFFFFF1C7);
  static const blue = Color(0xFF1F5FA8);
  static const blueSoft = Color(0xFFDCEAF9);
  static const ink = Color(0xFF14181F);
  static const inkSoft = Color(0xFF4A5260);
  static const paper = Color(0xFFFBF8F1);
  static const card = Color(0xFFFFFFFF);
  static const line = Color(0xFFD9D3C5);

  static Color severity(Severity s) => switch (s) {
    Severity.green => green,
    Severity.yellow => amber,
    Severity.red => red,
  };

  static Color severitySoft(Severity s) => switch (s) {
    Severity.green => greenSoft,
    Severity.yellow => amberSoft,
    Severity.red => redSoft,
  };

  /// The severity colour as an icon, border or text on a light background (see [amberDark]): at least 4.5:1 on paper
  /// and white, and at least 3:1 on its own soft panel.
  static Color severityAccent(Severity s) => switch (s) {
    Severity.green => green,
    Severity.yellow => amberDark,
    Severity.red => red,
  };

  /// Text colour that stays readable on [severity] backgrounds.
  static Color onSeverity(Severity s) => s == Severity.yellow ? ink : Colors.white;
}

/// Touch target and spacing sizes in dp. No target is smaller than [minTouch].
class Dimens {
  const Dimens._();

  static const minTouch = 64.0;
  static const primary = 96.0;
  static const hero = 148.0;
  static const gutter = 16.0;
  static const radius = 24.0;
}

/// The picture of every button, in one place. The voice prompts name exactly these pictures.
class AppIcons {
  const AppIcons._();

  static const tick = Icons.check_rounded; // "green tick"
  static const cross = Icons.close_rounded; // "red cross"
  static const plus = Icons.add_rounded; // "plus sign"
  static const camera = Icons.photo_camera_rounded; // "camera picture"
  static const gallery = Icons.photo_library_rounded; // "gallery picture" (photos already in the phone)
  static const speaker = Icons.volume_up_rounded; // "speaker picture"
  static const notebook = Icons.edit_note_rounded; // "notebook picture"
  static const gear = Icons.settings_rounded; // "gear picture"
  static const bell = Icons.notifications_rounded; // "bell picture"
  static const cloud = Icons.cloud_rounded; // "cloud picture"
  static const field = Icons.grass_rounded; // "field picture" (shown with the cloud on the My field button)
  static const house = Icons.home_rounded; // "house picture"
  static const back = Icons.arrow_back_rounded; // "arrow that points left"
  static const question = Icons.live_help_rounded; // "question mark picture" (speech bubble with a ?)
  static const roundArrow = Icons.refresh_rounded; // "round arrow"
  static const greenArrow = Icons.arrow_forward_rounded; // "green arrow"
  static const expert = Icons.support_agent_rounded;
  static const offline = Icons.cloud_off_rounded;
  static const warning = Icons.warning_amber_rounded;
  static const danger = Icons.report_rounded;
  static const leaf = Icons.eco_rounded;
  static const tree = Icons.park_rounded;
  static const grass = Icons.grass_rounded;
  static const noVoice = Icons.volume_off_rounded;
  static const medicine = Icons.science_rounded;
  static const clock = Icons.schedule_rounded;
  static const slow = Icons.slow_motion_video_rounded;
  static const normalSpeed = Icons.play_arrow_rounded;
  static const fast = Icons.fast_forward_rounded;
  static const volumeLow = Icons.volume_mute_rounded;
  static const volumeMedium = Icons.volume_down_rounded;
  static const volumeHigh = Icons.volume_up_rounded;
  static const captions = Icons.subtitles_rounded;
  static const logout = Icons.logout_rounded;
  static const person = Icons.person_rounded; // "person picture" (user name)
  static const lock = Icons.lock_rounded; // "lock picture" (password)
  static const eye = Icons.visibility_rounded; // "eye picture": shows the password
  static const eyeOff = Icons.visibility_off_rounded; // crossed-out eye: hides the password
  static const noDisease = Icons.search_off_rounded;
  static const info = Icons.info_outline_rounded;
}

ThemeData buildAppTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: AppColors.green, brightness: Brightness.light).copyWith(
    primary: AppColors.green,
    onPrimary: Colors.white,
    error: AppColors.red,
    surface: AppColors.paper,
    onSurface: AppColors.ink,
  );

  const text = TextStyle(color: AppColors.ink, height: 1.3);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: AppColors.paper,
    materialTapTargetSize: MaterialTapTargetSize.padded,
    textTheme: TextTheme(
      displaySmall: text.copyWith(fontSize: 36, fontWeight: FontWeight.w800),
      headlineMedium: text.copyWith(fontSize: 30, fontWeight: FontWeight.w800),
      headlineSmall: text.copyWith(fontSize: 26, fontWeight: FontWeight.w700),
      titleLarge: text.copyWith(fontSize: 24, fontWeight: FontWeight.w700),
      titleMedium: text.copyWith(fontSize: 22, fontWeight: FontWeight.w700),
      bodyLarge: text.copyWith(fontSize: 22),
      bodyMedium: text.copyWith(fontSize: 20),
      labelLarge: text.copyWith(fontSize: 20, fontWeight: FontWeight.w700),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(Dimens.minTouch, Dimens.minTouch),
        textStyle: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Dimens.radius)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(Dimens.minTouch, Dimens.minTouch),
        textStyle: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        side: const BorderSide(color: AppColors.ink, width: 2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Dimens.radius)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(minimumSize: const Size(Dimens.minTouch, Dimens.minTouch)),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(Dimens.minTouch, Dimens.minTouch)),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.green, linearMinHeight: 12),
  );
}
