"""SQLite-backed mock data layer seeded from the real IRS reference files."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pandas as pd

from .config import (
    ALL_IRS_USERS_PATH,
    CUSTOMERS_LIST_PATH,
    DB_PATH,
    KNOWN_LOCATION_OVERRIDES,
    MONTHLY_REPORT_PATH,
    QA_REQUESTERS_PATH,
    REQUESTERS_LIST_PATH,
    REQUESTERS_TEID_PATH,
    SITES_REFERENCE_PATH,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bod_lookup (
    bod_code TEXT PRIMARY KEY,
    fk_customer INTEGER NOT NULL,
    customer_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS site_catalog (
    customer_name TEXT NOT NULL,
    bod_code TEXT NOT NULL,
    site_name TEXT NOT NULL,
    has_teid INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_name, site_name)
);

CREATE TABLE IF NOT EXISTS site_reference (
    customer_name TEXT NOT NULL,
    bod_code TEXT NOT NULL,
    teid TEXT NOT NULL,
    site_name TEXT,
    state TEXT,
    max_pin TEXT,
    next_pin TEXT,
    fk_customer INTEGER NOT NULL,
    fk_location INTEGER NOT NULL,
    PRIMARY KEY (customer_name, teid)
);

CREATE TABLE IF NOT EXISTS requestor_reference (
    requester_id TEXT PRIMARY KEY,
    seid TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    account_id TEXT,
    office_location TEXT,
    pin_code TEXT,
    teid TEXT,
    site_name TEXT,
    customer_name TEXT,
    bod_code TEXT,
    connect_guid TEXT NOT NULL,
    account_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS raw_customers_list (
    account_id TEXT,
    account_name TEXT,
    type TEXT,
    registered_date TEXT,
    parent_account_id TEXT,
    address TEXT,
    country TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    email TEXT,
    service_type TEXT,
    unique_identifier TEXT,
    ivr_number TEXT,
    status TEXT,
    total_users TEXT,
    total_child_accounts TEXT
);

CREATE TABLE IF NOT EXISTS raw_requesters_all_irs (
    requester_id TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone_number TEXT,
    address TEXT,
    country TEXT,
    city TEXT,
    state TEXT,
    zipcode TEXT,
    account_id TEXT,
    account_name TEXT,
    office_location TEXT,
    default_service_type_opi TEXT,
    other_service_types TEXT,
    pre_call_policy TEXT,
    ivr_pin TEXT,
    role TEXT,
    status TEXT,
    joined_date TEXT,
    last_assignment TEXT,
    last_login TEXT,
    scheduled_telephonic TEXT,
    ondemand_telephonic TEXT,
    ondemand_video_interpreting TEXT,
    scheduled_video_interpreting TEXT,
    onsite_consecutive TEXT,
    onsite_simultaneous TEXT,
    third_party_platform TEXT
);

CREATE TABLE IF NOT EXISTS raw_requesters_list (
    requester_id TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone_number TEXT,
    address TEXT,
    country TEXT,
    city TEXT,
    state TEXT,
    zipcode TEXT,
    account_id TEXT,
    account_name TEXT,
    office_location TEXT,
    default_service_type_opi TEXT,
    other_service_types TEXT,
    pre_call_policy TEXT,
    ivr_pin TEXT,
    role TEXT,
    status TEXT,
    joined_date TEXT,
    last_assignment TEXT,
    last_login TEXT,
    scheduled_telephonic TEXT,
    ondemand_telephonic TEXT,
    ondemand_video_interpreting TEXT,
    scheduled_video_interpreting TEXT,
    onsite_consecutive TEXT,
    onsite_simultaneous TEXT,
    third_party_platform TEXT
);

CREATE TABLE IF NOT EXISTS raw_qa_requesters (
    requester_id TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone_number TEXT,
    address TEXT,
    country TEXT,
    city TEXT,
    state TEXT,
    zipcode TEXT,
    account_id TEXT,
    account_name TEXT,
    office_location TEXT,
    default_service_type_opi TEXT,
    other_service_types TEXT,
    pre_call_policy TEXT,
    ivr_pin TEXT,
    role TEXT,
    status TEXT,
    joined_date TEXT,
    last_assignment TEXT,
    last_login TEXT,
    scheduled_telephonic TEXT,
    ondemand_telephonic TEXT,
    ondemand_video_interpreting TEXT,
    scheduled_video_interpreting TEXT,
    onsite_consecutive TEXT,
    onsite_simultaneous TEXT,
    third_party_platform TEXT
);

CREATE TABLE IF NOT EXISTS raw_requesters_teid (
    pin_code TEXT,
    teid TEXT,
    source_id TEXT,
    site_name TEXT,
    state TEXT,
    user_email TEXT,
    seid TEXT,
    first_name TEXT,
    last_name TEXT,
    customer_email TEXT,
    customer_unique_identifier TEXT,
    customer_name TEXT
);

CREATE TABLE IF NOT EXISTS stg_irs_pin_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seid TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    bod TEXT,
    site_id TEXT,
    site_name TEXT,
    pin_9digit TEXT,
    connect_guid TEXT,
    status TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_dt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_dt TEXT
);

CREATE TABLE IF NOT EXISTS stg_irs_teid_registry (
    teid TEXT PRIMARY KEY,
    site_name TEXT,
    site_address TEXT,
    fk_customer INTEGER,
    fk_location INTEGER,
    created_dt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def normalize_teid(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    digits = "".join(character for character in text if character.isdigit())
    return digits.zfill(4) if digits else ""


def normalize_pin(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    digits = "".join(character for character in text if character.isdigit())
    return digits


def extract_bod_code(label: object) -> str:
    text = normalize_text(label)
    if "(" in text and ")" in text:
        return text.rsplit("(", 1)[-1].replace(")", "").strip()
    upper = text.upper()
    if "APPEALS" in upper:
        return "APPEALS"
    if "MEDIA" in upper:
        return "MEDIA"
    return ""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with get_connection(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        bod_lookup = load_bod_lookup()
        seed_bod_lookup(connection, bod_lookup)
        seed_raw_customers_list(connection)
        seed_raw_requesters_export(
            connection,
            csv_path=REQUESTERS_LIST_PATH,
            table_name="raw_requesters_list",
        )
        seed_raw_requesters_export(
            connection,
            csv_path=QA_REQUESTERS_PATH,
            table_name="raw_qa_requesters",
        )
        site_reference = load_site_reference(bod_lookup)
        seed_site_reference(connection, site_reference)
        seed_site_catalog(connection, site_reference, bod_lookup)
        seed_requestor_reference(connection, site_reference, bod_lookup)
        sync_teid_registry(connection)
        connection.commit()

    return db_path


def load_bod_lookup() -> pd.DataFrame:
    mapping = pd.read_excel(SITES_REFERENCE_PATH, sheet_name="BOD MAPPING", dtype=str).fillna("")
    mapping = mapping.rename(
        columns={
            "BOD_Code": "bod_code",
            "fK_Customer": "fk_customer",
            "Full_Account_Name": "customer_name",
        }
    )
    mapping["bod_code"] = mapping["bod_code"].map(normalize_text)
    mapping["customer_name"] = mapping["customer_name"].map(normalize_text)
    mapping["fk_customer"] = mapping["fk_customer"].map(lambda value: int(normalize_pin(value)))
    return mapping[["bod_code", "fk_customer", "customer_name"]].drop_duplicates()


def seed_raw_customers_list(connection: sqlite3.Connection) -> None:
    customers = pd.read_csv(CUSTOMERS_LIST_PATH, dtype=str).fillna("")
    customers = customers.rename(
        columns={
            "Account Id": "account_id",
            "Account Name": "account_name",
            "Type": "type",
            "Registered Date": "registered_date",
            "Parent Account ID": "parent_account_id",
            "Address": "address",
            "Country": "country",
            "City": "city",
            "State": "state",
            "Postal Code": "postal_code",
            "Email": "email",
            "Service Type": "service_type",
            "Unique Identifier": "unique_identifier",
            "IVR Number": "ivr_number",
            "Status": "status",
            "Total users": "total_users",
            "Total Child Accounts": "total_child_accounts",
        }
    ).fillna("")
    connection.executemany(
        """
        INSERT INTO raw_customers_list (
            account_id, account_name, type, registered_date, parent_account_id, address,
            country, city, state, postal_code, email, service_type, unique_identifier,
            ivr_number, status, total_users, total_child_accounts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        customers[
            [
                "account_id",
                "account_name",
                "type",
                "registered_date",
                "parent_account_id",
                "address",
                "country",
                "city",
                "state",
                "postal_code",
                "email",
                "service_type",
                "unique_identifier",
                "ivr_number",
                "status",
                "total_users",
                "total_child_accounts",
            ]
        ].itertuples(index=False, name=None),
    )


