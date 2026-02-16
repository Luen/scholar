"""
Crossref API client for fetching publication metadata and citation counts.

Uses the Crossref REST API: https://api.crossref.org/documentation
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from .logger import print_warn

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CROSSREF_BASE = "https://api.crossref.org/works"

_logged_failures: set[str] = set()


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


def fetch_crossref_details(doi: str) -> CrossrefResponse | None:
    """
    Fetch publication metadata and citation count from Crossref API.
    """
    try:
        encoded_doi = quote(doi, safe="")
        url = f"{CROSSREF_BASE}/{encoded_doi}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        resp = requests.get(url, headers=headers, timeout=30)
        if not resp.ok:
            return None

        data = resp.json()
        message = data.get("message")
        if not message:
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
            print_warn(f"Failed to fetch Crossref data for DOI {doi}: {e}")
            _logged_failures.add(doi)
        return None
