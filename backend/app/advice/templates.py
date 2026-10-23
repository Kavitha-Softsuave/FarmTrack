"""Safe template drafts (English + Hindi) for every rule status, and the lines every advice must carry.

The template is what the farmer gets when the LLM is off, fails, or fails validation. It is built only from the RuleOutput,
so it can never contain a product, dose or timing the rules did not produce.
"""
from __future__ import annotations

import re

from app.advice import phrases
from app.advice.dose import dose_text
from app.advice.names import display_brand
from app.advice.refdata import RefData
from app.advice.spoken import build_spoken, normalise_spoken
from app.advice.validator import recommends_spraying, timing_problems
from app.domain.types import (
    AdviceDraft,
    LocalizedText,
    ProductChoice,
    RuleOutput,
    Severity,
    SpokenText,
    WarningItem,
)

MAX_PRODUCTS = 3
MAX_RISKS = 2
MAX_WARNINGS = 6
_LEVEL_ORDER = {Severity.red: 0, Severity.yellow: 1, Severity.green: 2}
_PPE_MARK = {"en": re.compile(r"gloves|goggles|glasses|mask", re.I), "hi": re.compile("दस्ताने|चश्मा|मास्क")}
_EXPERT_MARK = {"en": re.compile(r"expert", re.I), "hi": re.compile("विशेषज्ञ|एक्सपर्ट|जानकार|कृषि अधिकारी")}


def _both(text: LocalizedText) -> LocalizedText:
    """Never show an empty field: a text missing one language falls back to the other."""
    return LocalizedText(en=text.en or text.hi, hi=text.hi or text.en)


def _ingredient(product: ProductChoice, ref: RefData) -> LocalizedText:
    return LocalizedText(en=product.active_ingredient,
                         hi=product.active_ingredient_hi or ref.hindi_ingredient(product.active_ingredient) or product.active_ingredient)


