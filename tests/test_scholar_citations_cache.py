import json
from datetime import datetime, timedelta

from src import scholar_citations as sc
from src.doi_utils import normalize_doi


def test_doi_metrics_cache_round_trips_special_character_doi(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    doi = "10.1002/(SICI)1099-0844:199912"

    cache_path = sc._doi_metrics_cache_file(doi, "scholar")
    assert cache_path is not None
    assert cache_path.parent == tmp_path.resolve()
    assert cache_path.name.startswith("scholar_10.1002_")
    assert "/" not in cache_path.name
    assert ":" not in cache_path.name
    assert "(" not in cache_path.name

    sc._write_cache(
        doi,
        "scholar",
        {"found": True, "citations": 7, "last_fetched_result": sc.FETCH_RESULT_SUCCESS},
    )

    cached, expired = sc._read_cache(doi, "scholar")
    assert expired is False
    assert cached is not None
    assert cached["doi"] == normalize_doi(doi)
    assert cached["citations"] == 7


def test_list_cached_dois_with_scholar_cache_prefers_json_doi(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    doi = "10.1234/has_under_score"
    cache_path = tmp_path / "scholar_10.1234_has_underscore.json"
    cache_path.write_text(json.dumps({"doi": doi}), encoding="utf-8")

    assert sc.list_cached_dois_with_scholar_cache() == {doi}


def test_list_cached_dois_with_scholar_cache_falls_back_to_encoded_filename(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    doi = "10.1002/(sici)1099-0844"
    safe = sc._normalize_doi_for_cache(doi)
    cache_path = tmp_path / f"scholar_{safe}.json"
    cache_path.write_text("{not json", encoding="utf-8")

    assert sc.list_cached_dois_with_scholar_cache() == {normalize_doi(doi)}


def test_list_cached_dois_with_scholar_cache_falls_back_for_non_object_json(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    cache_path = tmp_path / "scholar_10.1234_example.json"
    cache_path.write_text("[]", encoding="utf-8")

    assert sc.list_cached_dois_with_scholar_cache() == {"10.1234/example"}


def test_read_cache_treats_non_object_json_as_miss(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    cache_path = sc._doi_metrics_cache_file("10.1234/example", "scholar")
    assert cache_path is not None
    cache_path.write_text("[]", encoding="utf-8")

    cached, expired = sc._read_cache("10.1234/example", "scholar")
    assert cached is None
    assert expired is True


def test_list_cached_successful_dois_accepts_legacy_special_character_filename(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(sc, "CACHE_DIR", str(tmp_path))
    doi = "10.1002/(sici)1099-0844"
    legacy_safe = normalize_doi(doi).replace("/", "_").replace(":", "_")
    cache_path = tmp_path / f"scholar_{legacy_safe}.json"
    cache_path.write_text(
        json.dumps(
            {
                "doi": doi,
                "found": True,
                "expires_at": (datetime.now() + timedelta(days=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert sc.list_cached_successful_dois() == {normalize_doi(doi)}
