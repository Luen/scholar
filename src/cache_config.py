"""
Configure requests-cache for HTTP response caching.

Must be imported before any code that uses requests or scholarly,
so that all HTTP traffic (DOI APIs, Hero scraper, scholarly, etc.) is cached.
"""

import os

import requests_cache

CACHE_DIR = os.environ.get("CACHE_DIR", "cache")
CACHE_DB = os.path.join(CACHE_DIR, "http_cache")
EXPIRE_AFTER = int(os.environ.get("CACHE_EXPIRE_SECONDS", 60 * 60 * 24 * 30))  # 30 days default

os.makedirs(CACHE_DIR, exist_ok=True)

requests_cache.install_cache(
    CACHE_DB,
    backend="sqlite",
    expire_after=EXPIRE_AFTER,
    allowable_methods=("GET", "POST"),
    allowable_codes=(200, 203, 300, 301),
)
