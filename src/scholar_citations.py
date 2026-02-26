"""
DOI metrics: Altmetric score and Google Scholar citations.

Fetches and caches results for two weeks. Uses Crossref first to verify that
Rummer, Bergseth, or Wu are authors; returns 401 if not. No page-content
author check after fetching.
"""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .altmetric import fetch_altmetric_details
from .crossref import fetch_crossref_details
from .doi_utils import normalize_doi
from .proxy_config import get_request_proxy_chain

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GOOGLE_SCHOLAR_BASE = "https://scholar.google.com/scholar"

ALLOWED_AUTHORS = ("Rummer", "Bergseth", "Wu")
CACHE_SECONDS = 14 * 24 * 60 * 60  # 2 weeks
CACHE_DIR = os.environ.get("DOI_METRICS_CACHE_DIR", "")
if not CACHE_DIR:
    base = os.environ.get("CACHE_DIR", "cache")
    CACHE_DIR = os.path.join(base, "doi_metrics")


def _normalize_doi_for_cache(doi: str) -> str:
    """Safe filename from DOI. Expects already-normalized DOI."""
    return doi.replace("/", "_").replace(":", "_").strip()


def _authors_contain_allowed(authors: list[str] | None) -> bool:
    """Return True if any author family name contains Rummer, Bergseth, or Wu."""
    if not authors:
        return False
    combined = " ".join(authors).lower()
    return any(a.lower() in combined for a in ALLOWED_AUTHORS)


