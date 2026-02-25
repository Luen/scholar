"""
Shared DOI helpers. Normalize DOIs so they are never double-encoded in URLs or cache.
"""

from urllib.parse import unquote


def normalize_doi(doi: str | None) -> str:
    """
    Return a canonical DOI string: fully unquoted and stripped.
    Use before building URLs or storing in cache to avoid repeated encoding.
    Repeatedly unquotes until stable so multi-encoded values (e.g. %252520...)
    become a single clean DOI.
    """
    if doi is None:
        return ""
    s = doi.strip()
    while True:
        t = unquote(s)
        if t == s:
            break
        s = t
    return s.strip()
