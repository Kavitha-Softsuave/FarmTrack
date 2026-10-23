"""Path safety for files under the storage directory. Names are always server-generated; this is the second line of defence."""
from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def safe_join(root: Path, *parts: str) -> Path:
    """Join `parts` under `root` and refuse anything that resolves outside it (.., absolute parts, symlinks, NUL bytes)."""
    if any("\x00" in part for part in parts):
        raise UnsafePathError("invalid path")
    try:
        base = root.resolve()
        candidate = base.joinpath(*parts).resolve()
    except (OSError, ValueError) as exc:
        raise UnsafePathError("invalid path") from exc
    if candidate != base and base not in candidate.parents:
        raise UnsafePathError("path escapes the storage directory")
    return candidate
