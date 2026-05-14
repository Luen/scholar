"""Tests for cached news artifact maintenance in the main pipeline."""

import json

import main as pipeline


def test_refresh_cached_news_artifacts_preserves_last_fetched(monkeypatch, tmp_path):
    original_last_fetched = "2026-05-14T01:00:00+00:00"
    author = {
        "last_fetched": original_last_fetched,
        "media": [{"title": "raw", "url": "https://example.com/a"}],
    }
    output_path = tmp_path / "ynWS968AAAAJ.json"

    monkeypatch.setattr(
        pipeline,
        "filter_media_items",
        lambda items: [{"title": "filtered", "url": "", "description": ""}],
    )
    monkeypatch.setattr(pipeline, "enrich_filtered_media_thumbnails", lambda _sid, _items: 0)

    assert pipeline._refresh_cached_news_artifacts(
        author,
        "ynWS968AAAAJ",
        str(output_path),
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["last_fetched"] == original_last_fetched
    assert saved["media_filtered"] == [{"title": "filtered", "url": "", "description": ""}]


def test_refresh_cached_news_artifacts_saves_thumbnail_only_changes(monkeypatch, tmp_path):
    original_last_fetched = "2026-05-14T01:00:00+00:00"
    author = {
        "last_fetched": original_last_fetched,
        "media_filtered": [{"title": "filtered", "url": "", "description": ""}],
    }
    output_path = tmp_path / "ynWS968AAAAJ.json"

    def add_image(_sid, items):
        items[0]["image"] = {"url": "/scholar/ynWS968AAAAJ/news/thumbnail/x.jpg"}
        return 1

    monkeypatch.setattr(pipeline, "enrich_filtered_media_thumbnails", add_image)

    assert pipeline._refresh_cached_news_artifacts(
        author,
        "ynWS968AAAAJ",
        str(output_path),
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["last_fetched"] == original_last_fetched
    assert (
        saved["media_filtered"][0]["image"]["url"] == "/scholar/ynWS968AAAAJ/news/thumbnail/x.jpg"
    )