def _plain(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def _timing_step(out: RuleOutput) -> LocalizedText:
    """Our one-line statement of the rule action, plus the rules' own sentence unless that already says the same."""
    action = out.timing.action if out.timing else "unknown"
    repeat = out.timing.repeat_within_days if out.timing else None
    base = phrases.timing_sentence(action, repeat)
    if not out.timing or not (out.timing.text.en or out.timing.text.hi):
        return base
    rule = _both(out.timing.text)
    if _plain(base.en) in _plain(rule.en) or (action in ("wait", "repeat_within_days") and not timing_problems(action, repeat, rule.en, rule.hi)):
        return rule
    return LocalizedText(en=f"{base.en} {rule.en}", hi=f"{base.hi} {rule.hi}")


def _products(out: RuleOutput) -> list[ProductChoice]:
    return out.products[:MAX_PRODUCTS]


def _advice_steps(out: RuleOutput, ref: RefData) -> list[LocalizedText]:
    steps = [_timing_step(out)]
    steps += [_both(r.text) for r in out.risks if r.level in (Severity.red, Severity.yellow)][:MAX_RISKS]
    if len(out.products) > 1:
        steps.append(phrases.CHOOSE_ONE)
    for product in _products(out):
        brand = display_brand(product.brand_examples[0]) if product.brand_examples else ""
        steps.append(phrases.product_step(_ingredient(product, ref), brand, dose_text(product),
                                          phrases.waiting_sentence(product.waiting_period_days)))
    steps += [_both(m) for m in out.non_chemical]
    return steps


def _unique(lines: list[LocalizedText]) -> list[LocalizedText]:
    unique: dict[str, LocalizedText] = {}
    for line in lines:
        unique.setdefault(line.en, line)
    return list(unique.values())


def _measures(out: RuleOutput) -> list[LocalizedText]:
    """General protective measures when no medicine is given: the rules' own (never one that says to spray) or the generic ones."""
    own = [_both(m) for m in out.non_chemical
           if not (recommends_spraying(m.en, "en", include_use=True) or recommends_spraying(m.hi, "hi", include_use=True))]
    return own or list(phrases.GENERIC_MEASURES)


def build_template(out: RuleOutput, ref: RefData) -> AdviceDraft:
    """The safe draft for `out`. The spoken text still has digits; finalize_draft() turns them into words."""
    crop = ref.crop_name(out.crop_id)
    spoken = build_spoken(out, ref)
    if out.status == "advice" and out.products:
        disease = ref.disease_name(out.disease_id)
        shown = _products(out)
        return AdviceDraft(
            headline=phrases.advice_headline(disease, crop),
            summary=phrases.diagnosis_summary(disease, crop, out.severity.value),
            steps=_advice_steps(out, ref),
            spoken=spoken,
            product_ids_mentioned=[p.product_id for p in shown],
            doses_mentioned=[dose_text(p).en for p in shown],
        )
    if out.status == "no_approved_data":
        return AdviceDraft(headline=phrases.NO_DATA_HEADLINE, summary=phrases.no_data_summary(crop),
                           steps=_unique([*_measures(out), phrases.GENERIC_MEASURES[1]]), spoken=spoken)
    if out.status == "not_a_disease":
        return AdviceDraft(headline=phrases.NOT_DISEASE_HEADLINE, summary=phrases.not_disease_summary(crop),
                           steps=[phrases.GENERIC_MEASURES[1]], spoken=spoken)
    if out.status == "needs_more_info":
        return AdviceDraft(headline=phrases.MORE_INFO_HEADLINE, summary=phrases.MORE_INFO_SUMMARY,
                           steps=list(phrases.MORE_INFO_STEPS), spoken=spoken)
    # expert_review, and 'advice' that ended up with no approved product: plain "not sure", safe measures, no medicine
    return AdviceDraft(headline=phrases.EXPERT_HEADLINE, summary=phrases.expert_summary(crop),
                       steps=_unique([phrases.NO_SPRAY_UNTIL_EXPERT, *_measures(out)]), spoken=spoken)


def _warning_lines(out: RuleOutput, shown: list[ProductChoice]) -> list[LocalizedText]:
    items: list[WarningItem] = [*out.warnings, *(w for p in shown for w in p.warnings)]
    lines: list[LocalizedText] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda w: _LEVEL_ORDER[w.level]):
        text = _both(item.text)
        if text.en and text.en not in seen:
            seen.add(text.en)
            lines.append(text)
    return lines[:MAX_WARNINGS]


def _append_unique(target: list[LocalizedText], lines: list[LocalizedText]) -> None:
    present = {t.en.strip() for t in target}
    target.extend(line for line in lines if line.en.strip() not in present)


def finalize_draft(draft: AdviceDraft, out: RuleOutput, ref: RefData) -> AdviceDraft:
    """Add what every advice must carry, whoever wrote the draft, and turn the spoken text into words.

    Warnings from the rules, the standard safety lines (protective clothing from advisory_notes, no mixing, expert confirms) and
    the spoken protective-clothing and expert sentences are appended when missing. None of this is written by the LLM.
    """
    safety = [*draft.safety]
    spoken = SpokenText(en=draft.spoken.en.strip(), hi=draft.spoken.hi.strip())
    has_medicine = out.status == "advice" and bool(out.products)
    _append_unique(safety, _warning_lines(out, _products(out)))
    if has_medicine:
        _append_unique(safety, [*ref.safety_lines, phrases.MIXING, phrases.EXPERT_CONFIRM])
        for lang in ("en", "hi"):
            text = getattr(spoken, lang)
            if not _PPE_MARK[lang].search(text):
                text = f"{text} {getattr(phrases.PPE_SPOKEN, lang)}".strip()
            if not _EXPERT_MARK[lang].search(text):
                text = f"{text} {getattr(phrases.EXPERT_CONFIRM, lang)}".strip()
            setattr(spoken, lang, text)
    elif out.status == "expert_review":
        _append_unique(safety, [phrases.EXPERT_WILL_CONFIRM])
    return draft.model_copy(update={
        "safety": safety,
        "spoken": SpokenText(en=normalise_spoken(spoken.en, "en", ref), hi=normalise_spoken(spoken.hi, "hi", ref)),
    })

