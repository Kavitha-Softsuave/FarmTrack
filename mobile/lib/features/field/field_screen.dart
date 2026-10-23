import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/models/models.dart';
import '../../core/providers.dart';
import '../../core/router/routes.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/haptics.dart';
import '../../core/voice/utterance.dart';
import '../../core/widgets/big_buttons.dart';
import '../../core/widgets/status_views.dart';
import '../../core/widgets/voice_scaffold.dart';
import '../diary/date_words.dart';
import 'field_providers.dart';
import 'field_widgets.dart';
import 'field_words.dart';

/// Route `/field`: "My field". Big picture tiles with a word for the weather now, risk cards (scab first), a
/// seven-day strip, and a round arrow to look again. It says the server's spoken summary when it opens.
///
/// Old information (a quiet sensor, or the last answer kept on the phone because there is no internet) is marked on
/// the screen and announced with `field_stale`; an answer with nothing in it says `field_no_data`.
class FieldScreen extends ConsumerStatefulWidget {
  const FieldScreen({super.key});

  @override
  ConsumerState<FieldScreen> createState() => _FieldScreenState();
}

class _FieldScreenState extends ConsumerState<FieldScreen> {
  final Object _owner = Object();
  bool _reloading = false;

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(Routes.home);
    }
  }

  /// What to say for [view]: the intro (first time only), the stale / no-data prompts when the server's own spoken
  /// text does not already say them, and the server's summary.
  List<Utterance> _script(FieldView view, {bool intro = true}) {
    final lang = ref.read(languageProvider);
    final catalogue = ref.read(promptCatalogueProvider);
    final spoken = view.field.spoken.toUtterance(lang);
    bool says(String promptId) => spoken != null && spoken.text.contains(catalogue.text(promptId, lang));
    return [
      if (intro) const PromptUtterance('field_intro'),
      // The old answer's own summary is not read out: its weather is not today's.
      if (view.fromCache)
        const PromptUtterance('field_stale')
      else if (view.hasNoData) ...[
        if (!says('field_no_data')) const PromptUtterance('field_no_data'),
        ?spoken,
        const PromptUtterance('field_reload'),
      ] else ...[
        if (view.field.stale && !says('field_stale')) const PromptUtterance('field_stale'),
        ?spoken,
      ],
    ];
  }

  Future<void> _reload() async {
    if (_reloading) return;
    final voice = ref.read(voiceServiceProvider);
    setState(() => _reloading = true);
    ref.invalidate(fieldProvider);
    try {
      final view = await ref.read(fieldProvider.future);
      if (!mounted) return;
      final script = _script(view, intro: false);
      // Fresh information is announced as such before it is read out.
      final fresh = !view.isOld && !view.hasNoData;
      await voice.speak([if (fresh) const PromptUtterance('field_updated_ok'), ...script], owner: _owner);
    } on Object catch (e) {
      Haptics.error();
      await voice.speak(promptList([errorPromptFor(e)]), owner: _owner);
    } finally {
      if (mounted) setState(() => _reloading = false);
    }
  }

  Future<void> _say(String sentence) {
    final lang = ref.read(languageProvider);
    return ref.read(voiceServiceProvider).speak([TextUtterance(sentence, lang: lang)], owner: _owner);
  }

  Future<void> _sayRisk(RiskOut risk) {
    final lang = ref.read(languageProvider);
    // Title and text together, in every language the server sent, so a fallback language is spoken in its own voice.
    final text = LocalizedText({
      for (final code in {...risk.title.values.keys, ...risk.text.values.keys})
        code: [
          risk.title.values[code],
          risk.text.values[code],
        ].whereType<String>().where((s) => s.isNotEmpty).join('. '),
    });
    final utterance = SpokenOut(text: text).toUtterance(lang);
    return utterance == null ? Future.value() : ref.read(voiceServiceProvider).speak([utterance], owner: _owner);
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(stringsProvider);
    final words = ref.watch(dateWordsProvider);
    final field = ref.watch(fieldProvider);

    if (field.hasError && !field.hasValue) {
      return ErrorRetryScreen(error: field.error!, onRetry: () => ref.invalidate(fieldProvider), onBack: _back);
    }
    final view = field.value;
    final theme = Theme.of(context).textTheme;

    return VoiceScaffold(
      owner: _owner,
      script: view == null ? const [] : _script(view),
      speakEnabled: view != null,
      onBack: _back,
      bottomRight: BigIconButton(
        key: const ValueKey('field-reload'),
        icon: AppIcons.roundArrow,
        size: 96,
        semanticLabel: t('field_reload_label'),
        label: t('field_reload_label'),
        onPressed: _reloading || view == null ? null : _reload,
      ),
      body: view == null
          ? const Center(child: CircularProgressIndicator())
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_reloading) const Padding(padding: EdgeInsets.only(bottom: 8), child: LinearProgressIndicator()),
                if (view.isOld && !view.hasNoData) ...[
                  OldInfoBanner(since: view.fromCache ? view.savedAt : null),
                  const SizedBox(height: 12),
                ],
                _header(view.field, words, theme),
                if (view.hasNoData)
                  const Padding(padding: EdgeInsets.symmetric(vertical: 24), child: NoFieldData())
                else ...[
                  // The danger first: it is what the farmer must see without scrolling.
                  if (view.field.risks.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text(t('field_risks_title'), style: theme.titleLarge),
                    const SizedBox(height: 8),
                    for (final risk in sortedRisks(view.field.risks))
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: RiskCard(risk: risk, onSpeak: () => _sayRisk(risk)),
                      ),
                  ],
                  const SizedBox(height: 12),
                  ReadingTiles(tiles: readingTiles(view.field.readings), onSpeak: _say),
                  if (view.field.forecast.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    Text(t('field_forecast_title'), style: theme.titleLarge),
                    const SizedBox(height: 8),
                    ForecastStrip(days: view.field.forecast.take(7).toList()),
                  ],
                ],
              ],
            ),
    );
  }

  /// The village, and when the information is from (small digits).
  Widget _header(FieldOut field, DateWords words, TextTheme theme) {
    final village = field.village;
    final asOf = field.asOf;
    if ((village == null || village.isEmpty) && asOf == null) return const SizedBox.shrink();
    final local = asOf?.toLocal();
    final time = local == null
        ? ''
        : '${words.written(local)}, ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    return Column(
      children: [
        if (village != null && village.isNotEmpty)
          Text(village, key: const ValueKey('field-village'), textAlign: TextAlign.center, style: theme.headlineSmall),
        if (time.isNotEmpty)
          Text(
            time,
            key: const ValueKey('field-as-of'),
            style: theme.bodyMedium?.copyWith(color: AppColors.inkSoft),
          ),
      ],
    );
  }
}
