import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers.dart';
import 'utterance.dart';
import 'voice_service.dart';

/// The speech of one screen visit: who owns it and how to play it again.
class VoiceSession {
  const VoiceSession({required this.owner, required this.script, required this.replay});

  final Object owner;
  final List<Utterance> script;
  final Future<void> Function() replay;

  static VoiceSession? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_VoiceSessionScope>()?.session;
}

class _VoiceSessionScope extends InheritedWidget {
  const _VoiceSessionScope({required this.session, required super.child});

  final VoiceSession session;

  @override
  bool updateShouldNotify(_VoiceSessionScope oldWidget) => oldWidget.session.script != session.script;
}

/// Speaks [script] once when the screen appears (once per visit), and stops when the screen goes away.
///
/// The speech starts after the first frame, so the screen is already visible. Changing [restartKey] speaks the
/// (new) script again, for screens whose content changes while they are open. The farmer's language, speed and
/// volume settings are applied by the [VoiceService]; captions are shown by `VoiceCaption`.
class SpeakOnEnter extends ConsumerStatefulWidget {
  const SpeakOnEnter({
    super.key,
    required this.script,
    required this.child,
    this.replayScript,
    this.restartKey,
    this.enabled = true,
    this.owner,
  });

  /// Identifies this screen's speech. A screen that speaks in answer to taps creates one and passes the same
  /// object to `VoiceService.speak(owner: ...)`, so those sentences get the screen's caption too.
  final Object? owner;

  final List<Utterance> script;

  /// What the speaker button plays; defaults to [script] (use it when the first visit says more or less).
  final List<Utterance>? replayScript;
  final Widget child;
  final Object? restartKey;

  /// Set to false while the screen has nothing to say yet (for example while data loads).
  final bool enabled;

  @override
  ConsumerState<SpeakOnEnter> createState() => _SpeakOnEnterState();
}

class _SpeakOnEnterState extends ConsumerState<SpeakOnEnter> {
  late final VoiceService _voice;

  Object get _owner => widget.owner ?? this;

  @override
  void initState() {
    super.initState();
    _voice = ref.read(voiceServiceProvider);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _speak();
    });
  }

  @override
  void didUpdateWidget(SpeakOnEnter oldWidget) {
    super.didUpdateWidget(oldWidget);
    final becameEnabled = widget.enabled && !oldWidget.enabled;
    if (becameEnabled || (widget.enabled && widget.restartKey != oldWidget.restartKey)) {
      // Not during build: speaking updates the caption, which rebuilds widgets.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _speak();
      });
    }
  }

  void _speak() {
    if (!widget.enabled || widget.script.isEmpty) return;
    unawaited(_voice.speak(widget.script, owner: _owner));
  }

  Future<void> _replay() => _voice.speak(widget.replayScript ?? widget.script, owner: _owner);

  @override
  void dispose() {
    // Only stops our own speech: the next screen may already have started talking. Deferred, because the voice
    // state notifies widgets and the widget tree is locked while a screen is being removed.
    final owner = _owner;
    scheduleMicrotask(() => unawaited(_voice.stop(owner: owner)));
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _VoiceSessionScope(
    session: VoiceSession(owner: _owner, script: widget.replayScript ?? widget.script, replay: _replay),
    child: widget.child,
  );
}
