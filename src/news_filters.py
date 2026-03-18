from __future__ import annotations

import json
import os
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from time import time

import requests
try:
    from scrapling.fetchers import FetcherSession  # type: ignore

    _SCRAPLING_AVAILABLE = True
except Exception:  # pragma: no cover
    FetcherSession = None  # type: ignore
    _SCRAPLING_AVAILABLE = False

URL_CHECK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RummerLab/1.0; +https://rummerlab.org)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

RUMMER_STRONG_MARKERS = (
    "rummerlab",
    "physioshark",
    "physiologyfish",
)

RUMMER_NAME_MARKERS = (
    "jodie rummer",
    "dr jodie rummer",
    "professor jodie rummer",
)

RUMMER_CONTEXT_MARKERS = (
    "shark",
    "sharks",
    "fish",
    "marine",
    "jcu",
    "james cook university",
)

NEWS_HTML_CACHE_DIR = Path(os.environ.get("CACHE_DIR", "cache")) / "news_html"
NEWS_HTML_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _news_html_cache_max_age_seconds() -> int | None:
    """
    Returns:
    - None: keep forever (no expiry)
    - int: max age in seconds
    """
    raw = os.environ.get("NEWS_HTML_CACHE_EXPIRE_SECONDS", None)
    if raw is None:
        return 60 * 60 * 24 * 365  # 365 days default
    if raw.strip() == "":
        return None
    return int(raw)


NEWS_HTML_CACHE_MAX_AGE_SECONDS = _news_html_cache_max_age_seconds()


def _url_cache_key(url: str) -> str:
    return sha256(url.encode("utf-8")).hexdigest()


def _cache_paths_for_url(url: str) -> tuple[Path, Path]:
    key = _url_cache_key(url)
    return (NEWS_HTML_CACHE_DIR / f"{key}.html", NEWS_HTML_CACHE_DIR / f"{key}.json")


def _is_likely_blocked_or_captcha(text_lower: str) -> bool:
    """
    Heuristics to avoid persisting "fake 200" pages (captcha / bot detection / blocked).
    Keep this broad; false positives are preferable to caching a captcha page.
    """
    markers = (
        "captcha",
        "recaptcha",
        "hcaptcha",
        "cloudflare",
        "ddos protection",
        "attention required",
        "verify you are human",
        "are you a robot",
        "access denied",
        "request blocked",
        "bot detection",
        "unusual traffic",
        "temporarily unavailable",
        "incapsula",
        "imperva",
        "akamai",
        "sucuri",
    )
    return any(m in text_lower for m in markers)


def _load_cached_html(url: str) -> str | None:
    html_path, meta_path = _cache_paths_for_url(url)
    if not html_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fetched_at = float(meta.get("fetched_at", 0))
        if fetched_at <= 0:
            return None
        if NEWS_HTML_CACHE_MAX_AGE_SECONDS is not None:
            if time() - fetched_at > NEWS_HTML_CACHE_MAX_AGE_SECONDS:
                return None
        return html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    except (ValueError, TypeError):
        return None


