import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/voice/voice_service.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/redirect.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'ask_flow.dart';

/// Route `/ask/answer`: speaks the question (suggestion cards only), waits for the server, then speaks the answer and
/// shows it as large text with the sources small underneath. When the server refuses (no approved note supports an
/// answer) it speaks the refusal and offers one big button that asks a farm expert.
class AskAnswerScreen extends ConsumerStatefulWidget {
  const AskAnswerScreen({super.key});

  @override
  ConsumerState<AskAnswerScreen> createState() => _AskAnswerScreenState();
}

class _AskAnswerScreenState extends ConsumerState<AskAnswerScreen> {
  final Object _owner = Object();

  /// The question has been spoken: from now on the answer may be spoken (it never cuts the question off).
  bool _introDone = false;
  AskOut? _spokenAnswer;
  bool _sending = false;
  bool _sent = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_intro()));
  }

  Future<void> _intro() async {
    if (!mounted) return;
    final flow = ref.read(askFlowProvider);
    final id = flow.promptId;
    if (flow.phase != AskPhase.idle && id != null) {
      final known = ref.read(promptCatalogueProvider).contains(id);
      await ref.read(voiceServiceProvider).speak([
        if (known) PromptUtterance(id) else TextUtterance(flow.question, lang: ref.read(languageProvider)),
      ], owner: _owner);
    }
    if (!mounted) return;
    _introDone = true;
    _speakFor(ref.read(askFlowProvider));
  }

  /// What to say for the state the screen is in. Errors speak for themselves (`ErrorRetryScreen`).
  void _speakFor(AskState flow) {
    if (!mounted || !_introDone) return;
    final voice = ref.read(voiceServiceProvider);
    switch (flow.phase) {
      case AskPhase.asking:
        unawaited(voice.speakPrompts(const ['ask_wait'], owner: _owner));
      case AskPhase.answered:
        final answer = flow.answer;
        if (answer == null || identical(answer, _spokenAnswer)) return;
        _spokenAnswer = answer;
        Haptics.success();
        unawaited(voice.speak(_answerScript(answer), owner: _owner));
      case AskPhase.failed:
      case AskPhase.idle:
        break;
    }
  }

  /// The server's own spoken version (with its audio), else its text; a refusal without text says `ask_no_answer`.
  List<Utterance> _answerScript(AskOut answer) {
    final lang = answer.language.isEmpty ? ref.read(languageProvider) : answer.language;
    final spoken = answer.spoken?.toUtterance(lang);
    if (spoken != null) return [spoken];
    if (answer.answer.trim().isNotEmpty) return [TextUtterance(answer.answer, lang: lang)];
    return answer.refused ? promptList(const ['ask_no_answer']) : const [];
  }

  String _answerText(AskOut answer) {
    if (answer.answer.trim().isNotEmpty) return answer.answer;
    return answer.spoken?.text.forLang(answer.language.isEmpty ? ref.read(languageProvider) : answer.language) ?? '';
  }

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.ask);
    }
  }

  Future<void> _askExpert(AskState flow) async {
    if (_sending || _sent) return;
    final voice = ref.read(voiceServiceProvider);
    setState(() => _sending = true);
    try {
      final message = flow.question.length > AskFlowNotifier.maxLength
          ? flow.question.substring(0, AskFlowNotifier.maxLength)
          : flow.question;
      await ref.read(apiClientProvider).createExpertRequest(ExpertRequestIn(message: message));
      Haptics.success();
      if (mounted) setState(() => _sent = true);
      await voice.speak(promptList(const ['ask_expert_sent']), owner: _owner);
    } on Object catch (e) {
      Haptics.error();
      await voice.speak(promptList([errorPromptFor(e)]), owner: _owner);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(askFlowProvider);
    ref.listen<AskState>(askFlowProvider, (previous, next) {
      if (previous?.phase != next.phase) _speakFor(next);
    });
    final t = ref.watch(stringsProvider);

    switch (flow.phase) {
      case AskPhase.idle:
        // Opened without a question (the app was restarted on this screen).
        return const Redirect(to: Routes.ask);
      case AskPhase.failed:
        return ErrorRetryScreen(
          error: flow.error ?? Exception('ask failed'),
          onRetry: () => unawaited(ref.read(askFlowProvider.notifier).retry()),
          onBack: _back,
        );
      case AskPhase.asking:
        return VoiceScaffold(
          owner: _owner,
          speakEnabled: false,
          script: const [],
          replayScript: promptList(const ['ask_wait']),
          onBack: _back,
          body: _Waiting(label: t('ask_loading')),
        );
      case AskPhase.answered:
        final answer = flow.answer!;
        return answer.refused ? _refused(context, flow, answer, t) : _answered(context, answer, t);
    }
  }

  Widget _answered(BuildContext context, AskOut answer, String Function(String, {Map<String, Object> args}) t) {
    final sources = {
      for (final c in answer.citations)
        if (c.source.trim().isNotEmpty) c.source.trim(),
    };
    return VoiceScaffold(
      owner: _owner,
      speakEnabled: false,
      showCaption: false, // the answer itself is on screen below
      script: const [],
      replayScript: _answerScript(answer),
      onBack: _back,
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Icon(AppIcons.question, size: 64, color: AppColors.blue),
          const SizedBox(height: 12),
          _AnswerCard(key: const ValueKey('ask-answer'), text: _answerText(answer)),
          if (sources.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 10, left: 4, right: 4),
              child: Text(
                '${t('ask_sources')}: ${sources.join(', ')}',
                key: const ValueKey('ask-sources'),
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 15, color: AppColors.inkSoft),
              ),
            ),
        ],
      ),
      bottomRight: BigIconButton(
        key: const ValueKey('ask-home'),
        icon: AppIcons.house,
        semanticLabel: t('a11y_home'),
        size: 96,
        onPressed: () => context.go(Routes.home),
      ),
    );
  }

  Widget _refused(
    BuildContext context,
    AskState flow,
    AskOut answer,
    String Function(String, {Map<String, Object> args}) t,
  ) {
    final text = _answerText(answer);
    return VoiceScaffold(
      owner: _owner,
      speakEnabled: false,
      showCaption: false,
      script: const [],
      replayScript: _answerScript(answer),
      onBack: _back,
      body: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Icon(AppIcons.info, size: 72, color: AppColors.blue),
          const SizedBox(height: 8),
          Text(t('ask_refused_title'), textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineMedium),
          if (text.isNotEmpty) ...[
            const SizedBox(height: 12),
            _AnswerCard(key: const ValueKey('ask-refusal'), text: text),
          ],
          const SizedBox(height: 16),
          Center(
            child: BigIconButton(
              key: const ValueKey('ask-home'),
              icon: AppIcons.house,
              color: AppColors.card,
              foreground: AppColors.ink,
              semanticLabel: t('a11y_home'),
              size: Dimens.minTouch + 8,
              onPressed: () => context.go(Routes.home),
            ),
          ),
        ],
      ),
      bottomRight: _sent
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  key: const ValueKey('ask-expert-sent'),
                  width: 96,
                  height: 96,
                  decoration: const BoxDecoration(color: AppColors.green, shape: BoxShape.circle),
                  child: const Icon(AppIcons.tick, size: 56, color: Colors.white),
                ),
                SizedBox(
                  width: 128,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(t('expert_sent'), style: Theme.of(context).textTheme.labelLarge),
                  ),
                ),
              ],
            )
          : BigIconButton(
              key: const ValueKey('ask-expert'),
              icon: AppIcons.expert,
              color: AppColors.blue,
              size: 104,
              semanticLabel: t('a11y_expert'),
              onPressed: _sending ? null : () => unawaited(_askExpert(flow)),
            ),
    );
  }
}

/// The answer as large text on a white card.
class _AnswerCard extends StatelessWidget {
  const _AnswerCard({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: AppColors.card,
      borderRadius: BorderRadius.circular(20),
      border: Border.all(color: AppColors.line, width: 2),
    ),
    child: Text(
      text,
      style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w600, height: 1.35),
    ),
  );
}

/// Picture, words and a bar while the server looks for the answer. The bar stands still when the phone asks for
/// no animations.
class _Waiting extends StatelessWidget {
  const _Waiting({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Icon(AppIcons.question, size: 96, color: AppColors.blue),
      const SizedBox(height: 12),
      Text(label, textAlign: TextAlign.center, style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 16),
      ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: MediaQuery.disableAnimationsOf(context)
            ? Container(key: const ValueKey('ask-waiting-bar'), height: 14, color: AppColors.blue)
            : const LinearProgressIndicator(key: ValueKey('ask-waiting-bar'), minHeight: 14),
      ),
    ],
  );
}
