"""Tests for /scholar/<id>/news and pre-filtered media."""

import json

from src.serve import _served_media_items


def test_served_media_items_prefers_media_filtered():
    assert _served_media_items(
        {
            "media_filtered": [{"title": "precooked", "url": ""}],
            "media": [{"title": "raw", "url": "https://example.com/a"}],
        }
    ) == [{"title": "precooked", "url": ""}]


def test_served_media_items_empty_filtered_list_is_used():
    """Empty precooked list means 'no items passed filter', not 'fall back to raw'."""
    assert (
        _served_media_items({"media_filtered": [], "media": [{"title": "x", "url": "https://a"}]})
        == []
    )


def test_news_endpoint_skips_live_filter_when_media_filtered_present(monkeypatch, tmp_path):
    from src import news_filters, serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    scholar_id = "ynWS968AAAAJ"
    payload = {
        "name": "Test",
        "media": [
            {
                "source": "Google Search",
                "title": "noise",
                "description": "marine biology JCU only",
                "url": "https://example.test/n",
            }
        ],
        "media_filtered": [{"title": "ok", "url": "", "description": ""}],
        "media_filtered_at": "2026-05-14T12:00:00+00:00",
    }
    (tmp_path / f"{scholar_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    def boom(*_a, **_k):
        raise RuntimeError("filter_media_items must not run when media_filtered is set")

    monkeypatch.setattr(news_filters, "filter_media_items", boom)
    c = serve.app.test_client()
    res = c.get(f"/scholar/{scholar_id}/news?limit=50")
    assert res.status_code == 200
    assert res.json["media"][0]["title"] == "ok"
    assert res.json["filtered_at"] == "2026-05-14T12:00:00+00:00"
