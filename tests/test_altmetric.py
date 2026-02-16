"""Tests for Altmetric fetcher."""

import pytest

from src.altmetric import ScrapedAltmetricDetails, fetch_altmetric_details


@pytest.mark.integration
def test_fetch_altmetric_details_returns_result():
    """Fetch Altmetric details for a known DOI."""
    doi = "10.1038/nclimate2195"
    result = fetch_altmetric_details(doi)
    assert result is not None
    assert isinstance(result, ScrapedAltmetricDetails)
    assert result.doi == doi
    assert result.title or result.journal or result.authors or result.year


@pytest.mark.integration
def test_fetch_altmetric_details_invalid_doi():
    """Invalid or non-existent DOI returns None."""
    result = fetch_altmetric_details("10.9999/nonexistent-doi-xyz")
    assert result is None
