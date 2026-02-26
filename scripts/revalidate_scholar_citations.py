#!/usr/bin/env python3
"""
Revalidate DOI metrics cache for previously successful requests.

Run weekly via cron (every 7 days) to refresh Altmetric scores and Google Scholar
citation counts when cache is expired. Only revalidates DOIs that previously
returned success. Does not use force_refresh so that if we get CAPTCHA/blocked
we fall back to the existing (possibly expired) cache instead of overwriting it.
Uses TOR_PROXY first (5 attempts), then SOCKS5_PROXIES (see .env.template).
"""

import logging
import sys

from common import setup_script

setup_script()

from src.scholar_citations import (
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
            a = fetch_altmetric_score(doi, force_refresh=False)
            s = fetch_google_scholar_citations(doi, force_refresh=False)
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
