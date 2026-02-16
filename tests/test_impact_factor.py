"""Tests for journal impact factor loading."""

import os

import pytest

# Skip entire module if credentials missing (avoids import which would exit)
pytestmark = pytest.mark.skipif(
    not os.path.exists("google-credentials.json"),
    reason="google-credentials.json not found (required for Google Sheets API)",
)


@pytest.mark.credentials
def test_load_impact_factor():
    """Load impact factor data from Google Sheet and verify structure."""
    from src.journal_impact_factor import load_impact_factor

    data = load_impact_factor()
    assert isinstance(data, dict)
    assert "nature" in data
    # Nature impact factor changes annually; assert it's a non-empty string
    assert isinstance(data["nature"], str)
    assert len(data["nature"]) > 0
