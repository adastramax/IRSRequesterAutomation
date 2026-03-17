"""Configuration for the v7-aligned mock IRS PIN project."""

from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = MOCK_DIR.parent
DATA_DIR = MOCK_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "mock_irs_pin.db"

REFERENCE_DIR = PROJECT_ROOT / "Imp Data Regarding Customers and Requesters"
SITES_REFERENCE_PATH = REFERENCE_DIR / "IRS_All_Sites_Reference.xlsx"
REQUESTERS_TEID_PATH = REFERENCE_DIR / "requesters_with_company_details_TEID.xlsx"
ALL_IRS_USERS_PATH = REFERENCE_DIR / "Requesters_List_all_IRS_Users_pins.csv"
MONTHLY_REPORT_PATH = REFERENCE_DIR / "IRS_report_monthly_2026-03-01.xlsx"
QA_REQUESTERS_PATH = REFERENCE_DIR / "QA_Requesters_List.csv"
CUSTOMERS_LIST_PATH = REFERENCE_DIR / "Customers_List.csv"
REQUESTERS_LIST_PATH = REFERENCE_DIR / "Requesters_List.csv"

EMAIL_DOMAIN = "ad-astrainc.com"
DEFAULT_NATIVE_LANGUAGE = None
DEFAULT_TIMEZONE = "b9efba83-5fb3-11ef-8538-0291956bad29"
DEFAULT_PRECALL_POLICY = 19
DEFAULT_SERVICE_TYPE = "SVC_COM"
SITE_MATCH_THRESHOLD = 80.0

PAYLOAD_DEFAULTS = {
    "address": "400 West Bay Street",
    "city": "Jacksonville",
    "state": "Florida",
    "postal_code": "32202",
    "latitude": 30.3269,
    "longitude": -81.6637,
    "country": "United States",
}

KNOWN_LOCATION_OVERRIDES = {
    ("US GSA IRS Taxpayer Advocate Service (TAS)", "5485"): 3176,
}
