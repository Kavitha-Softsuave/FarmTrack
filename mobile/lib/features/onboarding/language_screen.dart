import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n/app_resources.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/speak_on_enter.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';

/// One huge button per language, labelled in its own script. Tapping plays that language's name in its own
/// voice, applies the choice, and calls [onChosen].
class LanguageButtons extends ConsumerStatefulWidget {
  const LanguageButtons({
    super.key,
    required this.onChosen,
    this.selected,
    this.speakChoice = true,
    this.compact = false,
  });

  final Future<void> Function(String code) onChosen;

  /// Highlights the current language (settings screen).
  final String? selected;
  final bool speakChoice;

  /// Smaller buttons side by side (settings), instead of two huge stacked ones (first launch).
  final bool compact;

  @override
  ConsumerState<LanguageButtons> createState() => _LanguageButtonsState();
}

class _LanguageButtonsState extends ConsumerState<LanguageButtons> {
  bool _busy = false;

  Future<void> _choose(LanguageInfo language) async {
    if (_busy) return;
    final owner = VoiceSession.maybeOf(context)?.owner;
    setState(() => _busy = true);
    try {
      await ref.read(settingsProvider.notifier).setLanguage(language.code);
      if (widget.speakChoice && language.promptId.isNotEmpty) {
        // Plays "Hindi." / "English." in that language's own voice before moving on.
        await ref.read(voiceServiceProvider).speak([
          PromptUtterance(language.promptId, lang: language.code),
        ], owner: owner);
      }
      await widget.onChosen(language.code);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final resources = ref.watch(resourcesProvider);
    final tiles = [
      for (final language in resources.languages)
        SizedBox(
          height: widget.compact ? 84 : 132,
          width: double.infinity,
          child: PictureTile(
            key: ValueKey('language-${language.code}'),
            semanticLabel: language.nativeName,
            borderColor: widget.selected == language.code ? AppColors.green : AppColors.ink,
            color: widget.selected == language.code ? AppColors.greenSoft : AppColors.card,
            onPressed: _busy ? null : () => _choose(language),
            child: _LanguageFace(
              language: language,
              selected: widget.selected == language.code,
              fontSize: widget.compact ? 34 : 52,
            ),
          ),
        ),
    ];
    // Two languages fit side by side in the compact (settings) layout; more are stacked, so the list can grow as data.
    if (widget.compact && tiles.length <= 2) {
      return Row(
        children: [
          for (var i = 0; i < tiles.length; i++) ...[if (i > 0) const SizedBox(width: 12), Expanded(child: tiles[i])],
        ],
      );
    }
    final gap = widget.compact ? 12.0 : 20.0;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final tile in tiles) ...[tile, SizedBox(height: gap)],
      ],
    );
  }
}

/// The face of a language button: a round badge with a letter, the name in its own script, and a green tick when it
/// is the chosen language.
class _LanguageFace extends StatelessWidget {
  const _LanguageFace({required this.language, required this.selected, required this.fontSize});

  final LanguageInfo language;
  final bool selected;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final badge = fontSize * 1.1;
    // The tile scales its picture down to fit (FittedBox), so this row sizes itself to its content.
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          key: ValueKey('language-badge-${language.code}'),
          width: badge,
          height: badge,
          alignment: Alignment.center,
          decoration: BoxDecoration(color: AppColors.ink, shape: BoxShape.circle),
          child: Text(
            language.badgeText,
            style: TextStyle(fontSize: fontSize * 0.62, fontWeight: FontWeight.w800, color: Colors.white),
          ),
        ),
        SizedBox(width: fontSize * 0.3),
        Text(
          language.nativeName,
          style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.w800, color: AppColors.ink),
        ),
        if (selected) ...[
          SizedBox(width: fontSize * 0.3),
          Icon(
            AppIcons.tick,
            key: ValueKey('language-selected-${language.code}'),
            size: fontSize,
            color: AppColors.green,
          ),
        ],
      ],
    );
  }
}

/// First launch: speaks "choose your language" in Hindi, then in English.
class LanguageScreen extends ConsumerWidget {
  const LanguageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resources = ref.watch(resourcesProvider);
    return VoiceScaffold(
      showBack: false,
      // Every language says the sentence in its own voice, one after the other (hi then en).
      script: [for (final l in resources.languages) PromptUtterance('choose_language', lang: l.code)],
      body: LanguageButtons(
        onChosen: (_) async {
          if (context.mounted) context.go(Routes.welcome);
        },
      ),
    );
  }
}
