"""
Altmetric data fetcher.

Fetches the public Altmetric details page and parses bibliographic fields plus
metrics (score, mention counts, Mendeley readers) from the score-panel HTML.
Also fetches the badge embed endpoint for cited_by_posts_count and other counts
that are not on the details page. Embed cache: 1 week; details cache: 2 weeks.

Reference: https://medium.com/@christopherfkk_19802/data-ingestion-scraping-altmetric-12c1fd234366
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import requests
import requests_cache
from bs4 import BeautifulSoup

from .doi_utils import normalize_doi
from .logger import print_warn
from .proxy_config import get_request_proxy_chain

# Altmetric details: 2-week TTL (bi-weekly updates)
_CACHE_DIR = os.environ.get("CACHE_DIR", "cache")
_ALT_CACHE_DB = os.path.join(_CACHE_DIR, "http_cache_altmetric")
_ALT_EMBED_CACHE_DB = os.path.join(_CACHE_DIR, "http_cache_altmetric_embed")
os.makedirs(_CACHE_DIR, exist_ok=True)
_altmetric_session = requests_cache.CachedSession(
    _ALT_CACHE_DB,
    backend="sqlite",
    expire_after=timedelta(weeks=2),
    allowable_methods=("GET",),
    allowable_codes=(200, 203, 300, 301),
)
# Embed: 1-week TTL for cited_by_posts_count and other counts
_altmetric_embed_session = requests_cache.CachedSession(
    _ALT_EMBED_CACHE_DB,
    backend="sqlite",
    expire_after=timedelta(weeks=1),
    allowable_methods=("GET",),
    allowable_codes=(200, 203, 300, 301),
)

ALT_EMBED_BASE = "https://api.altmetric.com/v1/internal-556fdf0f/id"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ALT_DETAILS_BASE = "https://www.altmetric.com/details/doi"

_logged_failures: set[str] = set()


def _get_with_proxy_retries(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str],
    timeout: int = 30,
    allow_redirects: bool = True,
) -> requests.Response:
    """
    Try session.get(url, ...) with Tor proxy first (up to 5 attempts), then
    each SOCKS5 proxy in turn; return first successful response. Raises the
    last RequestException if all attempts fail.
    """
    proxies_list = get_request_proxy_chain()
    last_e: requests.RequestException | None = None
    for proxies in proxies_list:
        try:
            return session.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
            )
        except requests.RequestException as e:
            last_e = e
            continue
    if last_e is not None:
        raise last_e
    raise requests.RequestException("Altmetric request failed (no proxies tried)")


@dataclass
class AltmetricEmbedResponse:
    """Response from the Altmetric badge embed endpoint."""

    doi: str | None = None
    url: str | None = None
    score: int | None = None
    cited_by_posts_count: int | None = None
    cited_by_accounts_count: int | None = None
    cited_by_msm_count: int | None = None
    cited_by_bluesky_count: int | None = None
    cited_by_tweeters_count: int | None = None
    cited_by_peer_review_sites_count: int | None = None
    readers: dict[str, Any] | None = None


@dataclass
class ScrapedAltmetricDetails:
    """Altmetric scraped details."""

    doi: str
    title: str | None = None
    journal: str | None = None
    published_text: str | None = None
    year: int | None = None
    authors: list[str] | None = None
    url: str | None = None
    score: int | None = None
    cited_by_posts_count: int | None = None
    cited_by_accounts_count: int | None = None
    cited_by_msm_count: int | None = None
    cited_by_bluesky_count: int | None = None
    cited_by_tweeters_count: int | None = None
    cited_by_peer_review_sites_count: int | None = None
    mendeley_readers: int | None = None
    altmetric_id: str | None = None


def _coerce_int(value) -> int | None:
    """Coerce value to int if possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_embed_response(data: dict[str, Any]) -> AltmetricEmbedResponse:
    """Parse raw embed JSON into typed response."""
    readers = data.get("readers") or {}
    return AltmetricEmbedResponse(
        doi=data.get("doi"),
        url=data.get("url"),
        score=_coerce_int(data.get("score")),
        cited_by_posts_count=_coerce_int(data.get("cited_by_posts_count")),
        cited_by_accounts_count=_coerce_int(data.get("cited_by_accounts_count")),
        cited_by_msm_count=_coerce_int(data.get("cited_by_msm_count")),
        cited_by_bluesky_count=_coerce_int(data.get("cited_by_bluesky_count")),
        cited_by_tweeters_count=_coerce_int(data.get("cited_by_tweeters_count")),
        cited_by_peer_review_sites_count=_coerce_int(data.get("cited_by_peer_review_sites_count")),
        readers=readers if isinstance(readers, dict) else None,
    )


