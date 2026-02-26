#!/usr/bin/env python3
"""
Check why DOIs are "missing" for Altmetric/Google Scholar API.

The API returns 401 when Crossref does not list Rummer, Bergseth, or Wu as authors.
This script fetches Crossref metadata for each DOI and reports whether it would
pass the allowlist and what authors Crossref returns.
"""

import os
import sys

# Allow importing from project root
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, _project_root)

import src.cache_config  # noqa: F401
from src.crossref import fetch_crossref_details
from src.scholar_citations import ALLOWED_AUTHORS, _authors_contain_allowed
from src.doi_utils import normalize_doi

DOIS = [
    "10.7717/peerj.20222",
    "10.1016/j.tree.2023.12.004",
    "10.1111/cobi.14390",
    "10.1655/0018-0831-77.1.37",
    "10.1093/conphys/coaa138",
    "10.7717/peerj.3805",
    "10.1098/rsif.2018.0276",
    "10.5268/IW-3.3.550",
    "10.1242/jeb.113803",
    "10.1111/gcb.15127",
    "10.1038/s41598-022-09950-y",
    "10.1242/jeb.192245",
    "10.1093/conphys/coaf038",
    "10.1038/s41586-025-08665-0",
]


def main():
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
        def safe(s):
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
