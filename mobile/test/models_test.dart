import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:farmtrack/core/models/models.dart';

Json obj(String source) => Json.from(jsonDecode(source) as Map);

const _lt = '{"en": "Apple", "hi": "सेब"}';

void main() {
  group('LocalizedText', () {
    test('reads en and hi and keeps unknown languages', () {
      final t = LocalizedText.fromJson(jsonDecode('{"en": "Apple", "hi": "सेब", "pa": "ਸੇਬ"}'));
      expect(t.en, 'Apple');
      expect(t.hi, 'सेब');
      expect(t.forLang('pa'), 'ਸੇਬ');
      expect(t.toJson(), {'en': 'Apple', 'hi': 'सेब', 'pa': 'ਸੇਬ'});
    });

    test('falls back to English, then Hindi, then anything; tolerates junk', () {
      expect(LocalizedText.pair(en: 'Apple').forLang('hi'), 'Apple');
      expect(LocalizedText.pair(hi: 'सेब').forLang('en'), 'सेब');
      expect(LocalizedText.fromJson(null).isEmpty, isTrue);
      expect(LocalizedText.fromJson('x').forLang('hi'), '');
      expect(LocalizedText.fromJson({'en': 3, 'hi': 'ठीक'}).forLang('en'), 'ठीक');
      expect(LocalizedText.pair(en: 'a'), LocalizedText.pair(en: 'a'));
    });
  });

  group('SpokenOut / AudioRef', () {
    final json = obj('''
      {"text": $_lt,
       "audio": {"hi": {"url": "/audio/ab12.mp3", "sha256": "ab12", "duration_s": 3.5}, "en": null},
       "extra": 1}''');

    test('parses audio per language and drops null entries', () {
      final s = SpokenOut.fromJson(json);
      expect(s.text.hi, 'सेब');
      expect(s.audio.keys, ['hi']);
      expect(s.audio['hi']!.url, '/audio/ab12.mp3');
      expect(s.audio['hi']!.sha256, 'ab12');
      expect(s.audio['hi']!.durationS, 3.5);
      expect(SpokenOut.fromJson(s.toJson()).audio['hi']!.url, '/audio/ab12.mp3');
    });

    test('is empty for missing or malformed input', () {
      expect(SpokenOut.fromJson(null).isEmpty, isTrue);
      expect(SpokenOut.fromJson({'text': 5, 'audio': 7}).isEmpty, isTrue);
    });
  });

  group('auth models', () {
    final farmer = obj('''
      {"id": "F001", "name": "Ramesh", "phone_masked": "+91 ***** *0001", "language": "hi",
       "district": "Shimla", "village": null, "crops": ["apple", "potato"], "primary_crop": "apple",
       "station_id": "ST08", "something_new": true}''');

    test('FarmerOut', () {
      final f = FarmerOut.fromJson(farmer);
      expect(f.id, 'F001');
      expect(f.village, isNull);
      expect(f.crops, ['apple', 'potato']);
      expect(FarmerOut.fromJson(f.toJson()).primaryCrop, 'apple');
    });

    test('TokenOut', () {
      final t = TokenOut.fromJson(
        obj('''
        {"access_token": "aaa", "refresh_token": "rrr", "token_type": "bearer", "expires_in": 900,
         "farmer": ${jsonEncode(farmer)}}'''),
      );
      expect(t.accessToken, 'aaa');
      expect(t.refreshToken, 'rrr');
      expect(t.expiresIn, 900);
      expect(t.farmer.name, 'Ramesh');
      expect(TokenOut.fromJson(t.toJson()).farmer.id, 'F001');
    });

    test('request bodies', () {
      expect(const LoginIn(username: 'f001', password: 'farm1234').toJson(), {
        'username': 'f001',
        'password': 'farm1234',
      });
      expect(const LoginIn(username: 'f001', password: 'farm1234', deviceId: 'd').toJson()['device_id'], 'd');
      expect(const RefreshIn(refreshToken: 'x').toJson(), {'refresh_token': 'x'});
      expect(const FarmerPatch(language: 'en').toJson(), {'language': 'en'});
      expect(const DeviceIn(platform: 'android', pushToken: 't').toJson(), {'platform': 'android', 'push_token': 't'});
    });
  });

  group('meta and voice catalogue', () {
    test('MetaOut and HealthOut', () {
      final m = MetaOut.fromJson(
        obj('''
        {"app_version": "0.1.0", "env": "dev", "demo_clock": "2026-05-12T08:00:00+05:30",
         "supported_languages": ["hi", "en"], "supported_crops": ["apple", "tomato"],
         "providers": {"llm": "mock", "bad": 3}}'''),
      );
      expect(m.supportedCrops, ['apple', 'tomato']);
      expect(m.demoClock!.year, 2026);
      expect(m.providers, {'llm': 'mock'});
      expect(HealthOut.fromJson(obj('{"status": "ok", "db": true}')).db, isTrue);
      expect(MetaOut.fromJson(obj('{}')).supportedLanguages, ['hi', 'en']);
    });

    test('VoiceCatalogueOut', () {
      final c = VoiceCatalogueOut.fromJson(
        obj('''
        {"version": "v1", "language": "hi", "prompts": [
          {"id": "welcome", "text": "स्वागत", "audio": {"url": "/audio/x.mp3", "sha256": "x"}},
          {"id": "scan_send", "text": "भेजिए", "audio": null}]}'''),
      );
      expect(c.prompts, hasLength(2));
      expect(c.prompts.first.audio!.url, '/audio/x.mp3');
      expect(c.prompts.last.audio, isNull);
      expect(VoiceCatalogueOut.fromJson(c.toJson()).prompts.first.id, 'welcome');
    });
  });

  group('scan models', () {
    final okScan = obj('''
      {"id": "s1", "status": "ok", "created_at": "2026-05-12T02:30:00Z", "photos": 2,
       "crop": {"crop_id": "apple", "name": $_lt, "confidence": 0.93, "needs_confirmation": false, "unknown": false,
                "candidates": [{"crop_id": "pear", "name": {"en": "Pear", "hi": "नाशपाती"}, "confidence": 0.1}],
                "source": "server"},
       "quality": {"usable": true, "issues": [], "tip_prompt_id": null},
       "disease": {"disease_id": "scab", "name": {"en": "Apple scab", "hi": "स्कैब"}, "confidence": 0.88,
                   "route": "auto_advice", "candidates": [{"disease_id": "scab", "name": {"en": "Scab", "hi": "स्कैब"}, "confidence": 0.88}]},
       "advice": {
         "id": "a1", "scan_id": "s1", "crop_id": "apple", "disease_id": "scab", "severity": "yellow",
         "headline": {"en": "Apple scab", "hi": "स्कैब"}, "summary": {"en": "Spray soon", "hi": "छिड़काव कीजिए"},
         "products": [{
           "product_id": "P007", "active_ingredient": {"en": "Difenoconazole", "hi": "डिफेनोकोनाज़ोल"},
           "brand_examples": ["Score"], "formulation": "25 EC", "category": "fungicide", "frac_irac_code": "3",
           "dose_text": {"en": "Thirty millilitres in two hundred litres of water.", "hi": "तीस मिलीलीटर"},
           "dose_min": 30, "dose_max": 30, "dose_unit": "ml/200L", "waiting_period_days": 14,
           "warnings": [{"code": "proposed_ban", "level": "yellow", "text": {"en": "Proposed ban", "hi": "प्रस्तावित रोक"}}]}],
         "timing": {"action": "spray_now", "text": {"en": "Spray today", "hi": "आज छिड़काव"}, "rain_next_12h_mm": 0.0, "repeat_within_days": null},
         "steps": [{"en": "Mix", "hi": "घोलिए"}], "safety": [{"en": "Wear a mask", "hi": "मास्क"}],
         "warnings": [{"code": "no_mixing", "level": "red", "text": {"en": "Do not mix", "hi": "मत मिलाइए"}}],
         "sources": ["HP 2026"], "validated": true,
         "spoken": {"text": {"en": "Spray Score", "hi": "स्कोर छिड़किए"}, "audio": {"hi": {"url": "/audio/a.mp3", "sha256": "a"}}},
         "created_at": "2026-05-12T02:30:00Z"},
       "review_task_id": null,
       "next_steps": [{"action": "mark_sprayed", "prompt_id": "result_next_diary"}],
       "spoken": {"text": {"en": "Apple scab", "hi": "स्कैब"}, "audio": {}}}''');

    test('ScanOut ok with advice, products, timing, warnings and spoken', () {
      final s = ScanOut.fromJson(okScan);
      expect(s.status, ScanStatus.ok);
      expect(s.photos, 2);
      expect(s.crop!.cropId, 'apple');
      expect(s.crop!.isKnown, isTrue);
      expect(s.crop!.candidates.single.cropId, 'pear');
      expect(s.disease!.route, DiseaseRoute.autoAdvice);
      final a = s.advice!;
      expect(a.severity, Severity.yellow);
      expect(a.products.single.doseText.en, startsWith('Thirty'));
      expect(a.products.single.waitingPeriodDays, 14);
      expect(a.products.single.warnings.single.code, 'proposed_ban');
      expect(a.timing!.action, TimingAction.sprayNow);
      expect(a.warnings.single.level, Severity.red);
      expect(a.steps.single.hi, 'घोलिए');
      expect(a.safety.single.en, 'Wear a mask');
      expect(a.spoken.audio['hi']!.sha256, 'a');
      expect(s.promptsFor(NextAction.markSprayed), ['result_next_diary']);
    });

    test('ScanOut survives a to/from JSON round trip', () {
      final again = ScanOut.fromJson(ScanOut.fromJson(okScan).toJson());
      expect(again.advice!.products.single.productId, 'P007');
      expect(again.advice!.createdAt, isNotNull);
      expect(again.nextSteps.single.action, NextAction.markSprayed);
    });

    test('every status parses; an unknown status becomes needs_expert', () {
      for (final status in ScanStatus.values) {
        expect(ScanStatus.parse(status.wire), status);
      }
      expect(ScanStatus.parse('brand_new_status'), ScanStatus.needsExpert);
      expect(ScanStatus.parse(null), ScanStatus.needsExpert);
    });

    test('photo_unusable carries the quality tip', () {
      final s = ScanOut.fromJson(
        obj('''
        {"id": "s2", "status": "photo_unusable", "created_at": "2026-05-12T02:30:00Z", "photos": 1, "crop": null,
         "quality": {"usable": false, "issues": ["blurry"], "tip_prompt_id": "scan_retake_blurry"},
         "disease": null, "advice": null, "next_steps": [{"action": "retake", "prompt_id": "scan_retake_tap"}],
         "spoken": {"text": {"en": "Not clear", "hi": "साफ़ नहीं"}}}'''),
      );
      expect(s.status, ScanStatus.photoUnusable);
      expect(s.quality.usable, isFalse);
      expect(s.quality.tipPromptId, 'scan_retake_blurry');
      expect(s.crop, isNull);
      expect(s.advice, isNull);
    });

    test('confirm_crop and unknown crop', () {
      final s = ScanOut.fromJson(
        obj('''
        {"id": "s3", "status": "confirm_crop", "created_at": "2026-05-12T02:30:00Z", "photos": 1,
         "crop": {"crop_id": null, "name": null, "confidence": 0.2, "needs_confirmation": true, "unknown": true, "candidates": [], "source": "stub"},
         "quality": {"usable": true}, "spoken": {"text": {"en": "?", "hi": "?"}}}'''),
      );
      expect(s.crop!.isKnown, isFalse);
      expect(s.crop!.needsConfirmation, isTrue);
    });

    test('tolerates missing, null and wrong-typed fields', () {
      final s = ScanOut.fromJson(
        obj('{"id": 5, "status": null, "photos": "x", "crop": 3, "next_steps": "no", "unexpected": {}}'),
      );
      expect(s.id, '');
      expect(s.photos, 0);
      expect(s.crop, isNull);
      expect(s.nextSteps, isEmpty);
      expect(s.quality.usable, isTrue);
      expect(AdviceOut.fromJson(obj('{}')).severity, Severity.yellow);
    });

    test('ScanListOut, CropConfirmIn, ExpertRequest', () {
      final l = ScanListOut.fromJson(obj('{"items": [${jsonEncode(okScan)}], "next_cursor": "c2"}'));
      expect(l.items.single.id, 's1');
      expect(l.nextCursor, 'c2');
      expect(const CropConfirmIn(cropId: 'apple').toJson(), {'crop_id': 'apple'});
      expect(const ExpertRequestIn(scanId: 's1').toJson(), {'scan_id': 's1'});
      expect(const ExpertRequestIn(scanId: 's1', message: 'help').toJson()['message'], 'help');
      expect(ExpertRequestOut.fromJson(obj('{"id": "e1", "status": "open"}')).status, 'open');
    });

    test('enums parse every wire value and fall back safely', () {
      for (final v in TimingAction.values) {
        expect(TimingAction.parse(v.wire), v);
      }
      for (final v in NextAction.values) {
        expect(NextAction.parse(v.wire), v);
      }
      expect(DiseaseRoute.parse('expert_queue'), DiseaseRoute.expertQueue);
      expect(DiseaseRoute.parse('???'), DiseaseRoute.none);
      expect(Severity.parse('purple'), Severity.yellow);
      expect(NextAction.parse('dance'), NextAction.unknown);
    });
  });

  group('diary, field, alerts, ask', () {
    test('SprayLogIn / SprayLogOut', () {
      final body = SprayLogIn(
        cropId: 'apple',
        adviceId: 'a1',
        productId: 'P007',
        sprayedAt: DateTime.utc(2026, 5, 12, 3),
        notes: 'done',
      ).toJson();
      expect(body['crop_id'], 'apple');
      expect(body['sprayed_at'], '2026-05-12T03:00:00.000Z');
      expect(body.containsKey('free_text'), isFalse);

      final out = SprayLogOut.fromJson(
        obj('''
        {"id": "l1", "crop_id": "apple", "product_id": "P007", "product_name": "Score",
         "sprayed_at": "2026-05-12T03:00:00Z", "advice_id": "a1",
         "warnings": [{"code": "nutrient_same_day", "level": "yellow", "text": {"en": "Do not mix", "hi": "मत मिलाइए"}}],
         "synced_to_zoho": true, "spoken": {"text": {"en": "Saved", "hi": "लिख दिया"}}}'''),
      );
      expect(out.productName, 'Score');
      expect(out.warnings.single.code, 'nutrient_same_day');
      expect(out.syncedToZoho, isTrue);
      expect(out.spoken!.text.hi, 'लिख दिया');
      expect(SprayLogOut.fromJson(obj('{"id": "x"}')).spoken, isNull);
      expect(SprayLogOut.fromJson(out.toJson()).id, 'l1');
    });

    test('FieldOut with readings, forecast and risks', () {
      final f = FieldOut.fromJson(
        obj('''
        {"station_id": "ST08", "village": "Kotgarh", "as_of": "2026-05-12T02:30:00Z", "stale": true,
         "readings": {"temp_c": 17.5, "rh_pct": 82, "rain_24h_mm": 6.5, "leaf_wetness_min": 340, "soil_moisture_pct": null},
         "forecast": [{"day": "2026-05-13", "tmin_c": 8, "tmax_c": 19.5, "rain_mm": 0}],
         "risks": [{"id": "scab", "level": "red", "title": {"en": "Scab risk", "hi": "ख़तरा"}, "text": {"en": "Wet", "hi": "गीला"}}],
         "spoken": {"text": {"en": "Warm", "hi": "गर्म"}}}'''),
      );
      expect(f.stale, isTrue);
      expect(f.readings!.tempC, 17.5);
      expect(f.readings!.leafWetnessMin, 340);
      expect(f.readings!.soilMoisturePct, isNull);
      expect(f.forecast.single.tmaxC, 19.5);
      expect(f.risks.single.level, Severity.red);
      expect(FieldOut.fromJson(f.toJson()).village, 'Kotgarh');
      expect(FieldOut.fromJson(obj('{}')).readings, isNull);
    });

    test('AlertOut and AlertListOut', () {
      final list = AlertListOut.fromJson(
        obj('''
        {"items": [{"id": "al1", "kind": "rain_wash", "level": "red", "title": {"en": "Rain", "hi": "बारिश"},
                    "body": {"en": "Spray again", "hi": "दोबारा"}, "spoken": {"text": {"en": "Rain", "hi": "बारिश"}},
                    "created_at": "2026-05-12T02:30:00Z", "read_at": null}], "unread": 1}'''),
      );
      expect(list.unread, 1);
      expect(list.items.single.isRead, isFalse);
      expect(list.items.single.level, Severity.red);
      final read = AlertOut.fromJson(obj('{"id": "al2", "read_at": "2026-05-12T03:00:00Z"}'));
      expect(read.isRead, isTrue);
      expect(AlertListOut.fromJson(list.toJson()).items.single.kind, 'rain_wash');
    });

    test('AskIn and AskOut', () {
      expect(const AskIn(question: 'q').toJson(), {'question': 'q', 'language': 'hi'});
      expect(const AskIn(question: 'q', language: 'en', cropId: 'apple').toJson()['crop_id'], 'apple');
      final a = AskOut.fromJson(
        obj(
          '''
        {"answer": "Spray Score", "language": "en", "refused": false,
         "citations": [{"note_id": "N1", "source": "HP 2026"}], "spoken": {"text": {"en": "Spray Score", "hi": "स्कोर"}}}''',
        ),
      );
      expect(a.citations.single.noteId, 'N1');
      expect(a.spoken!.text.en, 'Spray Score');
      expect(AskOut.fromJson(obj('{"answer": "", "language": "hi", "refused": true}')).refused, isTrue);
      expect(AskOut.fromJson(a.toJson()).answer, 'Spray Score');
    });
  });

  group('ErrorOut', () {
    test('parses the API error shape and tolerates anything else', () {
      final e = ErrorOut.fromJson(
        obj('{"code": "invalid_credentials", "message": "Wrong", "details": {"attempts_left": 2}}'),
      );
      expect(e.code, 'invalid_credentials');
      expect(e.details!['attempts_left'], 2);
      expect(ErrorOut.fromJson(obj('{}')).code, 'unknown');
      expect(ErrorOut.fromJson(e.toJson()).message, 'Wrong');
    });
  });
}
