"""
Shared DOI helpers. Normalize DOIs so they are never double-encoded in URLs or cache.
"""

from urllib.parse import unquote


def normalize_doi(doi: str | None) -> str:
    """
    Return a canonical DOI string: fully unquoted, stripped, and lowercased.
    DOIs are treated case-insensitively (e.g. 10.5268/IW-3.3.550 and 10.5268/iw-3.3.550
    are the same). Use before building URLs or storing in cache.
    """
    if doi is None:
        return ""
    s = doi.strip()
    while True:
        t = unquote(s)
        if t == s:
            break
        s = t
    return s.strip().lower()
