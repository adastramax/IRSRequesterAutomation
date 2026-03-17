"""Configuration shared by the QA implementation."""

from __future__ import annotations

import os
from pathlib import Path

QA_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = QA_DIR.parent
DATA_DIR = QA_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
DB_PATH = DATA_DIR / "qa_irs_pin.db"

EMAIL_DOMAIN = "ad-astrainc.com"
DEFAULT_NATIVE_LANGUAGE = None
DEFAULT_TIMEZONE = "b9efba83-5fb3-11ef-8538-0291956bad29"
DEFAULT_PRECALL_POLICY = int(os.getenv("QA_PRECALL_POLICY", "19"))
DEFAULT_SERVICE_TYPE = "SVC_COM"
SITE_MATCH_THRESHOLD = float(os.getenv("SITE_MATCH_THRESHOLD", "80"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("QA_REQUEST_TIMEOUT_SECONDS", "30"))

CONNECT_AUTH_BASE = os.getenv("QA_CONNECT_AUTH_BASE", "https://connectapiqas.ad-astrainc.com")
CONNECT_API_BASE = os.getenv("QA_CONNECT_API_BASE", "https://connectapiqas.ad-astrainc.com")
CONNECT_SEARCH_BASE = os.getenv("QA_CONNECT_SEARCH_BASE", CONNECT_API_BASE)
CONNECT_EMAIL = os.getenv("CONNECT_EMAIL", "almaskhan@ad-astrainc.com")
CONNECT_PASSWORD = os.getenv("CONNECT_PASSWORD", "Welcome123!")

PAYLOAD_DEFAULTS = {
    "address": "400 West Bay Street",
    "city": "Jacksonville",
    "state": "Florida",
    "postal_code": "32202",
    "latitude": 30.3269,
    "longitude": -81.6637,
    "country": "United States",
}

CUSTOMER_CREATE_OVERRIDES = {
    "markytech": {
        "default_native_language": "EN",
        "default_timezone": DEFAULT_TIMEZONE,
        "default_location": 13,
        "sub_customer_ids": [317],
        "opi_scheduled": True,
        "opi_ondemand": True,
        "password": "Welcome123!",
        "set_password": True,
        "precall_policy": 19,
        "service_type": "SVC_COM",
        "service_types": [DEFAULT_SERVICE_TYPE],
    },
    "esided": {
        "default_native_language": "urd",
        "default_timezone": "b9efc227-5fb3-11ef-8538-0291956bad29",
        "default_location": 5,
        "sub_customer_ids": [270],
        "opi_scheduled": True,
        "opi_ondemand": True,
        "password": "Welcome123!",
        "set_password": True,
        "precall_policy": 9,
        "service_type": "BU",
        "service_types": ["BU"],
    }
}

SITE_PROFILE_OVERRIDES = {
    ("markytech", "jacksonville, fl, usa"): {
        "address": "Jacksonville, FL, USA",
        "city": "Jacksonville",
        "state": "Florida",
        "postal_code": "32202",
        "latitude": 30.3297566,
        "longitude": -81.6591529,
        "country": "United States",
    },
    ("markytech", "florida city, fl, usa"): {
        "address": "Jacksonville, FL, USA",
        "city": "Jacksonville",
        "state": "Florida",
        "postal_code": "32202",
        "latitude": 30.3297566,
        "longitude": -81.6591529,
        "country": "United States",
    },
    ("markytech", "miami, fl, usa"): {
        "address": "Miami, FL, USA",
        "city": "Miami",
        "state": "Florida",
        "postal_code": "331010",
        "latitude": 25.7617,
        "longitude": -80.1918,
        "country": "United States",
    },
    ("esided", "islamabad, pakistan"): {
        "address": "Islamabad, Pakistan",
        "city": "Islamabad",
        "state": "ICT",
        "postal_code": "46000",
        "latitude": 33.6844,
        "longitude": 73.0479,
        "country": "Pakistan",
    },
}

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
    "MARKYTECH": {"bod_code": "MARKYTECH", "customer_name": "Markytech", "fk_customer": 277},
    "MT": {"bod_code": "MT", "customer_name": "Markytech", "fk_customer": 277},
    "MZ": {"bod_code": "MZ", "customer_name": "Markytech", "fk_customer": 277},
    "ESIDED": {"bod_code": "ESIDED", "customer_name": "Esided", "fk_customer": 270},
    "ES": {"bod_code": "ES", "customer_name": "Esided", "fk_customer": 270},
    "QA": {"bod_code": "QA", "customer_name": "Markytech", "fk_customer": 277},
}

CUSTOMER_LOOKUP = {
    payload["customer_name"].lower(): payload
    for payload in BOD_LOOKUP.values()
}
