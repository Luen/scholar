"""
DOI metrics: Altmetric score and Google Scholar citations.

Fetches and caches results for two weeks. Returns 401 if the page does not
contain Rummer, Bergseth, or Wu (author validation).
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .altmetric import fetch_altmetric_details

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


def _page_contains_allowed_author(text: str) -> bool:
    """Return True if text contains Rummer, Bergseth, or Wu."""
    if not text:
        return False
    lower = text.lower()
    return any(a.lower() in lower for a in ALLOWED_AUTHORS)


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


def fetch_altmetric_score(doi: str, force_refresh: bool = False) -> AltmetricResult:
    """
    Fetch Altmetric score for a DOI. Cached for 2 weeks.
    Returns found=False (401) if page does not contain Rummer, Bergseth, or Wu.
    """
    path = _cache_path(doi, "altmetric")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return AltmetricResult(
            doi=doi,
            score=cached.get("score"),
            found=cached.get("found", True),
        )

    details = fetch_altmetric_details(doi)
    if not details:
        _write_cache(path, {"found": False, "score": None}, doi=doi)
        return AltmetricResult(doi=doi, score=None, found=False)

    # Check authors (from Altmetric page)
    text_to_check = " ".join(details.authors) if details.authors else ""
    if not text_to_check and details.title:
        text_to_check = details.title
    if not _page_contains_allowed_author(text_to_check):
        _write_cache(path, {"found": False, "score": None}, doi=doi)
        return AltmetricResult(doi=doi, score=details.score, found=False)

    result = AltmetricResult(doi=doi, score=details.score, found=True)
    _write_cache(path, {"found": True, "score": details.score}, doi=doi)
    return result


@dataclass
class ScholarCitationsResult:
    doi: str
    citations: int | None
    found: bool


def fetch_google_scholar_citations(doi: str, force_refresh: bool = False) -> ScholarCitationsResult:
    """
    Fetch Google Scholar citation count for a DOI. Cached for 2 weeks.
    Returns found=False (401) if page does not contain Rummer, Bergseth, or Wu.
    """
    path = _cache_path(doi, "scholar")
    cached, expired = _read_cache(path)
    if not force_refresh and cached is not None and not expired:
        return ScholarCitationsResult(
            doi=doi,
            citations=cached.get("citations"),
            found=cached.get("found", True),
        )

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
            return ScholarCitationsResult(doi=doi, citations=None, found=False)

        html = resp.text
        final_url = resp.url or search_url

        if _is_blocked_response(html, final_url):
            logger.warning("Google Scholar appears to be blocking requests (CAPTCHA/IP block)")
            return ScholarCitationsResult(doi=doi, citations=None, found=False)

        if not _page_contains_allowed_author(html):
            _write_cache(path, {"found": False, "citations": None}, doi=doi)
            return ScholarCitationsResult(doi=doi, citations=None, found=False)

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
        return ScholarCitationsResult(doi=doi, citations=None, found=False)
