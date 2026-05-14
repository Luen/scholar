#!/usr/bin/env python3
"""Orchestrate scholar data fetch: author, coauthors, publications, DOI, impact factor, news, video."""

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

import src.cache_config  # noqa: F401 - configure HTTP cache before any requests
from src.config import Config
from src.doi_resolver import resolve_doi_for_publication
from src.logging_config import setup_logging
from src.news_filters import filter_media_items
from src.news_scraper import get_news_data
from src.news_thumbnails import enrich_filtered_media_thumbnails
from src.output import is_fresh, load_author, save_author, set_last_successful_index
from src.scholar_fetcher import fetch_full_author
from src.standardise import standardise_authors
from src.video_scraper import get_video_data


def _journal_is_symposium_or_conference(journal: str) -> bool:
    j = (journal or "").strip().lower()
    return any(x in j for x in ["symposium", "conference", "workshop", "annual meeting"])


def _enrich_publication(
    pub: dict,
    author_name: str,
    journal_impact_factor_dic: dict[str, str],
    previous_pub: dict | None,
) -> None:
    """Add standardised authors, DOI, and impact factor to a publication."""
    bib = pub.setdefault("bib", {})
    journal_name = (bib.get("journal") or "").strip().lower()
    if journal_name == "null":
        journal_name = ""

    if _journal_is_symposium_or_conference(journal_name):
        pub["doi"] = ""
        pub["doi_link"] = ""
        pub["doi_short"] = ""
        pub["doi_short_link"] = ""
        pub["doi_resolved_link"] = ""
        bib["impact_factor"] = ""
        return

    pub_title = bib.get("title", "")
    pub_url = pub.get("pub_url", "")
    author_last = author_name.split()[-1] if author_name else ""

    prev = previous_pub or {}
    prev_doi = prev.get("doi") or ""
    prev_link = prev.get("doi_link") or ""
    prev_short = prev.get("doi_short") or ""
    prev_short_link = prev.get("doi_short_link") or ""
    prev_resolved = prev.get("doi_resolved_link") or ""

    if prev_doi or prev_link:
        doi_res = {
            "doi": prev_doi or pub.get("doi", ""),
            "doi_link": prev_link or pub.get("doi_link", ""),
            "doi_short": prev_short or pub.get("doi_short", ""),
            "doi_short_link": prev_short_link or pub.get("doi_short_link", ""),
            "doi_resolved_link": prev_resolved or "",
        }
    else:
        try:
            doi_res = resolve_doi_for_publication(
                pub_url,
                pub_title,
                author_last,
                previous_doi=None,
                previous_doi_link=None,
                previous_doi_short=None,
                previous_doi_short_link=None,
            )
        except Exception:
            doi_res = {
                "doi": "",
                "doi_link": "",
                "doi_short": "",
                "doi_short_link": "",
                "doi_resolved_link": "",
            }

    pub["doi"] = doi_res.get("doi", "") or ""
    pub["doi_link"] = doi_res.get("doi_link", "") or ""
    pub["doi_short"] = doi_res.get("doi_short", "") or ""
    pub["doi_short_link"] = doi_res.get("doi_short_link", "") or ""
    pub["doi_resolved_link"] = doi_res.get("doi_resolved_link", "") or ""

    authors = bib.get("author", "")
    bib["authors_standardised"] = standardise_authors(authors)

    if journal_name:
        if journal_name in journal_impact_factor_dic:
            bib["impact_factor"] = journal_impact_factor_dic[journal_name]
        else:
            from src.journal_impact_factor import add_impact_factor

            add_impact_factor(journal_name, "")
            bib["impact_factor"] = ""


def bake_media_filtered_fields(author: dict[str, Any], scholar_id: str) -> None:
    """Set ``media_filtered``, ``media_filtered_at``, and news thumbnails from ``author['media']``."""
    raw_media = author.get("media", []) or []
    author["media_filtered"] = filter_media_items(raw_media)
    author["media_filtered_at"] = datetime.now(timezone.utc).isoformat()
    enrich_filtered_media_thumbnails(scholar_id, author["media_filtered"])


def refresh_news_to_disk(config: Config) -> int:
    """
    Load scholar JSON, fetch fresh ``media`` via ``get_news_data``, then filter + thumbnails, save.

    Does not bump ``last_fetched`` so the full Scholar scrape idempotency window is unchanged.
    """
    import logging

    log = logging.getLogger(__name__)
    author = load_author(config.output_path)
    if not author:
        log.error("No author JSON at %s", config.output_path)
        return 1
    name = (author.get("name") or "").strip()
    if not name:
        log.error("Author JSON at %s has no name; cannot refresh news", config.output_path)
        return 1
    log.info("Refreshing news/media for %s (%s)", config.scholar_id, name)
    author.update(get_news_data(name))
    bake_media_filtered_fields(author, config.scholar_id)
    save_author(author, config.output_path, bump_last_fetched=False)
    log.info("Wrote media + media_filtered for %s", config.output_path)
    return 0


