import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';
import '../voice/speak_on_enter.dart';
import '../voice/utterance.dart';
import '../voice/voice_widgets.dart';
import 'big_buttons.dart';
import 'demo_clock_banner.dart';

/// The frame of every screen: a back arrow on top, the content, the spoken caption, and the speaker button at
/// the bottom-left. It speaks [script] when the screen appears.
class VoiceScaffold extends ConsumerWidget {
  const VoiceScaffold({
    super.key,
    required this.script,
    required this.body,
    this.replayScript,
    this.owner,
    this.restartKey,
    this.speakEnabled = true,
    this.bottomRight,
    this.topRight = const [],
    this.showBack = true,
    this.onBack,
    this.scrollable = true,
    this.showCaption = true,
  });

  /// What to say when the screen opens (and when the speaker button is tapped).
  final List<Utterance> script;
  final Widget body;

  /// What the speaker button plays, when it differs from [script].
  final List<Utterance>? replayScript;

  /// The screen's speech identity (see [SpeakOnEnter.owner]).
  final Object? owner;

  /// Change it to speak the script again while the screen stays open.
  final Object? restartKey;
  final bool speakEnabled;

  /// The screen's main action, bottom-right (the speaker is always bottom-left).
  final Widget? bottomRight;

  /// Small buttons at the top-right (settings, alerts).
  final List<Widget> topRight;
  final bool showBack;
  final VoidCallback? onBack;

  /// Wrap [body] in a scroll view (needed at large text sizes). Set false for bodies that fill the space.
  final bool scrollable;

  /// Show the spoken sentence as a caption. Turn it off when the screen already shows that text itself (an answer).
  final bool showCaption;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final canGoBack = showBack && (onBack != null || Navigator.of(context).canPop());
    final keyboardOpen = MediaQuery.viewInsetsOf(context).bottom > 0;
    return PopScope(
      // With an explicit [onBack] the phone's own back button does the same as the arrow on screen.
      canPop: onBack == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) onBack?.call();
      },
      child: Scaffold(
        body: SafeArea(
          child: SpeakOnEnter(
            script: script,
            replayScript: replayScript,
            owner: owner,
            restartKey: restartKey,
            enabled: speakEnabled,
            child: Column(
              children: [
                // Thin strip while the server runs on a demo clock. Never spoken.
                const DemoClockBanner(),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(Dimens.gutter, 8, Dimens.gutter, Dimens.gutter),
                    child: Column(
                      children: [
                        SizedBox(
                          height: Dimens.minTouch + 8,
                          child: Row(
                            children: [
                              if (canGoBack)
                                BigIconButton(
                                  icon: AppIcons.back,
                                  semanticLabel: t('a11y_back'),
                                  color: AppColors.card,
                                  foreground: AppColors.ink,
                                  size: Dimens.minTouch,
                                  onPressed: onBack ?? () => Navigator.of(context).maybePop(),
                                ),
                              const Spacer(),
                              for (final w in topRight) ...[w, const SizedBox(width: 8)],
                            ],
                          ),
                        ),
                        Expanded(child: scrollable ? _ScrollingBody(child: body) : body),
                        // While the keyboard is up the room is needed for the fields: the caption and the banner wait.
                        if (!keyboardOpen) const VoiceMissingBanner(),
                        if (showCaption && !keyboardOpen) const VoiceCaption(),
                        const SizedBox(height: 4),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [const SpeakerButton(), const Spacer(), ?bottomRight],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ScrollingBody extends StatelessWidget {
  const _ScrollingBody({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) => SingleChildScrollView(
      child: ConstrainedBox(
        constraints: BoxConstraints(minHeight: constraints.maxHeight),
        child: Align(alignment: Alignment.center, child: child),
      ),
    ),
  );
}
