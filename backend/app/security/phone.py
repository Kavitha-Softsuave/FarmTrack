"""Phone number normalisation. Stored form: '+' and digits only, e.g. '+910000000001'."""
from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")
DEFAULT_COUNTRY_CODE = "91"


def normalize_phone(raw: str) -> str | None:
    """Return '+<digits>' or None when the input cannot be a phone number.

    Accepts '+91 00000 00001', '09000000001', '9000000001', '919000000001'. A bare 10-digit number is assumed to be Indian.
    """
    text = raw.strip()
    digits = _NON_DIGITS.sub("", text)
    if not digits:
        return None
    if not text.startswith("+"):
        if len(digits) == 10:
            digits = DEFAULT_COUNTRY_CODE + digits
        elif len(digits) == 11 and digits.startswith("0"):
            digits = DEFAULT_COUNTRY_CODE + digits[1:]
    if not 10 <= len(digits) <= 15:
        return None
    return "+" + digits


def mask_phone(phone: str) -> str:
    """'+910000000001' -> '+91******0001' (country code and last four digits only)."""
    if len(phone) <= 7:
        return "*" * len(phone)
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
