"""Input parsing and validation for the QA workflow."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

import pandas as pd

from .models import ParsedRow
from utils.helpers import extract_employee_id_from_pin, extract_teid_from_pin

HEADER_ALIASES = {
    "bod": "bod",
    "customer": "customer_name",
    "customer name": "customer_name",
    "account name": "customer_name",
    "requested action": "contact_status",
    "last name": "last_name",
    "lastname": "last_name",
    "first name": "first_name",
    "firstname": "first_name",
    "seid": "seid",
    "sidn": "seid",
    "pin": "user_pin",
    "site id": "site_id",
    "site id / teid": "site_id",
    "site:location id": "site_id",
    "teid": "site_id",
    "location id": "site_id",
    "site": "site_name",
    "site name": "site_name",
    "location": "site_name",
    "employee id": "employee_id",
    "employeeid": "employee_id",
    "manual site name": "manual_site_name",
    "manual site choice": "manual_site_name",
    "selected site name": "manual_site_name",
    "canonical site name": "manual_site_name",
    "new site:site id": "new_site_id",
    "new site site id": "new_site_id",
    "new site id": "new_site_id",
    "new site:location id": "new_site_id",
    "new location id": "new_site_id",
    "new site": "new_site_name",
    "new site name": "new_site_name",
    "new location": "new_site_name",
    "current user pin": "user_pin",
    "9-digit user pin": "user_pin",
    "9 digit user pin": "user_pin",
    "9-digit user pin (completed by ad astra)": "user_pin",
    "9 digit user pin (completed by ad astra)": "user_pin",
    "user pin": "user_pin",
    "pin action required": "contact_status",
    "contact status": "contact_status",
    "action": "contact_status",
    "request type": "contact_status",
    "reason for deletion": "contact_status",
    "comments": "comments",
    "comments (if needed)": "comments",
    "new bod": "new_bod",
    "new account": "new_bod",
    "new customer name": "new_customer_name",
    "new customer": "new_customer_name",
    # analyst-use columns — map to a no-op key so they are silently ignored
    "new opi pin": "_analyst_only",
    "date of completion": "_analyst_only",
    "manager": "_analyst_only",
}

ADD_REQUIRED_FIELDS = ("last_name", "first_name", "seid", "site_name")
DEACTIVATE_REQUIRED_FIELDS = ("seid",)
ACTIVATE_REQUIRED_FIELDS = ("seid",)
MODIFY_FUNCTION_REQUIRED_FIELDS = ("last_name", "first_name", "seid", "site_name", "employee_id", "new_site_name")
MEANINGFUL_ROW_FIELDS = (
    "last_name",
    "first_name",
    "seid",
    "site_id",
    "site_name",
    "manual_site_name",
    "user_pin",
    "employee_id",
    "new_site_id",
    "new_site_name",
    "contact_status",
    "new_bod",
    "new_customer_name",
)


def normalize_header(value: str) -> str:
    cleaned = str(value).strip().lower().replace("_", " ").replace("\n", " ").replace("\r", " ")
    return " ".join(cleaned.split())


def normalize_value(value: str | None) -> str:
    return "" if value is None else str(value).strip()


def normalize_explicit_teid(value: str | None) -> str:
    normalized = normalize_value(value)
    return normalized if normalized.isdigit() and len(normalized) == 4 else ""


def _first_non_empty(values: list[object]) -> str:
    for value in values:
        normalized = normalize_value(value)
        if normalized:
            return normalized
    return ""


def coalesce_duplicate_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.columns.is_unique:
        return dataframe

    merged: dict[str, pd.Series] = {}
    ordered_columns = list(dict.fromkeys(dataframe.columns))
    for column in ordered_columns:
        duplicate_frame = dataframe.loc[:, dataframe.columns == column]
        if isinstance(duplicate_frame, pd.Series):
            merged[column] = duplicate_frame.fillna("")
            continue
        if duplicate_frame.shape[1] == 1:
            merged[column] = duplicate_frame.iloc[:, 0].fillna("")
            continue
        merged[column] = duplicate_frame.apply(lambda row: _first_non_empty(row.tolist()), axis=1)
    return pd.DataFrame(merged).fillna("")


def _row_identity_key(normalized: dict[str, str], contact_status: str) -> tuple[str, ...]:
    action = normalize_value(contact_status).lower()
    bod_or_customer = normalize_value(normalized.get("bod") or normalized.get("customer_name")).lower()
    seid = normalize_value(normalized.get("seid")).lower()
    current_site_id = normalize_value(normalized.get("site_id")).lower()
    current_site_name = normalize_value(normalized.get("site_name")).lower()
    new_site_id = normalize_value(normalized.get("new_site_id")).lower()
    new_site_name = normalize_value(normalized.get("new_site_name")).lower()
    employee_id = normalize_value(normalized.get("employee_id")).lower()

    if action == "modify-function change":
        return (action, bod_or_customer, seid, current_site_id, current_site_name, new_site_id, new_site_name, employee_id)
    if action == "deactivate":
        return (action, bod_or_customer, seid, current_site_id, current_site_name)
    return (action, bod_or_customer, seid, current_site_id, current_site_name)


def normalize_contact_status(raw_status: str, *, default_status: str = "Add") -> tuple[str, bool]:
    status = normalize_value(raw_status).lower()
    if not status:
        return default_status, True
    if "activate existing" in status:
        return "Activate", True
    if status == "activate":
        return "Activate", True
    if "switch to ad astra" in status:
        return "Modify-Function Change", True
    if "modify-function" in status or "modify function" in status:
        return "Modify-Function Change", True
    if "deactivat" in status or "delete" in status or "separat" in status:
        return "Deactivate", True
    if "remov" in status or "terminat" in status or "inactive" in status:
        return "Deactivate", True
    if "transfer" in status or status == "move" or status.startswith("move ") or status.endswith(" move"):
        return "Modify-Function Change", True
    if "add" in status or "new pin" in status:
        return "Add", True
    if status == "active":
        return "Completed", True
    return normalize_value(raw_status), False


def looks_like_move_comment(comment: str) -> bool:
    normalized = normalize_value(comment).lower()
    if not normalized:
        return False
    move_patterns = (
        r"\bmoving\s+from\b",
        r"\bmoved\s+from\b",
        r"\bmove\s+from\b",
        r"\btransfer(?:ring|red)?\s+from\b",
        r"\brelocat(?:e|ing|ed)\s+from\b",
    )
    return any(re.search(pattern, normalized) for pattern in move_patterns)


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
    dataframe = coalesce_duplicate_columns(dataframe)

    rows: list[ParsedRow] = []
    seen_row_keys: set[tuple[str, ...]] = set()

    for frame_index, raw_row in dataframe.iterrows():
        row_number = frame_index + 2
        normalized = {
            column: normalize_value(raw_row.get(column, ""))
            for column in dataframe.columns
        }
        if not any(normalized.get(field, "") for field in MEANINGFUL_ROW_FIELDS):
            continue
        original_site_id = normalized.get("site_id", "")
        original_new_site_id = normalized.get("new_site_id", "")
        normalized["site_id"] = normalize_explicit_teid(original_site_id)
        normalized["new_site_id"] = normalize_explicit_teid(original_new_site_id)
        contact_status, status_is_valid = normalize_contact_status(
            normalized.get("contact_status", ""),
            default_status=default_contact_status,
        )
        if contact_status == "Completed":
            continue
        notes: list[str] = []
        error_fields: list[str] = []

        new_bod_val = normalized.get("new_bod", "").strip()
        if (
            contact_status in ("Add", "Modify-Function Change")
            and new_bod_val
            and new_bod_val.lower() != normalized.get("bod", "").strip().lower()
            and new_bod_val.lower() != normalized.get("customer_name", "").strip().lower()
        ):
            contact_status = "Modify-Function Change"
            notes.append("Promoted to cross-account Modify-Function Change because New BOD differs from source BOD.")

        if (
            contact_status == "Add"
            and normalized.get("user_pin")
            and normalized.get("site_name")
            and looks_like_move_comment(normalized.get("comments", ""))
        ):
            contact_status = "Modify-Function Change"
            notes.append("Promoted Add row to Modify-Function Change because comments indicate the requester is moving and Current User PIN was provided.")

        if contact_status == "Modify-Function Change" and not normalized.get("new_site_name") and normalized.get("site_name"):
            normalized["new_site_name"] = normalized["site_name"]
            notes.append("Treating Site Name as New Site for Switch to Ad Astra / modify-function input.")

        if contact_status == "Modify-Function Change" and not normalized.get("site_id") and normalized.get("user_pin"):
            derived_old_teid = extract_teid_from_pin(normalized.get("user_pin"))
            if derived_old_teid:
                normalized["site_id"] = derived_old_teid
                notes.append("Derived old-site TEID from Current User PIN for modify-function processing.")

        if contact_status == "Modify-Function Change" and not normalized.get("employee_id") and normalized.get("user_pin"):
            derived_employee_id = extract_employee_id_from_pin(normalized.get("user_pin"))
            if derived_employee_id:
                normalized["employee_id"] = derived_employee_id
                notes.append("Derived Employee ID from Current User PIN for modify-function processing.")

        if contact_status in ("Activate", "Add") and not normalized.get("site_id") and normalized.get("user_pin"):
            derived_teid = extract_teid_from_pin(normalized.get("user_pin"))
            if derived_teid:
                normalized["site_id"] = derived_teid
                notes.append("Derived TEID from PIN column.")

        if contact_status == "Add" and not normalized.get("first_name") and normalized.get("seid"):
            normalized["first_name"] = normalized["seid"]

        if original_site_id and not normalized.get("site_id"):
            notes.append("Site ID ignored because it is not a 4-digit numeric TEID; site name will be used instead.")
        if original_new_site_id and not normalized.get("new_site_id"):
            notes.append("New Site ID ignored because it is not a 4-digit numeric TEID; new site name will be used instead.")

        if contact_status == "Deactivate":
            required_fields = DEACTIVATE_REQUIRED_FIELDS
        elif contact_status == "Activate":
            required_fields = ACTIVATE_REQUIRED_FIELDS
        elif contact_status == "Modify-Function Change":
            required_fields = MODIFY_FUNCTION_REQUIRED_FIELDS
        else:
            required_fields = ADD_REQUIRED_FIELDS
        for field_name in required_fields:
            if not normalized.get(field_name, ""):
                error_fields.append(field_name)

        if not normalized.get("bod") and not normalized.get("customer_name"):
            error_fields.append("bod_or_customer_name")

        if not status_is_valid:
            error_fields.append("contact_status")

        duplicate_in_batch = False
        row_key = _row_identity_key(normalized, contact_status)
        if row_key[2]:
            if row_key in seen_row_keys:
                duplicate_in_batch = True
                notes.append("Duplicate row identity in upload; later occurrence will be skipped.")
            else:
                seen_row_keys.add(row_key)

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
                employee_id=normalized.get("employee_id", ""),
                new_site_id=normalized.get("new_site_id", ""),
                new_site_name=normalized.get("new_site_name", ""),
                contact_status=contact_status,
                validation_status=validation_status,
                notes=notes,
                error_fields=error_fields,
                duplicate_in_batch=duplicate_in_batch,
                new_bod=normalized.get("new_bod", ""),
                new_customer_name=normalized.get("new_customer_name", ""),
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
