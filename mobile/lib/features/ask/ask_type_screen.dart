import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'ask_flow.dart';

/// Route `/ask/type`: the farmer types a question with the phone's own keyboard (at most 500 characters), then taps
/// the green tick. The question goes to the server in the app language, with the farmer's main crop.
class AskTypeScreen extends ConsumerStatefulWidget {
  const AskTypeScreen({super.key});

  @override
  ConsumerState<AskTypeScreen> createState() => _AskTypeScreenState();
}

class _AskTypeScreenState extends ConsumerState<AskTypeScreen> {
  final TextEditingController _controller = TextEditingController();

  bool get _canSend => _controller.text.trim().length >= AskFlowNotifier.minLength;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _send() {
    if (!_canSend || !(ModalRoute.of(context)?.isCurrent ?? true)) return;
    unawaited(ref.read(askFlowProvider.notifier).ask(_controller.text));
    // The answer replaces this screen, so "back" from the answer returns to the cards.
    context.pushReplacement(Routes.askAnswer);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      script: promptList(const ['ask_type_question', 'ask_tap_send']),
      body: TextField(
        key: const ValueKey('ask-field'),
        controller: _controller,
        autofocus: true,
        maxLength: AskFlowNotifier.maxLength,
        minLines: 3,
        maxLines: 8,
        keyboardType: TextInputType.multiline,
        textCapitalization: TextCapitalization.sentences,
        style: Theme.of(context).textTheme.titleMedium,
        decoration: InputDecoration(
          hintText: t('ask_type_hint'),
          hintStyle: Theme.of(context).textTheme.titleMedium?.copyWith(color: AppColors.inkSoft),
          filled: true,
          fillColor: AppColors.card,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(20),
            borderSide: const BorderSide(color: AppColors.ink, width: 2),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(20),
            borderSide: const BorderSide(color: AppColors.blue, width: 3),
          ),
        ),
      ),
      bottomRight: TickButton(
        key: const ValueKey('ask-send'),
        semanticLabel: t('ask_send'),
        onPressed: _canSend ? _send : null,
      ),
    );
  }
}
