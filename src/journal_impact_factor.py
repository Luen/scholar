import logging
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from .logger import print_error

logger = logging.getLogger(__name__)

_SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1lP75APkxXAgT8aobV4UjTR51BpX9Ee0wgYA7tTd-zrM/edit?gid=0"
)

# ``None`` = not yet tried; ``False`` = unavailable (missing creds or error); else worksheet.
_worksheet: object | None = None


def _get_worksheet():
    """Return the first worksheet, or ``None`` if credentials/sheet are unavailable."""
    global _worksheet
    if _worksheet is False:
        return None
    if _worksheet is not None:
        return _worksheet

    cred_path = "./google-credentials.json"
    if not os.path.exists(cred_path):
        print_error("google-credentials.json file not found")
        _worksheet = False
        return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, _SCOPE)
        client = gspread.authorize(creds)
        _worksheet = client.open_by_url(_SHEET_URL).sheet1
    except Exception as e:
        logger.warning("Journal impact factor sheet unavailable: %s", e)
        _worksheet = False
        return None

    return _worksheet


def load_impact_factor():
    """
    Load the impact factor data from the Google Sheet and return it as a dictionary with lowercase keys.
    """
    sheet = _get_worksheet()
    if sheet is None:
        return {}

    journal_names = sheet.col_values(1)[1:]  # Column A (Journal names), excluding the header
    impact_factors = sheet.col_values(2)[1:]  # Column B (Impact factors), excluding the header

    # Extend lists to match length
    max_length = max(len(journal_names), len(impact_factors))
    journal_names.extend([None] * (max_length - len(journal_names)))
    impact_factors.extend([None] * (max_length - len(impact_factors)))

    # Create a dictionary with lowercase journal names as keys
    impact_factor_data = {
        journal_name.lower(): impact_factor
        for journal_name, impact_factor in zip(journal_names, impact_factors)
        if journal_name
    }

    return impact_factor_data


def add_impact_factor(journal_name, impact_factor):
    """
    Add a new journal name and impact factor to the Google Sheet.
    """
    sheet = _get_worksheet()
    if sheet is None:
        return
    sheet.append_row([journal_name, impact_factor])
