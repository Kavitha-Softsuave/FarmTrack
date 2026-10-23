"""Password hashing and the username/password rules (stdlib PBKDF2, no plain passwords anywhere)."""
import hashlib

import pytest

from app.security import passwords
from app.security.passwords import (
    PRODUCTION_ITERATIONS,
    hash_password,
    normalize_username,
    password_problem,
    verify_password,
)


def test_production_cost_is_at_least_150k_iterations():
    assert PRODUCTION_ITERATIONS >= 150_000


def test_stored_format_is_algo_params_salt_hash():
    stored = hash_password("farm1234", iterations=PRODUCTION_ITERATIONS)
    algorithm, iterations, salt, digest = stored.split("$")
    assert algorithm == "pbkdf2_sha256" and int(iterations) == PRODUCTION_ITERATIONS
    assert len(bytes.fromhex(salt)) == 16 and len(bytes.fromhex(digest)) == 32
    assert "farm1234" not in stored and len(stored) <= 255                     # fits the String(255) column
    expected = hashlib.pbkdf2_hmac("sha256", b"farm1234", bytes.fromhex(salt), PRODUCTION_ITERATIONS, dklen=32)
    assert bytes.fromhex(digest) == expected                                    # plain PBKDF2-HMAC-SHA256, nothing exotic


def test_the_right_password_verifies_and_a_wrong_one_does_not():
    stored = hash_password("farm1234")
    assert verify_password("farm1234", stored)
    assert not verify_password("farm1235", stored)
    assert not verify_password("", stored)
    assert not verify_password("FARM1234", stored)


def test_every_hash_has_its_own_random_salt():
    assert hash_password("same-password") != hash_password("same-password")


def test_the_iteration_count_comes_from_the_stored_hash():
    old = hash_password("farm1234", iterations=2_000)
    assert verify_password("farm1234", old)                                    # still verifies after the default changes


@pytest.mark.parametrize("stored", [None, "", "plain-text", "a$b$c", "pbkdf2_sha256$x$00$00", "pbkdf2_sha256$1000$zz$zz",
                                    "md5$1000$00$00", "pbkdf2_sha256$0$00$00", "pbkdf2_sha256$99999999999$00$00",
                                    "pbkdf2_sha256$1000$00$", "pbkdf2_sha256$1000$00$00$00"])
def test_a_missing_or_malformed_hash_never_matches_and_never_raises(stored):
    assert verify_password("anything", stored) is False


def test_the_decoy_check_costs_a_real_verification(monkeypatch):
    calls = []
    real = passwords._derive
    monkeypatch.setattr(passwords, "_derive", lambda *a: calls.append(a) or real(*a))
    passwords.burn_password_check("whatever")
    assert len(calls) == 1 and calls[0][2] == passwords.DEFAULT_ITERATIONS


@pytest.mark.parametrize("raw,expected", [("f001", "f001"), ("F001", "f001"), ("  Dinesh.Sharma ", "dinesh.sharma"), ("a_b-c", "a_b-c"),
                                          ("abc", "abc"), ("a" * 40, "a" * 40)])
def test_valid_usernames_are_lower_cased(raw, expected):
    assert normalize_username(raw) == expected


@pytest.mark.parametrize("raw", ["", "ab", "a" * 41, "has space", "slash/name", "umlautü", "a@b", "name!", "हिन्दी"])
def test_invalid_usernames_are_refused(raw):
    assert normalize_username(raw) is None


def test_the_only_password_rule_is_the_length():
    assert password_problem("123456") is None
    assert password_problem("aaaaaa") is None                                    # no composition rules
    assert password_problem("12345") is not None
    assert password_problem("x" * passwords.MAX_PASSWORD_LENGTH) is None
    assert password_problem("x" * (passwords.MAX_PASSWORD_LENGTH + 1)) is not None
