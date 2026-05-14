"""Tests for journal impact factor loading."""

from pathlib import Path

import pytest

from src import journal_impact_factor


class FakeWorksheet:
    """Minimal worksheet fake for impact-factor unit tests."""

    def __init__(self, columns=None):
        self.columns = columns or {}
        self.appended_rows = []

    def col_values(self, col):
        return list(self.columns.get(col, []))

    def append_row(self, values):
        self.appended_rows.append(values)


@pytest.fixture(autouse=True)
def reset_worksheet_cache(monkeypatch):
    """Keep the module-level worksheet cache isolated between tests."""
    monkeypatch.setattr(journal_impact_factor, "_worksheet", None)
    yield
    monkeypatch.setattr(journal_impact_factor, "_worksheet", None)


def test_load_impact_factor_without_credentials_returns_empty(monkeypatch, tmp_path):
    """Missing credentials should disable sheet access without raising."""
    messages = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(journal_impact_factor, "print_error", messages.append)

    assert journal_impact_factor.load_impact_factor() == {}
    assert messages == ["google-credentials.json file not found"]


def test_add_impact_factor_without_credentials_noops(monkeypatch, tmp_path):
    """Appending should no-op when the sheet is unavailable."""
    messages = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(journal_impact_factor, "print_error", messages.append)

    journal_impact_factor.add_impact_factor("nature", "")
    journal_impact_factor.add_impact_factor("science", "")

    assert messages == ["google-credentials.json file not found"]


def test_load_impact_factor_normalises_sheet_values(monkeypatch):
    """Sheet rows should become lowercase string values and skip blank journals."""
    worksheet = FakeWorksheet(
        {
            1: ["Journal", " Nature ", "", "Science", None],
            2: ["Impact factor", 64.8, "ignored", None, "ignored"],
        }
    )
    monkeypatch.setattr(journal_impact_factor, "_worksheet", worksheet)

    assert journal_impact_factor.load_impact_factor() == {
        "nature": "64.8",
        "science": "",
    }


def test_add_impact_factor_appends_to_available_sheet(monkeypatch):
    """Known-available worksheets should receive new impact-factor rows."""
    worksheet = FakeWorksheet()
    monkeypatch.setattr(journal_impact_factor, "_worksheet", worksheet)

    journal_impact_factor.add_impact_factor("nature", "64.8")

    assert worksheet.appended_rows == [["nature", "64.8"]]


@pytest.mark.integration
@pytest.mark.credentials
@pytest.mark.skipif(
    not Path("google-credentials.json").exists(),
    reason="google-credentials.json not found (required for Google Sheets API)",
)
def test_load_impact_factor_from_google_sheet():
    """Load impact factor data from Google Sheet and verify structure."""
    data = journal_impact_factor.load_impact_factor()
    assert isinstance(data, dict)
    assert "nature" in data
    # Nature impact factor changes annually; assert it's a non-empty string
    assert isinstance(data["nature"], str)
    assert len(data["nature"]) > 0
