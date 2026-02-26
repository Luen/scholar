#!/usr/bin/env python3
"""
Check why DOIs are "missing" for Altmetric/Google Scholar API.

The API returns 401 when Crossref does not list Rummer, Bergseth, or Wu as authors.
This script fetches Crossref metadata for each DOI and reports whether it would
pass the allowlist and what authors Crossref returns.
"""

from common import DOIS, setup_script

setup_script()

from src.crossref import fetch_crossref_details  # noqa: E402
from src.doi_utils import normalize_doi  # noqa: E402
from src.scholar_citations import ALLOWED_AUTHORS, _authors_contain_allowed  # noqa: E402


def main() -> None:
    print("Allowed author names for API:", ALLOWED_AUTHORS)
    print()
    for raw_doi in DOIS:
        doi = normalize_doi(raw_doi)
        crossref = fetch_crossref_details(doi)
        if not crossref:
            print(f"  {doi}")
            print("    -> Crossref: no metadata (DOI not found or request failed)")
            print()
            continue
        authors = crossref.authors or []
        allowed = _authors_contain_allowed(crossref.authors)
        status = "PASS (would get Altmetric/GS)" if allowed else "FAIL (401 - author not in allowlist)"

        def safe(s: str | None) -> str:
            return s.encode("ascii", errors="replace").decode("ascii") if s else ""

        title_safe = safe((crossref.title or "")[:70]) + "..."
        authors_preview = [safe(a) for a in authors[:8]]
        if len(authors) > 8:
            authors_preview.append("...")
        print(f"  {doi}")
        print(f"    Title: {title_safe}")
        print(f"    Authors: {authors_preview}")
        print(f"    -> {status}")
        print()


if __name__ == "__main__":
    main()
