"""Tests for news scraper."""

import src.news_scraper as news_scraper
from src.news_scraper import (
    CUSTOM_MEDIA_ADDITIONS,
    MediaItem,
    does_article_mention_keywords,
    does_article_mention_rummer,
    url_is_excluded_own_site,
)


def _disable_external_news_sources(monkeypatch):
    monkeypatch.setattr(news_scraper, "RSS_FEEDS", {})
    monkeypatch.setattr(news_scraper, "fetch_guardian_articles", lambda: [])
    monkeypatch.setattr(news_scraper, "fetch_newsapi_articles", lambda: [])
    monkeypatch.setattr(news_scraper, "fetch_gnews_articles", lambda: [])
    monkeypatch.setattr(news_scraper.time, "sleep", lambda _: None)
    monkeypatch.setenv("NEWS_ENABLE_GOOGLE_SEARCH", "0")
    monkeypatch.setenv("NEWS_ENABLE_NEWSPAPER4K", "0")
    monkeypatch.setenv("NEWS_ENABLE_WEB_SCRAPE", "0")


def _media_item(title: str, url: str = "", source: str = "Print Source") -> MediaItem:
    return {
        "type": "article",
        "source": source,
        "title": title,
        "description": "Curated coverage.",
        "url": url,
        "date": "2026-05-26T00:00:00Z",
        "sourceType": "Other",
        "image": None,
        "keywords": ["custom"],
    }


def test_custom_media_additions_structure():
    """Custom additions have required fields and unique non-empty URLs."""
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


def test_url_is_excluded_own_site():
    assert url_is_excluded_own_site("https://rummerlab.com/about")
    assert url_is_excluded_own_site("https://www.jodierummer.com/news/post")
    assert url_is_excluded_own_site("https://physioshark.org/research")
    assert url_is_excluded_own_site("https://blog.rummerlab.com/article")
    assert url_is_excluded_own_site("https://www.facebook.com/jodie.rummer/")
    assert url_is_excluded_own_site("https://au.linkedin.com/in/jodie-rummer-486a9556")
    assert url_is_excluded_own_site("https://x.com/physiologyfish")
    assert url_is_excluded_own_site("http://portfolio.jcu.edu.au/researchers/jodie.rummer/")
    assert url_is_excluded_own_site("https://www.instagram.com/rummerjodie/?hl=en")
    assert url_is_excluded_own_site("https://www.facebook.com/physioshark/")
    assert url_is_excluded_own_site("https://www.facebook.com/rummerlab/")
    assert url_is_excluded_own_site("https://www.instagram.com/physioshark/")
    assert url_is_excluded_own_site("https://www.instagram.com/rummerlab/")
    assert url_is_excluded_own_site(
        "https://www.facebook.com/physioshark/posts/remember-gail-schwieterman-our-visiting-scientist-from-last-season-since-leaving/582888185569924/"
    )
    assert not url_is_excluded_own_site("https://www.abc.net.au/news/2026-01-16/example")
    assert not url_is_excluded_own_site("https://www.facebook.com/someotherpage/posts/123")
    assert not url_is_excluded_own_site("")


def test_custom_media_includes_expected_sources():
    """Custom additions include Cairns Post, Discover Wildlife, ABC, Conversation."""
    sources = {a["source"] for a in CUSTOM_MEDIA_ADDITIONS}
    assert "Cairns Post" in sources
    assert "Discover Wildlife" in sources
    assert "The Conversation" in sources
    assert "ABC News" in sources


def test_fetch_all_news_preserves_distinct_url_less_custom_items(monkeypatch):
    """URL-less print placements should dedupe by title, not collapse into one blank URL."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [_media_item("First print placement"), _media_item("Second print placement")],
    )

    titles = {item["title"] for item in news_scraper.fetch_all_news()}

    assert titles == {"First print placement", "Second print placement"}


def test_fetch_all_news_preserves_real_url_less_custom_items(monkeypatch):
    """The curated URL-less custom entries survive fetch_all_news deduplication."""
    _disable_external_news_sources(monkeypatch)
    expected_url_less_titles = {
        item["title"] for item in CUSTOM_MEDIA_ADDITIONS if not item["url"].strip()
    }

    returned_url_less_titles = {
        item["title"] for item in news_scraper.fetch_all_news() if not item["url"].strip()
    }

    assert len(expected_url_less_titles) >= 2
    assert returned_url_less_titles == expected_url_less_titles


def test_fetch_all_news_still_dedupes_non_empty_urls(monkeypatch):
    """Articles sharing a non-empty URL should collapse to the highest-priority source."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [
            _media_item(
                "Lower-priority duplicate",
                url="https://example.test/news/story",
                source="NewsAPI",
            ),
            _media_item(
                "Higher-priority duplicate",
                url="https://example.test/news/story",
                source="Cairns Post",
            ),
        ],
    )

    titles = [item["title"] for item in news_scraper.fetch_all_news()]

    assert titles == ["Higher-priority duplicate"]


