"""Unit tests for standardise module."""

import pytest

from src.standardise import initialize, standardise_authors, levenshtein


def test_initialize_empty():
    assert initialize("") == ""
    assert initialize(None) == ""


def test_initialize_single_name():
    assert initialize("Smith") == "Smith, "


def test_initialize_two_names():
    assert initialize("John Smith") == "Smith, J."


def test_initialize_three_names():
    assert initialize("John Paul Smith") == "Smith, J. P."


def test_standardise_authors_empty():
    assert standardise_authors(None) == ""


def test_standardise_authors_single():
    assert standardise_authors("John Smith") == "Smith, J."


def test_standardise_authors_multiple():
    result = standardise_authors("John Smith and Jane Doe")
    assert "Smith, J." in result
    assert "Doe, J." in result
    assert ", " in result


def test_levenshtein_identical():
    assert levenshtein("test", "test") == 0


def test_levenshtein_one_edit():
    assert levenshtein("test", "tost") == 1
