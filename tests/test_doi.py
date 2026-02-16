"""Tests for DOI extraction and resolution."""

import pytest

from src.doi import (
    extract_doi_from_url,
    get_doi,
    get_doi_link,
    get_doi_short,
    get_doi_short_link,
)


@pytest.mark.integration
def test_get_doi_from_nature_url():
    """Extract DOI from Nature article URL."""
    publication_url = "https://www.nature.com/articles/nclimate2195"
    expected_doi = "10.1038/nclimate2195"
    assert get_doi(publication_url, "Rummer") == expected_doi


def test_extract_doi_from_url():
    """Extract DOI from URL patterns without network."""
    assert extract_doi_from_url("https://doi.org/10.1000/123") == "10.1000/123"
    assert extract_doi_from_url("https://example.com/doi/10.1000/456") == "10.1000/456"
    assert extract_doi_from_url("https://example.com/no-doi-here") is None


@pytest.mark.integration
def test_get_doi_link_and_short():
    """Resolve DOI link and short DOI (requires network)."""
    doi = "10.1038/nclimate2195"
    link = get_doi_link(doi)
    assert link is not None
    assert "doi.org" in link
    assert doi in link

    short_doi = get_doi_short(doi)
    if short_doi:
        short_link = get_doi_short_link(short_doi)
        assert short_link is not None
        assert "doi.org" in short_link
