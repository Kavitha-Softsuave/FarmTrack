import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';

enum AskPhase { idle, asking, answered, failed }

/// The question being asked or answered. The answer screen reads it.
class AskState {
  const AskState({this.question = '', this.promptId, this.phase = AskPhase.idle, this.answer, this.error});

  /// The question text sent to the server (in the app language).
  final String question;

  /// The voice prompt that speaks [question] (suggestion cards). Null for a typed question: it is not read back.
  final String? promptId;
  final AskPhase phase;
  final AskOut? answer;
  final Object? error;

  /// [answer] and [error] are replaced, not kept: a new phase starts without the old outcome.
  AskState copyWith({AskPhase? phase, AskOut? answer, Object? error}) =>
      AskState(question: question, promptId: promptId, phase: phase ?? this.phase, answer: answer, error: error);
}

final askFlowProvider = NotifierProvider<AskFlowNotifier, AskState>(AskFlowNotifier.new);

/// Sends one question at a time to `POST /v1/ask` with the app language and the farmer's main crop.
class AskFlowNotifier extends Notifier<AskState> {
  /// The server accepts 2 to 500 characters.
  static const maxLength = 500;
  static const minLength = 2;

  int _run = 0;

  @override
  AskState build() => const AskState();

  /// Starts asking [question]. Returns the answer, or null on failure (see [AskState.error]).
  Future<AskOut?> ask(String question, {String? promptId}) {
    var text = question.trim();
    if (text.length < minLength) return Future.value();
    if (text.length > maxLength) text = text.substring(0, maxLength);
    state = AskState(question: text, promptId: promptId, phase: AskPhase.asking);
    return _send(++_run);
  }

  /// Sends the same question again (the retry button of the error screen).
  Future<AskOut?> retry() {
    if (state.question.isEmpty) return Future.value();
    state = state.copyWith(phase: AskPhase.asking);
    return _send(++_run);
  }

  void reset() {
    _run++;
    state = const AskState();
  }

  Future<AskOut?> _send(int run) async {
    final farmer = ref.read(sessionProvider).farmer;
    final request = AskIn(
      question: state.question,
      language: ref.read(languageProvider),
      cropId: farmer?.primaryCrop ?? farmer?.crops.firstOrNull,
    );
    try {
      final answer = await ref.read(apiClientProvider).ask(request);
      if (run != _run) return null;
      state = state.copyWith(phase: AskPhase.answered, answer: answer);
      return answer;
    } on Object catch (e) {
      if (run != _run) return null;
      state = state.copyWith(phase: AskPhase.failed, error: e);
      return null;
    }
  }
}