def _save_cached_html(url: str, html: str) -> None:
    html_path, meta_path = _cache_paths_for_url(url)
    try:
        html_path.write_text(html, encoding="utf-8", errors="ignore")
        meta_path.write_text(
            json.dumps({"url": url, "fetched_at": time()}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        # Best-effort cache only
        return


def _scrapling_fetch_html_prefix(url: str, *, timeout_s: int = 8) -> tuple[int, str, str] | None:
    """
    Fetch a page using Scrapling's static engine (browser-like TLS + headers).

    Returns (status_code, content_type_lower, text_lower) or None on any error.
    Only returns a bounded prefix of the page text (to keep it fast).
    """
    if not _SCRAPLING_AVAILABLE or FetcherSession is None:
        return None
    try:
        # NOTE: we create a short-lived session per call to keep this simple and safe.
        # If this becomes a hotspot, we can switch to a longer-lived session/pool.
        with FetcherSession(
            impersonate="chrome",
            timeout=timeout_s,
            stealthy_headers=True,
            follow_redirects=True,
            retries=2,
            retry_delay=1,
            verify=True,
        ) as s:
            resp = s.get(url)
        status_code = int(getattr(resp, "status_code", 0) or 0)
        headers = getattr(resp, "headers", {}) or {}
        # curl-cffi headers are case-insensitive; treat like dict
        ctype = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
        text = getattr(resp, "text", "") or ""
        if not isinstance(text, str):
            return None
        text_lower = text[:200_000].lower()
        return status_code, ctype, text_lower
    except Exception:
        return None


@lru_cache(maxsize=4096)
def url_is_definitely_404(url: str) -> bool:
    """
    Return True only when we're confident the URL is a 404.
    We do HEAD with redirects and a short timeout, with GET fallback for sites
    that block/disable HEAD.
    """
    try:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=5,
            headers=URL_CHECK_HEADERS,
        )
        if resp.status_code == 404:
            return True
        if resp.status_code in (405, 403):
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=5,
                headers=URL_CHECK_HEADERS,
                stream=True,
            )
            return resp.status_code == 404
        return False
    except requests.RequestException:
        # Only exclude on definitive 404. Any network hiccup -> keep the item.
        return False


@lru_cache(maxsize=4096)
def url_page_is_about_rummer(url: str) -> bool | None:
    """
    Best-effort content check.

    Returns:
    - True: confident the page mentions Dr Jodie Rummer / lab terms
    - False: confident it does NOT (based on fetched content)
    - None: unknown (blocked, paywall, non-HTML, network error) -> do not exclude
    """
    cached_html = _load_cached_html(url)
    if cached_html:
        text = cached_html.lower()
        if any(m in text for m in RUMMER_STRONG_MARKERS):
            return True
        if any(m in text for m in RUMMER_NAME_MARKERS):
            return True
        if "rummer" in text and any(m in text for m in ("jodie", *(RUMMER_CONTEXT_MARKERS))):
            return True
        return False

    try:
        fetched = _scrapling_fetch_html_prefix(url, timeout_s=8)
        if not fetched:
            return None
        status_code, ctype, text = fetched
        if status_code == 404:
            # Let the 404 filter handle it; treat as unknown here.
            return None
        if ctype and ("text/html" not in ctype and "application/xhtml+xml" not in ctype):
            return None
        if not text.strip():
            return None
        if _is_likely_blocked_or_captcha(text):
            return None

        if any(m in text for m in RUMMER_STRONG_MARKERS):
            _save_cached_html(url, text)
            return True
        if any(m in text for m in RUMMER_NAME_MARKERS):
            _save_cached_html(url, text)
            return True

        # We only accept generic "rummer" when there's some relevant context.
        if "rummer" in text and any(m in text for m in ("jodie", *(RUMMER_CONTEXT_MARKERS))):
            _save_cached_html(url, text)
            return True

        # If we successfully fetched HTML and found none of the markers, treat as not about.
        _save_cached_html(url, text)
        return False
    except requests.RequestException:
        return None


def filter_media_items(items: list[dict]) -> list[dict]:
    """
    Filter media items:
    - drop items with absolute URL that is definitively 404
    - drop items with absolute URL that we confidently conclude are not about Rummer
    - keep on unknown (errors, blocked, non-HTML) to avoid false negatives
    - keep items without an absolute URL
    """
    filtered: list[dict] = []
    for item in items:
        url = (item.get("url") or "").strip() if isinstance(item, dict) else ""
        # Keep items without an absolute URL (e.g. curated/in-site items).
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            filtered.append(item)
            continue
        if url_is_definitely_404(url):
            continue
        about = url_page_is_about_rummer(url)
        if about is False:
            continue
        filtered.append(item)
    return filtered


def clear_caches() -> None:
    url_is_definitely_404.cache_clear()
    url_page_is_about_rummer.cache_clear()

