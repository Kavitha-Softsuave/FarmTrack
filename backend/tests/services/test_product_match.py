"""Matching typed medicine names to the product master: exact identities only, never a guess."""
import pytest

from app.config import Settings
from app.services.product_match import AMBIGUOUS, UNKNOWN, ProductMatcher, keys, tokens


@pytest.fixture(scope="module")
def matcher() -> ProductMatcher:
    return ProductMatcher(Settings(_env_file=None).data_dir)


def resolved(matcher: ProductMatcher, text: str, crop: str | None = "Apple") -> str | None:
    match = matcher.resolve(text, crop)
    return match.product_id if match.status == "resolved" else None


# ------------------------------------------------------------------------------------------------ tokens and keys
def test_tokens_drop_punctuation_case_and_percent_strengths():
    assert tokens("  Mancozeb-75% WP. ") == ["mancozeb", "wp"]
    assert tokens("Dithane M-45") == ["dithane", "m", "45"]
    assert tokens("captan 50wp") == ["captan", "50", "wp"]
    assert tokens("A + B & C") == ["a", "+", "b", "&", "c"]


def test_hindi_is_compared_without_the_nukta_dot_or_joiners():
    assert tokens("मैन्कोज़ेब") == tokens("मैन्कोजेब")
    assert tokens("a‍b") == ["ab"]


def test_keys_peel_trailing_formulation_unit_and_number_words_longest_first():
    assert list(keys(["mancozeb", "75", "wp"])) == ["mancozeb75wp", "mancozeb75", "mancozeb"]
    assert list(keys(["dithane", "m", "45"])) == ["dithanem45", "dithanem"]
    assert list(keys(["dithane", "m", "45"], numbers=False)) == ["dithanem45"]


# ------------------------------------------------------------------------------------------------ resolving
@pytest.mark.parametrize("typed", ["mancozeb", "MANCOZEB", " Mancozeb 75 WP ", "mancozeb-75%wp", "Mancozeb.", "मैन्कोज़ेब", "Dithane M-45",
                                   "indofil m 45", "Abic M-45", "P005", "p005"])
def test_mancozeb_in_all_its_spellings(matcher, typed):
    assert resolved(matcher, typed) == "P005", typed


def test_how_a_name_was_found_is_reported(matcher):
    assert matcher.resolve("p012", "Apple").via == "id"
    assert matcher.resolve("Systhane", "Apple").via == "brand"
    assert matcher.resolve("myclobutanil", "Apple").via == "active"
    assert matcher.resolve("मायक्लोब्यूटानिल", "Apple").product_id == "P012"           # the Hindi spelling of the master


def test_the_product_id_wins_even_for_another_crop(matcher):
    assert resolved(matcher, "P070", "Apple") == "P070"                                    # an explicit id is taken as typed


def test_mixtures_match_as_a_set_in_any_order(matcher):
    assert resolved(matcher, "Carbendazim + Mancozeb") == "P020"
    assert resolved(matcher, "mancozeb & carbendazim") == "P020"
    assert resolved(matcher, "Carbendazim 12% + Mancozeb 63% WP") == "P020"
    assert resolved(matcher, "Carbendazim") == "P009"                                      # the single active is not the mixture


def test_rows_of_one_identity_that_agree_on_safety_resolve_to_the_lowest_usable_id(matcher):
    assert resolved(matcher, "Mancozeb") == "P005"                                         # P005, P023 (stages) and P050 (drench)


def test_rows_that_disagree_about_the_waiting_period_are_ambiguous(matcher):
    assert matcher.resolve("Ziram", "Apple") == AMBIGUOUS                                  # P003/P042 have none, P043 has 21 days
    assert resolved(matcher, "Cuman L") == "P003"                                          # but the brand narrows it to its own rows
    assert resolved(matcher, "IPL Ziram-80") == "P043"


def test_the_crop_selects_the_rows(matcher):
    assert resolved(matcher, "mancozeb", "Tomato") == "P070"
    assert resolved(matcher, "mancozeb", "grape") == "P095"
    assert matcher.resolve("mancozeb", "Peach") == UNKNOWN
    assert resolved(matcher, "Bavistin", "Grape") == "P096"                                # the brand stands for carbendazim in any crop
    assert matcher.resolve("Bavistin", "Tomato") == UNKNOWN                                # ... but tomato has no carbendazim row


@pytest.mark.parametrize("typed", ["", "   ", "!!", "75 wp", "Local mix", "Dithane", "mancozeb and zinc", "mancozeb with sugar",
                                   "chlorpyrifos plus something"])
def test_everything_else_is_unknown(matcher, typed):
    assert matcher.resolve(typed, "Apple") == UNKNOWN


def test_without_a_crop_the_first_agreeing_identity_is_used(matcher):
    assert matcher.resolve("Bavistin", None).status == "resolved"
