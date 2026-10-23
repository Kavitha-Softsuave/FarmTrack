"""Auto-advice policy: which diseases may receive medicine advice without an agronomist.

Field tests (data/model_test/review_2026-10-19.md) showed that only apple scab is recognised with any reliability and that
confidence values do not separate right from wrong. So by default ONLY apple scab gets automatic product advice; every
other disease goes to the expert queue with general non-chemical measures.

RULES_AUTO_ADVICE_DISEASES extends the set: a comma list of catalogue disease ids, or '*' for every catalogue disease
whose chemical_control is 'yes'. The variable is read on every call so tests and operators can change it without a restart. The same value may also come from a
`rules_auto_advice_diseases` setting (read from the .env file, which is not exported to os.environ); both sources are added.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from app.rules.data import Disease

AUTO_ADVICE: frozenset[str] = frozenset({"Apple___Apple_scab"})
ENV_VAR = "RULES_AUTO_ADVICE_DISEASES"


def auto_advice_diseases(catalogue: Mapping[str, Disease], configured: str | None = None) -> frozenset[str]:
    """The default set plus what RULES_AUTO_ADVICE_DISEASES and the optional `configured` setting value add."""
    items: set[str] = set()
    for raw in (os.environ.get(ENV_VAR, ""), configured or ""):
        items.update(part.strip() for part in raw.split(",") if part.strip())
    extra = set(items - {"*"})
    if "*" in items:
        extra.update(d.disease_id for d in catalogue.values() if d.chemical_control == "yes")
    return AUTO_ADVICE | frozenset(extra)


def is_auto_advice(disease_id: str, catalogue: Mapping[str, Disease], configured: str | None = None) -> bool:
    return disease_id in auto_advice_diseases(catalogue, configured)
