"""Configuration shared by the live implementation."""

from __future__ import annotations

import os
from pathlib import Path

QA_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = QA_DIR.parent
DATA_DIR = QA_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "qa_irs_pin.db"
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "7"))

EMAIL_DOMAIN = "ad-astrainc.com"
DEFAULT_NATIVE_LANGUAGE = None
DEFAULT_TIMEZONE = "b9efba83-5fb3-11ef-8538-0291956bad29"
_default_precall_policy = os.getenv("DEFAULT_PRECALL_POLICY", "").strip()
DEFAULT_PRECALL_POLICY = int(_default_precall_policy) if _default_precall_policy else None
DEFAULT_SERVICE_TYPE = "SVC_COM"
DEFAULT_NEW_SITE_PIN_SUFFIX = 5
DEFAULT_NEW_SITE_PIN_TOTAL_LENGTH = 9
SITE_MATCH_THRESHOLD = float(os.getenv("SITE_MATCH_THRESHOLD", "80"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

DEFAULT_CONNECT_BASE = "https://appbe.ad-astrainc.com"
DEFAULT_CONNECT_EMAIL = "aiagentdjango@adastra-inc.com"
DEFAULT_CONNECT_PASSWORD = "Aiagent123@"
CONNECT_AUTH_BASE = os.getenv("CONNECT_AUTH_BASE", DEFAULT_CONNECT_BASE).rstrip("/")
CONNECT_API_BASE = os.getenv("CONNECT_API_BASE", CONNECT_AUTH_BASE or DEFAULT_CONNECT_BASE).rstrip("/")
CONNECT_SEARCH_BASE = os.getenv("CONNECT_SEARCH_BASE", CONNECT_API_BASE or DEFAULT_CONNECT_BASE).rstrip("/")
CONNECT_EMAIL = os.getenv("CONNECT_EMAIL", DEFAULT_CONNECT_EMAIL)
CONNECT_PASSWORD = os.getenv("CONNECT_PASSWORD", DEFAULT_CONNECT_PASSWORD)
DEV_USE_USERNAME = os.getenv("DEV_USE_USERNAME", "")
DEV_USE_PASSWORD = os.getenv("DEV_USE_PASSWORD", "")

GRAPH_TENANT = os.getenv("GRAPH_TENANT", "adastrainccom.onmicrosoft.com")
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "d3590ed6-52b3-4102-aeff-aad2292ab01c")
GRAPH_USERNAME = os.getenv("GRAPH_USERNAME", "")
GRAPH_PASSWORD = os.getenv("GRAPH_PASSWORD", "")

PAYLOAD_DEFAULTS = {
    "address": "400 West Bay Street",
    "city": "Jacksonville",
    "state": "Florida",
    "postal_code": "32202",
    "latitude": 30.3269,
    "longitude": -81.6637,
    "country": "United States",
}

IRS_CREATE_OVERRIDE = {
    "default_native_language": "EN",
    "password": "Welcome123!",
    "set_password": True,
    "service_type": "IRSOPI",
    "service_types": ["IRSOPI"],
}

CUSTOMER_CREATE_OVERRIDES = {
    "z- ad astra demo account": {
        "password": "Welcome123!",
        "set_password": True,
        "service_type": "CS",
        "service_types": ["CS"],
    },
}

SITE_PROFILE_OVERRIDES = {}

BOD_LOOKUP = {
    "TAS": {"bod_code": "TAS", "customer_name": "US GSA IRS Taxpayer Advocate Service (TAS)", "fk_customer": 1219},
    "FA": {"bod_code": "FA", "customer_name": "US GSA IRS TS Field Assistance (FA)", "fk_customer": 1222},
    "SBSE": {"bod_code": "SBSE", "customer_name": "US GSA IRS Small Business Self-Employed (SBSE)", "fk_customer": 1218},
    "AM": {"bod_code": "AM", "customer_name": "US GSA IRS TS Account Management (AM)", "fk_customer": 1220},
    "CC": {"bod_code": "CC", "customer_name": "US GSA IRS Chief Counsel (CC)", "fk_customer": 1213},
    "CI": {"bod_code": "CI", "customer_name": "US GSA IRS Criminal Investigation (CI)", "fk_customer": 1214},
    "TEGE": {"bod_code": "TEGE", "customer_name": "US GSA IRS Exempt Organizations & Government (TEGE)", "fk_customer": 1215},
    "LB&I": {"bod_code": "LB&I", "customer_name": "US GSA IRS Large Business & International (LB&I)", "fk_customer": 1217},
    "EPSS": {"bod_code": "EPSS", "customer_name": "US GSA IRS TS Electronic Products & Services Support (EPSS)", "fk_customer": 1221},
    "RICS": {"bod_code": "RICS", "customer_name": "US GSA IRS TS Return Integrity & Compliance Services (RICS)", "fk_customer": 1223},
    "SPEC": {"bod_code": "SPEC", "customer_name": "US GSA IRS TS Stakeholder Partnerships, Education & Communication (SPEC)", "fk_customer": 1224},
    "FMSS": {"bod_code": "FMSS", "customer_name": "US GSA IRS Facilities Management & Security Services (FMSS)", "fk_customer": 1216},
    "APPEALS": {"bod_code": "APPEALS", "customer_name": "US GSA IRS Independent Office of Appeals", "fk_customer": 1225},
    "MEDIA": {"bod_code": "MEDIA", "customer_name": "US GSA IRS TS Media & Publications - Distribution", "fk_customer": 1226},
    "Z-DEMO": {"bod_code": "Z-DEMO", "customer_name": "z- Ad Astra Demo Account", "fk_customer": 271},
    "Z-ORIENTATION": {"bod_code": "Z-ORIENTATION", "customer_name": "Z- Ad Astra Orientation Inc.", "fk_customer": 269},
}

CUSTOMER_LOOKUP = {
    payload["customer_name"].lower(): payload
    for payload in BOD_LOOKUP.values()
}

for payload in BOD_LOOKUP.values():
    CUSTOMER_CREATE_OVERRIDES[payload["customer_name"].lower()] = dict(IRS_CREATE_OVERRIDE)
