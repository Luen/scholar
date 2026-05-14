"""
Download article cover images for news items missing thumbnails.

Runs during ``main.py`` (cron). Stores files under
``{SCHOLAR_DATA_DIR}/news_thumbnails/<scholar_id>/`` and sets each item's
``image.url`` to a public URL (see ``PUBLIC_API_BASE_URL``) or root-relative
``/scholar/<id>/news/thumbnail/<filename>`` for the API to serve.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from scrapling.fetchers import FetcherSession  # type: ignore

    _SCRAPLING_AVAILABLE = True
except Exception:  # pragma: no cover
    FetcherSession = None  # type: ignore
    _SCRAPLING_AVAILABLE = False

from src.news_scraper import extract_image_from_html, strip_html

logger = logging.getLogger(__name__)

PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; RummerLab/1.0; +https://rummerlab.org)",
}
IMAGE_HEADERS = {
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; RummerLab/1.0; +https://rummerlab.org)",
}

_MAX_HTML_BYTES = 600_000
_MAX_IMAGE_BYTES_DEFAULT = 2_500_000
_THUMBNAIL_FILENAME_RE = re.compile(r"^[a-f0-9]{64}\.(?:jpe?g|png|gif|webp)$", re.IGNORECASE)


def _max_image_bytes() -> int:
    raw = os.environ.get("NEWS_THUMB_MAX_BYTES", "").strip()
    if not raw:
        return _MAX_IMAGE_BYTES_DEFAULT
    try:
        n = int(raw)
    except ValueError:
        return _MAX_IMAGE_BYTES_DEFAULT
    return max(100_000, min(n, 8_000_000))


def _thumb_delay_seconds() -> float:
    raw = os.environ.get("NEWS_THUMB_FETCH_DELAY_SECONDS", "0.25").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.25


def scholar_data_dir() -> Path:
    return Path(os.environ.get("SCHOLAR_DATA_DIR", "scholar_data")).expanduser()


def public_api_base_url() -> str:
    """
    When set (e.g. ``https://api.rummerlab.com``), thumbnail ``image.url`` in JSON is
    absolute so consumers do not need to resolve paths. Empty → root-relative ``/scholar/...``.
    """
    return os.environ.get("PUBLIC_API_BASE_URL", "").strip().rstrip("/")


def thumbnail_image_public_url(scholar_id: str, filename: str) -> str:
    """Path served by Flask at ``GET /scholar/<id>/news/thumbnail/<filename>``."""
    path = f"/scholar/{scholar_id}/news/thumbnail/{filename}"
    base = public_api_base_url()
    if base:
        return f"{base}{path}"
    return path


def thumbnail_dir(scholar_id: str) -> Path:
    d = scholar_data_dir() / "news_thumbnails" / scholar_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def sniff_image_format(data: bytes) -> tuple[str, str] | None:
    """Return (file_extension, mime_type) or None."""
    if len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif", "image/gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _find_existing_thumbnail(thumb_dir: Path, digest: str) -> Path | None:
    for p in thumb_dir.glob(f"{digest}.*"):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp") and p.is_file():
            return p
    return None


def _fetch_html_page(url: str, *, timeout_s: int = 18) -> str | None:
    """Return raw HTML for meta / og:image discovery."""
    try:
        r = requests.get(
            url,
            headers=PAGE_HEADERS,
            timeout=timeout_s,
            allow_redirects=True,
        )
        if 200 <= r.status_code < 300 and r.text:
            return r.text[:_MAX_HTML_BYTES]
    except requests.RequestException as e:
        logger.debug("requests HTML fetch failed for %s: %s", url, e)

    if not _SCRAPLING_AVAILABLE or FetcherSession is None:
        return None
    try:
        with FetcherSession(
            impersonate="chrome",
            timeout=timeout_s,
            stealthy_headers=True,
            follow_redirects=True,
            retries=1,
            retry_delay=1,
            verify=True,
        ) as s:
            resp = s.get(url)
        code = int(getattr(resp, "status_code", 0) or 0)
        text = getattr(resp, "text", "") or ""
        if 200 <= code < 300 and isinstance(text, str) and text.strip():
            return text[:_MAX_HTML_BYTES]
    except Exception as e:
        logger.debug("Scrapling HTML fetch failed for %s: %s", url, e)
    return None


def _download_image_bytes(image_url: str, *, timeout_s: int = 25) -> bytes | None:
    if not image_url.startswith(("http://", "https://")):
        return None
    parsed = urlparse(image_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    max_b = _max_image_bytes()
    try:
        r = requests.get(
            image_url,
            headers=IMAGE_HEADERS,
            timeout=timeout_s,
            allow_redirects=True,
            stream=True,
        )
        if not (200 <= r.status_code < 300):
            return None
        chunks: list[bytes] = []
        total = 0
        for chunk in r.iter_content(64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_b:
                logger.warning("Image too large, skipping %s", image_url)
                return None
            chunks.append(chunk)
        return b"".join(chunks)
    except requests.RequestException as e:
        logger.debug("Image download failed %s: %s", image_url, e)
        return None


def _media_item_image_url(item: dict[str, Any]) -> str:
    img = item.get("image")
    if not isinstance(img, dict):
        return ""
    u = (img.get("url") or "").strip()
    return u


def _managed_thumbnail_filename(scholar_id: str, image_url: str) -> str | None:
    """Return the managed thumbnail filename when ``image_url`` points at our API route."""
    if not image_url:
        return None
    path = urlparse(image_url).path
    prefix = f"/scholar/{scholar_id}/news/thumbnail/"
    if not path.startswith(prefix):
        return None
    filename = path[len(prefix) :]
    if "/" in filename or not _THUMBNAIL_FILENAME_RE.match(filename):
        return None
    return filename


def _thumbnail_alt_text(item: dict[str, Any]) -> str:
    return strip_html((item.get("title") or "")[:500])


def _set_managed_thumbnail_image(scholar_id: str, filename: str, item: dict[str, Any]) -> bool:
    """Set the item image to the configured API URL. Returns True if data changed."""
    current = item.get("image")
    image = dict(current) if isinstance(current, dict) else {}
    before = dict(image)
    image["url"] = thumbnail_image_public_url(scholar_id, filename)
    alt = image.get("alt")
    if not isinstance(alt, str) or not alt.strip():
        image["alt"] = _thumbnail_alt_text(item)
    item["image"] = image
    return image != before


def _sync_existing_managed_thumbnail_url(scholar_id: str, item: dict[str, Any]) -> bool:
    filename = _managed_thumbnail_filename(scholar_id, _media_item_image_url(item))
    if not filename:
        return False
    return _set_managed_thumbnail_image(scholar_id, filename, item)


def ensure_thumbnail_for_item(scholar_id: str, item: dict[str, Any]) -> bool:
    """
    If item has an absolute article URL but no image, try og:image (etc.), download,
    and set ``image`` to a local API path. Returns True if ``image`` was set/updated.
    """
    if _sync_existing_managed_thumbnail_url(scholar_id, item):
        return True
    if _media_item_image_url(item):
        return False
    page_url = (item.get("url") or "").strip()
    if not page_url.startswith(("http://", "https://")):
        return False

    tdir = thumbnail_dir(scholar_id)
    digest = url_hash(page_url)
    existing = _find_existing_thumbnail(tdir, digest)
    if existing is not None:
        return _set_managed_thumbnail_image(scholar_id, existing.name, item)

    html = _fetch_html_page(page_url)
    if not html:
        return False
    remote_image = extract_image_from_html(html, page_url)
    if not remote_image:
        return False

    raw = _download_image_bytes(remote_image)
    if not raw:
        return False
    sniffed = sniff_image_format(raw)
    if not sniffed:
        logger.debug("Not a recognised image format from %s", remote_image)
        return False
    ext, _mime = sniffed
    dest = tdir / f"{digest}.{ext}"
    try:
        dest.write_bytes(raw)
    except OSError as e:
        logger.warning("Could not write thumbnail %s: %s", dest, e)
        return False

    return _set_managed_thumbnail_image(scholar_id, dest.name, item)


def enrich_filtered_media_thumbnails(scholar_id: str, items: list[dict[str, Any]]) -> int:
    """
    Populate missing thumbnails for filtered media. Returns count of items updated.
    """
    updated = 0
    delay = _thumb_delay_seconds()
    for item in items:
        try:
            if ensure_thumbnail_for_item(scholar_id, item):
                updated += 1
        except Exception as e:
            logger.warning("Thumbnail step failed for %s: %s", item.get("url"), e)
        if delay:
            time.sleep(delay)
    if updated:
        logger.info("News thumbnails: updated %d items for %s", updated, scholar_id)
    return updated
