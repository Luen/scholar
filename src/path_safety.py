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
    clean_parts: list[str] = []
    for part in parts:
        if not part or part in (".", "..") or os.path.isabs(part):
            return None
        # Reject / and \\ on all platforms (os.altsep is None on POSIX).
        if "/" in part or "\\" in part:
            return None
        # CodeQL-modeled sanitizer: basename strips any remaining dir components.
        name = os.path.basename(part)
        if name != part or not name or name in (".", ".."):
            return None
        clean_parts.append(name)

    base = os.path.realpath(os.fspath(base_dir))
    candidate = os.path.realpath(os.path.join(base, *clean_parts))
    if candidate == base or candidate.startswith(base + os.sep):
        return Path(candidate)
    return None
