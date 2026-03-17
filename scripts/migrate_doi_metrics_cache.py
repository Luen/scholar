#!/usr/bin/env python3
"""
One-off migration: add last_fetched_result and last_successful_fetch to existing
DOI metrics cache files (altmetric_*.json, scholar_*.json, crossref_*.json).

Run once after deploying the new cache schema. Idempotent: skips files that
already have last_fetched_result. Safe to run multiple times.

Usage:
  python scripts/migrate_doi_metrics_cache.py

From project root or: docker exec scholar_web python scripts/migrate_doi_metrics_cache.py
"""

import json
import os
import sys

from common import PROJECT_ROOT, setup_script  # noqa: E402

setup_script()

from src.scholar_citations import (  # noqa: E402
    CACHE_DIR,
    FETCH_RESULT_AUTHOR_NOT_ALLOWED,
    FETCH_RESULT_BLOCKED,
    FETCH_RESULT_ERROR,
    FETCH_RESULT_NOT_FOUND,
    FETCH_RESULT_SUCCESS,
)


def _infer_last_fetched_result(path: str, data: dict) -> str:
    """Infer last_fetched_result from existing cache fields."""
    prefix = os.path.basename(path).split("_")[0]
    found = data.get("found", True)
    error_reason = (data.get("error_reason") or "").lower()
    warning = (data.get("warning") or "").lower()

    if prefix == "crossref":
        if found:
            return FETCH_RESULT_SUCCESS
        return FETCH_RESULT_NOT_FOUND if "not found" in error_reason or "no data" in error_reason else FETCH_RESULT_ERROR

    if prefix == "altmetric":
        if found:
            return FETCH_RESULT_SUCCESS
        return FETCH_RESULT_AUTHOR_NOT_ALLOWED if "allowlist" in error_reason or "author" in error_reason else FETCH_RESULT_NOT_FOUND

    # scholar
    if not found:
        return FETCH_RESULT_AUTHOR_NOT_ALLOWED if "allowlist" in error_reason or "author" in error_reason else FETCH_RESULT_NOT_FOUND
    if warning:
        return FETCH_RESULT_BLOCKED if "blocked" in warning else FETCH_RESULT_ERROR
    return FETCH_RESULT_SUCCESS


def _infer_last_successful_fetch(data: dict, result: str) -> str | None:
    """Set last_successful_fetch to fetched_at when current record is a success."""
    if result != FETCH_RESULT_SUCCESS:
        return None
    return data.get("fetched_at")


def migrate_file(path: str, dry_run: bool) -> bool:
    """Add last_fetched_result and last_successful_fetch if missing. Returns True if updated."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  skip {os.path.basename(path)}: read failed - {e}", file=sys.stderr)
        return False

    if data.get("last_fetched_result") is not None:
        return False

    result = _infer_last_fetched_result(path, data)
    data["last_fetched_result"] = result
    successful = _infer_last_successful_fetch(data, result)
    if successful is not None:
        data["last_successful_fetch"] = successful

    if dry_run:
        print(f"  [dry-run] would add last_fetched_result={result!r} last_successful_fetch={successful!r} -> {os.path.basename(path)}")
        return True

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"  failed to write {path}: {e}", file=sys.stderr)
        return False
    print(f"  migrated {os.path.basename(path)} -> last_fetched_result={result!r}")
    return True


def main() -> int:
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    if dry_run:
        print("Dry run (no files will be modified)\n")

    cache_dir = CACHE_DIR
    if not os.path.isabs(cache_dir):
        cache_dir = os.path.join(PROJECT_ROOT, cache_dir)

    if not os.path.isdir(cache_dir):
        print(f"Cache dir not found: {cache_dir}", file=sys.stderr)
        return 0

    prefixes = ("altmetric_", "scholar_", "crossref_")
    updated = 0
    skipped = 0
    for name in sorted(os.listdir(cache_dir)):
        if not name.endswith(".json"):
            continue
        if not any(name.startswith(p) for p in prefixes):
            continue
        path = os.path.join(cache_dir, name)
        if not os.path.isfile(path):
            continue
        if migrate_file(path, dry_run=dry_run):
            updated += 1
        else:
            skipped += 1

    print(f"\nDone: {updated} migrated, {skipped} already up to date (or skipped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