def _cache_path(doi: str, prefix: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = _normalize_doi_for_cache(doi)
    return os.path.join(CACHE_DIR, f"{prefix}_{safe}.json")


def _read_cache(path: str) -> tuple[dict | None, bool]:
    """Return (cached_value, is_expired). Cached value has 'value' and 'expires_at'."""
    if not os.path.isfile(path):
        return None, True
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        expires = data.get("expires_at")
        if not expires:
            return None, True
        exp_dt = datetime.fromisoformat(expires)
        if datetime.now() > exp_dt:
            return data, True
        return data, False
    except (json.JSONDecodeError, OSError, ValueError):
        return None, True


def list_cached_successful_dois() -> set[str]:
    """Return DOIs that have successful cached results (found=True)."""
    dois: set[str] = set()
    if not os.path.isdir(CACHE_DIR):
        return dois
    for name in os.listdir(CACHE_DIR):
        if not name.endswith(".json"):
            continue
        path = os.path.join(CACHE_DIR, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("found") and data.get("doi"):
                dois.add(normalize_doi(data["doi"]))
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return dois


def _write_cache(path: str, value: dict, doi: str = "") -> None:
    now = datetime.now()
    expires = now + timedelta(seconds=CACHE_SECONDS)
    data = {
        **value,
        "expires_at": expires.isoformat(),
        "fetched_at": now.isoformat(),
        "doi": doi,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning("Failed to write DOI metrics cache: %s", e)


def _parse_scholar_citations(soup: BeautifulSoup) -> tuple[int | None, bool]:
    """
    Extract citation count from a Scholar results page.
    Returns (citations, no_results): no_results is True when the page says
    "did not match any articles".
    """
    citations: int | None = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text.startswith("Cited by"):
            m = re.search(r"Cited by (\d+)", text)
            if m:
                try:
                    citations = int(m.group(1))
                    break
                except ValueError:
                    pass

    no_results = "did not match any articles" in soup.get_text()
    # Result found but no "Cited by" link (e.g. new article) => treat as 0
    if citations is None and not no_results:
        citations = 0
    return citations, no_results


def _scholar_search(query: str, headers: dict, proxies: dict | None) -> tuple[int | None, bool] | None:
    """
    Run one Google Scholar search and parse the result.
    Returns (citations, no_results) on success, or None if the request failed or was blocked.
    """
    url = f"{GOOGLE_SCHOLAR_BASE}?hl=en&as_sdt=0%2C5&q={quote(query)}&btnG="
    try:
        resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
    except requests.RequestException:
        raise
    if not resp.ok:
        logger.warning(
            "Google Scholar search failed (%s) for query: %.60s", resp.status_code, query
        )
        return None
    if _is_blocked_response(resp.text, resp.url or url):
        logger.warning("Google Scholar appears to be blocking requests (CAPTCHA/IP block)")
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_scholar_citations(soup)


def _scholar_search_with_proxy_retries(
    query: str, headers: dict
) -> tuple[int | None, bool] | None:
    """
    Try Google Scholar search: Tor proxy first (up to 5 attempts, same proxy),
    then each SOCKS5 proxy in turn. Returns first successful result or None.
    """
    proxies_list = get_request_proxy_chain()
    last_e: requests.RequestException | None = None
    for proxies in proxies_list:
        try:
            result = _scholar_search(query, headers, proxies)
            if result is not None:
                return result
        except requests.RequestException as e:
            last_e = e
            logger.debug("Scholar search failed with proxy: %s", e)
            continue
    if last_e is not None:
        logger.warning(
            "Scholar search failed for all proxies for query %.60s: %s", query, last_e
        )
    return None


def _is_blocked_response(html: str, url: str) -> bool:
    """Detect if Google Scholar has blocked the request."""
    lower = html.lower()
    if "captcha" in lower or "recaptcha" in lower:
        return True
    if any(
        x in lower
        for x in (
            "unusual traffic",
            "automated queries",
            "our systems have detected",
            "sorry, we have detected",
        )
    ):
        return True
    if "scholar.google.com" not in url:
        return True
    return False


def _last_fetch_from_cache(cached: dict, path: str) -> str | None:
    """Last fetch timestamp from cache: use fetched_at if present, else file mtime."""
    if cached.get("fetched_at"):
        return cached["fetched_at"]
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    except OSError:
        return None


@dataclass
class AltmetricResult:
    doi: str
    score: int | None
    found: bool  # True if authors validated
    details: dict | None = None  # Full Altmetric data for API response
    last_fetch: str | None = None  # ISO timestamp when data was last fetched


def fetch_altmetric_score(doi: str, force_refresh: bool = False) -> AltmetricResult:
    """
    Fetch Altmetric data for a DOI. Cached for 2 weeks.
    Returns found=False (401) if Crossref does not list Rummer, Bergseth, or Wu.
    Uses Crossref first to verify authors; no page-content author check after fetch.
    """
    doi = normalize_doi(doi)
    path = _cache_path(doi, "altmetric")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return AltmetricResult(
            doi=doi,
            score=cached.get("score"),
            found=cached.get("found", True),
            details=cached.get("details"),
            last_fetch=_last_fetch_from_cache(cached, path),
        )

    # Crossref first: verify allowed author before fetching
    crossref = fetch_crossref_details(doi, force_refresh=force_refresh)
    if not crossref or not _authors_contain_allowed(crossref.authors):
        if not crossref:
            logger.warning(
                "Altmetric 401 for DOI %s: Crossref returned no metadata (API error or DOI not found)",
                doi,
            )
        else:
            logger.warning(
                "Altmetric 401 for DOI %s: author not in allowlist (Rummer/Bergseth/Wu). Crossref authors: %s",
                doi,
                (crossref.authors or [])[:10],
            )
        now_iso = datetime.now().isoformat()
        _write_cache(path, {"found": False, "score": None, "details": None}, doi=doi)
        return AltmetricResult(
            doi=doi, score=None, found=False, details=None, last_fetch=now_iso
        )

    details = fetch_altmetric_details(doi)
    if details:
        details_dict = asdict(details)
        score = details.score
    else:
        details_dict = {"doi": doi, "score": None}
        score = None
    now_iso = datetime.now().isoformat()
    _write_cache(path, {"found": True, "score": score, "details": details_dict}, doi=doi)
    return AltmetricResult(
        doi=doi, score=score, found=True, details=details_dict, last_fetch=now_iso
    )


@dataclass
class ScholarCitationsResult:
    doi: str
    citations: int | None
    found: bool
    last_fetch: str | None = None  # ISO timestamp when data was last fetched


def fetch_google_scholar_citations(doi: str, force_refresh: bool = False) -> ScholarCitationsResult:
    """
    Fetch Google Scholar citation count for a DOI. Cached for 2 weeks.
    Searches by DOI first; if that returns no results, searches by publication title.
    Returns found=False (401) if Crossref does not list Rummer, Bergseth, or Wu.
    """
    doi = normalize_doi(doi)
    path = _cache_path(doi, "scholar")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return ScholarCitationsResult(
            doi=doi,
            citations=cached.get("citations"),
            found=cached.get("found", True),
            last_fetch=_last_fetch_from_cache(cached, path),
        )

    # Crossref first: verify allowed author and get title for fallback
    crossref = fetch_crossref_details(doi, force_refresh=force_refresh)
    if not crossref or not _authors_contain_allowed(crossref.authors):
        if not crossref:
            logger.warning(
                "Google Scholar 401 for DOI %s: Crossref returned no metadata (API error or DOI not found)",
                doi,
            )
        else:
            logger.warning(
                "Google Scholar 401 for DOI %s: author not in allowlist (Rummer/Bergseth/Wu). Crossref authors: %s",
                doi,
                (crossref.authors or [])[:10],
            )
        now_iso = datetime.now().isoformat()
        _write_cache(path, {"found": False, "citations": None}, doi=doi)
        return ScholarCitationsResult(
            doi=doi, citations=None, found=False, last_fetch=now_iso
        )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://scholar.google.com/",
    }

    try:
        # 1. Search by DOI (try each proxy in turn if one is offline or blocked)
        result = _scholar_search_with_proxy_retries(doi, headers)
        if result is None:
            if cached is not None:
                return ScholarCitationsResult(
                    doi=doi,
                    citations=cached.get("citations"),
                    found=cached.get("found", True),
                    last_fetch=_last_fetch_from_cache(cached, path),
                )
            return ScholarCitationsResult(
                doi=doi, citations=None, found=True, last_fetch=None
            )

        citations, no_results = result

        # 2. If DOI search had no results, search by publication title
        if citations is None and no_results and crossref.title:
            title_query = crossref.title.strip()
            if title_query:
                title_result = _scholar_search_with_proxy_retries(title_query, headers)
                if title_result is not None and title_result[0] is not None:
                    citations = title_result[0]
                    logger.info(
                        "Scholar DOI search had no results; got citations via title: %.60s",
                        title_query,
                    )

        now_iso = datetime.now().isoformat()
        _write_cache(path, {"found": True, "citations": citations}, doi=doi)
        return ScholarCitationsResult(
            doi=doi, citations=citations, found=True, last_fetch=now_iso
        )

    except requests.RequestException as e:
        logger.warning("Failed to scrape Google Scholar citations for DOI %s: %s", doi, e)
        now_iso = datetime.now().isoformat()
        _write_cache(path, {"found": True, "citations": None}, doi=doi)
        return ScholarCitationsResult(
            doi=doi, citations=None, found=True, last_fetch=now_iso
        )
