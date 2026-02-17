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
    """Safe filename from DOI."""
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
                dois.add(data["doi"])
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return dois


def _write_cache(path: str, value: dict, doi: str = "") -> None:
    expires = datetime.now() + timedelta(seconds=CACHE_SECONDS)
    data = {**value, "expires_at": expires.isoformat(), "doi": doi}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning("Failed to write DOI metrics cache: %s", e)


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


@dataclass
class AltmetricResult:
    doi: str
    score: int | None
    found: bool  # True if authors validated
    details: dict | None = None  # Full Altmetric data for API response


def fetch_altmetric_score(doi: str, force_refresh: bool = False) -> AltmetricResult:
    """
    Fetch Altmetric data for a DOI. Cached for 2 weeks.
    Returns found=False (401) if Crossref does not list Rummer, Bergseth, or Wu.
    Uses Crossref first to verify authors; no page-content author check after fetch.
    """
    path = _cache_path(doi, "altmetric")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return AltmetricResult(
            doi=doi,
            score=cached.get("score"),
            found=cached.get("found", True),
            details=cached.get("details"),
        )

    # Crossref first: verify allowed author before fetching
    crossref = fetch_crossref_details(doi)
    if not crossref or not _authors_contain_allowed(crossref.authors):
        _write_cache(path, {"found": False, "score": None, "details": None}, doi=doi)
        return AltmetricResult(doi=doi, score=None, found=False, details=None)

    details = fetch_altmetric_details(doi)
    if details:
        details_dict = asdict(details)
        score = details.score
    else:
        details_dict = {"doi": doi, "score": None}
        score = None
    _write_cache(path, {"found": True, "score": score, "details": details_dict}, doi=doi)
    return AltmetricResult(doi=doi, score=score, found=True, details=details_dict)


@dataclass
class ScholarCitationsResult:
    doi: str
    citations: int | None
    found: bool


def fetch_google_scholar_citations(doi: str, force_refresh: bool = False) -> ScholarCitationsResult:
    """
    Fetch Google Scholar citation count for a DOI. Cached for 2 weeks.
    Returns found=False (401) if Crossref does not list Rummer, Bergseth, or Wu.
    Uses Crossref first to verify authors; no page-content author check after fetch.
    """
    path = _cache_path(doi, "scholar")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return ScholarCitationsResult(
            doi=doi,
            citations=cached.get("citations"),
            found=cached.get("found", True),
        )

    # Crossref first: verify allowed author before fetching
    crossref = fetch_crossref_details(doi)
    if not crossref or not _authors_contain_allowed(crossref.authors):
        _write_cache(path, {"found": False, "citations": None}, doi=doi)
        return ScholarCitationsResult(doi=doi, citations=None, found=False)

    search_url = f"{GOOGLE_SCHOLAR_BASE}?hl=en&as_sdt=0%2C5&q={quote(doi)}&btnG="
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://scholar.google.com/",
    }

    try:
        resp = requests.get(search_url, headers=headers, timeout=30)
        if not resp.ok:
            logger.warning("Google Scholar search failed (%s) for DOI %s", resp.status_code, doi)
            _write_cache(path, {"found": True, "citations": None}, doi=doi)
            return ScholarCitationsResult(doi=doi, citations=None, found=True)

        html = resp.text
        final_url = resp.url or search_url

        if _is_blocked_response(html, final_url):
            logger.warning("Google Scholar appears to be blocking requests (CAPTCHA/IP block)")
            _write_cache(path, {"found": True, "citations": None}, doi=doi)
            return ScholarCitationsResult(doi=doi, citations=None, found=True)

        soup = BeautifulSoup(html, "html.parser")
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

        _write_cache(path, {"found": True, "citations": citations}, doi=doi)
        return ScholarCitationsResult(doi=doi, citations=citations, found=True)

    except requests.RequestException as e:
        logger.warning("Failed to scrape Google Scholar citations for DOI %s: %s", doi, e)
        _write_cache(path, {"found": True, "citations": None}, doi=doi)
        return ScholarCitationsResult(doi=doi, citations=None, found=True)
