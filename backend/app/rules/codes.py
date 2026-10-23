"""FRAC / IRAC code normalisation and resistance-group helpers.

Codes arrive in many spellings ('M3', 'M03', '1 + M03', '7+3', 'IRAC 3A'). Every comparison in the engine uses the
normalised components: M-groups are zero padded ('M3' -> 'M03'), plain numbers lose leading zeros, spaces and the
FRAC/IRAC prefix are dropped, and mixtures are split on '+' into components.

DMI is component '3' (FRAC) and is NOT the same as IRAC '3A' (pyrethroids): the letter suffix keeps them apart.
"""
from __future__ import annotations

import re

DMI = "3"
QOI = "11"
SDHI = "7"
MBC = "1"

_PREFIX = re.compile(r"\b(?:FRAC|IRAC)\b[\s:.\-]*", re.IGNORECASE)
_SPLIT = re.compile(r"[+/,;&\s]+")
_PREFIXED = re.compile(r"(M|P|U|NC|BM)0*(\d{1,2})([A-Z]?)")
_NUMERIC = re.compile(r"0*(\d{1,2})([A-Z]?)")
_NAMED = {"UNM", "NC", "NOCODE"}


def _component(token: str) -> str | None:
    t = token.strip().upper()
    if not t:
        return None
    m = _PREFIXED.fullmatch(t)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{m.group(3)}"
    m = _NUMERIC.fullmatch(t)
    if m:
        return f"{int(m.group(1))}{m.group(2)}"
    if t in _NAMED:
        return t
    return None


def components(code: str | None) -> tuple[str, ...]:
    """Normalised components of a (possibly mixed) code. Unknown tokens are dropped; no code gives ()."""
    if not code:
        return ()
    cleaned = _PREFIX.sub(" ", code)
    out: list[str] = []
    for token in _SPLIT.split(cleaned):
        comp = _component(token)
        if comp and comp not in out:
            out.append(comp)
    return tuple(out)


def normalise_code(code: str | None) -> str:
    """'M3' -> 'M03'; '1 + M3' -> '1+M03'; 'IRAC 3A' -> '3A'; None -> ''."""
    return "+".join(components(code))


def code_system(code: str | None) -> str | None:
    """'irac' or 'frac' when the raw text says so explicitly, else None."""
    if not code:
        return None
    upper = code.upper()
    if "IRAC" in upper:
        return "irac"
    if "FRAC" in upper:
        return "frac"
    return None


def looks_like_irac(code: str | None) -> bool:
    """Heuristic for category inference: an explicit IRAC prefix, or a plain-number group with a letter suffix ('4A')."""
    if code_system(code) == "irac":
        return True
    comps = components(code)
    return bool(comps) and all(re.fullmatch(r"\d{1,2}[A-Z]", c) for c in comps)


def has_dmi(comps: tuple[str, ...]) -> bool:
    return DMI in comps


def has_qoi(comps: tuple[str, ...]) -> bool:
    return QOI in comps


def has_sdhi(comps: tuple[str, ...]) -> bool:
    return SDHI in comps


def shared(a: tuple[str, ...], b: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(c for c in a if c in b)
