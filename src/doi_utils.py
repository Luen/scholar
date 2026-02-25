"""
Shared DOI helpers. Normalize DOIs so they are never double-encoded in URLs or cache.
"""

from urllib.parse import unquote


def normalize_doi(doi: str | None) -> str:
    """
    Return a canonical DOI string: unquoted and stripped.
    Use before building URLs or storing in cache to avoid repeated encoding.
    """
    if doi is None:
        return ""
    return unquote(doi).strip()
