"""Validate an advice draft (from the LLM or a template) against the RuleOutput. Returns problem codes; an empty list means valid.

What it enforces (the LLM only explains, the rules decide):
- both languages present, Hindi in Devanagari, spoken text of a sensible length
- only the rule products are named; no other master product, brand, banned or off-label name; no excluded product
- every dose figure equals the rule dose (checked per sentence when a product is named), waiting periods and other numbers
  come from the rules; numbers written as words are read back and checked too
- nothing recommends spraying when the timing is 'wait' or 'not_needed' or the status carries no medicine
- the timing action (wait, repeat within N days) is actually conveyed; no disease other than the diagnosed one is named

Trade-offs (see docs/design-notes/advice.md): the check is deliberately strict, and a rejected draft costs only the LLM wording, never safety.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

from app.advice.dose import allowed_quantities, dose_amounts
from app.advice.names import DEVA_RANGE, has_devanagari, norm_deva
from app.advice.quantities import DAYS, MASS, MM, PERCENT, VOLUME, extract_quantities
from app.advice.refdata import RefData, is_safe_note_text
from app.advice.spoken import split_sentences
from app.domain.types import AdviceDraft, LocalizedText, Note, ProductChoice, RuleOutput

SPOKEN_MIN_SENTENCES = 2
SPOKEN_MAX_SENTENCES = 8
_DOSE_FAMILIES = (MASS, VOLUME)
_SUFFIX_NAME = re.compile(r"\b[a-z]{3,}(?:conazole|strobin|thrin|mectin|cloprid|zeb|phos|fos|thion)\b", re.IGNORECASE)


def _hi(pattern: str) -> str:
    return norm_deva(pattern)


_D = DEVA_RANGE
_SPRAY_EN = re.compile(r"\b(?:spray(?:s|ed|ing)?|apply|applying|applied|drench(?:ing)?|dust(?:ing)?)\b", re.IGNORECASE)
_USE_EN = re.compile(r"\b(?:use|using|mix|mixing|dissolve|add)\b", re.IGNORECASE)
_HEDGE_EN = re.compile(
    r"\b(?:not|never|avoid|wait|waiting|until|after|once|later|delay|hold|unless|before|if|when|while|during|no|without|ask|expert|confirm)\b|n't",
    re.IGNORECASE)
_SPRAY_HI = re.compile(_hi("छिड़क|स्प्रे|स्प्रै|छिडक"))
_USE_HI = re.compile(_hi("इस्तेमाल|प्रयोग|मिला|डाल"))
_HEDGE_HI = re.compile(
    rf"(?<![{_D}])(?:नहीं|न|मत|बाद|पहले|यदि|अगर|जब|समय|बिना|विशेषज्ञ|एक्सपर्ट|जानकार)(?![{_D}])|"
    + _hi("रुक|इंतज़ार|प्रतीक्षा|टाल|पूछ|पुष्टि|पक्का|जब तक"))
_WAIT_EN = re.compile(r"\b(?:do not spray|don't spray|not to spray|should not spray|wait|hold off|delay)\b", re.IGNORECASE)
_WAIT_HI = re.compile(_hi("न छिड़कें|नहीं छिड़क|मत छिड़क|रुक|इंतज़ार|प्रतीक्षा|टाल|न करें"))
_EXPERT = {"en": re.compile(r"expert", re.IGNORECASE), "hi": re.compile(_hi("विशेषज्ञ|एक्सपर्ट|जानकार|कृषि अधिकारी"))}
_WAITING_KEYWORDS = re.compile(r"waiting|harvest|" + _hi("तुड़ाई|इंतज़ार|प्रतीक्षा|रुकने"), re.IGNORECASE)


def recommends_spraying(sentence: str, lang: str, *, include_use: bool = False) -> bool:
    """A spray/apply sentence with no 'not', 'wait', 'before', 'when', 'ask' ... in it counts as a recommendation."""
    if lang == "hi":
        text = norm_deva(sentence)
        verbs = _SPRAY_HI.search(text) or (include_use and _USE_HI.search(text))
        return bool(verbs) and not _HEDGE_HI.search(text)
    verbs = _SPRAY_EN.search(sentence) or (include_use and _USE_EN.search(sentence))
    return bool(verbs) and not _HEDGE_EN.search(sentence)


def _sentence_key(sentence: str) -> str:
    return re.sub(r"[\s.,;:!?।]+", " ", norm_deva(sentence).lower()).strip()


def _fields(draft: AdviceDraft) -> list[tuple[str, LocalizedText]]:
    fields = [("headline", draft.headline), ("summary", draft.summary), ("spoken", LocalizedText(en=draft.spoken.en, hi=draft.spoken.hi))]
    fields += [(f"steps[{i}]", s) for i, s in enumerate(draft.steps)]
    fields += [(f"safety[{i}]", s) for i, s in enumerate(draft.safety)]
    return fields


def _rule_texts(out: RuleOutput, notes: Iterable[Note]) -> tuple[list[str], list[str]]:
    """(texts written by the rules, texts of the retrieved notes): both are trusted wording."""
    rules: list[str] = []
    if out.timing:
        rules += [out.timing.text.en, out.timing.text.hi]
    for w in [*out.warnings, *(w for p in out.products for w in p.warnings)]:
        rules += [w.text.en, w.text.hi]
    for m in out.non_chemical:
        rules += [m.en, m.hi]
    for r in out.risks:
        rules += [r.title.en, r.title.hi, r.text.en, r.text.hi]
    return [t for t in rules if t], [t for n in notes for t in (n.text_en, n.text_hi) if t]


class _Context:
    def __init__(self, out: RuleOutput, ref: RefData, notes: list[Note]) -> None:
        self.out, self.ref = out, ref
        rule_texts, note_texts = _rule_texts(out, notes)
        trusted = " \n ".join([*rule_texts, *note_texts])
        # sentences copied word for word from the rules (for example 'spray 5% urea on the orchard floor') are the rules' own advice
        self.rule_sentences = {_sentence_key(s) for t in rule_texts for s in split_sentences(t)}
        self.has_medicine = out.status == "advice" and bool(out.products)
        self.action = out.timing.action if out.timing else "unknown"
        # names of the products the rules chose
        self.name_pids: dict[str, set[str]] = {}
        self.allowed_names: set[str] = set()
        self.dose_allowed: dict[str, set[tuple[str, Decimal]]] = {}
        for p in out.products:
            latin, deva = ref.names_of(p)
            for name in latin | deva:
                self.name_pids.setdefault(name, set()).add(p.product_id)
            self.allowed_names |= latin | deva
            self.dose_allowed[p.product_id] = allowed_quantities(p)
        self.trusted_names = ref.latin_matcher.find(trusted) | ref.deva_matcher.find(trusted)
        self.excluded_names: set[str] = set()
        for ex in out.excluded:
            row = ref.products.get(ex.product_id)
            if row:
                latin, deva = ref.names_of(ProductChoice(product_id=row.product_id, crop=row.crop, active_ingredient=row.active_ingredient,
                                                         active_ingredient_hi=row.active_ingredient_hi, category=""))
                self.excluded_names |= (latin | deva) - self.allowed_names
        # numbers the rules and notes already contain
        self.rule_quantities = [q for t in rule_texts for q in extract_quantities(t)]
        self.note_quantities = [q for t in note_texts for q in extract_quantities(t)]
        self.waiting_days = {Decimal(p.waiting_period_days) for p in out.products if p.waiting_period_days is not None}
        self.repeat_days = {Decimal(out.timing.repeat_within_days)} if out.timing and out.timing.repeat_within_days is not None else set()
        self.allowed_disease_ids = {d for d in (out.disease_id, out.treat_as) if d}
        self.allowed_disease_ids |= {i for n in ref.disease_latin_matcher.find(trusted) for i in ref.disease_latin[n]}
        self.allowed_disease_ids |= {i for n in ref.disease_deva_matcher.find(trusted) for i in ref.disease_deva[n]}

    def allowed_values(self, family: str, pids: set[str]) -> set[Decimal]:
        values = {q.value for q in self.rule_quantities if q.family == family}
        if family in _DOSE_FAMILIES or family == PERCENT:
            sources = [self.dose_allowed[p] for p in pids if p in self.dose_allowed] or list(self.dose_allowed.values())
            values |= {v for s in sources for f, v in s if f == family}
        elif family == DAYS:
            values |= self.waiting_days | self.repeat_days | {q.value for q in self.note_quantities if q.family == DAYS}
        else:
            values |= {q.value for q in self.note_quantities if q.family == family}
            if family == MM and self.out.timing and self.out.timing.rain_next_12h_mm is not None:
                values.add(Decimal(str(self.out.timing.rain_next_12h_mm)))
        return values


def _product_problems(text: str, ctx: _Context) -> list[str]:
    problems: list[str] = []
    ref = ctx.ref
    found = ref.latin_matcher.find(text) | ref.deva_matcher.find(text)
    for name in sorted(found):
        if name in ctx.allowed_names:
            continue
        if name in ctx.excluded_names:
            problems.append(f"excluded_product_mentioned:{name}")
        elif name in ctx.trusted_names:
            continue                                   # named by the rules themselves (checked sentence by sentence below)
        elif not (ref.latin_index.get(name) or ref.deva_index.get(name)):
            problems.append(f"banned_or_offlabel_product_mentioned:{name}")
        else:
            problems.append(f"product_not_in_rules:{name}")
    known_tokens = {tok for n in (*ref.latin_index, *ctx.allowed_names) for tok in n.split()}
    for word in sorted({w.lower() for w in _SUFFIX_NAME.findall(text)}):
        if word not in known_tokens:
            problems.append(f"unlisted_chemical_name:{word}")
    return problems


def _quantity_problems(sentence: str, lang: str, ctx: _Context) -> list[str]:
    problems: list[str] = []
    ref = ctx.ref
    found = ref.latin_matcher.find(sentence) | ref.deva_matcher.find(sentence)
    pids = {pid for name in found for pid in ctx.name_pids.get(name, ())}
    quantities = extract_quantities(sentence)
    for q in quantities:
        if q.value not in ctx.allowed_values(q.family, pids):
            code = "dose_mismatch" if q.family in (*_DOSE_FAMILIES, PERCENT) else "number_not_in_rules"
            problems.append(f"{code}:{q.text}")
    if pids and _WAITING_KEYWORDS.search(norm_deva(sentence)):
        mine = {Decimal(p.waiting_period_days) for p in ctx.out.products if p.product_id in pids and p.waiting_period_days is not None}
        for q in (x for x in quantities if x.family == DAYS):
            if q.value not in mine:
                problems.append(f"waiting_period_mismatch:{q.text}")
    return problems


def _spraying_problems(sentence: str, lang: str, ctx: _Context, no_spray_reason: str | None) -> list[str]:
    problems: list[str] = []
    masked = ctx.ref.latin_matcher.replace(sentence, lambda _name: "PRODUCT")      # a brand such as 'HP Spray Oil E' is not a verb
    if no_spray_reason and _sentence_key(sentence) not in ctx.rule_sentences \
            and recommends_spraying(masked, lang, include_use=not ctx.has_medicine):
        problems.append(f"spray_recommended_when_{no_spray_reason}")
    found = ctx.ref.latin_matcher.find(sentence) | ctx.ref.deva_matcher.find(sentence)
    if found & (ctx.trusted_names - ctx.allowed_names) and recommends_spraying(masked, lang, include_use=True):
        problems.append("recommends_product_not_in_rules")      # a product only the rules' warnings mention, offered as advice
    return problems


def _disease_problems(text: str, lang: str, ctx: _Context) -> list[str]:
    ref = ctx.ref
    names = ref.disease_latin_matcher.find(text) if lang == "en" else ref.disease_deva_matcher.find(text)
    problems = []
    for name in sorted(names):
        ids = ref.disease_latin.get(name) or ref.disease_deva.get(name) or set()
        if not ids & ctx.allowed_disease_ids:
            problems.append(f"disease_not_in_rules:{name}")
    return problems


def timing_problems(action: str, repeat_days: int | None, en: str, hi: str) -> list[str]:
    """Problem codes when the texts fail to convey the rules' timing: 'wait' must be said, 'repeat within N days' must name N."""
    problems: list[str] = []
    if action == "wait":
        if not _WAIT_EN.search(en):
            problems.append("timing_not_conveyed:en")
        if not _WAIT_HI.search(norm_deva(hi)):
            problems.append("timing_not_conveyed:hi")
    if action == "repeat_within_days" and repeat_days is not None:
        if not any(q.family == DAYS and q.value == Decimal(repeat_days) for q in extract_quantities(en)):
            problems.append("repeat_days_missing")
    return problems


