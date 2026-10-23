import re

import pytest

from app.security.errors import ApiError
from app.security.otp import dev_fixed_code, generate_code, hash_otp, otp_matches
from app.security.ratelimit import SlidingWindowLimiter, enforce
from tests.fakes import plain_settings as Settings  # noqa: N813


class Ticker:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_limit_then_blocks_with_retry_after():
    ticker = Ticker()
    limiter = SlidingWindowLimiter(3, 60, clock=ticker)
    assert all(limiter.hit("k").allowed for _ in range(3))
    blocked = limiter.hit("k")
    assert not blocked.allowed and 0 < blocked.retry_after <= 60


def test_limiter_window_slides():
    ticker = Ticker()
    limiter = SlidingWindowLimiter(2, 60, clock=ticker)
    limiter.hit("k")
    ticker.now += 30
    limiter.hit("k")
    assert not limiter.hit("k").allowed
    ticker.now += 31                         # the first hit left the window, the second did not
    assert limiter.hit("k").allowed
    assert not limiter.hit("k").allowed


def test_limiter_keys_are_independent_and_denied_hits_are_not_counted():
    ticker = Ticker()
    limiter = SlidingWindowLimiter(1, 60, clock=ticker)
    assert limiter.hit("a").allowed and limiter.hit("b").allowed
    for _ in range(5):
        limiter.hit("a")
    ticker.now += 61
    assert limiter.hit("a").allowed          # five denied attempts did not extend the block


def test_limiter_bounds_memory():
    limiter = SlidingWindowLimiter(1, 60, clock=Ticker(), max_keys=10)
    for i in range(100):
        limiter.hit(f"key{i}")
    assert len(limiter._hits) <= 10


def test_enforce_raises_429_with_retry_after_header():
    limiter = SlidingWindowLimiter(1, 60, clock=Ticker())
    enforce(limiter, "k")
    with pytest.raises(ApiError) as caught:
        enforce(limiter, "k")
    assert caught.value.status_code == 429 and caught.value.code == "rate_limited"
    assert int(caught.value.headers["Retry-After"]) >= 1


def test_generated_codes_are_six_digits_with_leading_zeros():
    codes = {generate_code() for _ in range(200)}
    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
    assert len(codes) > 150


def test_hash_is_peppered_bound_to_the_request_and_never_the_code():
    a = Settings(secret_key="k1" * 20)
    b = Settings(secret_key="k2" * 20)
    digest = hash_otp(a, "req1", "123456")
    assert "123456" not in digest and len(digest) == 64
    assert digest != hash_otp(b, "req1", "123456")          # different pepper
    assert digest != hash_otp(a, "req2", "123456")          # different request
    assert otp_matches(a, "req1", "123456", digest)
    assert not otp_matches(a, "req1", "654321", digest)


@pytest.mark.parametrize("env,fixed,expected", [
    ("dev", "123456", "123456"), ("test", "123456", "123456"), ("prod", "123456", None),
    ("dev", None, None), ("dev", "abc", None), ("dev", "12", None),
])
def test_dev_fixed_code_only_outside_prod_and_only_if_valid(env, fixed, expected):
    assert dev_fixed_code(Settings(env=env, dev_fixed_otp=fixed)) == expected