def normalize_requesters_export_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    return dataframe.rename(
        columns={
            "Requester ID": "requester_id",
            "First Name": "first_name",
            "Last Name": "last_name",
            "Email": "email",
            "Phone Number": "phone_number",
            "Address": "address",
            "Country": "country",
            "City": "city",
            "State": "state",
            "Zipcode": "zipcode",
            "Account ID": "account_id",
            "Account Name": "account_name",
            "Office Location": "office_location",
            "Default Service Type(OPI)": "default_service_type_opi",
            "Other Service Types": "other_service_types",
            "Pre Call Policy": "pre_call_policy",
            "IVR Pin": "ivr_pin",
            "Role": "role",
            "Status": "status",
            "Joined Date": "joined_date",
            "Last Assignment": "last_assignment",
            "Last Login": "last_login",
            "Scheduled Telephonic": "scheduled_telephonic",
            "On-Demand Telephonic": "ondemand_telephonic",
            "On-Demand Video Interpreting": "ondemand_video_interpreting",
            "Scheduled Video Interpreting": "scheduled_video_interpreting",
            "Onsite Consecutive": "onsite_consecutive",
            "Onsite Simultaneous": "onsite_simultaneous",
            "Third Party Platform": "third_party_platform",
        }
    ).fillna("")


def seed_raw_requesters_export(
    connection: sqlite3.Connection,
    *,
    csv_path: Path,
    table_name: str,
) -> None:
    dataframe = normalize_requesters_export_frame(pd.read_csv(csv_path, dtype=str))
    connection.executemany(
        f"""
        INSERT INTO {table_name} (
            requester_id, first_name, last_name, email, phone_number, address, country, city,
            state, zipcode, account_id, account_name, office_location, default_service_type_opi,
            other_service_types, pre_call_policy, ivr_pin, role, status, joined_date,
            last_assignment, last_login, scheduled_telephonic, ondemand_telephonic,
            ondemand_video_interpreting, scheduled_video_interpreting, onsite_consecutive,
            onsite_simultaneous, third_party_platform
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        dataframe[
            [
                "requester_id",
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "address",
                "country",
                "city",
                "state",
                "zipcode",
                "account_id",
                "account_name",
                "office_location",
                "default_service_type_opi",
                "other_service_types",
                "pre_call_policy",
                "ivr_pin",
                "role",
                "status",
                "joined_date",
                "last_assignment",
                "last_login",
                "scheduled_telephonic",
                "ondemand_telephonic",
                "ondemand_video_interpreting",
                "scheduled_video_interpreting",
                "onsite_consecutive",
                "onsite_simultaneous",
                "third_party_platform",
            ]
        ].itertuples(index=False, name=None),
    )


def assign_fk_locations(site_reference: pd.DataFrame) -> pd.DataFrame:
    ordered = site_reference.sort_values(["customer_name", "teid"]).reset_index(drop=True).copy()
    ordered["fk_location"] = ordered.index + 3000
    for (customer_name, teid), fk_location in KNOWN_LOCATION_OVERRIDES.items():
        mask = (ordered["customer_name"] == customer_name) & (ordered["teid"] == teid)
        ordered.loc[mask, "fk_location"] = fk_location
    return ordered


def load_site_reference(bod_lookup: pd.DataFrame) -> pd.DataFrame:
    site_reference = pd.read_excel(SITES_REFERENCE_PATH, sheet_name="ALL SITES", dtype=str).fillna("")
    site_reference = site_reference.rename(
        columns={
            "CustomerName": "customer_name",
            "TEID": "teid",
            "Site Name": "site_name",
            "State": "state",
            "Max_PIN": "max_pin",
            "Next_PIN": "next_pin",
        }
    )
    site_reference["customer_name"] = site_reference["customer_name"].map(normalize_text)
    site_reference["teid"] = site_reference["teid"].map(normalize_teid)
    site_reference["site_name"] = site_reference["site_name"].map(normalize_text)
    site_reference["state"] = site_reference["state"].map(normalize_text)
    site_reference["max_pin"] = site_reference["max_pin"].map(normalize_pin)
    site_reference["next_pin"] = site_reference["next_pin"].map(normalize_pin)
    site_reference = site_reference.merge(bod_lookup, on="customer_name", how="left")
    site_reference = assign_fk_locations(site_reference)
    return site_reference[
        [
            "customer_name",
            "bod_code",
            "teid",
            "site_name",
            "state",
            "max_pin",
            "next_pin",
            "fk_customer",
            "fk_location",
        ]
    ].drop_duplicates(subset=["teid"])


def seed_bod_lookup(connection: sqlite3.Connection, bod_lookup: pd.DataFrame) -> None:
    connection.executemany(
        """
        INSERT INTO bod_lookup (bod_code, fk_customer, customer_name)
        VALUES (?, ?, ?)
        """,
        bod_lookup[["bod_code", "fk_customer", "customer_name"]].itertuples(index=False, name=None),
    )


def seed_site_reference(connection: sqlite3.Connection, site_reference: pd.DataFrame) -> None:
    connection.executemany(
        """
        INSERT INTO site_reference (
            customer_name, bod_code, teid, site_name, state, max_pin, next_pin, fk_customer, fk_location
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        site_reference[
            [
                "customer_name",
                "bod_code",
                "teid",
                "site_name",
                "state",
                "max_pin",
                "next_pin",
                "fk_customer",
                "fk_location",
            ]
        ].itertuples(index=False, name=None),
    )


def seed_site_catalog(
    connection: sqlite3.Connection,
    site_reference: pd.DataFrame,
    bod_lookup: pd.DataFrame,
) -> None:
    site_catalog = site_reference[["customer_name", "bod_code", "site_name"]].copy()
    site_catalog["has_teid"] = 1

    monthly = pd.read_excel(MONTHLY_REPORT_PATH, dtype=str).fillna("")
    monthly = monthly.rename(columns={"BOD": "bod_label", "Site": "site_name"})
    monthly["site_name"] = monthly["site_name"].map(normalize_text)
    monthly["bod_code"] = monthly["bod_label"].map(extract_bod_code)
    monthly = monthly.merge(bod_lookup, on="bod_code", how="left")
    monthly = monthly[["customer_name", "bod_code", "site_name"]].dropna().drop_duplicates()
    monthly["has_teid"] = 0

    combined = pd.concat([site_catalog, monthly], ignore_index=True)
    combined["customer_name"] = combined["customer_name"].map(normalize_text)
    combined["bod_code"] = combined["bod_code"].map(normalize_text)
    combined["site_name"] = combined["site_name"].map(normalize_text)
    combined = combined[combined["customer_name"] != ""]
    combined = combined[combined["site_name"] != ""]
    combined = (
        combined.sort_values(["customer_name", "site_name", "has_teid"])
        .drop_duplicates(subset=["customer_name", "site_name"], keep="first")
    )

    connection.executemany(
        """
        INSERT INTO site_catalog (customer_name, bod_code, site_name, has_teid)
        VALUES (?, ?, ?, ?)
        """,
        combined[["customer_name", "bod_code", "site_name", "has_teid"]].itertuples(index=False, name=None),
    )


def seed_requestor_reference(
    connection: sqlite3.Connection,
    site_reference: pd.DataFrame,
    bod_lookup: pd.DataFrame,
) -> None:
    requestors_teid = pd.read_excel(REQUESTERS_TEID_PATH, sheet_name="Sheet1", dtype=str).fillna("")
    requestors_teid = requestors_teid.rename(
        columns={
            "PinCode": "pin_code",
            "TEID": "teid",
            "Site Name": "site_name",
            "UserEmail": "email",
            "SEID": "seid",
            "LastName": "last_name",
            "CustomerName": "customer_name",
        }
    )
    requestors_teid["pin_code"] = requestors_teid["pin_code"].map(normalize_pin)
    requestors_teid["teid"] = requestors_teid["teid"].map(normalize_teid)
    requestors_teid["site_name"] = requestors_teid["site_name"].map(normalize_text)
    requestors_teid["email"] = requestors_teid["email"].map(normalize_text)
    requestors_teid["seid"] = requestors_teid["seid"].map(normalize_text)
    requestors_teid["last_name"] = requestors_teid["last_name"].map(normalize_text)
    requestors_teid["customer_name"] = requestors_teid["customer_name"].map(normalize_text)
    requestors_teid = requestors_teid[
        ["seid", "customer_name", "pin_code", "teid", "site_name", "email", "last_name"]
    ].drop_duplicates(subset=["seid", "customer_name", "pin_code"])
    connection.executemany(
        """
        INSERT INTO raw_requesters_teid (
            pin_code, teid, source_id, site_name, state, user_email, seid, first_name,
            last_name, customer_email, customer_unique_identifier, customer_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        pd.read_excel(REQUESTERS_TEID_PATH, sheet_name="Sheet1", dtype=str)
        .fillna("")
        .rename(
            columns={
                "PinCode": "pin_code",
                "TEID": "teid",
                "ID": "source_id",
                "Site Name": "site_name",
                "State": "state",
                "UserEmail": "user_email",
                "SEID": "seid",
                "FirstName": "first_name",
                "LastName": "last_name",
                "CustomerEmail": "customer_email",
                "CustomerUniqueIdentifier": "customer_unique_identifier",
                "CustomerName": "customer_name",
            }
        )[
            [
                "pin_code",
                "teid",
                "source_id",
                "site_name",
                "state",
                "user_email",
                "seid",
                "first_name",
                "last_name",
                "customer_email",
                "customer_unique_identifier",
                "customer_name",
            ]
        ]
        .itertuples(index=False, name=None),
    )

    all_users = pd.read_csv(ALL_IRS_USERS_PATH, dtype=str).fillna("")
    raw_all_users = all_users.rename(
        columns={
            "Requester ID": "requester_id",
            "First Name": "first_name",
            "Last Name": "last_name",
            "Email": "email",
            "Phone Number": "phone_number",
            "Address": "address",
            "Country": "country",
            "City": "city",
            "State": "state",
            "Zipcode": "zipcode",
            "Account ID": "account_id",
            "Account Name": "account_name",
            "Office Location": "office_location",
            "Default Service Type(OPI)": "default_service_type_opi",
            "Other Service Types": "other_service_types",
            "Pre Call Policy": "pre_call_policy",
            "IVR Pin": "ivr_pin",
            "Role": "role",
            "Status": "status",
            "Joined Date": "joined_date",
            "Last Assignment": "last_assignment",
            "Last Login": "last_login",
            "Scheduled Telephonic": "scheduled_telephonic",
            "On-Demand Telephonic": "ondemand_telephonic",
            "On-Demand Video Interpreting": "ondemand_video_interpreting",
            "Scheduled Video Interpreting": "scheduled_video_interpreting",
            "Onsite Consecutive": "onsite_consecutive",
            "Onsite Simultaneous": "onsite_simultaneous",
            "Third Party Platform": "third_party_platform",
        }
    )
    connection.executemany(
        """
        INSERT INTO raw_requesters_all_irs (
            requester_id, first_name, last_name, email, phone_number, address, country, city,
            state, zipcode, account_id, account_name, office_location, default_service_type_opi,
            other_service_types, pre_call_policy, ivr_pin, role, status, joined_date,
            last_assignment, last_login, scheduled_telephonic, ondemand_telephonic,
            ondemand_video_interpreting, scheduled_video_interpreting, onsite_consecutive,
            onsite_simultaneous, third_party_platform
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        raw_all_users[
            [
                "requester_id",
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "address",
                "country",
                "city",
                "state",
                "zipcode",
                "account_id",
                "account_name",
                "office_location",
                "default_service_type_opi",
                "other_service_types",
                "pre_call_policy",
                "ivr_pin",
                "role",
                "status",
                "joined_date",
                "last_assignment",
                "last_login",
                "scheduled_telephonic",
                "ondemand_telephonic",
                "ondemand_video_interpreting",
                "scheduled_video_interpreting",
                "onsite_consecutive",
                "onsite_simultaneous",
                "third_party_platform",
            ]
        ].itertuples(index=False, name=None),
    )

    requestors = all_users.rename(
        columns={
            "Requester ID": "requester_id",
            "First Name": "seid",
            "Last Name": "last_name",
            "Email": "email_live",
            "IVR Pin": "pin_code",
            "Account Name": "customer_name",
            "Account ID": "account_id",
            "Office Location": "office_location",
            "Status": "account_status",
            "Joined Date": "created_at",
        }
    )
    requestors["requester_id"] = requestors["requester_id"].map(normalize_text)
    requestors["seid"] = requestors["seid"].map(normalize_text)
    requestors["last_name"] = requestors["last_name"].map(normalize_text)
    requestors["email_live"] = requestors["email_live"].map(normalize_text)
    requestors["pin_code"] = requestors["pin_code"].map(normalize_pin)
    requestors["customer_name"] = requestors["customer_name"].map(normalize_text)
    requestors["account_id"] = requestors["account_id"].map(normalize_text)
    requestors["office_location"] = requestors["office_location"].map(normalize_text)
    requestors["account_status"] = requestors["account_status"].map(normalize_text)
    requestors["created_at"] = requestors["created_at"].map(normalize_text)
    requestors["teid"] = requestors["pin_code"].str[:4]
    requestors["first_name"] = requestors["seid"]
    requestors = requestors.merge(
        bod_lookup[["customer_name", "bod_code"]].drop_duplicates(),
        on="customer_name",
        how="left",
    )

    site_lookup = site_reference[["customer_name", "teid", "site_name"]].drop_duplicates()
    requestors = requestors.merge(site_lookup, on=["customer_name", "teid"], how="left")
    requestors = requestors.merge(
        requestors_teid,
        on=["seid", "customer_name", "pin_code"],
        how="left",
        suffixes=("", "_teid"),
    )
    requestors["site_name"] = requestors["site_name"].where(
        requestors["site_name"].map(normalize_text) != "",
        requestors["site_name_teid"],
    )
    requestors["email"] = requestors["email_live"].where(
        requestors["email_live"] != "",
        requestors["email"],
    )
    requestors["last_name"] = requestors["last_name"].where(
        requestors["last_name"] != "",
        requestors["last_name_teid"],
    )
    requestors["account_status"] = requestors["account_status"].where(
        requestors["account_status"] != "",
        "Active",
    )
    requestors["requester_id"] = requestors.apply(
        lambda row: str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{row['seid']}|{row['customer_name']}|{row['pin_code']}|{row['teid']}",
            )
        ),
        axis=1,
    )
    requestors["connect_guid"] = requestors["requester_id"].map(
        lambda value: str(uuid.uuid5(uuid.NAMESPACE_URL, f"connect-{value}"))
    )
    requestors["created_at"] = requestors["created_at"].where(
        requestors["created_at"] != "",
        "2026-03-13T00:00:00Z",
    )
    requestors["updated_at"] = "2026-03-13T00:00:00Z"
    requestors = requestors[requestors["seid"] != ""]
    requestors = requestors[requestors["teid"] != ""]
    requestors = requestors[requestors["customer_name"].isin(set(bod_lookup["customer_name"]))]
    requestors = requestors.drop_duplicates(subset=["requester_id"])

    connection.executemany(
        """
        INSERT INTO requestor_reference (
            requester_id, seid, first_name, last_name, email, account_id, office_location, pin_code, teid, site_name,
            customer_name, bod_code, connect_guid, account_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        requestors[
            [
                "requester_id",
                "seid",
                "first_name",
                "last_name",
                "email",
                "account_id",
                "office_location",
                "pin_code",
                "teid",
                "site_name",
                "customer_name",
                "bod_code",
                "connect_guid",
                "account_status",
                "created_at",
                "updated_at",
            ]
        ].itertuples(index=False, name=None),
    )


def sync_teid_registry(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM stg_irs_teid_registry")
    connection.execute(
        """
        INSERT INTO stg_irs_teid_registry (teid, site_name, site_address, fk_customer, fk_location)
        SELECT teid, COALESCE(site_name, ''), '', fk_customer, fk_location
        FROM site_reference
        """
    )


def get_customer_by_bod(connection: sqlite3.Connection, bod_code: str) -> dict | None:
    row = connection.execute(
        """
        SELECT bod_code, fk_customer, customer_name
        FROM bod_lookup
        WHERE UPPER(bod_code) = UPPER(?)
        LIMIT 1
        """,
        (bod_code,),
    ).fetchone()
    return None if row is None else dict(row)


def get_site_strings(connection: sqlite3.Connection, customer_name: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT site_name
        FROM site_catalog
        WHERE customer_name = ?
        ORDER BY site_name
        """,
        (customer_name,),
    ).fetchall()
    return [row["site_name"] for row in rows]


