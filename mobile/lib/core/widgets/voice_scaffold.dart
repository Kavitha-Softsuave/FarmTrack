import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import '../theme/app_theme.dart';
import '../voice/speak_on_enter.dart';
import '../voice/utterance.dart';
import '../voice/voice_widgets.dart';
import 'big_buttons.dart';
import 'demo_clock_banner.dart';

/// The frame of every screen, kept as thin as possible so the content is the main thing: one slim bar on top (back
/// arrow, the screen's small buttons, the speaker), the content, and at the bottom only the screen's one main action.
/// The spoken sentence floats over the content as a one-line caption (tap for all of it) instead of taking a footer.
/// It speaks [script] when the screen appears.
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

  /// The screen's one main action, bottom-right. Its row is the only thing under the content.
  final Widget? bottomRight;

  /// Small buttons at the top, next to the speaker (settings, alerts).
  final List<Widget> topRight;
  final bool showBack;
  final VoidCallback? onBack;

  /// Wrap [body] in a scroll view (needed at large text sizes). Set false for bodies that fill the space.
  final bool scrollable;

  /// Show the spoken sentence as a caption. Turn it off when the screen already shows that text itself (an answer).
  final bool showCaption;

  /// Tallest the main action's row gets; a bigger button, or one with a word under it, shrinks to fit.
  static const actionHeight = 88.0;

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
                  child: Stack(
                    children: [
                      Padding(
                        padding: const EdgeInsets.fromLTRB(Dimens.gutter, 4, Dimens.gutter, 4),
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
                                  // The screen's own buttons shrink together if the phone is narrow; never an overflow.
                                  Expanded(
                                    child: Align(
                                      alignment: Alignment.centerRight,
                                      child: FittedBox(
                                        fit: BoxFit.scaleDown,
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            for (final w in topRight) ...[w, const SizedBox(width: 8)],
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                  const SpeakerButton(),
                                ],
                              ),
                            ),
                            if (!keyboardOpen) const VoiceMissingBanner(),
                            Expanded(
                              child: scrollable ? _ScrollingBody(captionRoom: !keyboardOpen, child: body) : body,
                            ),
                            if (bottomRight != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Align(
                                  alignment: Alignment.centerRight,
                                  child: ConstrainedBox(
                                    // A little smaller while the keyboard is up: the fields need the room.
                                    constraints: BoxConstraints(
                                      maxHeight: keyboardOpen ? actionHeight - 24 : actionHeight,
                                    ),
                                    child: FittedBox(fit: BoxFit.scaleDown, child: bottomRight),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      // Floats over the lowest part of the content, above the main action's row; it makes room for
                      // the fields while the keyboard is up.
                      if (showCaption && !keyboardOpen)
                        Positioned(
                          left: Dimens.gutter,
                          right: Dimens.gutter,
                          bottom: bottomRight == null ? 8 : actionHeight + 12,
                          child: const VoiceCaption(),
                        ),
                    ],
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
  const _ScrollingBody({required this.child, required this.captionRoom});

  final Widget child;

  /// Leave room under the last item for the floating caption (not while the keyboard is up: there is no caption then).
  final bool captionRoom;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final room = captionRoom ? 56.0 : 0.0;
      return SingleChildScrollView(
        padding: EdgeInsets.only(bottom: room),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: (constraints.maxHeight - room).clamp(0.0, double.infinity)),
          child: Align(alignment: Alignment.center, child: child),
        ),
      );
    },
  );
}
