#!/usr/bin/env python3
"""Validate voice/prompts.json (pure standard library).

Usage:  python validate_prompts.py [path/to/prompts.json]
Prints a table of problems and exits 1 if there is any; exits 0 when clean.

The texts are turned into audio by a generated voice, so they are checked
for the ear: short sentences, numbers as words, no symbols a voice would
read out loud, and Hindi written only in Devanagari.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

MAX_SENTENCES = 2
MAX_WORDS_PER_SENTENCE = 18
LANGS = ("en", "hi")
EXPECTED_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SENTENCE_END = ".?!।"  # . ? ! and the Devanagari danda
ALLOWED_PUNCT = set(".,?!'’-।")  # ' also covers the apostrophe in "phone's"
INTERNAL_TERMS_EN = re.compile(r"\b(server|ai|model|confidence|algorithm|database)\b", re.I)
INTERNAL_TERMS_HI = ("सर्वर", "मॉडल", "एआई", "कॉन्फिडेंस", "एल्गोरिदम")

REQUIRED_IDS = """
welcome choose_language language_hindi language_english ask_phone ask_otp otp_sent otp_wrong
login_ok home_intro home_scan home_field home_diary home_ask scan_open_camera scan_hold_close
scan_one_leaf scan_daylight scan_tap_capture scan_photo_taken scan_add_more scan_send
scan_uploading scan_wait scan_retake_blurry scan_retake_dark scan_retake_far scan_retake_no_leaf
crop_confirm_prompt crop_tap_yes crop_tap_no crop_choose_other result_intro result_expert
result_no_data result_not_disease result_listen_again result_next_diary diary_intro
diary_tick_sprayed diary_saved diary_warning field_intro field_stale alert_new alert_open
ask_intro ask_type_question ask_no_answer error_no_internet error_try_again offline_saved
back_online_sent settings_speed settings_volume camera_permission notification_permission
""".split()

CROP_IDS = """
apple tomato potato maize grape pear plum peach apricot cherry walnut pomegranate kiwi
strawberry pea cauliflower cabbage capsicum beans wheat paddy barley ginger cucumber mango
citrus litchi
""".split()

EXTRA_REQUIRED_IDS = [
    "crop_is_unknown",
    "scan_add_more_yes",
    "scan_add_more_no",
    "scan_photo_count_one",
    "scan_photo_count_two",
    "scan_photo_count_three",
    "scan_photo_count_four",
    "diary_pick_product",
    "alert_read_more",
    "expert_photos_saved",
    "settings_language_changed",
    "app_updating",
    "permission_denied_camera",
]

ALL_REQUIRED = REQUIRED_IDS + [f"crop_is_{c}" for c in CROP_IDS] + EXTRA_REQUIRED_IDS


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[" + re.escape(SENTENCE_END) + r"]+", text)
    return [p.strip() for p in parts if p.strip()]


def is_devanagari_letter(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


def check_text(lang: str, text: str) -> list[str]:
    """Return the list of problems found in one prompt text."""
    problems: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["empty"]
    if text != text.strip() or "  " in text or "\n" in text:
        problems.append("extra or odd whitespace")
    if text.strip()[-1] not in SENTENCE_END:
        problems.append("does not end with . ? ! or the Hindi danda")

    sentences = split_sentences(text)
    if len(sentences) > MAX_SENTENCES:
        problems.append(f"{len(sentences)} sentences (max {MAX_SENTENCES})")
    for s in sentences:
        n = len(s.split())
        if n > MAX_WORDS_PER_SENTENCE:
            problems.append(f"sentence has {n} words (max {MAX_WORDS_PER_SENTENCE}): {s[:30]}...")

    bad_chars: set[str] = set()
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Nd":
            problems.append(f"digit {ch!r} (write numbers as words)")
            break
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] in "LM" or ch == " " or ch in ALLOWED_PUNCT:
            continue
        if cat != "Nd":
            bad_chars.add(ch)
    if bad_chars:
        problems.append("forbidden characters: " + " ".join(sorted(repr(c) for c in bad_chars)))

    if lang == "hi":
        if not any(c.isalpha() and is_devanagari_letter(c) for c in text):
            problems.append("no Devanagari")
        latin = sorted({c for c in text if c.isalpha() and not is_devanagari_letter(c)})
        if latin:
            problems.append("non-Devanagari letters in Hindi: " + "".join(latin))
        for term in INTERNAL_TERMS_HI:
            if term in text:
                problems.append(f"internal term {term}")
    else:
        if any(is_devanagari_letter(c) for c in text):
            problems.append("Devanagari inside English text")
        m = INTERNAL_TERMS_EN.search(text)
        if m:
            problems.append(f"internal term {m.group(0)!r}")
    return problems


def validate(doc: object) -> list[tuple[str, str, str]]:
    """Return (id, lang, problem) rows."""
    rows: list[tuple[str, str, str]] = []

    def bad(pid: str, lang: str, msg: str) -> None:
        rows.append((pid, lang, msg))

    if not isinstance(doc, dict):
        return [("-", "-", "top level must be an object")]
    version = doc.get("version")
    if not isinstance(version, str) or not EXPECTED_VERSION_RE.match(version):
        bad("-", "-", "version must look like 2026-10-19.1")
    if doc.get("languages") != ["hi", "en"]:
        bad("-", "-", 'languages must be ["hi", "en"]')
    if doc.get("review") != "draft_needs_native_review":
        bad("-", "-", 'review must be "draft_needs_native_review"')
    prompts = doc.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        return rows + [("-", "-", "prompts must be a non-empty list")]

    seen: set[str] = set()
    for i, p in enumerate(prompts):
        if not isinstance(p, dict):
            bad(f"#{i}", "-", "prompt must be an object")
            continue
        pid = p.get("id")
        label = pid if isinstance(pid, str) else f"#{i}"
        if not isinstance(pid, str) or not ID_RE.match(pid):
            bad(label, "-", "id must be snake_case (lowercase letters, digits, underscores)")
        elif pid in seen:
            bad(label, "-", "duplicate id")
        else:
            seen.add(pid)
        for key in ("screen", "when"):
            if not isinstance(p.get(key), str) or not p[key].strip():
                bad(label, "-", f"missing {key}")
        extra = set(p) - {"id", "screen", "when", "en", "hi", "notes"}
        if extra:
            bad(label, "-", f"unknown keys: {sorted(extra)}")
        for lang in LANGS:
            for problem in check_text(lang, p.get(lang)):
                bad(label, lang, problem)

    for pid in ALL_REQUIRED:
        if pid not in seen:
            bad(pid, "-", "required id is missing")
    return rows


def print_table(rows: list[tuple[str, str, str]]) -> None:
    headers = ("id", "lang", "problem")
    widths = [max(len(headers[c]), *(len(r[c]) for r in rows)) for c in range(3)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)))


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("prompts.json")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {path}: {exc}")
        return 1
    rows = validate(doc)
    if rows:
        print_table(rows)
        print(f"\nFAILED: {len(rows)} problem(s) in {path}")
        return 1
    print(f"OK: {len(doc['prompts'])} prompts, {len(ALL_REQUIRED)} required ids present, {path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main(sys.argv))
