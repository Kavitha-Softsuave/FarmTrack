import '../../core/models/models.dart';
import '../../core/voice/prompt_catalogue.dart';

/// The first of [serverIds] that the app has a prompt for (the server is the source of truth), else [fallback].
String pickPrompt(Iterable<String> serverIds, String fallback, PromptCatalogue catalogue) {
  for (final id in serverIds) {
    if (catalogue.contains(id)) return id;
  }
  return fallback;
}

/// Quality tip prompt per issue: blurry, too dark or too bright, too small, no leaf.
const _issueTips = {
  'blurry': 'scan_retake_blurry',
  'too_dark': 'scan_retake_dark',
  'too_bright': 'scan_retake_dark',
  'too_small': 'scan_retake_far',
  'no_leaf': 'scan_retake_no_leaf',
};

/// What to say about an unusable photo: the server's `tip_prompt_id`, else our mapping of its issues.
String qualityTipPrompt(QualityOut? quality, PromptCatalogue catalogue) {
  if (quality == null) return 'scan_retake_blurry';
  final tip = quality.tipPromptId;
  if (tip != null && catalogue.contains(tip)) return tip;
  for (final issue in quality.issues) {
    final mapped = _issueTips[issue];
    if (mapped != null) return mapped;
  }
  return 'scan_retake_blurry';
}

/// The prompt that names a detected crop (`crop_is_apple`), or null when the catalogue has none for it.
String? cropPrompt(String? cropId, PromptCatalogue catalogue) {
  if (cropId == null || cropId.isEmpty) return null;
  final id = 'crop_is_${cropId.toLowerCase()}';
  return catalogue.contains(id) ? id : null;
}