def _presence_problems(draft: AdviceDraft, ctx: _Context) -> list[str]:
    problems: list[str] = []
    out = ctx.out
    texts = {"en": " ".join(f.en for _, f in _fields(draft)), "hi": " ".join(f.hi for _, f in _fields(draft))}
    if ctx.has_medicine:
        listed = {p.product_id for p in out.products}
        declared = set(draft.product_ids_mentioned)
        problems += [f"declared_product_not_in_rules:{pid}" for pid in sorted(declared - listed)]
        if not declared & listed:
            problems.append("no_product_declared")
        for lang, text in texts.items():
            found = ctx.ref.latin_matcher.find(text) | ctx.ref.deva_matcher.find(text)
            if not found & ctx.allowed_names:
                problems.append(f"no_product_named:{lang}")
            quantities = {(q.family, q.value) for q in extract_quantities(text)}
            for p in out.products:
                if p.product_id in declared and p.product_id in listed and dose_amounts(p) and not dose_amounts(p) & quantities:
                    problems.append(f"dose_missing:{p.product_id}:{lang}")
    elif draft.product_ids_mentioned:
        problems.append("product_declared_without_medicine")
    problems += timing_problems(ctx.action, out.timing.repeat_within_days if out.timing else None, texts["en"], texts["hi"])
    if out.status in ("expert_review", "no_approved_data"):
        for lang in ("en", "hi"):
            if not _EXPERT[lang].search(norm_deva(texts[lang]) if lang == "hi" else texts[lang]):
                problems.append(f"expert_not_mentioned:{lang}")
    return problems


