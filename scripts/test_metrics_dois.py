#!/usr/bin/env python3
"""
Test Google Scholar citations and Altmetric scores for the DOIs in common.DOIS.

Reports which DOIs fail to get Altmetric data and which fail to get Google Scholar
citations (e.g. 401 author allowlist, no data, or request/parse failure).
Uses TOR_PROXY first (5 attempts), then SOCKS5_PROXIES (see .env.template).
"""

from common import DOIS, setup_script

setup_script()

from src.doi_utils import normalize_doi
from src.scholar_citations import (
    fetch_altmetric_score,
    fetch_google_scholar_citations,
)


def main() -> None:
    failed_altmetric: list[str] = []
    failed_scholar: list[str] = []

    print("Testing Google Scholar citations and Altmetric scores for", len(DOIS), "DOIs\n")
    print("-" * 70)

    for raw_doi in DOIS:
        doi = normalize_doi(raw_doi)
        alt = fetch_altmetric_score(doi)
        scholar = fetch_google_scholar_citations(doi)

        alt_ok = alt.found and alt.score is not None
        scholar_ok = scholar.found and scholar.citations is not None

        if not alt_ok:
            failed_altmetric.append(doi)
        if not scholar_ok:
            failed_scholar.append(doi)

        status_alt = "OK" if alt_ok else "FAIL"
        status_scholar = "OK" if scholar_ok else "FAIL"
        score_str = str(alt.score) if alt.score is not None else "n/a"
        cites_str = str(scholar.citations) if scholar.citations is not None else "n/a"

        print(f"  {doi}")
        print(f"    Altmetric: {status_alt}  (score={score_str})")
        print(f"    Scholar:   {status_scholar}  (citations={cites_str})")
        if not alt_ok and alt.found is False:
            print("    -> Altmetric: author not in allowlist (401)")
        elif not alt_ok:
            print("    -> Altmetric: no score / fetch failed")
        if not scholar_ok and scholar.found is False:
            print("    -> Scholar: author not in allowlist (401)")
        elif not scholar_ok:
            print("    -> Scholar: no citations / fetch failed or blocked")
        print()

    print("-" * 70)
    print("SUMMARY")
    print("-" * 70)
    print(f"Altmetric failures ({len(failed_altmetric)}):")
    for d in failed_altmetric:
        print(f"  {d}")
    if not failed_altmetric:
        print("  (none)")
    print()
    print(f"Google Scholar failures ({len(failed_scholar)}):")
    for d in failed_scholar:
        print(f"  {d}")
    if not failed_scholar:
        print("  (none)")
    both = [d for d in failed_altmetric if d in failed_scholar]
    if both:
        print()
        print(f"Failed both ({len(both)}):")
        for d in both:
            print(f"  {d}")


if __name__ == "__main__":
    main()
