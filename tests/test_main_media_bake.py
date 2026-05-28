"""Tests for ``--bake-media-filtered`` and ``--refresh-news`` (without full Scholar scrape)."""

import json

from main import bake_media_filtered_to_disk, refresh_news_to_disk
from src.config import Config


def test_bake_preserves_last_fetched_and_writes_filtered(tmp_path, monkeypatch):
    d = tmp_path / "scholar_data"
    d.mkdir()
    sid = "ynWS968AAAAJ"
    fp = d / f"{sid}.json"
    old = "2019-06-01T12:00:00"
    fp.write_text(
        json.dumps({"name": "N", "media": [], "last_fetched": old}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(d))
    assert bake_media_filtered_to_disk(Config(scholar_id=sid)) == 0
    data = json.loads(fp.read_text(encoding="utf-8"))
    assert data["last_fetched"] == old
    assert data["media_filtered"] == []
    assert "media_filtered_at" in data


def test_refresh_news_updates_media_preserves_last_fetched(tmp_path, monkeypatch):
    d = tmp_path / "scholar_data"
    d.mkdir()
    sid = "ynWS968AAAAJ"
    fp = d / f"{sid}.json"
    old = "2018-01-01T00:00:00"
    fp.write_text(
        json.dumps({"name": "Dr X", "media": [{"title": "old", "url": ""}], "last_fetched": old}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(d))

    def fake_news(_name: str, existing_urls=None):
        assert existing_urls == set()
        return {"media": [{"title": "new item", "url": ""}]}

    monkeypatch.setattr("main.get_news_data", fake_news)
    monkeypatch.setattr("main.filter_media_items", lambda items: list(items))
    monkeypatch.setattr("main.enrich_filtered_media_thumbnails", lambda _sid, _items: 0)

    assert refresh_news_to_disk(Config(scholar_id=sid)) == 0
    data = json.loads(fp.read_text(encoding="utf-8"))
    assert data["last_fetched"] == old
    assert data["media"][0]["title"] == "new item"
    assert data["media_filtered"][0]["title"] == "new item"


def test_refresh_news_fails_without_author_name(tmp_path, monkeypatch):
    d = tmp_path / "scholar_data"
    d.mkdir()
    sid = "ynWS968AAAAJ"
    fp = d / f"{sid}.json"
    fp.write_text(
        json.dumps({"media": [], "last_fetched": "2020-01-01T00:00:00"}), encoding="utf-8"
    )
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(d))
    assert refresh_news_to_disk(Config(scholar_id=sid)) == 1


def test_refresh_news_passes_existing_media_filtered_urls(tmp_path, monkeypatch):
    d = tmp_path / "scholar_data"
    d.mkdir()
    sid = "ynWS968AAAAJ"
    fp = d / f"{sid}.json"
    existing_url = "https://example.test/already-indexed"
    fp.write_text(
        json.dumps(
            {
                "name": "Dr X",
                "media": [],
                "media_filtered": [{"title": "old", "url": existing_url}],
                "last_fetched": "2018-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(d))

    def fake_news(_name: str, existing_urls=None):
        assert existing_urls == {existing_url}
        return {"media": [{"title": "new item", "url": ""}]}

    monkeypatch.setattr("main.get_news_data", fake_news)
    monkeypatch.setattr("main.filter_media_items", lambda items: list(items))
    monkeypatch.setattr("main.enrich_filtered_media_thumbnails", lambda _sid, _items: 0)

    assert refresh_news_to_disk(Config(scholar_id=sid)) == 0
