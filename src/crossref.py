"""
Crossref API client for fetching publication metadata and citation counts.

Uses the Crossref REST API: https://api.crossref.org/documentation

Crossref metadata (authors, title, journal) is immutable per DOI; only citation
counts may change. Uses a permanent cache (never expire) for Crossref requests.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
import requests_cache

from .doi_utils import normalize_doi
from .logger import print_warn

logger = logging.getLogger(__name__)

# Crossref metadata does not change; cache forever
_CACHE_DIR = os.environ.get("CACHE_DIR", "cache")
_CROSSREF_CACHE_DB = os.path.join(_CACHE_DIR, "http_cache_crossref")
os.makedirs(_CACHE_DIR, exist_ok=True)
_crossref_session = requests_cache.CachedSession(
    _CROSSREF_CACHE_DB,
    backend="sqlite",
    expire_after=None,  # Never expire
    allowable_methods=("GET",),
    allowable_codes=(200, 203, 300, 301),
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CROSSREF_BASE = "https://api.crossref.org"
CROSSREF_WORKS = f"{CROSSREF_BASE}/works"

CACHE_DIR = os.path.join(os.environ.get("CACHE_DIR", "cache"), "crossref_title")
CACHE_FILE = os.path.join(CACHE_DIR, "doi_by_title.json")

_logged_failures: set[str] = set()
_crossref_title_cache: dict[str, str | None] | None = None


def _cache_key(title: str, author: str) -> str:
    key = f"{title.strip().lower()}|{(author or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _load_title_cache() -> dict[str, str | None]:
    global _crossref_title_cache
    if _crossref_title_cache is not None:
        return _crossref_title_cache
    if not os.path.isfile(CACHE_FILE):
        _crossref_title_cache = {}
        return _crossref_title_cache
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _crossref_title_cache = json.load(f)
    except (json.JSONDecodeError, OSError):
        _crossref_title_cache = {}
    return _crossref_title_cache


def _save_title_cache() -> None:
    if _crossref_title_cache is None:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_crossref_title_cache, f, indent=2)
    except OSError:
        pass


@dataclass
class CrossrefResponse:
    """Publication metadata from Crossref API."""

    title: str | None = None
    journal: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    url: str | None = None
    citation_count: int | None = None


def _coerce_int(value: Any) -> int | None:
    """Coerce value to int if possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def search_doi_by_title(pub_title: str, author_last_name: str) -> str | None:
    """
    Search Crossref by publication title and author; return the best-matching DOI.

    Results are cached forever (DOIs do not change). Uses the Crossref REST API
    /works endpoint with query.title and query.author.
    """
    if not pub_title or not pub_title.strip():
        return None

    cache = _load_title_cache()
    key = _cache_key(pub_title.strip(), author_last_name or "")
    if key in cache:
        return cache[key]

    try:
        params = {
            "query.title": pub_title.strip(),
            "rows": 5,
        }
        if author_last_name and author_last_name.strip():
            params["query.author"] = author_last_name.strip()

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        resp = _crossref_session.get(CROSSREF_WORKS, params=params, headers=headers, timeout=30)
        if not resp.ok:
            cache[key] = None
            _save_title_cache()
            return None

        data = resp.json()
        items = data.get("message", {}).get("items", [])
        if not items:
            cache[key] = None
            _save_title_cache()
            return None

        author_lower = author_last_name.strip().lower() if author_last_name else ""
        for item in items:
            doi = item.get("DOI")
            if not doi:
                continue
            if author_lower:
                authors = item.get("author", [])
                for a in authors:
                    if isinstance(a, dict) and author_lower in (a.get("family") or "").lower():
                        cache[key] = doi
                        _save_title_cache()
                        return doi
            else:
                cache[key] = doi
                _save_title_cache()
                return doi
        # No author filter, or no author match: return first result if no author given
        result = items[0].get("DOI") if not author_lower else None
        cache[key] = result
        _save_title_cache()
        return result
    except (requests.RequestException, KeyError, TypeError, IndexError) as e:
        if "crossref_title_search" not in _logged_failures:
            print_warn(f"Crossref title search failed for '{pub_title[:50]}...': {e}")
            _logged_failures.add("crossref_title_search")
        cache[key] = None
        _save_title_cache()
        return None


def fetch_crossref_details(doi: str, force_refresh: bool = False) -> CrossrefResponse | None:
    """
    Fetch publication metadata and citation count from Crossref API.
    When force_refresh=True, bypass the permanent cache (e.g. for ?refresh=1 on the API).
    """
    doi = normalize_doi(doi)
    try:
        encoded_doi = quote(doi, safe="")
        url = f"{CROSSREF_WORKS}/{encoded_doi}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if force_refresh:
            resp = requests.get(url, headers=headers, timeout=30)
        else:
            resp = _crossref_session.get(url, headers=headers, timeout=30)
        if not resp.ok:
            logger.warning(
                "Crossref API failed for DOI %s: HTTP %s %s",
                doi,
                resp.status_code,
                resp.reason or "",
            )
            return None

        data = resp.json()
        message = data.get("message")
        if not message:
            logger.warning("Crossref API returned no message for DOI %s", doi)
            return None

        crossref_authors: list[str] | None = None
        author_list = message.get("author")
        if isinstance(author_list, list):
            authors = []
            for author in author_list:
                if isinstance(author, dict):
                    given = author.get("given", "")
                    family = author.get("family", "")
                    parts = [str(x).strip() for x in (given, family) if x]
                    name = " ".join(parts).strip()
                    if name:
                        authors.append(name)
            crossref_authors = authors if authors else None

        year: int | None = None
        for date_key in ("issued", "published", "published-print", "published-online"):
            date_parts = message.get(date_key, {}).get("date-parts", [[]])
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list):
                parts = date_parts[0]
                if parts:
                    year = _coerce_int(parts[0])
                    break

        title = None
        title_list = message.get("title")
        if isinstance(title_list, list) and title_list:
            title = str(title_list[0]).strip() or None

        journal = None
        container = message.get("container-title")
        if isinstance(container, list) and container:
            journal = str(container[0]).strip() or None

        url_val = message.get("URL")
        citation_count = _coerce_int(message.get("is-referenced-by-count"))

        return CrossrefResponse(
            title=title,
            journal=journal,
            authors=crossref_authors,
            year=year,
            url=str(url_val) if url_val else None,
            citation_count=citation_count,
        )
    except (requests.RequestException, KeyError, IndexError, TypeError) as e:
        if doi not in _logged_failures:
            logger.warning("Failed to fetch Crossref data for DOI %s: %s", doi, e)
            print_warn(f"Failed to fetch Crossref data for DOI {doi}: {e}")
            _logged_failures.add(doi)
        return None
