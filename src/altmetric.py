"""
Altmetric data fetcher.

Fetches the public Altmetric details page, parses bibliographic fields with BeautifulSoup,
then calls the badge embed endpoint for quantitative metrics.

Reference: https://medium.com/@christopherfkk_19802/data-ingestion-scraping-altmetric-12c1fd234366
As of 10 November 2025, all users need an API key to access the Altmetric Details Page API.
We use the Altmetric details page and the badge embed endpoint to scrape data.
"""

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .logger import print_warn

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ALT_DETAILS_BASE = "https://www.altmetric.com/details/doi"
ALT_EMBED_BASE = "https://api.altmetric.com/v1/internal-556fdf0f/id"

_logged_failures: set[str] = set()


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


def _coerce_int(value: Any) -> int | None:
    """Coerce value to int if possible."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_altmetric_embed(altmetric_id: str) -> AltmetricEmbedResponse | None:
    """Fetch Altmetric badge embed data for a given Altmetric ID."""
    url = f"{ALT_EMBED_BASE}/{altmetric_id}?callback=_altmetric.embed_callback"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://www.altmetric.com/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
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


def fetch_altmetric_details(doi: str) -> ScrapedAltmetricDetails | None:
    """
    Fetch and parse Altmetric details for a DOI.

    Fetches the public Altmetric details page, parses bibliographic fields,
    calls the badge embed endpoint for metrics, and falls back to Crossref
    when Altmetric lacks structured metadata.
    """
    title: str | None = None
    link_href: str | None = None
    journal: str | None = None
    published_text: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    altmetric_id: str | None = None
    embed_data: AltmetricEmbedResponse | None = None

    encoded_doi = quote(doi, safe="")
    details_url = f"{ALT_DETAILS_BASE}/{encoded_doi}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
    }

    try:
        resp = requests.get(details_url, headers=headers, timeout=30)
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
                    embed_data = _fetch_altmetric_embed(altmetric_id)
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

    mendeley = None
    if embed_data and embed_data.readers:
        mendeley = _coerce_int(embed_data.readers.get("mendeley"))

    return ScrapedAltmetricDetails(
        doi=doi,
        title=title,
        journal=journal,
        published_text=published_text,
        year=year,
        authors=authors,
        url=link_href or (embed_data.url if embed_data else None),
        score=embed_data.score if embed_data else None,
        cited_by_posts_count=embed_data.cited_by_posts_count if embed_data else None,
        cited_by_accounts_count=embed_data.cited_by_accounts_count if embed_data else None,
        cited_by_msm_count=embed_data.cited_by_msm_count if embed_data else None,
        cited_by_bluesky_count=embed_data.cited_by_bluesky_count if embed_data else None,
        cited_by_tweeters_count=embed_data.cited_by_tweeters_count if embed_data else None,
        cited_by_peer_review_sites_count=(
            embed_data.cited_by_peer_review_sites_count if embed_data else None
        ),
        mendeley_readers=mendeley,
        altmetric_id=altmetric_id,
    )
