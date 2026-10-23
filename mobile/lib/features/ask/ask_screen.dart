import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'ask_flow.dart';
import 'ask_suggestions.dart';

/// Route `/ask`: ten big picture cards with common questions (tap one: it is spoken and sent) and one big button
/// that opens the typing screen. Speaks `ask_intro`, then says what to tap.
class AskScreen extends ConsumerWidget {
  const AskScreen({super.key});

  void _ask(BuildContext context, WidgetRef ref, AskSuggestion suggestion) {
    // A second tap while the answer screen is opening must not ask (and push) twice.
    if (!(ModalRoute.of(context)?.isCurrent ?? true)) return;
    final lang = ref.read(languageProvider);
    unawaited(ref.read(askFlowProvider.notifier).ask(suggestion.question.forLang(lang), promptId: suggestion.promptId));
    context.push(Routes.askAnswer);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    final lang = ref.watch(languageProvider);
    final suggestions = ref.watch(askSuggestionsProvider).value ?? const <AskSuggestion>[];
    // Two cards per row, one per row when the text is large (a label must never be squeezed).
    final twoColumns = MediaQuery.textScalerOf(context).scale(20) < 26;

    Widget card(AskSuggestion s) => _SuggestionCard(
      key: ValueKey('ask-card-${s.id}'),
      icon: s.icon,
      label: s.label.forLang(lang),
      wide: !twoColumns,
      onTap: () => _ask(context, ref, s),
    );

    return VoiceScaffold(
      script: promptList(const ['ask_intro', 'ask_tap_picture']),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _OwnQuestionButton(label: t('ask_own'), onTap: () => context.push(Routes.askType)),
          const SizedBox(height: 14),
          if (twoColumns)
            for (var i = 0; i < suggestions.length; i += 2)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(child: card(suggestions[i])),
                      const SizedBox(width: 12),
                      Expanded(child: i + 1 < suggestions.length ? card(suggestions[i + 1]) : const SizedBox.shrink()),
                    ],
                  ),
                ),
              )
          else
            for (final s in suggestions) Padding(padding: const EdgeInsets.only(bottom: 12), child: card(s)),
        ],
      ),
    );
  }
}

/// The wide button that opens the typing screen.
class _OwnQuestionButton extends StatelessWidget {
  const _OwnQuestionButton({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: label,
    excludeSemantics: true,
    child: Material(
      key: const ValueKey('ask-own'),
      color: AppColors.blue,
      borderRadius: BorderRadius.circular(Dimens.radius),
      elevation: 3,
      child: InkWell(
        borderRadius: BorderRadius.circular(Dimens.radius),
        onTap: () {
          Haptics.tap();
          onTap();
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: Dimens.primary),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                const Icon(Icons.keyboard_rounded, size: 56, color: Colors.white),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(label, style: Theme.of(context).textTheme.titleLarge?.copyWith(color: Colors.white)),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({super.key, required this.icon, required this.label, required this.wide, required this.onTap});

  final IconData icon;
  final String label;

  /// One card per row: picture on the left, words on the right.
  final bool wide;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final picture = Icon(icon, size: 52, color: AppColors.blue);
    final words = Text(
      label,
      textAlign: wide ? TextAlign.start : TextAlign.center,
      style: Theme.of(context).textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w700),
    );
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: AppColors.card,
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Dimens.radius),
          side: const BorderSide(color: AppColors.blue, width: 3),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(Dimens.radius),
          onTap: () {
            Haptics.tap();
            onTap();
          },
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: Dimens.primary),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: wide
                  ? Row(
                      children: [
                        picture,
                        const SizedBox(width: 12),
                        Expanded(child: words),
                      ],
                    )
                  : Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [picture, const SizedBox(height: 8), words],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
