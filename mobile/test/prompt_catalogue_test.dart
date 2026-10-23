import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';
import 'package:farmtrack/core/network/mock_data.dart';
import 'package:farmtrack/core/voice/prompt_catalogue.dart';

import 'support/harness.dart';

void main() {
  final catalogue = loadCatalogue();

  test('loads every fixed prompt (at least the original 120) for both languages', () {
    expect(catalogue.length, greaterThanOrEqualTo(120));
    expect(catalogue.languages, ['hi', 'en']);
    for (final id in catalogue.ids) {
      for (final lang in catalogue.languages) {
        expect(catalogue.text(id, lang).trim(), isNotEmpty, reason: '$id has no $lang text');
        expect(catalogue[id]!.text.containsKey(lang), isTrue, reason: '$id has no own $lang text');
      }
    }
  });

  test('the bundled asset is the same file as voice/prompts.json', () {
    final bundled = File('assets/voice/prompts.json').readAsStringSync();
    final source = File('../voice/prompts.json').readAsStringSync();
    expect(bundled, source, reason: 'run: python tool/sync_voice_assets.py');
  });

  test('lookup returns the right sentence per language, empty for unknown ids', () {
    expect(catalogue.text('scan_send', 'en'), contains('green tick'));
    expect(catalogue.text('scan_send', 'hi'), contains('हरा सही का निशान'));
    expect(catalogue.text('no_such_prompt', 'hi'), '');
    expect(catalogue.contains('welcome'), isTrue);
    expect(catalogue.contains('no_such_prompt'), isFalse);
    expect(catalogue['welcome']!.screen, 'language');
  });

  test('every prompt the app names exists: ids in the brief, home, scan, result and crop prompts', () {
    const needed = [
      'welcome',
      'choose_language',
      'language_hindi',
      'language_english',
      'login_intro',
      'login_ask_username',
      'login_ask_password',
      'login_tap_tick',
      'login_wrong',
      'login_fields_needed',
      'login_show_password',
      'login_hide_password',
      'login_ok',
      'login_again',
      'home_intro',
      'home_scan',
      'home_field',
      'home_diary',
      'home_ask',
      'home_settings',
      'scan_open_camera',
      'scan_hold_close',
      'scan_one_leaf',
      'scan_daylight',
      'scan_photo_taken',
      'scan_photo_count_one',
      'scan_photo_count_two',
      'scan_photo_count_three',
      'scan_photo_count_four',
      'scan_add_more',
      'scan_send',
      'scan_photo_limit',
      'scan_need_photo',
      'scan_uploading',
      'scan_wait',
      'scan_retake_blurry',
      'scan_retake_dark',
      'scan_retake_far',
      'scan_retake_no_leaf',
      'scan_retake_tap',
      'crop_confirm_prompt',
      'crop_tap_yes',
      'crop_tap_no',
      'crop_choose_other',
      'result_intro',
      'result_expert',
      'result_no_data',
      'result_not_disease',
      'result_next_diary',
      'permission_denied_camera',
      'camera_permission',
      'error_no_internet',
      'error_try_again',
      'settings_speed',
      'settings_volume',
      'settings_language_changed',
      'diary_intro',
      'field_intro',
      'alert_open',
      'ask_intro',
      'tap_green_tick',
    ];
    for (final id in needed) {
      expect(catalogue.contains(id), isTrue, reason: 'missing prompt $id');
    }
  });

  test('a crop_is_<crop> prompt exists for every crop the mock server supports', () {
    for (final crop in MockData.supportedCrops) {
      expect(catalogue.contains('crop_is_$crop'), isTrue, reason: 'crop_is_$crop');
    }
    expect(catalogue.contains('crop_is_unknown'), isTrue);
  });

  test('no prompt id used in the app source is missing from the catalogue', () {
    final quoted = RegExp(r"'([a-z]+(?:_[a-z]+)+)'");
    final callSites = RegExp(
      r'(?:PromptUtterance\(|promptList\(|speakPrompts\(|_say\(|pickPrompt\(|_tour =|const \[)([^;]*?)[\)\];]',
      dotAll: true,
    );
    final used = <String>{};
    for (final file in Directory(
      'lib',
    ).listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'))) {
      final text = file.readAsStringSync();
      for (final site in callSites.allMatches(text)) {
        for (final m in quoted.allMatches(site.group(1)!)) {
          used.add(m.group(1)!);
        }
      }
    }
    // Ids are the only snake_case literals inside these call sites except UI string keys and wire values.
    const notPrompts = {
      'spray_now',
      'not_a_disease',
      'needs_expert',
      'no_approved_data',
      'confirm_crop',
      'photo_unusable',
      'auto_advice',
      'expert_queue',
      'mark_sprayed',
      'add_photo',
      'ask_expert',
      'repeat_within_days',
      'not_needed',
      'too_dark',
      'too_bright',
      'too_small',
      'no_leaf',
      'invalid_credentials',
    };
    final promptLike = used.where((id) => !notPrompts.contains(id) && RegExp(r'^[a-z]+(_[a-z]+)+$').hasMatch(id));
    expect(promptLike.length, greaterThan(30), reason: 'the scan found too few prompt ids: the pattern is broken');
    final missing = promptLike.where((id) => !catalogue.contains(id) && !id.startsWith('a11y_')).toList()..sort();
    // UI string keys (strings.json) are looked up with t(...), not spoken: accept them.
    final resources = loadResources();
    final unknown = missing.where((id) => resources.t(id, 'en') == id).toList();
    expect(unknown, isEmpty, reason: 'ids that are neither prompts nor UI strings: $unknown');
  });

  group('resolve order', () {
    test('bundled audio first, then server audio, then plain text for speech', () {
      final c = loadCatalogue(bundledAudio: {PromptCatalogue.assetPath('hi', 'welcome')});
      expect(c.resolve('welcome', 'hi')!.bundledAsset, 'assets/voice/hi/welcome.mp3');
      expect(c.resolve('welcome', 'en')!.bundledAsset, isNull);
      expect(c.hasBundledAudio('hi', 'welcome'), isTrue);
      expect(c.hasAnyBundledAudio('hi'), isTrue);
      expect(c.hasAnyBundledAudio('en'), isFalse);

      c.applyServer(
        const VoiceCatalogueOut(
          version: 'v1',
          language: 'en',
          prompts: [
            PromptOut(
              id: 'welcome',
              text: 'Welcome (server)',
              audio: AudioRef(url: '/audio/w.mp3', sha256: 'w'),
            ),
            PromptOut(
              id: 'scan_send',
              text: '',
              audio: AudioRef(url: '/audio/s.mp3'),
            ),
          ],
        ),
      );
      final welcomeEn = c.resolve('welcome', 'en')!;
      expect(welcomeEn.bundledAsset, isNull);
      expect(welcomeEn.remote!.url, '/audio/w.mp3');
      expect(welcomeEn.text, 'Welcome (server)');
      // Empty server text keeps the bundled sentence, which the audio was generated from.
      expect(c.resolve('scan_send', 'en')!.text, contains('green tick'));
      // Bundled audio is tried before server audio (the server copy stays as the next source).
      c.applyServer(
        const VoiceCatalogueOut(
          version: 'v1',
          language: 'hi',
          prompts: [
            PromptOut(
              id: 'welcome',
              text: 'x',
              audio: AudioRef(url: '/audio/hi.mp3'),
            ),
          ],
        ),
      );
      expect(c.resolve('welcome', 'hi')!.bundledAsset, isNotNull);
      expect(c.resolve('welcome', 'hi')!.remote!.url, '/audio/hi.mp3');
      expect(c.resolve('welcome', 'hi')!.text, isNot('x'), reason: 'the caption matches the bundled audio');
      // No audio anywhere: text only (spoken by the on-device voice).
      final plain = c.resolve('ask_intro', 'hi')!;
      expect(plain.bundledAsset, isNull);
      expect(plain.remote, isNull);
      expect(plain.text, isNotEmpty);
      expect(c.serverAudio('welcome', 'en')!.sha256, 'w');
    });

    test('unknown ids resolve to null; a language without text falls back to English', () {
      expect(catalogue.resolve('nope', 'hi'), isNull);
      final c = PromptCatalogue.fromJson(
        '{"version": "1", "languages": ["hi", "en", "pa"], '
        '"prompts": [{"id": "x", "screen": "s", "en": "Hello", "hi": "नमस्ते"}]}',
      );
      final r = c.resolve('x', 'pa')!;
      expect(r.lang, 'en');
      expect(r.text, 'Hello');
    });

    test('a prompt only the server knows can still be spoken', () {
      final c = loadCatalogue();
      c.applyServer(
        const VoiceCatalogueOut(
          language: 'hi',
          prompts: [
            PromptOut(
              id: 'brand_new',
              text: 'नया वाक्य',
              audio: AudioRef(url: '/audio/n.mp3'),
            ),
          ],
        ),
      );
      expect(c.contains('brand_new'), isFalse);
      final r = c.resolve('brand_new', 'hi')!;
      expect(r.text, 'नया वाक्य');
      expect(r.remote!.url, '/audio/n.mp3');
    });
  });
}
