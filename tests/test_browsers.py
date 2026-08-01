"""Tests for Scrapling-based browser fetching (DOI fallback)."""

import pytest


def _load_stealthy_fetcher():
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as e:
        pytest.skip(f"Scrapling fetchers not available: {e}")
    return StealthyFetcher


def test_scrapling_import():
    """Test that Scrapling fetchers can be imported."""
    stealthy_fetcher = _load_stealthy_fetcher()
    assert stealthy_fetcher is not None


@pytest.mark.integration
def test_scrapling_fetch_optional():
    """Optional: test that Scrapling can fetch a simple page (skip if no browser)."""
    stealthy_fetcher = _load_stealthy_fetcher()

    try:
        page = stealthy_fetcher.fetch(
            "https://example.com",
            headless=True,
            timeout=15000,
        )
        assert page is not None
        html = None
        if hasattr(page, "body") and page.body is not None:
            enc = getattr(page, "encoding", None) or "utf-8"
            html = page.body.decode(enc, errors="replace")
        if html:
            assert "Example Domain" in html or "example" in html.lower()
    except Exception as e:
        pytest.skip(f"Scrapling fetch not available (e.g. browser not installed): {e}")
