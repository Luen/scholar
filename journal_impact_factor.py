from logger import print_error, print_warn, print_info
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Define the scope and authenticate
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("./google-credentials.json", scope)
client = gspread.authorize(creds)

# Open the Google Sheet by URL
sheet_url = "https://docs.google.com/spreadsheets/d/1lP75APkxXAgT8aobV4UjTR51BpX9Ee0wgYA7tTd-zrM/edit?gid=0"
sheet = client.open_by_url(sheet_url).sheet1

def load_impact_factor():
    """
    Load the impact factor data from the Google Sheet and return it as a dictionary with lowercase keys.
    """
    journal_names = sheet.col_values(1)  # Column A (Journal names)
    impact_factors = sheet.col_values(2)  # Column B (Impact factors)

    # Extend lists to match length
    max_length = max(len(journal_names), len(impact_factors))
    journal_names.extend([None] * (max_length - len(journal_names)))
    impact_factors.extend([None] * (max_length - len(impact_factors)))

    # Create a dictionary with lowercase journal names as keys
    impact_factor_data = {journal_name.lower(): impact_factor for journal_name, impact_factor in zip(journal_names, impact_factors) if journal_name}

    print_info(f"Loaded {len(impact_factor_data)} impact factors from Google Sheet.")
    return impact_factor_data

def add_impact_factor(journal_name, impact_factor):
    """
    Add a new journal name and impact factor to the Google Sheet.
    """
    sheet.append_row([journal_name, impact_factor])