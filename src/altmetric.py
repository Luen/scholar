"""
Altmetric data fetcher.

Fetches the public Altmetric details page and parses bibliographic fields plus
metrics (score, mention counts, Mendeley readers) from the score-panel HTML.
No separate embed fetch is needed—the badge URL in the page contains the score.

Reference: https://medium.com/@christopherfkk_19802/data-ingestion-scraping-altmetric-12c1fd234366
"""

import re
from dataclasses import dataclass
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .logger import print_warn

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ALT_DETAILS_BASE = "https://www.altmetric.com/details/doi"

_logged_failures: set[str] = set()


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
        resp = requests.get(
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
