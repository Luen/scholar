"""Unit tests for output module."""

import os
import tempfile
from datetime import datetime, timedelta

from src.output import (
    SCHEMA_VERSION,
    get_last_successful_indices,
    is_fresh,
    load_author,
    save_author,
    set_last_successful_index,
)


def test_load_author_missing_file():
    assert load_author("/nonexistent/path.json") is None


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "author.json")
        author = {"name": "Test Author", "publications": []}
        save_author(author, path)
        loaded = load_author(path)
        assert loaded is not None
        assert loaded["name"] == "Test Author"
        assert loaded["schema_version"] == SCHEMA_VERSION
        assert "last_fetched" in loaded


def test_is_fresh_none():
    assert is_fresh(None, 3600) is False


def test_is_fresh_empty():
    assert is_fresh("", 3600) is False


def test_is_fresh_recent():
    now = datetime.now().isoformat()
    assert is_fresh(now, 3600) is True


def test_is_fresh_old():
    old = (datetime.now() - timedelta(days=8)).isoformat()
    assert is_fresh(old, 7 * 24 * 3600) is False


def test_get_last_successful_indices_default():
    data = {}
    indices = get_last_successful_indices(data)
    assert indices["coauthor"] == -1
    assert indices["publication"] == -1


def test_set_and_get_last_successful_index():
    author = {}
    set_last_successful_index(author, "coauthor", 5)
    set_last_successful_index(author, "publication", 10)
    assert author["_last_successful_coauthor_index"] == 5
    assert author["_last_successful_publication_index"] == 10
    indices = get_last_successful_indices(author)
    assert indices["coauthor"] == 5
    assert indices["publication"] == 10
