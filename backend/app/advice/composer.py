"""AdviceComposer: the LLM explains the rule output, the validator checks it, the safe template is the fallback.

The LLM is asked only for status 'advice' (the other statuses are fixed wording that must not drift: 'the app is not sure, an
expert will look, no medicine'). Any LLM failure or any validation problem returns the template, so the farmer always gets
advice that matches the rules.
"""
from __future__ import annotations

import logging
from collections.abc import Collection

from pydantic import ValidationError

from app.advice import prompt, templates
from app.advice.refdata import RefData
from app.advice.validator import validate_draft
from app.domain.types import AdviceDraft, Note, RuleInput, RuleOutput, ValidatedAdvice
from app.interfaces import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_LLM_STATUSES = frozenset({"advice"})


class LLMAdviceComposer:
    def __init__(self, llm: LLMProvider, ref: RefData, llm_statuses: Collection[str] = DEFAULT_LLM_STATUSES) -> None:
        self._llm = llm
        self._ref = ref
        self._llm_statuses = frozenset(llm_statuses)

    def compose(self, inp: RuleInput, out: RuleOutput, notes: list[Note]) -> ValidatedAdvice:
        """`inp` is unused on purpose: nothing about the farmer may reach the prompt."""
        if out.status in self._llm_statuses:
            draft, problems = self._ask_llm(out, notes)
            if draft is not None and not problems:
                return ValidatedAdvice(draft=templates.finalize_draft(draft, out, self._ref), validated=True, used_llm=True)
            logger.warning("advice: LLM draft rejected (%s); using the safe template", ", ".join(problems))
            return self._from_template(out, llm_problems=problems)
        return self._from_template(out, llm_problems=[])

    def _from_template(self, out: RuleOutput, llm_problems: list[str]) -> ValidatedAdvice:
        template = templates.build_template(out, self._ref)
        own_problems = validate_draft(template, out, self._ref)
        if own_problems:                                  # a template that fails its own validator is a bug: say so loudly
            logger.error("advice: template draft failed validation (%s)", ", ".join(own_problems))
        problems = [*llm_problems, *own_problems]
        return ValidatedAdvice(draft=templates.finalize_draft(template, out, self._ref), validated=not problems,
                               problems=problems, used_llm=False)

    def _ask_llm(self, out: RuleOutput, notes: list[Note]) -> tuple[AdviceDraft | None, list[str]]:
        facts = prompt.build_facts(out, notes, self._ref)
        try:
            raw = self._llm.generate_json(prompt.build_prompt(facts), prompt.ADVICE_SCHEMA, prompt.ADVICE_SCHEMA_NAME)
            draft = AdviceDraft.model_validate(raw)
        except ValidationError:
            return None, ["llm_output_not_valid_schema"]
        except Exception as exc:                          # any provider failure must fall back, never break the scan
            logger.warning("advice: LLM call failed (%s)", type(exc).__name__)
            return None, [f"llm_error:{type(exc).__name__}"]
        return draft, validate_draft(draft, out, self._ref, notes)
