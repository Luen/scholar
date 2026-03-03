#!/usr/bin/env python3
"""
Remove DOIs from scholar_data (publication entries) and from the DOI metrics cache.

Usage:
  python scripts/remove_dois_from_data_and_cache.py 10.1093/conphys/coab030 10.14288/1.0071389

Run from project root or via: docker exec scholar_web python scripts/remove_dois_from_data_and_cache.py DOI ...
"""

import json
import os
import sys

from common import PROJECT_ROOT, setup_script  # noqa: E402

setup_script()

from src.doi_utils import normalize_doi  # noqa: E402
from src.scholar_citations import CACHE_DIR  # noqa: E402


def _normalize_doi_for_cache(doi: str) -> str:
    return doi.replace("/", "_").replace(":", "_").strip()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: remove_dois_from_data_and_cache.py DOI [DOI ...]", file=sys.stderr)
        return 1

    to_remove = set()
    for raw in sys.argv[1:]:
        doi = (raw or "").strip()
        if doi:
            to_remove.add(normalize_doi(doi))

    if not to_remove:
        print("No DOIs to remove.", file=sys.stderr)
        return 1

    # Scholar data directory
    data_dir = os.environ.get("SCHOLAR_DATA_DIR", "scholar_data")
    if not os.path.isabs(data_dir):
        data_dir = os.path.join(PROJECT_ROOT, data_dir)

    removed_from_data = 0
    if os.path.isdir(data_dir):
        for name in os.listdir(data_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(data_dir, name)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            pubs = data.get("publications") or []
            new_pubs = [
                p for p in pubs if normalize_doi((p.get("doi") or "").strip()) not in to_remove
            ]
            dropped = len(pubs) - len(new_pubs)
            if dropped:
                data["publications"] = new_pubs
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    removed_from_data += dropped
                    print(f"  {name}: removed {dropped} publication(s)")
                except OSError as e:
                    print(f"  {name}: failed to write: {e}", file=sys.stderr)
    else:
        print(f"Scholar data dir not found: {data_dir}", file=sys.stderr)

    # DOI metrics cache (scholar_*.json, altmetric_*.json)
    removed_from_cache = 0
    if os.path.isdir(CACHE_DIR):
        for doi in to_remove:
            safe = _normalize_doi_for_cache(doi)
            for prefix in ("scholar", "altmetric"):
                p = os.path.join(CACHE_DIR, f"{prefix}_{safe}.json")
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                        removed_from_cache += 1
                        print(f"  removed cache: {os.path.basename(p)}")
                    except OSError as e:
                        print(f"  failed to remove {p}: {e}", file=sys.stderr)

    print(
        f"Done: {removed_from_data} publication(s) removed from data, {removed_from_cache} cache file(s) removed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