def get_site_by_teid(connection: sqlite3.Connection, customer_name: str, teid: str) -> dict | None:
    row = connection.execute(
        """
        SELECT customer_name, bod_code, teid, site_name, state, max_pin, next_pin, fk_customer, fk_location
        FROM site_reference
        WHERE customer_name = ? AND teid = ?
        LIMIT 1
        """,
        (customer_name, teid),
    ).fetchone()
    return None if row is None else dict(row)


def resolve_teid(connection: sqlite3.Connection, customer_name: str, site_name: str) -> dict:
    exact_match = connection.execute(
        """
        SELECT teid
        FROM site_reference
        WHERE customer_name = ? AND site_name = ?
        LIMIT 1
        """,
        (customer_name, site_name),
    ).fetchone()
    if exact_match is not None:
        return {
            "currentMaxTeid": None,
            "existingTeid": exact_match["teid"],
            "accountName": customer_name,
            "siteExists": True,
            "errorMessage": None,
        }

    max_row = connection.execute(
        """
        SELECT MAX(CAST(teid AS INTEGER)) AS current_max_teid
        FROM site_reference
        WHERE customer_name = ?
        """,
        (customer_name,),
    ).fetchone()
    if max_row is None or max_row["current_max_teid"] is None:
        raise ValueError(f"No TEIDs found for customer '{customer_name}'.")

    return {
        "currentMaxTeid": str(max_row["current_max_teid"]).zfill(4),
        "existingTeid": None,
        "accountName": customer_name,
        "siteExists": False,
        "errorMessage": None,
    }


