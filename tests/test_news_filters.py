import json

import pytest


class _FakeResp:
    def __init__(self, status_code=200, headers=None, body=b""):
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._body = body

    def iter_content(self, chunk_size=8192):
        # Yield in a couple chunks to simulate streaming.
        b = self._body
        for i in range(0, len(b), chunk_size):
            yield b[i : i + chunk_size]


def _write_scholar(tmp_path, scholar_id, media):
    p = tmp_path / f"{scholar_id}.json"
    p.write_text(json.dumps({"name": "Test", "media": media}), encoding="utf-8")


@pytest.fixture(autouse=True)
def isolated_news_html_cache(monkeypatch, tmp_path):
    from src import news_filters

    cache_dir = tmp_path / "news_html"
    cache_dir.mkdir()
    monkeypatch.setattr(news_filters, "NEWS_HTML_CACHE_DIR", cache_dir)
    news_filters.clear_caches()
    yield
    news_filters.clear_caches()


def test_news_filters_exclude_404_and_irrelevant(monkeypatch, tmp_path):
    # Import after tmp dir exists so we can patch module globals.
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "title": "Field season wrap-up",
            "description": "Updates from RummerLab and Physioshark in Moorea.",
            "url": "https://example.test/ok",
        },
        {"title": "drop 404", "url": "https://example.test/missing"},
        {
            "title": "Unrelated",
            "description": "No marine biology or Rummer content here.",
            "url": "https://example.test/irrelevant",
        },
        {"title": "keep no url", "url": ""},
    ]
    _write_scholar(tmp_path, scholar_id, media)

    def fake_head(url, *args, **kwargs):
        if url.endswith("/missing"):
            return _FakeResp(status_code=404)
        return _FakeResp(status_code=200)

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        if url.endswith("/ok"):
            return (
                200,
                "text/html; charset=utf-8",
                "<html><body>RummerLab physioshark</body></html>".lower(),
            )
        if url.endswith("/irrelevant"):
            return (
                200,
                "text/html; charset=utf-8",
                "<html><body>This is unrelated content about something else.</body></html>".lower(),
            )
        return 200, "text/html; charset=utf-8", "<html></html>"

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    titles = [x.get("title") for x in res.json["media"]]
    assert "Field season wrap-up" in titles
    assert "keep no url" in titles
    assert "drop 404" not in titles
    assert "Unrelated" not in titles


def test_news_filters_keep_on_network_errors(monkeypatch, tmp_path):
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "title": "External article with unavailable page text",
            "description": "A source page whose preview text is not enough to classify.",
            "url": "https://example.test/flaky",
        }
    ]
    _write_scholar(tmp_path, scholar_id, media)
    scrapling_calls: list[str] = []

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        scrapling_calls.append(url)
        return None

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    titles = [x.get("title") for x in res.json["media"]]
    assert titles == ["External article with unavailable page text"]
    assert scrapling_calls == ["https://example.test/flaky"]


def test_news_filters_drop_google_search_without_rummer_in_snippet(monkeypatch, tmp_path):
    """Google Search rows with only generic JCU/marine text must not hit Scrapling."""
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "source": "Google Search",
            "title": "Jacinta Jefferies | LinkedIn",
            "description": "Marine Scientist | Master of Marine Biology JCU Graduate",
            "url": "https://example.test/linkedin-jacinta",
        }
    ]
    _write_scholar(tmp_path, scholar_id, media)

    scrapling_calls: list[str] = []

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        scrapling_calls.append(url)
        return 200, "text/html; charset=utf-8", "<html><body>rummerlab</body></html>".lower()

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    assert res.json["media"] == []
    assert scrapling_calls == []


def test_news_filters_snippet_match_skips_url_page_fetch(monkeypatch, tmp_path):
    """When title/description pass strict relevance, do not call url_page_is_about_rummer."""
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "source": "The Guardian",
            "title": "Professor Jodie Rummer on reef fish",
            "description": "Research at James Cook University.",
            "url": "https://example.test/guardian-article",
        }
    ]
    _write_scholar(tmp_path, scholar_id, media)

    def boom(_url: str):
        raise RuntimeError("url_page_is_about_rummer should not run when snippet matches")

    boom.cache_clear = lambda: None  # teardown: clear_caches() calls this on patched name
    monkeypatch.setattr(news_filters, "url_page_is_about_rummer", boom)

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    monkeypatch.setattr(news_filters.requests, "head", fake_head)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    assert len(res.json["media"]) == 1
    assert res.json["media"][0]["title"] == "Professor Jodie Rummer on reef fish"


def test_news_filters_drop_gnews_without_rummer_in_snippet(monkeypatch, tmp_path):
    """GNews rows use the same strict snippet gate as Custom Search rows."""
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "source": "GNews",
            "title": "JCU marine biology graduate launches consultancy",
            "description": "A generic profile about reef science and marine biology.",
            "url": "https://example.test/gnews-generic",
        }
    ]
    _write_scholar(tmp_path, scholar_id, media)

    scrapling_calls: list[str] = []

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        scrapling_calls.append(url)
        return 200, "text/html; charset=utf-8", "<html><body>rummerlab</body></html>".lower()

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    assert res.json["media"] == []
    assert scrapling_calls == []


def test_news_filters_google_snippet_matches_ingestion_order(monkeypatch, tmp_path):
    """Snippet checks must mirror scraper ingestion order for boundary-sensitive handles."""
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {
            "source": "Google Search",
            "title": "Lab field update",
            "description": "Rummer",
            "url": "https://example.test/google-boundary",
        }
    ]
    _write_scholar(tmp_path, scholar_id, media)

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        return None

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    assert [x.get("title") for x in res.json["media"]] == ["Lab field update"]


def test_url_page_is_about_rummer_does_not_cache_non_2xx(monkeypatch):
    from src import news_filters

    url = "https://example.test/blocked"

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        return 403, "text/html; charset=utf-8", "<html><body>rummerlab</body></html>".lower()

    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    assert news_filters.url_page_is_about_rummer(url) is None
    html_path, meta_path = news_filters._cache_paths_for_url(url)
    assert not html_path.exists()
    assert not meta_path.exists()


def test_parts_news_is_rejected(monkeypatch, tmp_path):
    from src import serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)

    scholar_id = "ynWS968AAAAJ"
    _write_scholar(tmp_path, scholar_id, [{"title": "x", "url": "https://example.test/x"}])

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}?parts=news")
    assert res.status_code == 400
    assert "News must be fetched via /scholar/<id>/news" in res.json["error"]
