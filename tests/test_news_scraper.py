"""Tests for news scraper."""

from src.news_scraper import CUSTOM_MEDIA_ADDITIONS


def test_custom_media_additions_structure():
    """Custom additions have required fields and unique URLs (except one empty)."""
    assert len(CUSTOM_MEDIA_ADDITIONS) >= 5
    seen_urls = set()
    for item in CUSTOM_MEDIA_ADDITIONS:
        assert item["type"] == "article"
        assert "source" in item
        assert "title" in item
        assert "url" in item
        assert "date" in item
        if item["url"]:
            assert item["url"] not in seen_urls, f"Duplicate URL: {item['url']}"
            seen_urls.add(item["url"])


def test_custom_media_includes_expected_sources():
    """Custom additions include Cairns Post, Discover Wildlife, ABC, Conversation."""
    sources = {a["source"] for a in CUSTOM_MEDIA_ADDITIONS}
    assert "Cairns Post" in sources
    assert "Discover Wildlife" in sources
    assert "The Conversation" in sources
    assert "ABC News" in sources
