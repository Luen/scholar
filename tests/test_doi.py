"""Tests for DOI extraction and resolution."""

from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from src import doi
from src.doi import (
    extract_doi_from_url,
    get_doi,
    get_doi_link,
    get_doi_short,
    get_doi_short_link,
)


@pytest.mark.integration
def test_get_doi_from_nature_url():
    """Extract DOI from Nature article URL."""
    publication_url = "https://www.nature.com/articles/nclimate2195"
    expected_doi = "10.1038/nclimate2195"
    assert get_doi(publication_url, "Rummer") == expected_doi


def test_extract_doi_from_url():
    """Extract DOI from URL patterns without network."""
    assert extract_doi_from_url("https://doi.org/10.1000/123") == "10.1000/123"
    assert extract_doi_from_url("https://example.com/doi/10.1000/456") == "10.1000/456"
    assert extract_doi_from_url("https://example.com/no-doi-here") is None


def test_scrapling_response_html_prefers_body_bytes():
    """Scrapling responses expose HTML differently across fetcher implementations."""
    page = SimpleNamespace(body=b"<html>from body</html>", encoding="utf-8", text="ignored")

    assert doi._get_html_from_scrapling_response(page) == "<html>from body</html>"


def test_scrapling_uses_static_fallback_when_browser_fetcher_fails(monkeypatch):
    """A broken optional browser stack should not prevent static Scrapling fallback."""
    doi.get_url_content_using_scrapling.cache_clear()
    monkeypatch.setattr(doi, "last_scraped", {})
    calls = []

    def fake_browser_fetch(url):
        calls.append(("browser", url))
        return None

    def fake_static_fetch(url):
        calls.append(("static", url))
        return "<html>from static fetcher</html>"

    monkeypatch.setattr(doi, "_fetch_html_with_stealthy_fetcher", fake_browser_fetch)
    monkeypatch.setattr(doi, "_fetch_html_with_fetcher_session", fake_static_fetch)

    html = doi.get_url_content_using_scrapling("https://example.test/article")

    assert html == "<html>from static fetcher</html>"
    assert calls == [
        ("browser", "https://example.test/article"),
        ("static", "https://example.test/article"),
    ]


def test_scrapling_skips_static_fallback_when_browser_fetcher_succeeds(monkeypatch):
    doi.get_url_content_using_scrapling.cache_clear()
    monkeypatch.setattr(doi, "last_scraped", {})

    monkeypatch.setattr(
        doi,
        "_fetch_html_with_stealthy_fetcher",
        lambda url: "<html>from browser fetcher</html>",
    )

    def fail_static_fetch(url):
        raise AssertionError("static fallback should not be called")

    monkeypatch.setattr(doi, "_fetch_html_with_fetcher_session", fail_static_fetch)

    assert (
        doi.get_url_content_using_scrapling("https://example.test/article")
        == "<html>from browser fetcher</html>"
    )


@pytest.mark.integration
def test_get_doi_link_and_short():
    """Resolve DOI link and short DOI (requires network)."""
    doi = "10.1038/nclimate2195"
    link = get_doi_link(doi)
    assert link is not None
    host = urlparse(link).hostname or ""
    assert host == "doi.org" or host.endswith(".doi.org")
    assert doi in link

    short_doi = get_doi_short(doi)
    if short_doi:
        short_link = get_doi_short_link(short_doi)
        assert short_link is not None
        short_host = urlparse(short_link).hostname or ""
        assert short_host == "doi.org" or short_host.endswith(".doi.org")