def validate_draft(draft: AdviceDraft, out: RuleOutput, ref: RefData, notes: Iterable[Note] = ()) -> list[str]:
    """Problem codes for `draft` (empty list = valid)."""
    ctx = _Context(out, ref, list(notes))
    problems: list[str] = []

    # --- both languages, right scripts, sensible spoken length
    for name, field in _fields(draft):
        if not field.en.strip():
            problems.append(f"empty_text:{name}.en")
        if not field.hi.strip():
            problems.append(f"empty_text:{name}.hi")
        if field.hi.strip() and not has_devanagari(field.hi):
            problems.append(f"hindi_not_devanagari:{name}")
        if field.en.strip() and has_devanagari(field.en):
            problems.append(f"english_contains_devanagari:{name}")
    if ctx.has_medicine and not draft.steps:
        problems.append("no_steps")
    for lang in ("en", "hi"):
        n = len(split_sentences(getattr(draft.spoken, lang)))
        if getattr(draft.spoken, lang).strip() and not SPOKEN_MIN_SENTENCES <= n <= SPOKEN_MAX_SENTENCES:
            problems.append(f"spoken_length:{lang}:{n}")

    # --- names, numbers, spraying, per field
    no_spray_reason = None
    if not ctx.has_medicine:
        no_spray_reason = f"status_{out.status}"
    elif ctx.action in ("wait", "not_needed"):
        no_spray_reason = f"timing_{ctx.action}"
    for _name, field in _fields(draft):
        for lang in ("en", "hi"):
            text = getattr(field, lang)
            if not text.strip():
                continue
            problems += _product_problems(text, ctx)
            problems += _disease_problems(text, lang, ctx)
            if not is_safe_note_text(text):
                problems.append("phone_number_in_text")
            for sentence in split_sentences(text):
                problems += _quantity_problems(sentence, lang, ctx)
                problems += _spraying_problems(sentence, lang, ctx, no_spray_reason)
    for dose in draft.doses_mentioned:
        for q in extract_quantities(dose):
            if q.value not in ctx.allowed_values(q.family, set()):
                problems.append(f"dose_mismatch:{q.text}")

    problems += _presence_problems(draft, ctx)
    return list(dict.fromkeys(problems))