def test_fetch_all_news_replaces_same_url_and_removes_old_title(monkeypatch):
    """A URL replacement should not leave the old title in the title index."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [
            _media_item(
                "Lower-priority stale headline",
                url="https://example.test/news/story",
                source="NewsAPI",
            ),
            _media_item(
                "Higher-priority curated headline",
                url="https://example.test/news/story",
                source="Cairns Post",
            ),
        ],
    )

    titles = [item["title"] for item in news_scraper.fetch_all_news()]

    assert titles == ["Higher-priority curated headline"]


def test_fetch_all_news_dedupes_by_title_when_urls_differ(monkeypatch):
    """Articles with the same normalized title collapse even when one lacks a URL."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [
            _media_item(
                "Shared print headline",
                url="https://example.test/news/story",
                source="ABC News",
            ),
            _media_item("Shared print headline", source="Cairns Post"),
        ],
    )

    articles = news_scraper.fetch_all_news()

    assert len(articles) == 1
    assert articles[0]["source"] == "Cairns Post"
    assert articles[0]["url"] == ""


def test_fetch_all_news_keeps_custom_duplicate_over_scraped_source(monkeypatch):
    """Custom additions should win even when their source is not priority-listed."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [
            _media_item(
                "Curated duplicate story",
                url="https://example.com/curated-duplicate",
                source="Unlisted Custom Source",
            )
        ],
    )
    monkeypatch.setattr(
        news_scraper,
        "fetch_gnews_articles",
        lambda: [
            {
                "type": "article",
                "source": "GNews",
                "title": "Curated duplicate story",
                "description": "Scraped description.",
                "url": "https://example.com/curated-duplicate",
                "date": "2026-05-27T00:00:00Z",
                "sourceType": "Other",
                "image": None,
                "keywords": ["scraped"],
            }
        ],
    )

    articles = news_scraper.fetch_all_news()

    assert len(articles) == 1
    assert articles[0]["source"] == "Unlisted Custom Source"
    assert articles[0]["description"] == "Curated coverage."


def test_fetch_all_news_sorts_distinct_articles_by_source_priority(monkeypatch):
    """Custom duplicate priority should not move unrelated articles ahead of sources."""
    _disable_external_news_sources(monkeypatch)
    monkeypatch.setattr(
        news_scraper,
        "CUSTOM_MEDIA_ADDITIONS",
        [
            _media_item(
                "Curated lower-priority article",
                url="https://example.com/curated-lower-priority",
                source="Unlisted Custom Source",
            )
        ],
    )
    monkeypatch.setattr(
        news_scraper,
        "fetch_gnews_articles",
        lambda: [
            {
                "type": "article",
                "source": "GNews",
                "title": "Scraped higher-priority article",
                "description": "Scraped description.",
                "url": "https://example.com/scraped-higher-priority",
                "date": "2026-05-27T00:00:00Z",
                "sourceType": "Other",
                "image": None,
                "keywords": ["Jodie Rummer"],
            }
        ],
    )

    titles = [article["title"] for article in news_scraper.fetch_all_news()]

    assert titles == [
        "Scraped higher-priority article",
        "Curated lower-priority article",
    ]


def test_custom_media_includes_may_2026_shark_attack_coverage():
    """Custom additions include the curated May 2026 shark-attack coverage URLs."""
    urls = {a["url"] for a in CUSTOM_MEDIA_ADDITIONS}
    assert (
        "https://www.news.com.au/travel/travel-updates/incidents/bob-katter-calls-for-shark-culling-after-horror-attack-leaves-cairns-spearfisherman-dead/news-story/56ecba20db4aacb882e84930e8df0d33"
        in urls
    )
    assert (
        "https://www.abc.net.au/news/2026-05-25/queensland-spearfisher-shark-attack-victim-identified/106718104"
        in urls
    )
    assert (
        "https://divemagazine.com/scuba-diving-news/great-barrier-reef-spearfisher-killed-by-shark-bite"
        in urls
    )


def test_custom_media_includes_may_2026_print_placements():
    """Custom additions include the curated May 2026 print placements."""
    print_titles = {
        a["title"] for a in CUSTOM_MEDIA_ADDITIONS if "print" in (a.get("keywords") or [])
    }
    assert "Shark victim an action man" in print_titles
    assert "DIED WITH MATES" in print_titles
    assert "Cairns man identified as shark attack victim" in print_titles


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
