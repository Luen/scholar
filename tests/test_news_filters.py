import json


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


def test_news_filters_exclude_404_and_irrelevant(monkeypatch, tmp_path):
    # Import after tmp dir exists so we can patch module globals.
    from src import serve
    from src import news_filters

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [
        {"title": "keep strong marker", "url": "https://example.test/ok"},
        {"title": "drop 404", "url": "https://example.test/missing"},
        {"title": "drop irrelevant", "url": "https://example.test/irrelevant"},
        {"title": "keep no url", "url": ""},
    ]
    _write_scholar(tmp_path, scholar_id, media)

    def fake_head(url, *args, **kwargs):
        if url.endswith("/missing"):
            return _FakeResp(status_code=404)
        return _FakeResp(status_code=200)

    def fake_get(url, *args, **kwargs):
        raise AssertionError("requests.get should not be used for relevance fetching")

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        if url.endswith("/ok"):
            return 200, "text/html; charset=utf-8", "<html><body>RummerLab physioshark</body></html>".lower()
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
    assert "keep strong marker" in titles
    assert "keep no url" in titles
    assert "drop 404" not in titles
    assert "drop irrelevant" not in titles


def test_news_filters_keep_on_network_errors(monkeypatch, tmp_path):
    from src import serve
    from src import news_filters

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    news_filters.clear_caches()

    scholar_id = "ynWS968AAAAJ"
    media = [{"title": "keep on error", "url": "https://example.test/flaky"}]
    _write_scholar(tmp_path, scholar_id, media)

    def fake_head(url, *args, **kwargs):
        return _FakeResp(status_code=200)

    def fake_get(url, *args, **kwargs):
        raise AssertionError("requests.get should not be used for relevance fetching")

    def fake_scrapling_fetch(url: str, *, timeout_s: int = 8):
        return None

    monkeypatch.setattr(news_filters.requests, "head", fake_head)
    monkeypatch.setattr(news_filters, "_scrapling_fetch_html_prefix", fake_scrapling_fetch)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    titles = [x.get("title") for x in res.json["media"]]
    assert titles == ["keep on error"]


def test_parts_news_is_rejected(monkeypatch, tmp_path):
    from src import serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)

    scholar_id = "ynWS968AAAAJ"
    _write_scholar(tmp_path, scholar_id, [{"title": "x", "url": "https://example.test/x"}])

    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}?parts=news")
    assert res.status_code == 400
    assert "News must be fetched via /scholar/<id>/news" in res.json["error"]

