# Voice prompts: notes for the native Hindi reviewer and the app agents

All Hindi is a DRAFT (`"review": "draft_needs_native_review"`). Run `python voice/validate_prompts.py` after every edit.

## Wording a native speaker should check
- **Crop sentence.** Brief said "यह <फसल> लगती है"; I wrote "यह <नाम> की फसल लगती है" (e.g. "यह सेब की फसल लगती है") so the verb agrees with every crop (the crop names mix genders). Beans uses the oblique plural "फलियों की फसल".
- **citrus = नींबू** is narrower than the group (malta, orange, lemon); consider "संतरा-नींबू वाली फसल".
- **Buttons by picture:** green tick = "हरा सही का निशान", red cross = "लाल क्रॉस का निशान", plus = "प्लस का निशान", speaker = "स्पीकर वाली तस्वीर", notebook = "कॉपी वाली तस्वीर", gear = "दाँतों वाले पहिये की तस्वीर", bell, cloud, house, left arrow. Check each is what a farmer calls it.
- **Loanwords kept** because they are spoken daily: मैसेज (instead of संदेश), बटन, डायरी, इंटरनेट, सेटिंग, स्पीकर. "ऐप" is avoided: the product is spoken as फार्मट्रैक.
- **Farm words:** "छिड़काव" (spray), "दवा" (medicine), "खेती के जानकार" for agronomist/expert (instead of "विशेषज्ञ"), "सूचना" for alert, "पन्ना" for screen.
- **No first-person verbs** in Hindi (मैं बताऊँगा/बताऊँगी) so any voice gender works; passive or "हम" style used. English crop_is_unknown keeps "I".
- `language_hindi` / `language_english`: only the language name; play the hi text in the hi voice and the en text in the en voice.
- `scan_retake_dark` joins two cases (too dark, too bright) in one sentence on purpose (one prompt for both quality tips).
- App name "FarmTrack" is assumed from the repo name; change in welcome, camera_permission, notification_permission, app_updating if the product name differs.

## Decisions and cautions
- No digits anywhere: numbers are words (ten, six, one..four). `scan_photo_count_*` stops at four because `max_photos_per_scan` is 4; add more if that setting changes.
- `result_not_disease` deliberately does not say "healthy" (we cannot promise it). `expert_will_call_back` is a promise: only play it if the operations team really calls back.
- `diary_warning` and `result_intro` are only lead-ins; the real warning/advice text is dynamic (backend spoken version).
- Optional ids that depend on screen design (delete if unused): otp_resend, home_settings, scan_remove_photo, field_tap_weather, field_updated_ok, nav_home, nav_back, alert_none, ask_wait, login_again, phone_not_found.
- Replay hint `result_listen_again` is written to be usable on any screen. Location permission prompt was not added (location not in the farmer flow).
