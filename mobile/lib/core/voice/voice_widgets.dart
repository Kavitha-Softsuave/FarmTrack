import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';
import '../widgets/big_buttons.dart';
import 'speak_on_enter.dart';
import 'voice_service.dart';

/// The big speaker picture, always at the bottom-left of the screen content. Plays the screen's speech again.
class SpeakerButton extends ConsumerWidget {
  const SpeakerButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = VoiceSession.maybeOf(context);
    final voice = ref.watch(voiceServiceProvider);
    final t = ref.watch(stringsProvider);
    return ValueListenableBuilder<VoiceState>(
      valueListenable: voice.state,
      builder: (context, state, _) {
        final speaking = state.speaking && session != null && state.owner == session.owner;
        return Container(
          key: const ValueKey('speaker-button'),
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: speaking ? AppColors.blue : Colors.transparent, width: 3),
          ),
          child: BigIconButton(
            icon: AppIcons.speaker,
            semanticLabel: t('a11y_listen'),
            color: AppColors.blue,
            size: 80,
            onPressed: session == null ? null : () => session.replay(),
          ),
        );
      },
    );
  }
}

/// The sentence being spoken, as a large caption (switch off in settings). Shown only on the screen that spoke it.
class VoiceCaption extends ConsumerWidget {
  const VoiceCaption({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = VoiceSession.maybeOf(context);
    final enabled = ref.watch(settingsProvider.select((s) => s.captions));
    if (!enabled || session == null) return const SizedBox.shrink();
    final voice = ref.watch(voiceServiceProvider);
    final maxHeight = MediaQuery.sizeOf(context).height * 0.17;
    return ValueListenableBuilder<VoiceState>(
      valueListenable: voice.state,
      builder: (context, state, _) {
        final text = state.owner == session.owner ? state.caption : null;
        if (text == null || text.isEmpty) return const SizedBox.shrink();
        return Semantics(
          container: true,
          label: text,
          excludeSemantics: true,
          child: Container(
            key: const ValueKey('voice-caption'),
            width: double.infinity,
            constraints: BoxConstraints(maxHeight: maxHeight),
            margin: const EdgeInsets.only(bottom: 8),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.line, width: 2),
            ),
            child: SingleChildScrollView(
              child: Text(
                text,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontSize: 20, fontWeight: FontWeight.w600),
              ),
            ),
          ),
        );
      },
    );
  }
}

/// Shown when this phone has no voice for the farmer's language: the words stay readable on screen.
class VoiceMissingBanner extends ConsumerWidget {
  const VoiceMissingBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final voice = ref.watch(voiceServiceProvider);
    final lang = ref.watch(languageProvider);
    final t = ref.watch(stringsProvider);
    return ValueListenableBuilder<VoiceState>(
      valueListenable: voice.state,
      builder: (context, state, _) {
        if (!state.missingVoices.contains(lang)) return const SizedBox.shrink();
        return Container(
          key: const ValueKey('voice-missing'),
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: AppColors.amberSoft, borderRadius: BorderRadius.circular(16)),
          child: Row(
            children: [
              const Icon(AppIcons.noVoice, size: 36),
              const SizedBox(width: 12),
              Expanded(child: Text(t('voice_missing'), style: Theme.of(context).textTheme.bodyMedium)),
            ],
          ),
        );
      },
    );
  }
}
