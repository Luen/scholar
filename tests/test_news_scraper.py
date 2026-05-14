"""Tests for news scraper."""

from src.news_scraper import (
    CUSTOM_MEDIA_ADDITIONS,
    does_article_mention_keywords,
    does_article_mention_rummer,
)


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


def test_does_article_mention_rummer_accepts_name_and_lab():
    assert does_article_mention_rummer(
        "",
        "Walking sharks study",
        "Professor Jodie Rummer from James Cook University led the research.",
    )
    assert does_article_mention_rummer("", "RummerLab field season", "Updates from Moorea.")
    assert does_article_mention_rummer(
        "", "Physioshark tags juveniles", "Climate and shark physiology."
    )


def test_does_article_mention_rummer_rejects_generic_jcu_marine():
    assert not does_article_mention_rummer(
        "",
        "Master of Marine Biology - JCU Australia",
        "Information valid for students commencing in 2024.",
    )
    assert not does_article_mention_rummer(
        "",
        "JCU marine biology student explains volunteer experience",
        "James Cook University's location in the tropics allows access to reefs.",
    )


def test_does_article_mention_rummer_rejects_other_jcu_shark_experts():
    assert not does_article_mention_rummer(
        "",
        "Shark photobombs surfing competition",
        "Colin Simpfendorfer, a James Cook University shark expert, confirmed the image was of a shark.",
    )


def test_does_article_mention_rummer_rejects_unrelated_rummer_surname():
    assert not does_article_mention_rummer(
        "",
        "Catherine Rummer Obituary",
        "Catherine Marie Rummer passed away at her residence.",
    )


def test_does_article_mention_rummer_professor_rummer_needs_marine_context():
    assert does_article_mention_rummer(
        "",
        "Great Barrier Reef coral cover rebounds",
        "Professor Rummer said one species might be fast growing and repopulating quickly.",
    )
    assert not does_article_mention_rummer(
        "",
        "Zum Zusammenhang von Sprache und Emotion",
        "Professor Rummer weiter: Basierend auf diesen Befunden erscheint es uns naheliegend …",
    )


def test_does_article_mention_keywords_empty_when_not_relevant():
    assert not does_article_mention_keywords(
        "", "Marine Biology - JCU", "World leader in environmental sciences."
    )
