#!/usr/bin/env python3
"""
Revalidate DOI metrics cache: refetch missing/blocked every run; revalidate stale weekly.

Run daily via cron. Phase 1 (every run): fetch DOIs with no cache or with a
warning/blocked cache. Phase 2 (only when cache is older than 7 days): revalidate
DOIs that have successful cache older than a week. Does not use force_refresh so
that if we get CAPTCHA/blocked we keep existing cache. Uses TOR_PROXY first
(5 attempts), then SOCKS5_PROXIES (see .env.template).
"""

import json
import logging
import os
import sys

from common import PROJECT_ROOT, setup_script

setup_script()

STALE_SECONDS = 7 * 24 * 60 * 60  # 7 days

from src.doi_utils import normalize_doi  # noqa: E402
from src.scholar_citations import (  # noqa: E402
    fetch_altmetric_score,
    fetch_google_scholar_citations,
    list_cached_dois_with_warning,
    list_cached_successful_dois,
    list_cached_successful_dois_older_than,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def _all_dois_from_scholar_data() -> set[str]:
    """Collect all DOIs from scholar_data JSON files (publications with doi)."""
    data_dir = os.environ.get("SCHOLAR_DATA_DIR", "scholar_data")
    if not os.path.isabs(data_dir):
        data_dir = os.path.join(PROJECT_ROOT, data_dir)
    dois: set[str] = set()
    if not os.path.isdir(data_dir):
        return dois
    for name in os.listdir(data_dir):
        if not name.endswith(".json"):
            continue
        path = os.path.join(data_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for pub in data.get("publications") or []:
            doi = (pub.get("doi") or "").strip()
            if doi:
                dois.add(normalize_doi(doi))
    return dois


def main() -> int:
    all_dois = _all_dois_from_scholar_data()
    successful = list_cached_successful_dois()
    with_warning = list_cached_dois_with_warning()
    stale = list_cached_successful_dois_older_than(STALE_SECONDS)

    # Phase 1 (every run): missing + blocked/warning — refetch on each run
    missing = all_dois - successful
    refetch = missing | with_warning

    # Phase 2 (only after a week): successful cache older than 7 days
    if not all_dois:
        log.info("No DOIs found in scholar_data (empty or missing directory)")
        return 0

    total_ok = 0
    total_fail = 0

    if refetch:
        log.info(
            "Phase 1: refetching %d DOIs (missing: %d, blocked/warning: %d)",
            len(refetch),
            len(missing),
            len(with_warning & successful),
        )
        for doi in sorted(refetch):
            try:
                a = fetch_altmetric_score(doi, force_refresh=False)
                s = fetch_google_scholar_citations(doi, force_refresh=False)
                if a.found or s.found:
                    total_ok += 1
                else:
                    total_fail += 1
            except Exception as e:
                log.warning("Fetch failed for DOI %s: %s", doi, e)
                total_fail += 1

    if stale:
        log.info("Phase 2: revalidating %d DOIs with cache older than 7 days", len(stale))
        for doi in sorted(stale):
            try:
                a = fetch_altmetric_score(doi, force_refresh=False)
                s = fetch_google_scholar_citations(doi, force_refresh=False)
                if a.found or s.found:
                    total_ok += 1
                else:
                    total_fail += 1
            except Exception as e:
                log.warning("Revalidation failed for DOI %s: %s", doi, e)
                total_fail += 1

    log.info(
        "Revalidation complete: %d ok, %d failed (refetch: %d, stale: %d)",
        total_ok,
        total_fail,
        len(refetch),
        len(stale),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
