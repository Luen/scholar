"""Tests for Crossref API client."""

import pytest

from src.crossref import CrossrefResponse, fetch_crossref_details, search_doi_by_title


def test_search_doi_by_title_empty_title():
    """Empty title returns None without network."""
    assert search_doi_by_title("", "Rummer") is None
    assert search_doi_by_title("   ", "Rummer") is None


@pytest.mark.integration
def test_search_doi_by_title_returns_doi():
    """Crossref title search finds DOI for known paper."""
    doi = search_doi_by_title(
        "A framework for understanding climate change impacts on coral reef", "Rummer"
    )
    assert doi is not None
    assert doi.startswith("10.")
    assert "/" in doi


@pytest.mark.integration
def test_fetch_crossref_details_returns_result():
    """Fetch Crossref details for a known DOI."""
    doi = "10.1038/nclimate2195"
    result = fetch_crossref_details(doi)
    assert result is not None
    assert isinstance(result, CrossrefResponse)
    assert result.title is not None
    assert result.journal is not None or result.authors
    assert result.year is not None


@pytest.mark.integration
def test_fetch_crossref_details_invalid_doi():
    """Invalid or non-existent DOI returns None."""
    result = fetch_crossref_details("10.9999/nonexistent-doi-xyz")
    assert result is None
