"""Path containment helpers recognized by CodeQL ``py/path-injection``.

``pathlib.Path.resolve()`` / ``relative_to()`` are not modeled as sanitizers by
CodeQL (github/codeql#17226). ``os.path.realpath`` + ``startswith(base + sep)``
is the pattern CodeQL treats as a containment barrier.
"""

from __future__ import annotations

import os
from pathlib import Path


def safe_path_under(base_dir: str | os.PathLike[str], *parts: str) -> Path | None:
    """
    Join basename ``parts`` under ``base_dir`` and return a ``Path`` only if the
    result stays inside the real path of ``base_dir``.

    Each part must be a single path segment (no separators, no ``..``).
    Returns ``None`` on traversal / escape attempts.
    """
    for part in parts:
        if not part or part in (".", "..") or os.path.isabs(part):
            return None
        if os.sep in part or "/" in part or (os.altsep is not None and os.altsep in part):
            return None

    base = os.path.realpath(os.fspath(base_dir))
    candidate = os.path.realpath(os.path.join(base, *parts))
    if candidate == base or candidate.startswith(base + os.sep):
        return Path(candidate)
    return None
