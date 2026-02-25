#!/usr/bin/env python3
"""
Revalidate DOI metrics cache for previously successful requests.

Run every 2 weeks via cron to refresh Altmetric scores and Google Scholar
citation counts. Only revalidates DOIs that previously returned success.
"""

import logging
import os
import sys

# Ensure project root is on path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

import src.cache_config  # noqa: E402, F401
from src.scholar_citations import (  # noqa: E402
    fetch_altmetric_score,
    fetch_google_scholar_citations,
    list_cached_successful_dois,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def main() -> int:
    dois = list_cached_successful_dois()
    if not dois:
        log.info("No cached successful DOIs to revalidate")
        return 0

    log.info("Revalidating %d DOIs", len(dois))
    ok = 0
    fail = 0
    for doi in dois:
        try:
            a = fetch_altmetric_score(doi, force_refresh=True)
            s = fetch_google_scholar_citations(doi, force_refresh=True)
            if a.found or s.found:
                ok += 1
            else:
                fail += 1
        except Exception as e:
            log.warning("Revalidation failed for DOI %s: %s", doi, e)
            fail += 1

    log.info("Revalidation complete: %d ok, %d failed", ok, fail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
