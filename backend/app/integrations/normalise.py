"""Clean-up of the client's messy free-typed values (phones, FRAC/IRAC groups)."""
from __future__ import annotations

import re

_SHORT_M = re.compile(r"^M(\d)$")
_PREFIX = re.compile(r"^\s*(?:IRAC|FRAC)\s*[:\-]?\s*", re.IGNORECASE)


def normalise_phone(raw: str | None) -> str:
    """'+91 00000 00001' -> '+910000000001'. A bare 10-digit number gets the +91 prefix."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        digits = "91" + digits
    return "+" + digits


def normalise_frac(raw: str | None) -> str | None:
    """'M3' -> 'M03', 'IRAC 3A' -> '3A', '1 + M3' -> '1+M03', '' -> None. Order of mixture parts is kept."""
    if raw is None:
        return None
    text = _PREFIX.sub("", raw.strip())
    parts = []
    for part in text.split("+"):
        code = re.sub(r"\s+", "", part).upper()
        if not code:
            continue
        short = _SHORT_M.match(code)
        parts.append(f"M0{short.group(1)}" if short else code)
    return "+".join(parts) or None
