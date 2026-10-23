import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/voice_scaffold.dart';

/// A screen that is only a picture and its spoken introduction. Placeholder for features that come later; each
/// feature (diary, field, alerts, ask) replaces it with its own screen under the same route.
class PlaceholderScreen extends ConsumerWidget {
  const PlaceholderScreen({super.key, required this.icon, required this.introPrompt, required this.color});

  final IconData icon;
  final String introPrompt;
  final Color color;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(stringsProvider);
    return VoiceScaffold(
      script: promptList([introPrompt]),
      body: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 150, color: color),
          const SizedBox(height: 16),
          Text(t('coming_soon'), style: Theme.of(context).textTheme.headlineSmall),
        ],
      ),
    );
  }
}
