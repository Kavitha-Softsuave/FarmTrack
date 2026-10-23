"""The product default of RULES_AUTO_ADVICE_DISEASES is '*' (owner decision 19 Oct 2026); the test suite pins the narrow policy."""
from __future__ import annotations

from app.config import Settings
from app.rules.policy import ENV_VAR, auto_advice_diseases

SCAB = "Apple___Apple_scab"


def test_the_product_default_is_every_disease_with_chemical_control(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert Settings(_env_file=None).rules_auto_advice_diseases == "*"


def test_an_empty_setting_narrows_it_back_to_apple_scab(ref):
    assert auto_advice_diseases(ref.diseases, Settings(_env_file=None, rules_auto_advice_diseases="").rules_auto_advice_diseases) == {SCAB}


def test_the_default_setting_widens_the_policy_but_never_past_the_hard_guards(ref, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    allowed = auto_advice_diseases(ref.diseases, Settings(_env_file=None).rules_auto_advice_diseases)
    assert {SCAB, "Apple___Alternaria_leaf_spot", "Potato___Late_blight"} <= allowed
    assert "Tomato___Tomato_Yellow_Leaf_Curl_Virus" not in allowed        # no chemical cure
    assert "Apple___Cedar_apple_rust" not in allowed                      # expert referral
    assert "Apple___healthy" not in allowed


def test_the_test_suite_itself_runs_with_the_narrow_policy():
    import os

    assert os.environ[ENV_VAR] == ""
