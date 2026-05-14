"""Tests for news thumbnail download and JSON enrichment."""

from urllib.parse import urlparse

from src import news_thumbnails as nt


def test_max_image_bytes_invalid_env_uses_default(monkeypatch):
    monkeypatch.setenv("NEWS_THUMB_MAX_BYTES", "not-a-number")
    assert nt._max_image_bytes() == 2_500_000


def test_thumbnail_image_public_url_with_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.rummerlab.com")
    u = nt.thumbnail_image_public_url("ynWS968AAAAJ", "abc.jpg")
    assert u == "https://api.rummerlab.com/scholar/ynWS968AAAAJ/news/thumbnail/abc.jpg"


def test_thumbnail_image_public_url_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.rummerlab.com/")
    u = nt.thumbnail_image_public_url("ynWS968AAAAJ", "a.webp")
    assert u == "https://api.rummerlab.com/scholar/ynWS968AAAAJ/news/thumbnail/a.webp"


def test_enrich_normalizes_managed_thumbnail_to_configured_base(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.com")
    sid = "ynWS968AAAAJ"
    h = "a" * 64
    old = f"http://localhost:8000/scholar/{sid}/news/thumbnail/{h}.jpg"
    items = [{"url": "", "title": "x", "image": {"url": old}}]
    assert nt.enrich_filtered_media_thumbnails(sid, items) == 1
    assert (
        items[0]["image"]["url"] == f"https://api.example.com/scholar/{sid}/news/thumbnail/{h}.jpg"
    )


def test_enrich_normalizes_managed_thumbnail_to_root_relative(monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLIC_API_BASE_URL", raising=False)
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    sid = "ynWS968AAAAJ"
    h = "b" * 64
    old = f"https://wrong.host/scholar/{sid}/news/thumbnail/{h}.webp"
    items = [{"url": "", "title": "x", "image": {"url": old}}]
    assert nt.enrich_filtered_media_thumbnails(sid, items) == 1
    assert items[0]["image"]["url"] == f"/scholar/{sid}/news/thumbnail/{h}.webp"


def test_sniff_image_format():
    assert nt.sniff_image_format(b"\xff\xd8\xff" + b"\x00" * 20) == ("jpg", "image/jpeg")
    assert nt.sniff_image_format(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) == ("png", "image/png")
    assert nt.sniff_image_format(b"GIF89a" + b"\x00" * 20) == ("gif", "image/gif")
    assert nt.sniff_image_format(b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 20) == (
        "webp",
        "image/webp",
    )
    assert nt.sniff_image_format(b"not an image") is None


def test_ensure_thumbnail_skips_when_image_present(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    item = {
        "url": "https://example.com/p",
        "image": {"url": "https://cdn.example/i.jpg"},
    }
    assert nt.ensure_thumbnail_for_item("ynWS968AAAAJ", item) == (False, False)


def test_ensure_thumbnail_reuses_existing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    sid = "ynWS968AAAAJ"
    page = "https://example.com/article"
    digest = nt.url_hash(page)
    tdir = tmp_path / "news_thumbnails" / sid
    tdir.mkdir(parents=True)
    name = f"{digest}.png"
    (tdir / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

    item = {"url": page, "title": "Hello <b>World</b>"}
    assert nt.ensure_thumbnail_for_item(sid, item) == (True, False)
    assert item["image"]["url"] == f"/scholar/{sid}/news/thumbnail/{name}"
    assert item["image"]["alt"] == "Hello World"


def test_ensure_thumbnail_downloads_and_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_THUMB_FETCH_DELAY_SECONDS", "0")
    sid = "ynWS968AAAAJ"
    page = "https://example.com/story"
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200

    monkeypatch.setattr(
        nt,
        "_fetch_html_page",
        lambda url: (
            '<meta property="og:image" content="https://cdn.example/x.jpg">'
            if url == page
            else None
        ),
    )
    monkeypatch.setattr(
        nt,
        "_download_image_bytes",
        lambda url, timeout_s=25: jpeg if "cdn.example" in url else None,
    )

    item = {"url": page, "title": "T"}
    assert nt.ensure_thumbnail_for_item(sid, item) == (True, True)
    digest = nt.url_hash(page)
    written = tmp_path / "news_thumbnails" / sid / f"{digest}.jpg"
    assert written.is_file()
    assert written.read_bytes() == jpeg
    assert f"/scholar/{sid}/news/thumbnail/{digest}.jpg" in item["image"]["url"]


def test_news_thumbnail_route_serves_file(tmp_path):
    from src import serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    sid = "ynWS968AAAAJ"
    digest = nt.url_hash("https://rummerlab.org/x")
    name = f"{digest}.jpg"
    tdir = tmp_path / "news_thumbnails" / sid
    tdir.mkdir(parents=True)
    (tdir / name).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

    c = serve.app.test_client()
    res = c.get(f"/scholar/{sid}/news/thumbnail/{name}")
    assert res.status_code == 200
    assert res.mimetype == "image/jpeg"


def test_news_thumbnail_route_rejects_bad_filename(tmp_path):
    from src import serve

    serve.SCHOLAR_DATA_DIR_ABS = str(tmp_path)
    c = serve.app.test_client()
    res = c.get("/scholar/ynWS968AAAAJ/news/thumbnail/not-a-valid-name.jpg")
    assert res.status_code == 400


def test_mirror_remote_downloads_and_rewrites_url(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    sid = "ynWS968AAAAJ"
    img_url = "https://i.ytimg.com/vi/foo/hq720.jpg"
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    monkeypatch.setattr(
        nt,
        "_download_image_bytes",
        lambda u, timeout_s=25: (
            jpeg if (urlparse(u).hostname or "").endswith("ytimg.com") else None
        ),
    )
    item = {"url": "https://youtube.com/x", "image": {"url": img_url, "alt": "Keep"}}
    assert nt.mirror_remote_item_image(sid, item) == (True, True)
    assert "/scholar/ynWS968AAAAJ/news/thumbnail/" in item["image"]["url"]
    assert item["image"]["alt"] == "Keep"
    digest = nt.url_hash(img_url)
    assert (tmp_path / "news_thumbnails" / sid / f"{digest}.jpg").is_file()


def test_mirror_remote_reuses_file_without_network(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    sid = "ynWS968AAAAJ"
    img_url = "https://cdn.example/p.jpg"
    digest = nt.url_hash(img_url)
    tdir = tmp_path / "news_thumbnails" / sid
    tdir.mkdir(parents=True)
    (tdir / f"{digest}.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 80)

    def boom(*_a, **_k):
        raise AssertionError("_download_image_bytes should not run when file exists")

    monkeypatch.setattr(nt, "_download_image_bytes", boom)
    item = {"image": {"url": img_url}}
    assert nt.mirror_remote_item_image(sid, item) == (True, False)
    assert digest in item["image"]["url"]


def test_mirror_skips_already_proxied_url(tmp_path):
    sid = "ynWS968AAAAJ"
    u = f"/scholar/{sid}/news/thumbnail/{'b' * 64}.webp"
    item = {"image": {"url": u}}
    assert nt.mirror_remote_item_image(sid, item) == (False, False)
    assert item["image"]["url"] == u


def test_enrich_no_sleep_when_no_remote_io(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_THUMB_FETCH_DELAY_SECONDS", "0.5")
    sleeps: list[float] = []
    monkeypatch.setattr(nt.time, "sleep", lambda s: sleeps.append(s))
    items = [
        {"url": "", "title": "a"},
        {
            "url": "https://x.test/a",
            "image": {
                "url": f"/scholar/ynWS968AAAAJ/news/thumbnail/{'a' * 64}.jpg",
            },
            "title": "b",
        },
    ]
    assert nt.enrich_filtered_media_thumbnails("ynWS968AAAAJ", items) == 0
    assert sleeps == []


def test_enrich_sleeps_after_html_fetch_attempt(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEWS_THUMB_FETCH_DELAY_SECONDS", "0.01")
    sleeps: list[float] = []
    monkeypatch.setattr(nt.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(nt, "_fetch_html_page", lambda url: None)
    items = [{"url": "https://example.com/one", "title": "t"}]
    assert nt.enrich_filtered_media_thumbnails("ynWS968AAAAJ", items) == 0
    assert len(sleeps) == 1
