"""Unit tests for DOI resolver (with mocks)."""

from unittest.mock import patch

import pytest

from src.doi_resolver import resolve_doi_for_publication


@patch("src.doi_resolver.get_doi_resolved_link")
@patch("src.doi_resolver.get_doi")
@patch("src.doi_resolver.get_doi_link")
@patch("src.doi_resolver.get_doi_short")
@patch("src.doi_resolver.get_doi_short_link")
def test_resolve_uses_previous_data_when_provided(
    mock_short_link, mock_short, mock_link, mock_get_doi, mock_resolved
):
    """When previous DOI fields are provided, no network calls should be made."""
    result = resolve_doi_for_publication(
        "https://example.com/paper",
        "Test Paper",
        "Author",
        previous_doi="10.1000/123",
        previous_doi_link="https://doi.org/10.1000/123",
        previous_doi_short="10/abc",
        previous_doi_short_link="https://doi.org/10/abc",
        previous_doi_resolved_link="https://example.com/resolved",
    )
    mock_get_doi.assert_not_called()
    mock_link.assert_not_called()
    mock_short.assert_not_called()
    mock_short_link.assert_not_called()
    mock_resolved.assert_not_called()
    assert result["doi"] == "10.1000/123"
    assert result["doi_link"] == "https://doi.org/10.1000/123"
    assert result["doi_short"] == "10/abc"
    assert result["doi_short_link"] == "https://doi.org/10/abc"
    assert result["doi_resolved_link"] == "https://example.com/resolved"


def test_resolve_returns_empty_when_no_previous_and_mock_fails():
    """When no previous data and DOI lookup fails, returns empty strings."""
    with patch("src.doi_resolver.get_doi", return_value=None):
        with patch("src.doi_resolver.get_doi_from_title", return_value=None):
            result = resolve_doi_for_publication(
                "https://scholar.google.com/scholar?cluster=123",
                "Unknown Paper",
                "Author",
            )
    assert result["doi"] == ""
    assert result["doi_link"] == ""
    assert result["doi_short"] == ""
    assert result["doi_short_link"] == ""
