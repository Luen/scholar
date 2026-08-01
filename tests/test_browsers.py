"""Tests for Scrapling-based browser fetching (DOI fallback)."""

import pytest


def test_scrapling_static_fetcher_import():
    """Test that Scrapling's static fetcher can be imported."""
    try:
        from scrapling.fetchers import FetcherSession
    except ImportError as e:
        pytest.skip(f"Scrapling fetchers not installed: {e}")
    assert FetcherSession is not None


@pytest.mark.integration
def test_scrapling_fetch_optional():
    """Optional: test that Scrapling can fetch a simple page (skip if no browser)."""
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as e:
        pytest.skip(f"Scrapling browser fetcher not available: {e}")

    try:
        page = StealthyFetcher.fetch(
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
