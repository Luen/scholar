"""Tests for /scholar/<id>/news and pre-filtered media."""

import json

from src.serve import _served_media_items

SCHOLAR_ID = "ynWS968AAAAJ"


def _write_scholar(tmp_path, scholar_id=SCHOLAR_ID, **payload):
    data = {
        "name": "Test",
        "publications": [{"title": "paper"}],
        "media": [{"title": "raw", "url": "https://example.test/raw"}],
        "media_filtered": [{"title": "filtered", "url": "https://example.test/filtered"}],
        "media_filtered_at": "2026-05-14T12:00:00+00:00",
        **payload,
    }
    (tmp_path / f"{scholar_id}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


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
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    _write_scholar(
        tmp_path,
        media=[
            {
                "source": "Google Search",
                "title": "noise",
                "description": "marine biology JCU only",
                "url": "https://example.test/n",
            }
        ],
        media_filtered=[{"title": "ok", "url": "", "description": ""}],
    )

    def boom(*_a, **_k):
        raise RuntimeError("filter_media_items must not run when media_filtered is set")

    monkeypatch.setattr(serve, "filter_media_items", boom)
    c = serve.app.test_client()
    res = c.get(f"/scholar/{SCHOLAR_ID}/news?limit=50")
    assert res.status_code == 200
    assert res.json["media"][0]["title"] == "ok"
    assert res.json["filtered_at"] == "2026-05-14T12:00:00+00:00"


def test_news_endpoint_omits_filtered_at_for_legacy_media(monkeypatch, tmp_path):
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    _write_scholar(tmp_path, media_filtered=None)
    monkeypatch.setattr(serve, "filter_media_items", lambda items: items)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{SCHOLAR_ID}/news?limit=50")
    assert res.status_code == 200
    assert res.json["media"][0]["title"] == "raw"
    assert "filtered_at" not in res.json


def test_news_endpoint_warns_once_for_legacy_media(monkeypatch, tmp_path, caplog):
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    serve._legacy_news_filter_warned.clear()
    _write_scholar(tmp_path, media_filtered=None)
    monkeypatch.setattr(serve, "filter_media_items", lambda items: items)

    c = serve.app.test_client()
    caplog.set_level("WARNING", logger=serve.__name__)
    for _ in range(2):
        res = c.get(f"/scholar/{SCHOLAR_ID}/news?limit=50")
        assert res.status_code == 200

    warnings = [
        record for record in caplog.records if "JSON has no media_filtered list" in record.message
    ]
    assert len(warnings) == 1


def test_news_endpoint_skips_live_filter_for_empty_legacy_media(monkeypatch, tmp_path, caplog):
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    serve._legacy_news_filter_warned.clear()
    _write_scholar(tmp_path, media=[], media_filtered=None)

    def boom(*_a, **_k):
        raise RuntimeError("filter_media_items must not run when media is empty")

    monkeypatch.setattr(serve, "filter_media_items", boom)
    c = serve.app.test_client()
    caplog.set_level("WARNING", logger=serve.__name__)
    res = c.get(f"/scholar/{SCHOLAR_ID}/news?limit=50")

    assert res.status_code == 200
    assert res.json["media"] == []
    assert "JSON has no media_filtered list" not in caplog.text


def test_profile_parts_excludes_all_news_fields(monkeypatch, tmp_path):
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    _write_scholar(tmp_path)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{SCHOLAR_ID}?parts=profile")
    assert res.status_code == 200
    profile = res.json["profile"]
    assert "media" not in profile
    assert "media_filtered" not in profile
    assert "media_filtered_at" not in profile


def test_gscholar_excludes_prefiltered_news_fields_by_default(monkeypatch, tmp_path):
    from src import serve

    monkeypatch.setattr(serve, "SCHOLAR_DATA_DIR_ABS", str(tmp_path))
    _write_scholar(tmp_path)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{SCHOLAR_ID}/gscholar")
    assert res.status_code == 200
    assert "media" not in res.json
    assert "media_filtered" not in res.json
    assert "media_filtered_at" not in res.json
