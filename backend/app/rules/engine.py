"""RulesEngine implementation: deterministic, pure, offline. Wire it with `build_rules_engine(settings, disabled_products)`."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.config import Settings
from app.domain.types import (
    FarmerProfile,
    RiskItem,
    RuleInput,
    RuleOutput,
    SprayRecord,
    WarningItem,
    WeatherSnapshot,
)
from app.interfaces import RulesEngine
from app.rules import checks
from app.rules import recommend as recommend_module
from app.rules import risks as risk_rules
from app.rules.data import ReferenceData, load_reference

DisabledProducts = Callable[[], set[str]]


class RuleBasedEngine:
    """Implements the RulesEngine protocol on the reference data in data/reference."""

    def __init__(self, ref: ReferenceData, disabled_products: DisabledProducts | None = None,
                 auto_advice_setting: str | None = None, season_check: bool = True) -> None:
        self._ref = ref
        self._season_check = season_check
        self._disabled = disabled_products
        self._auto_advice_setting = auto_advice_setting

    def _disabled_ids(self) -> frozenset[str]:
        return frozenset(self._disabled() or ()) if self._disabled else frozenset()

    def recommend(self, inp: RuleInput) -> RuleOutput:
        return recommend_module.recommend(self._ref, self._disabled_ids(), inp, self._auto_advice_setting, self._season_check)

    def evaluate_risks(self, farmer: FarmerProfile, weather: WeatherSnapshot, now: datetime,
                       history: list[SprayRecord]) -> list[RiskItem]:
        return risk_rules.evaluate(self._ref, farmer, risk_rules.farmer_crops(farmer), weather, now, history)

    def supported_crops(self) -> list[str]:
        disabled = self._disabled_ids()
        return sorted({p.crop for p in self._ref.products if p.usable and p.product_id not in disabled})

    def check_spray(self, farmer: FarmerProfile, record: SprayRecord, history: list[SprayRecord],
                    now: datetime) -> list[WarningItem]:
        return checks.check_new_spray(self._ref, farmer, record, history, now)


def build_rules_engine(settings: Settings, disabled_products: DisabledProducts | None = None) -> RulesEngine:
    """Engine on settings.data_dir/reference (loaded once and cached); `disabled_products` returns product ids an admin switched off."""
    extra = getattr(settings, "rules_auto_advice_diseases", None)        # optional setting; the env var is read by the policy itself
    season_check = bool(getattr(settings, "rules_season_check", True))
    return RuleBasedEngine(load_reference(settings.data_dir), disabled_products, extra if isinstance(extra, str) else None,
                           season_check)