def get_pin_context(connection: sqlite3.Connection, customer_name: str, teid: str) -> dict:
    site = get_site_by_teid(connection, customer_name, teid)
    if site is None:
        raise ValueError(f"Customer '{customer_name}' does not have TEID '{teid}' in the mock database.")

    return {
        "teid": site["teid"],
        "accountName": site["customer_name"],
        "fK_Customer": site["fk_customer"],
        "fK_Location": site["fk_location"],
        "maxPinCode": site["max_pin"] or None,
        "siteName": site["site_name"],
    }


def ensure_direct_teid_placeholder(
    connection: sqlite3.Connection,
    *,
    customer_name: str,
    bod_code: str,
    teid: str,
    site_name: str,
) -> dict:
    existing = get_site_by_teid(connection, customer_name, teid)
    if existing is not None:
        return existing

    customer = get_customer_by_bod(connection, bod_code)
    if customer is None:
        raise ValueError(f"Unknown BOD '{bod_code}'.")

    max_pin_row = connection.execute(
        """
        SELECT MAX(CAST(pin_code AS INTEGER)) AS max_pin
        FROM requestor_reference
        WHERE customer_name = ? AND teid = ?
        """,
        (customer_name, teid),
    ).fetchone()
    max_pin = None if max_pin_row is None or max_pin_row["max_pin"] is None else str(max_pin_row["max_pin"])
    next_location_row = connection.execute(
        "SELECT COALESCE(MAX(fk_location), 3000) + 1 AS next_fk_location FROM site_reference"
    ).fetchone()
    fk_location = next_location_row["next_fk_location"]

    connection.execute(
        """
        INSERT INTO site_reference (
            customer_name, bod_code, teid, site_name, state, max_pin, next_pin, fk_customer, fk_location
        ) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?)
        """,
        (
            customer_name,
            bod_code,
            teid,
            site_name,
            max_pin,
            f"{teid}00001" if max_pin is None else str(int(max_pin) + 1),
            customer["fk_customer"],
            fk_location,
        ),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO site_catalog (customer_name, bod_code, site_name, has_teid)
        VALUES (?, ?, ?, 1)
        """,
        (customer_name, bod_code, site_name),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO stg_irs_teid_registry (teid, site_name, site_address, fk_customer, fk_location)
        VALUES (?, ?, '', ?, ?)
        """,
        (teid, site_name, customer["fk_customer"], fk_location),
    )
    connection.commit()
    return get_site_by_teid(connection, customer_name, teid)