def _refresh_cached_news_artifacts(
    author: dict[str, Any], scholar_id: str, output_path: str
) -> bool:
    """
    When a full scrape is skipped (fresh ``last_fetched``), still backfill derived news
    fields: missing ``media_filtered``, thumbnail downloads, and managed URL rewrites.

    Does not bump ``last_fetched``.
    """
    import logging

    log = logging.getLogger(__name__)
    changed = False

    raw_media = author.get("media")
    if not isinstance(raw_media, list):
        raw_media = []

    if not isinstance(author.get("media_filtered"), list):
        log.info("Backfilling media_filtered from cached media (%s)", output_path)
        author["media_filtered"] = filter_media_items(raw_media)
        author["media_filtered_at"] = datetime.now(timezone.utc).isoformat()
        changed = True

    n = enrich_filtered_media_thumbnails(scholar_id, author["media_filtered"])
    if n > 0:
        changed = True

    if changed:
        save_author(author, output_path, bump_last_fetched=False)
        log.info("Updated cached news artifacts in %s", output_path)
    return changed


def bake_media_filtered_to_disk(config: Config) -> int:
    """
    Load scholar JSON from disk, recompute ``media_filtered`` (+ thumbnails), save.

    Does not refresh ``last_fetched`` so a full scrape is not suppressed by this run.
    """
    import logging

    log = logging.getLogger(__name__)
    author = load_author(config.output_path)
    if not author:
        log.error("No author JSON at %s", config.output_path)
        return 1
    n = len(author.get("media", []) or [])
    log.info("Baking media_filtered from %d on-disk media rows for %s", n, config.scholar_id)
    bake_media_filtered_fields(author, config.scholar_id)
    save_author(author, config.output_path, bump_last_fetched=False)
    log.info("Wrote media_filtered to %s", config.output_path)
    return 0


def run(scholar_id: str, config: Config | None = None) -> int:
    """Run the full scholar fetch pipeline. Returns exit code."""
    import logging

    log = logging.getLogger(__name__)
    if config is None:
        config = Config(scholar_id=scholar_id)

    from src.journal_impact_factor import load_impact_factor

    journal_impact_factor_dic = load_impact_factor()
    log.info("Loaded %d impact factors", len(journal_impact_factor_dic))

    previous = load_author(config.output_path)
    if previous:
        log.info("Loaded previous data for %s", scholar_id)

    if is_fresh(previous.get("last_fetched") if previous else None, config.fresh_data_seconds):
        log.info(
            "Data is fresh (within %ds). Skipping fetch.",
            config.fresh_data_seconds,
        )
        if previous:
            _refresh_cached_news_artifacts(previous, scholar_id, config.output_path)
        return 0

    log.info("Fetching author profile (may encounter CAPTCHA in Docker)")
    prev_pubs = (previous or {}).get("publications", [])

    def on_coauthor_save(author: dict, idx: int, total: int) -> None:
        set_last_successful_index(author, "coauthor", idx - 1)
        save_author(author, config.output_path)

    def on_publication_save(author: dict, idx: int, total: int) -> None:
        set_last_successful_index(author, "publication", idx - 1)
        save_author(author, config.output_path)

    try:
        author = fetch_full_author(
            config.scholar_id,
            previous,
            config.coauthor_delay_seconds,
            config.publication_delay_seconds,
            on_coauthor_filled=on_coauthor_save,
            on_publication_filled=on_publication_save,
        )
    except (ValueError, Exception) as e:
        log.exception("Fetch failed: %s", e)
        return 1

    for i, pub in enumerate(author["publications"]):
        prev_pub = prev_pubs[i] if i < len(prev_pubs) else None
        _enrich_publication(
            pub,
            author.get("name", ""),
            journal_impact_factor_dic,
            prev_pub,
        )
        set_last_successful_index(author, "publication", i)
        save_author(author, config.output_path)

    log.info("Fetching news/RSS for %s", author.get("name"))
    author.update(get_news_data(author.get("name", "")))
    raw_media = author.get("media", []) or []
    log.info("Filtering %d media items for API (writes media_filtered)", len(raw_media))
    bake_media_filtered_fields(author, config.scholar_id)

    log.info("Fetching video data")
    author.update(get_video_data(author.get("name", "")))

    save_author(author, config.output_path)
    log.info("Author data written to %s", config.output_path)
    return 0


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(
        description="Full scholar scrape, refresh news only, or bake media_filtered from disk.",
    )
    p.add_argument("scholar_id", help="Google Scholar author ID (e.g. ynWS968AAAAJ)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--bake-media-filtered",
        action="store_true",
        help="Recompute media_filtered and thumbnails from on-disk media only; skip news fetch.",
    )
    mode.add_argument(
        "--refresh-news",
        action="store_true",
        help="Fetch fresh news/media (RSS/APIs), then filter + thumbnails; skip Scholar scrape.",
    )
    args = p.parse_args()
    config = Config(scholar_id=args.scholar_id)
    if args.bake_media_filtered:
        sys.exit(bake_media_filtered_to_disk(config))
    if args.refresh_news:
        sys.exit(refresh_news_to_disk(config))
    sys.exit(run(args.scholar_id, config))


if __name__ == "__main__":
    main()
