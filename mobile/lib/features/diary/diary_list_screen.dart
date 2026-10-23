import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import 'date_words.dart';
import 'diary_providers.dart';
import 'diary_widgets.dart';
import 'saved_speech.dart';

/// "My spray diary": newest first, each line with the crop picture, the medicine, the day in words and a badge for
/// warnings or for "waiting to send". Tapping a line says it aloud. The plus button writes a spray that was not advised.
class DiaryListScreen extends ConsumerStatefulWidget {
  const DiaryListScreen({super.key});

  @override
  ConsumerState<DiaryListScreen> createState() => _DiaryListScreenState();
}

class _DiaryListScreenState extends ConsumerState<DiaryListScreen> {
  final Object _owner = Object();

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.home);
    }
  }

  Future<void> _speakEntry(DiaryEntry entry) {
    final lang = ref.read(languageProvider);
    final t = ref.read(stringsProvider);
    final words = ref.read(dateWordsProvider);
    final name = entry.name.isEmpty ? t('diary_no_name') : entry.name;
    final items = <Utterance>[
      TextUtterance('$name, ${words.spoken(entry.date)}', lang: lang),
      if (entry.pending) const PromptUtterance('diary_waiting'),
      if (entry.warnings.isNotEmpty) const PromptUtterance('diary_warning'),
      for (final w in entry.warnings) ?warningUtterance(w, lang),
    ];
    return ref.read(voiceServiceProvider).speak(items, owner: _owner);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final now = ref.watch(clockProvider)();
    final logs = ref.watch(sprayLogsProvider);
    final pending = ref.watch(pendingSpraysProvider).items;

    // A waiting entry reached the server while the diary is open.
    ref.listen(pendingSpraysProvider.select((p) => p.sent), (previous, next) {
      if (next > (previous ?? 0)) {
        ref.read(voiceServiceProvider).speak(promptList(const ['diary_sent']), owner: _owner, interrupt: false);
      }
    });

    final failed = logs.hasError && !logs.hasValue;
    if (failed && pending.isEmpty) {
      return ErrorRetryScreen(error: logs.error!, onRetry: () => ref.invalidate(sprayLogsProvider), onBack: _back);
    }
    final loading = !logs.hasValue && !failed;
    final entries = mergeDiaryEntries(logs.value ?? const [], pending, now);
    final script = promptList([
      'diary_intro',
      if (failed) errorPromptFor(logs.error!) else if (entries.isEmpty) 'diary_empty' else 'diary_add_hint',
    ]);

    return VoiceScaffold(
      owner: _owner,
      script: script,
      speakEnabled: !loading,
      onBack: _back,
      bottomRight: BigIconButton(
        key: const ValueKey('diary-add'),
        icon: AppIcons.plus,
        color: AppColors.amber,
        foreground: AppColors.ink,
        size: 96,
        label: t('diary_add_label'),
        semanticLabel: t('diary_add_label'),
        onPressed: () => context.push(Routes.diaryAdd),
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : entries.isEmpty
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(AppIcons.notebook, size: Dimens.hero, color: AppColors.amberDark),
                const SizedBox(height: 12),
                Text(
                  t('diary_empty_title'),
                  key: const ValueKey('diary-empty'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ],
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (failed)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Row(
                      key: const ValueKey('diary-offline'),
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(AppIcons.offline, size: 36, color: AppColors.inkSoft),
                        const SizedBox(width: 8),
                        Flexible(child: Text(t('a11y_offline'), style: Theme.of(context).textTheme.titleMedium)),
                      ],
                    ),
                  ),
                for (final entry in entries)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: DiaryEntryCard(entry: entry, onTap: () => _speakEntry(entry)),
                  ),
              ],
            ),
    );
  }
}
