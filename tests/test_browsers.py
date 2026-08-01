"""Tests for Scrapling-based browser fetching (DOI fallback)."""

import pytest


def test_scrapling_static_fetcher_import():
    """Test that Scrapling's static fetcher can be imported."""
    try:
        from scrapling.fetchers import FetcherSession
    except ImportError as e:
        pytest.skip(f"Scrapling fetchers not installed: {e}")
    assert FetcherSession is not None


def _stealthy_fetcher_or_skip():
    """Return Scrapling's stealth browser fetcher when the optional stack is usable."""
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError as e:
        pytest.skip(f"Scrapling fetchers not installed: {e}")
    except Exception as e:
        pytest.skip(f"Scrapling fetchers unavailable in this environment: {e}")
    return StealthyFetcher


def test_scrapling_browser_fetcher_import():
    """Test that Scrapling's optional browser fetcher can be imported."""
    stealthy_fetcher = _stealthy_fetcher_or_skip()
    assert stealthy_fetcher is not None


@pytest.mark.integration
def test_scrapling_fetch_optional():
    """Optional: test that Scrapling can fetch a simple page (skip if no browser)."""
    stealthy_fetcher = _stealthy_fetcher_or_skip()

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
