import pytest
from journal_impact_factor import get_impact_factor

def test_get_impact_factor():
    journal_name = "Nature"
    expected_impact_factor = "64.8"
    assert get_impact_factor(journal_name) == expected_impact_factor
