"""DOI lookup and resolution with retries."""

import logging
from urllib.parse import urlparse

import requests

from .doi import (
    are_urls_equal,
    get_doi,
    get_doi_from_title,
    get_doi_link,
    get_doi_resolved_link,
    get_doi_short,
    get_doi_short_link,
)
from .retry import with_retry

logger = logging.getLogger(__name__)


def _get_doi_impl(url: str, author: str) -> str | None:
    return get_doi(url, author)


def _get_doi_from_title_impl(title: str, author: str) -> str | None:
    return get_doi_from_title(title, author)


@with_retry(
    max_retries=3,
    base_delay=5.0,
    exceptions=(ConnectionError, TimeoutError, OSError, requests.RequestException),
)
def resolve_doi_for_publication(
    pub_url: str,
    pub_title: str,
    author_last_name: str,
    previous_doi: str | None = None,
    previous_doi_link: str | None = None,
    previous_doi_short: str | None = None,
    previous_doi_short_link: str | None = None,
    previous_doi_resolved_link: str | None = None,
) -> dict[str, str]:
    """Resolve DOI and related fields for a publication.

    Returns dict with keys: doi, doi_link, doi_short, doi_short_link, doi_resolved_link.
    Uses previous_* when provided to avoid redundant lookups.
    """
    result: dict[str, str] = {
        "doi": "",
        "doi_link": "",
        "doi_short": "",
        "doi_short_link": "",
        "doi_resolved_link": "",
    }

    doi = previous_doi
    if not doi:
        host = urlparse(pub_url).hostname
        if host and host == "scholar.google.com" and pub_title:
            doi = _get_doi_from_title_impl(pub_title, author_last_name)
        else:
            try:
                doi = _get_doi_impl(pub_url, author_last_name)
            except Exception as e:
                logger.warning("DOI lookup failed for %s: %s", pub_url[:80], e)
                doi = None

    if not doi:
        logger.warning("DOI not found for %s", pub_title[:60] if pub_title else pub_url)
        return result

    result["doi"] = doi
    logger.info("DOI: %s", doi)

    doi_link = previous_doi_link or get_doi_link(doi)
    result["doi_link"] = doi_link or ""
    if previous_doi_resolved_link is not None:
        result["doi_resolved_link"] = previous_doi_resolved_link
    elif doi_link:
        resolved = get_doi_resolved_link(doi)
        result["doi_resolved_link"] = resolved or ""
        if resolved and pub_url and not are_urls_equal(pub_url, resolved):
            logger.warning(
                "Resolved DOI link does not match publication URL: %s vs %s",
                pub_url[:60],
                resolved[:60],
            )

    doi_short = previous_doi_short or get_doi_short(doi)
    result["doi_short"] = doi_short or ""
    result["doi_short_link"] = (
        previous_doi_short_link or (get_doi_short_link(doi_short) if doi_short else "") or ""
    )

    return result
