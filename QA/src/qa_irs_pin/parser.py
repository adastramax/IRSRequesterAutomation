"""Input parsing and validation for the QA workflow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from .models import ParsedRow

HEADER_ALIASES = {
    "bod": "bod",
    "customer": "customer_name",
    "customer name": "customer_name",
    "account name": "customer_name",
    "last name": "last_name",
    "lastname": "last_name",
    "first name": "first_name",
    "firstname": "first_name",
    "seid": "seid",
    "site id": "site_id",
    "site id / teid": "site_id",
    "teid": "site_id",
    "site name": "site_name",
    "manual site name": "manual_site_name",
    "manual site choice": "manual_site_name",
    "selected site name": "manual_site_name",
    "canonical site name": "manual_site_name",
    "9-digit user pin": "user_pin",
    "9 digit user pin": "user_pin",
    "user pin": "user_pin",
    "contact status": "contact_status",
}

ADD_REQUIRED_FIELDS = ("last_name", "first_name", "seid", "site_name")
DEACTIVATE_REQUIRED_FIELDS = ("seid",)


def normalize_header(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("_", " ").split())


def normalize_value(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def normalize_contact_status(raw_status: str, *, default_status: str = "Add") -> tuple[str, bool]:
    status = normalize_value(raw_status).lower()
    if not status:
        return default_status, True
    if "deactivat" in status:
        return "Deactivate", True
    if "add" in status:
        return "Add", True
    return normalize_value(raw_status), False


def load_input_frame(input_path: Path) -> pd.DataFrame:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        dataframe = pd.read_csv(input_path, dtype=str)
    elif suffix in {".xlsx", ".xls"}:
        dataframe = pd.read_excel(input_path, dtype=str)
    else:
        raise ValueError(f"Unsupported input file type: {suffix}")
    return dataframe.fillna("")


def parse_input_dataframe(dataframe: pd.DataFrame, *, default_contact_status: str = "Add") -> list[ParsedRow]:
    if dataframe.empty and len(dataframe.columns) == 0:
        raise ValueError("Input data is missing a header row.")

    mapped_headers = {
        column: HEADER_ALIASES.get(normalize_header(column), normalize_header(column))
        for column in dataframe.columns
    }
    dataframe = dataframe.rename(columns=mapped_headers).fillna("")

    rows: list[ParsedRow] = []
    seen_seids: set[str] = set()

    for frame_index, raw_row in dataframe.iterrows():
        row_number = frame_index + 2
        normalized = {
            column: normalize_value(raw_row.get(column, ""))
            for column in dataframe.columns
        }
        contact_status, status_is_valid = normalize_contact_status(
            normalized.get("contact_status", ""),
            default_status=default_contact_status,
        )
        notes: list[str] = []
        error_fields: list[str] = []

        required_fields = DEACTIVATE_REQUIRED_FIELDS if contact_status == "Deactivate" else ADD_REQUIRED_FIELDS
        for field_name in required_fields:
            if not normalized.get(field_name, ""):
                error_fields.append(field_name)

        if not normalized.get("bod") and not normalized.get("customer_name"):
            error_fields.append("bod_or_customer_name")

        duplicate_in_batch = False
        seid_key = normalized.get("seid", "").lower()
        if seid_key and seid_key in seen_seids:
            duplicate_in_batch = True
            notes.append("Duplicate SEID in upload; later occurrence will be skipped.")
        elif seid_key:
            seen_seids.add(seid_key)

        if not status_is_valid:
            error_fields.append("contact_status")

        if not normalized.get("site_id"):
            notes.append("Site ID blank; API 2 will resolve TEID after site matching.")

        validation_status = "Valid"
        if error_fields:
            validation_status = "Error"
        elif duplicate_in_batch or not normalized.get("site_id"):
            validation_status = "Warning"

        rows.append(
            ParsedRow(
                row_number=row_number,
                bod=normalized.get("bod", ""),
                customer_name=normalized.get("customer_name", ""),
                last_name=normalized.get("last_name", ""),
                first_name=normalized.get("first_name", ""),
                seid=normalized.get("seid", ""),
                site_id=normalized.get("site_id", ""),
                site_name=normalized.get("site_name", ""),
                manual_site_name=normalized.get("manual_site_name", ""),
                user_pin=normalized.get("user_pin", ""),
                contact_status=contact_status,
                validation_status=validation_status,
                notes=notes,
                error_fields=error_fields,
                duplicate_in_batch=duplicate_in_batch,
            )
        )

    return rows


def parse_input_records(records: list[dict], *, default_contact_status: str = "Add") -> list[ParsedRow]:
    return parse_input_dataframe(pd.DataFrame(records).fillna(""), default_contact_status=default_contact_status)


def parse_input_bytes(filename: str, content: bytes, *, default_contact_status: str = "Add") -> list[ParsedRow]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        dataframe = pd.read_csv(BytesIO(content), dtype=str)
    elif suffix in {".xlsx", ".xls"}:
        dataframe = pd.read_excel(BytesIO(content), dtype=str)
    else:
        raise ValueError(f"Unsupported input file type: {suffix}")
    return parse_input_dataframe(dataframe.fillna(""), default_contact_status=default_contact_status)


def parse_input_file(path: str | Path, *, default_contact_status: str = "Add") -> list[ParsedRow]:
    return parse_input_dataframe(load_input_frame(Path(path)), default_contact_status=default_contact_status)
