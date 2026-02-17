"""Fetch author, coauthors, and publications from Google Scholar (scholarly)."""

import logging
import time
from typing import Any, Callable

from scholarly import scholarly

from .retry import with_retry

logger = logging.getLogger(__name__)


@with_retry(max_retries=3, base_delay=5.0)
def fetch_author(scholar_id: str) -> dict[str, Any]:
    """Fetch author profile by Scholar ID. Raises if not found."""
    author = scholarly.search_author_id(scholar_id)
    if not author:
        raise ValueError(f"Author not found: {scholar_id}")
    return author


@with_retry(max_retries=3, base_delay=5.0)
def fill_author(author: dict[str, Any]) -> dict[str, Any]:
    """Fill author details (publications, citations, etc.)."""
    return scholarly.fill(author)


@with_retry(max_retries=3, base_delay=5.0)
def fill_coauthor(coauthor: dict[str, Any]) -> dict[str, Any]:
    """Fill a single coauthor's details."""
    return scholarly.fill(coauthor)


@with_retry(max_retries=3, base_delay=5.0)
def fill_publication(pub: dict[str, Any]) -> dict[str, Any]:
    """Fill a single publication's details."""
    return scholarly.fill(pub)


def fetch_full_author(
    scholar_id: str,
    previous_data: dict[str, Any] | None,
    coauthor_delay: float,
    publication_delay: float,
    on_coauthor_filled: Callable[[dict[str, Any], int, int], None] | None = None,
    on_publication_filled: Callable[[dict[str, Any], int, int], None] | None = None,
) -> dict[str, Any]:
    """Fetch full author with coauthors and publications.

    Uses previous_data for idempotency: skips already-filled coauthors/publications
    when last_fetched is still current. Tracks last_successful indices for resume.

    on_coauthor_filled(author, index, total) and on_publication_filled(author, index, total)
    are optional callbacks for saving progress.
    """
    author = fetch_author(scholar_id)
    logger.info("Author profile received: %s", author.get("name", "Unknown"))

    author = fill_author(author)
    pubs = author.get("publications", [])
    logger.info("Author details filled: %d publications", len(pubs))

    prev_pubs = (previous_data or {}).get("publications", [])
    prev_coauthors = (previous_data or {}).get("coauthors", [])
    last_coauthor_idx = (previous_data or {}).get("_last_successful_coauthor_index", -1)
    last_pub_idx = (previous_data or {}).get("_last_successful_publication_index", -1)

    # Fill coauthors
    coauthors_list = author.get("coauthors", [])
    total_co = len(coauthors_list)
    filled_coauthors: list[dict[str, Any]] = []

    for i, coauthor in enumerate(coauthors_list):
        if i <= last_coauthor_idx and i < len(prev_coauthors):
            filled_coauthors.append(prev_coauthors[i])
            continue
        try:
            filled = fill_coauthor(coauthor)
            filled_coauthors.append(filled)
            author["coauthors"] = filled_coauthors + list(coauthors_list[i + 1 :])
            if on_coauthor_filled:
                on_coauthor_filled(author, i + 1, total_co)
            time.sleep(coauthor_delay)
        except Exception as e:
            logger.warning("Error fetching coauthor %s: %s", coauthor.get("name"), e)
            filled_coauthors.append(coauthor)

    author["coauthors"] = filled_coauthors

    # Process publications (DOI/impact factor enrichment done in orchestration)
    pubs = list(author["publications"])
    filled_publications: list[dict[str, Any]] = []
    for index, pub in enumerate(pubs):
        if index <= last_pub_idx and index < len(prev_pubs):
            filled_publications.append(prev_pubs[index])
            continue
        try:
            filled = fill_publication(pub)
            filled_publications.append(filled)
            author["publications"] = filled_publications + pubs[index + 1 :]
            if on_publication_filled:
                on_publication_filled(author, index + 1, len(pubs))
            time.sleep(publication_delay)
        except Exception as e:
            logger.warning("Error filling publication %s: %s", pub.get("bib", {}).get("title"), e)
            filled_publications.append(pub)

    author["publications"] = filled_publications
    return author