def create_site_for_customer(connection: sqlite3.Connection, customer_name: str, site_name: str) -> dict:
    customer = connection.execute(
        """
        SELECT bod_code, fk_customer, customer_name
        FROM bod_lookup
        WHERE customer_name = ?
        LIMIT 1
        """,
        (customer_name,),
    ).fetchone()
    if customer is None:
        raise ValueError(f"Unknown customer '{customer_name}'.")

    max_row = connection.execute(
        """
        SELECT COALESCE(MAX(CAST(teid AS INTEGER)), 999) + 1 AS next_teid,
               COALESCE(MAX(fk_location), 3000) + 1 AS next_fk_location
        FROM site_reference
        WHERE customer_name = ?
        """,
        (customer_name,),
    ).fetchone()
    teid = str(max_row["next_teid"]).zfill(4)
    fk_location = max_row["next_fk_location"]

    connection.execute(
        """
        INSERT INTO site_reference (
            customer_name, bod_code, teid, site_name, state, max_pin, next_pin, fk_customer, fk_location
        ) VALUES (?, ?, ?, ?, '', NULL, ?, ?, ?)
        """,
        (
            customer_name,
            customer["bod_code"],
            teid,
            site_name,
            f"{teid}00001",
            customer["fk_customer"],
            fk_location,
        ),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO site_catalog (customer_name, bod_code, site_name, has_teid)
        VALUES (?, ?, ?, 1)
        """,
        (customer_name, customer["bod_code"], site_name),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO stg_irs_teid_registry (teid, site_name, site_address, fk_customer, fk_location)
        VALUES (?, ?, '', ?, ?)
        """,
        (teid, site_name, customer["fk_customer"], fk_location),
    )
    connection.commit()
    return {
        "teid": teid,
        "site_name": site_name,
        "fk_customer": customer["fk_customer"],
        "fk_location": fk_location,
        "customer_name": customer_name,
        "bod_code": customer["bod_code"],
    }