def _fetch_altmetric_embed(altmetric_id: str) -> AltmetricEmbedResponse | None:
    """Fetch Altmetric badge embed data for a given Altmetric ID. Cached 1 week."""
    url = f"{ALT_EMBED_BASE}/{altmetric_id}?callback=_altmetric.embed_callback"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://www.altmetric.com/",
    }
    try:
        resp = _get_with_proxy_retries(
            _altmetric_embed_session,
            url,
            headers=headers,
            timeout=30,
            allow_redirects=False,
        )
        resp.raise_for_status()
        body = resp.text.strip()
        json_str = body.replace("_altmetric.embed_callback(", "").rstrip(");").rstrip(";")
        data = json.loads(json_str)
        return _parse_embed_response(data)
    except requests.RequestException as e:
        if altmetric_id not in _logged_failures:
            print_warn(f"Altmetric embed fetch failed for id {altmetric_id}: {e}")
            _logged_failures.add(altmetric_id)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        if altmetric_id not in _logged_failures:
            print_warn(f"Altmetric embed parse failed for id {altmetric_id}: {e}")
            _logged_failures.add(altmetric_id)
        return None


def _parse_score_panel(soup: BeautifulSoup) -> dict:
    """
    Parse metrics from the .score-panel: score (from badge URL), mention counts, Mendeley.
    Badge URL: https://badges.altmetric.com/?style=donut&score=10&types=...
    """
    out = {}
    panel = soup.select_one(".score-panel")
    if not panel:
        return out
    html = str(panel)
    match = re.search(r"score=(\d+)", html)
    if match:
        out["score"] = _coerce_int(match.group(1))
    for dl in panel.select("dl.mention-counts"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue
        source = dt.get_text(strip=True).lower()
        strong = dd.find("strong")
        n = _coerce_int(strong.get_text(strip=True)) if strong else None
        if not n:
            continue
        if source == "twitter":
            out["cited_by_tweeters_count"] = n
        elif source == "bluesky":
            out["cited_by_bluesky_count"] = n
    for dl in panel.select("dl.reader-counts"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue
        source = dt.get_text(strip=True).lower()
        if source == "mendeley":
            strong = dd.find("strong")
            if strong:
                out["mendeley_readers"] = _coerce_int(strong.get_text(strip=True))
            break
    return out


def fetch_altmetric_details(doi: str) -> ScrapedAltmetricDetails | None:
    """
    Fetch and parse Altmetric details for a DOI.

    Fetches the public Altmetric details page and parses bibliographic fields
    plus metrics (score from badge URL, mention counts, Mendeley) from the HTML.
    """
    doi = normalize_doi(doi)
    title: str | None = None
    link_href: str | None = None
    journal: str | None = None
    published_text: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    altmetric_id: str | None = None
    panel: dict | None = None

    # Altmetric expects the DOI slash unencoded; quote(doi, safe="/") preserves it
    encoded_doi = quote(doi, safe="/")
    details_url = f"{ALT_DETAILS_BASE}/{encoded_doi}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
    }

    try:
        resp = _get_with_proxy_retries(
            _altmetric_session,
            details_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")

            header = soup.select_one(".document-header h1")
            if header:
                title = header.get_text(strip=True) or None
                link_el = header.find("a")
                if link_el and link_el.get("href"):
                    link_href = link_el["href"]

            for row in soup.select(".document-details-table tr"):
                th = row.find("th")
                td = row.find("td")
                if not th or not td:
                    continue
                heading = th.get_text(strip=True)
                content_el = td.select_one(".content-wrapper")
                content = content_el.get_text(strip=True) if content_el else td.get_text(strip=True)

                if heading == "Published in":
                    published_text = content or None
                    if content:
                        parts = content.split(",")
                        journal = parts[0].strip() if parts else None
                        year_match = re.search(r"(\d{4})", content)
                        if year_match:
                            year = _coerce_int(year_match.group(1))

                if heading == "Authors":
                    author_text = re.sub(r"\s+", " ", content)
                    authors = [a.strip() for a in author_text.split(",") if a.strip()]

            if not year:
                tagline = soup.select_one(".document-header .tagline")
                if tagline:
                    tag_text = tagline.get_text()
                    year_match = re.search(r"(\d{4})", tag_text)
                    if year_match:
                        year = _coerce_int(year_match.group(1))

            canonical = soup.select_one('link[rel="canonical"]')
            if canonical and canonical.get("href"):
                match = re.search(r"details/(\d+)", canonical["href"])
                if match:
                    altmetric_id = match.group(1)
            if not altmetric_id:
                # Altmetric redirects /details/doi/{doi} -> /details/{altmetric_id}; use final URL
                match = re.search(r"details/(\d+)(?:\?|$)", resp.url)
                if match:
                    altmetric_id = match.group(1)
            panel = _parse_score_panel(soup)
            if altmetric_id:
                embed_data = _fetch_altmetric_embed(altmetric_id)
                if embed_data:
                    p = panel or {}
                    p["score"] = (
                        embed_data.score if embed_data.score is not None else p.get("score")
                    )
                    p["cited_by_posts_count"] = embed_data.cited_by_posts_count
                    p["cited_by_accounts_count"] = embed_data.cited_by_accounts_count
                    p["cited_by_msm_count"] = embed_data.cited_by_msm_count
                    p["cited_by_bluesky_count"] = (
                        embed_data.cited_by_bluesky_count
                        if embed_data.cited_by_bluesky_count is not None
                        else p.get("cited_by_bluesky_count")
                    )
                    p["cited_by_tweeters_count"] = (
                        embed_data.cited_by_tweeters_count
                        if embed_data.cited_by_tweeters_count is not None
                        else p.get("cited_by_tweeters_count")
                    )
                    p["cited_by_peer_review_sites_count"] = (
                        embed_data.cited_by_peer_review_sites_count
                    )
                    if embed_data.readers and isinstance(embed_data.readers, dict):
                        mendeley = _coerce_int(embed_data.readers.get("mendeley"))
                        p["mendeley_readers"] = (
                            mendeley if mendeley is not None else p.get("mendeley_readers")
                        )
                    panel = p
        else:
            if doi not in _logged_failures:
                print_warn(
                    f"Altmetric details page fetch failed ({resp.status_code}) for DOI {doi}"
                )
                _logged_failures.add(doi)
    except requests.RequestException as e:
        if doi not in _logged_failures:
            print_warn(f"Failed to scrape Altmetric details for DOI {doi}: {e}")
            _logged_failures.add(doi)
    except Exception as e:
        if doi not in _logged_failures:
            print_warn(f"Altmetric parse error for DOI {doi}: {e}")
            _logged_failures.add(doi)

    if not title and not journal and not authors and year is None:
        return None

    p = panel or {}
    return ScrapedAltmetricDetails(
        doi=doi,
        title=title,
        journal=journal,
        published_text=published_text,
        year=year,
        authors=authors,
        url=link_href,
        score=p.get("score"),
        cited_by_posts_count=p.get("cited_by_posts_count"),
        cited_by_accounts_count=p.get("cited_by_accounts_count"),
        cited_by_msm_count=p.get("cited_by_msm_count"),
        cited_by_bluesky_count=p.get("cited_by_bluesky_count"),
        cited_by_tweeters_count=p.get("cited_by_tweeters_count"),
        cited_by_peer_review_sites_count=p.get("cited_by_peer_review_sites_count"),
        mendeley_readers=p.get("mendeley_readers"),
        altmetric_id=altmetric_id,
    )