def search_requestors_by_seid(
    connection: sqlite3.Connection,
    *,
    customer_name: str,
    seid: str,
    active_only: bool = True,
) -> list[dict]:
    status_filter = "AND UPPER(account_status) = 'ACTIVE'" if active_only else ""
    rows = connection.execute(
        f"""
        SELECT requester_id, seid, first_name, last_name, email, pin_code, teid, site_name,
               customer_name, bod_code, connect_guid, account_status
        FROM requestor_reference
        WHERE customer_name = ?
          AND UPPER(seid) = UPPER(?)
          {status_filter}
        ORDER BY created_at
        """,
        (customer_name, seid),
    ).fetchall()
    return [dict(row) for row in rows]


def record_created_requestor(
    connection: sqlite3.Connection,
    *,
    seid: str,
    first_name: str,
    last_name: str,
    email: str,
    pin_code: str,
    teid: str,
    site_name: str,
    customer_name: str,
    bod_code: str,
) -> dict:
    requester_id = str(uuid.uuid4())
    connect_guid = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO requestor_reference (
            requester_id, seid, first_name, last_name, email, pin_code, teid, site_name,
            customer_name, bod_code, connect_guid, account_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', '2026-03-13T00:00:00Z', '2026-03-13T00:00:00Z')
        """,
        (
            requester_id,
            seid,
            first_name,
            last_name,
            email,
            pin_code,
            teid,
            site_name,
            customer_name,
            bod_code,
            connect_guid,
        ),
    )
    connection.execute(
        """
        UPDATE site_reference
        SET max_pin = ?, next_pin = ?
        WHERE customer_name = ? AND teid = ?
        """,
        (pin_code, str(int(pin_code) + 1), customer_name, teid),
    )
    connection.commit()
    return {"requester_id": requester_id, "connect_guid": connect_guid}


def deactivate_requestor(connection: sqlite3.Connection, *, customer_name: str, seid: str) -> dict | None:
    existing = connection.execute(
        """
        SELECT requester_id, seid, connect_guid, pin_code, teid, site_name, account_status
        FROM requestor_reference
        WHERE customer_name = ?
          AND UPPER(seid) = UPPER(?)
          AND UPPER(account_status) = 'ACTIVE'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (customer_name, seid),
    ).fetchone()
    if existing is None:
        return None

    connection.execute(
        """
        UPDATE requestor_reference
        SET account_status = 'Inactive',
            updated_at = '2026-03-13T00:00:00Z'
        WHERE requester_id = ?
        """,
        (existing["requester_id"],),
    )
    connection.commit()
    return dict(existing)


def write_pin_registry(
    connection: sqlite3.Connection,
    *,
    seid: str,
    first_name: str,
    last_name: str,
    bod: str,
    site_id: str,
    site_name: str,
    pin_9digit: str | None,
    connect_guid: str | None,
    status: str,
    batch_id: str,
    created_by: str,
) -> None:
    connection.execute(
        """
        INSERT INTO stg_irs_pin_registry (
            seid, first_name, last_name, bod, site_id, site_name, pin_9digit,
            connect_guid, status, batch_id, created_by, updated_dt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            seid,
            first_name,
            last_name,
            bod,
            site_id,
            site_name,
            pin_9digit,
            connect_guid,
            status,
            batch_id,
            created_by,
        ),
    )
    connection.commit()
