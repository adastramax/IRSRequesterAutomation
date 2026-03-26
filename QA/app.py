"""FastAPI wrapper exposing the QA processor through a single main endpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_irs_pin import registry
from qa_irs_pin.config import CUSTOMER_CREATE_OVERRIDES, DB_PATH, DEFAULT_NEW_SITE_PIN_SUFFIX, SITE_MATCH_THRESHOLD
from qa_irs_pin.matching import best_site_match, requires_explicit_site_confirmation
from qa_irs_pin.parser import parse_input_bytes, parse_input_records
from qa_irs_pin.payloads import build_create_payload
from qa_irs_pin.processor import process_rows, resolve_blank_site_id_path
from utils.client import ConnectQAClient
from utils.helpers import is_missing_fk_value, next_new_site_pin, next_pin, normalize_teid, resolve_customer_context

app = FastAPI(title="IRS PIN QA Tool")


class InputRowRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "BOD": "MT",
                "First Name": "John",
                "Last Name": "Carlos",
                "SEID": "JC2019041",
                "Site Name": "Jacksonville, FL, USA",
                "Site ID": "8178",
                "Contact Status": "Add",
                "Manual Site Name": "",
            }
        },
    )

    bod: str = Field(default="", alias="BOD", description="QA BOD/customer alias, e.g. MT or ES.")
    first_name: str = Field(default="", alias="First Name", description="Requester first name.")
    last_name: str = Field(default="", alias="Last Name", description="Requester last name.")
    seid: str = Field(default="", alias="SEID", description="Unique requester SEID.")
    site_name: str = Field(default="", alias="Site Name", description="Input or corrected canonical site name.")
    site_id: str = Field(default="", alias="Site ID", description="TEID/site id. Leave blank to resolve from site name.")
    contact_status: str = Field(default="", alias="Contact Status", description="Use Add or Deactivate.")
    manual_site_name: str = Field(default="", alias="Manual Site Name", description="Optional canonical site override.")


class ProcessRowsRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rows": [
                    {
                        "BOD": "MT",
                        "First Name": "John",
                        "Last Name": "Carlos",
                        "SEID": "JC2019041",
                        "Site Name": "Jacksonville, FL, USA",
                        "Site ID": "8178",
                        "Contact Status": "Add",
                        "Manual Site Name": "",
                    }
                ],
                "created_by": "QA OPI Operator",
                "write_output": False,
                "debug": True,
            }
        }
    )

    rows: list[InputRowRequest] = Field(default_factory=list, description="List of parser-formatted input rows.")
    created_by: str = Field(default="QA OPI Operator", description="Audit user name for commit calls.")
    write_output: bool = Field(default=False, description="Write batch output file when true.")
    debug: bool = Field(default=False, description="Return raw QA/debug shape when true on commit.")


def _request_rows_to_dicts(rows: list[InputRowRequest]) -> list[dict[str, Any]]:
    return [row.model_dump(by_alias=True) for row in rows]


def _build_trimmed_summary(summary: dict[str, int]) -> dict[str, int]:
    return {
        "total": int(summary.get("total", 0)),
        "created": int(summary.get("Created", 0)),
        "deactivated": int(summary.get("Deactivated", 0)),
        "manual_selection_required": int(summary.get("Manual Selection Required", 0)),
        "failed": int(summary.get("Failed", 0)),
    }


def _build_result_message(row_result: dict[str, Any]) -> str:
    response = row_result.get("response") or {}
    if response.get("text"):
        return str(response["text"])
    notes = row_result.get("notes") or []
    return str(notes[-1]) if notes else ""


def _last_log_details(logs: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    for entry in reversed(logs):
        if entry.get("stage") == stage:
            details = entry.get("details")
            return details if isinstance(details, dict) else {}
    return {}


def _extract_match_score(logs: list[dict[str, Any]]) -> float | None:
    details = _last_log_details(logs, "site_match")
    score = details.get("score")
    if isinstance(score, (int, float)):
        return float(score)
    return None


def _build_api_trace(row_result: dict[str, Any], logs: list[dict[str, Any]], *, debug: bool) -> dict[str, Any]:
    api_trace = {
        "api_1": _last_log_details(logs, "pin_context"),
        "api_2": _last_log_details(logs, "teid_resolution"),
        "api_3": _last_log_details(logs, "addresses"),
        "response": row_result.get("response") or {},
        "verification": row_result.get("verification") or {},
    }
    if debug:
        api_trace["logs"] = logs
        if row_result.get("manual_selection"):
            api_trace["manual_selection"] = row_result["manual_selection"]
    return {key: value for key, value in api_trace.items() if value not in (None, [], {})}


def _format_rows_response(request_rows: list[dict[str, Any]], run_result: dict[str, Any], *, debug: bool) -> dict[str, Any]:
    row_results = run_result.get("row_results", [])
    logs = run_result.get("logs", [])
    results: list[dict[str, Any]] = []

    for index, row_result in enumerate(row_results):
        input_row = request_rows[index] if index < len(request_rows) else {}
        row_logs = [entry for entry in logs if entry.get("row_number") == row_result.get("row_number")]
        results.append(
            {
                "input": input_row,
                "corrected_data": {
                    "corrected_bod": row_result.get("customer_name") or "",
                    "corrected_site_name": row_result.get("matched_site_name") or row_result.get("input_site_name") or "",
                    "resolved_site_id": row_result.get("resolved_site_id") or "",
                    "match_score": _extract_match_score(row_logs),
                },
                "api_trace": _build_api_trace(row_result, row_logs, debug=debug),
                "connect_payload": row_result.get("payload") or {},
                "result": {
                    "status": row_result.get("status") or "",
                    "message": _build_result_message(row_result),
                    "guid": row_result.get("connect_guid") or "",
                    "teid": row_result.get("resolved_site_id") or "",
                    "pin": row_result.get("generated_pin") or "",
                    "posted_payload_address": (row_result.get("payload") or {}).get("address") or "",
                },
            }
        )

    return {
        "summary": _build_trimmed_summary(run_result.get("summary", {})),
        "results": results,
    }


def _review_status(summary: dict[str, int]) -> dict[str, int]:
    return {
        "total": int(summary.get("total", 0)),
        "reviewed": int(summary.get("Reviewed", 0)),
        "failed": int(summary.get("Failed", 0)),
        "error": int(summary.get("Error", 0)),
    }


def _run_commit_request(request: ProcessRowsRequest) -> dict[str, Any]:
    request_rows = _request_rows_to_dicts(request.rows)
    result = process_rows(
        parse_input_records(request_rows),
        client=app.state.client,
        created_by=request.created_by,
        db_path=DB_PATH,
        source_name="manual_rows.json",
        write_output=request.write_output,
    )
    result_dict = result.to_dict()
    return _format_rows_response(request_rows, result_dict, debug=request.debug)


def _new_site_pin_settings(customer_name: str) -> dict[str, int]:
    customer_override = CUSTOMER_CREATE_OVERRIDES.get(customer_name.lower(), {})
    if "new_site_pin_total_length" in customer_override:
        return {"total_length": int(customer_override["new_site_pin_total_length"])}
    return {"suffix_width": int(customer_override.get("new_site_pin_suffix", DEFAULT_NEW_SITE_PIN_SUFFIX))}


def _next_four_digit_teid(current_max_teid: str) -> str:
    next_teid = int(current_max_teid) + 1
    if next_teid > 9999:
        raise ValueError("Cannot assign a new TEID because the 4-digit TEID limit of 9999 has been reached.")
    return str(next_teid).zfill(4)


def _review_rows(request_rows: list[InputRowRequest], *, debug: bool) -> dict[str, Any]:
    request_row_dicts = _request_rows_to_dicts(request_rows)
    parsed_rows = parse_input_records(request_row_dicts)
    site_cache: dict[str, list[str]] = {}
    run_new_site_teids: dict[str, dict[str, str]] = {}
    run_next_new_teid: dict[str, int] = {}
    results: list[dict[str, Any]] = []
    summary = {"total": len(parsed_rows), "Reviewed": 0, "Failed": 0, "Error": 0}

    def assign_run_new_site_teid(customer_name: str, site_name: str, teid_resolution: dict[str, Any]) -> str:
        site_key = " ".join(str(site_name).strip().lower().split())
        customer_site_teids = run_new_site_teids.setdefault(customer_name, {})
        if site_key in customer_site_teids:
            return customer_site_teids[site_key]

        current_max_teid = normalize_teid(teid_resolution.get("currentMaxTeid"))
        if not current_max_teid:
            raise ValueError("API 2 did not return currentMaxTeid for a new site review.")

        next_teid = max(run_next_new_teid.get(customer_name, 0), int(current_max_teid) + 1)
        if next_teid > 9999:
            raise ValueError("Cannot assign a new TEID because the 4-digit TEID limit of 9999 has been reached.")
        assigned_teid = str(next_teid).zfill(4)
        customer_site_teids[site_key] = assigned_teid
        run_next_new_teid[customer_name] = next_teid + 1
        return assigned_teid

    for input_row, row in zip(request_row_dicts, parsed_rows):
        notes = list(row.notes)
        trace_logs: list[dict[str, Any]] = []
        corrected_bod = ""
        corrected_site_name = row.site_name
        resolved_site_id = normalize_teid(row.site_id)
        match_score: float | None = None
        teid_resolution: dict[str, Any] | None = None
        suggested_connect_payload: dict[str, Any] = {}
        suggested_commit_request: dict[str, Any] = {}
        status = "Reviewed"

        if row.validation_status == "Error":
            notes.append(f"Missing/invalid fields: {', '.join(row.error_fields)}")
            status = "Error"
            summary["Error"] += 1
        else:
            customer_context = resolve_customer_context(row.bod, row.customer_name)
            if customer_context is None:
                notes.append("Unknown BOD or customer mapping.")
                status = "Failed"
                summary["Failed"] += 1
            else:
                corrected_bod = customer_context["customer_name"]
                trace_logs.append(
                    {
                        "stage": "customer_context",
                        "message": "Resolved customer context",
                        "row_number": row.row_number,
                        "details": {
                            "customer_name": corrected_bod,
                            "fk_customer": customer_context.get("fk_customer"),
                        },
                    }
                )
                candidate_sites = site_cache.setdefault(corrected_bod, app.state.client.get_sites_for_customer(corrected_bod))
                trace_logs.append(
                    {
                        "stage": "addresses",
                        "message": "Fetched requester site list",
                        "row_number": row.row_number,
                        "details": {
                            "customer_name": corrected_bod,
                            "total_count": len(candidate_sites),
                        },
                    }
                )

                manual_site_name = row.manual_site_name.strip()
                if manual_site_name:
                    notes.append("Using manually selected canonical site string for review.")

                if not resolved_site_id:
                    site_resolution = resolve_blank_site_id_path(row, corrected_bod, candidate_sites, client=app.state.client)
                    corrected_site_name = str(site_resolution["matched_site_name"])
                    match_score = site_resolution["match_score"]
                    teid_resolution = dict(site_resolution["teid_resolution"])
                    resolved_site_id = str(site_resolution["resolved_teid"])
                    notes.extend(str(note) for note in site_resolution["notes"])
                    cached_run_teid = run_new_site_teids.get(corrected_bod, {}).get(" ".join(corrected_site_name.strip().lower().split()))
                    if cached_run_teid:
                        resolved_site_id = cached_run_teid
                    elif not teid_resolution.get("siteExists"):
                        resolved_site_id = assign_run_new_site_teid(corrected_bod, corrected_site_name, teid_resolution)
                    if site_resolution["strategy"] == "manual":
                        trace_logs.append(
                            {
                                "stage": "site_match",
                                "message": "Using manual site override",
                                "row_number": row.row_number,
                                "details": {"matched_site_name": corrected_site_name},
                            }
                        )
                    elif site_resolution["strategy"] == "existing":
                        trace_logs.append(
                            {
                                "stage": "site_match",
                                "message": "Selected top-ranked existing-site candidate for review",
                                "row_number": row.row_number,
                                "details": {"matched_site_name": corrected_site_name, "score": match_score},
                            }
                        )
                    else:
                        trace_logs.append(
                            {
                                "stage": "site_match",
                                "message": "Kept original site string for new-site review",
                                "row_number": row.row_number,
                                "details": {"matched_site_name": corrected_site_name},
                            }
                        )
                    trace_logs.append(
                        {
                            "stage": "teid_resolution",
                            "message": "Resolved TEID state for review",
                            "row_number": row.row_number,
                            "details": teid_resolution,
                        }
                    )
                elif corrected_site_name:
                    if manual_site_name:
                        corrected_site_name = manual_site_name
                        trace_logs.append(
                            {
                                "stage": "site_match",
                                "message": "Using manual site override",
                                "row_number": row.row_number,
                                "details": {"matched_site_name": corrected_site_name},
                            }
                        )
                    else:
                        match = best_site_match(row.site_name, candidate_sites)
                        corrected_site_name = match.matched_site_name or corrected_site_name
                        match_score = match.score
                        trace_logs.append(
                            {
                                "stage": "site_match",
                                "message": "Calculated site match score",
                                "row_number": row.row_number,
                                "details": {"matched_site_name": corrected_site_name, "score": match_score},
                            }
                        )
                        if match.matched_site_name is None:
                            notes.append("Could not resolve a candidate site name from API 3 results.")
                            status = "Failed"
                            summary["Failed"] += 1
                        elif match.score < SITE_MATCH_THRESHOLD or requires_explicit_site_confirmation(row.site_name, corrected_site_name):
                            notes.append("Manual site selection is required before processing can continue.")
                            status = "Manual Selection Required"
                            summary["Failed"] += 1

                    if status == "Reviewed":
                        teid_resolution = app.state.client.resolve_teid(corrected_bod, corrected_site_name)
                        trace_logs.append(
                            {
                                "stage": "teid_resolution",
                                "message": "Resolved TEID state for review",
                                "row_number": row.row_number,
                                "details": teid_resolution,
                            }
                        )
                if row.contact_status == "Add" and corrected_site_name and teid_resolution is not None:
                    effective_teid = resolved_site_id
                    if not effective_teid and not teid_resolution.get("siteExists"):
                        current_max_teid = normalize_teid(teid_resolution.get("currentMaxTeid"))
                        if current_max_teid:
                            effective_teid = _next_four_digit_teid(current_max_teid)
                    if effective_teid:
                        resolved_site_id = effective_teid
                        pin_context = app.state.client.get_pin_context(corrected_bod, effective_teid)
                        pin_context["siteName"] = corrected_site_name
                        pin_context["customerName"] = corrected_bod
                        if is_missing_fk_value(pin_context.get("fK_Customer")) and customer_context.get("fk_customer"):
                            pin_context["fK_Customer"] = customer_context["fk_customer"]
                        generated_pin = (
                            next_pin(pin_context.get("maxPinCode"), effective_teid, **_new_site_pin_settings(corrected_bod))
                            if pin_context.get("maxPinCode")
                            else next_new_site_pin(effective_teid, **_new_site_pin_settings(corrected_bod))
                        )
                        suggested_connect_payload = build_create_payload(row, pin_context, generated_pin)
                        commit_site_name = corrected_site_name
                        commit_site_id = effective_teid
                        if not row.site_id and not teid_resolution.get("siteExists"):
                            commit_site_name = row.site_name
                            commit_site_id = ""
                        suggested_commit_request = {
                            "rows": [
                                {
                                    "BOD": row.bod,
                                    "First Name": row.first_name,
                                    "Last Name": row.last_name,
                                    "SEID": row.seid,
                                    "Site Name": commit_site_name,
                                    "Site ID": commit_site_id,
                                    "Contact Status": row.contact_status,
                                    "Manual Site Name": "",
                                }
                            ],
                            "created_by": "QA OPI Operator",
                            "write_output": False,
                            "debug": True,
                        }

                if status == "Reviewed":
                    summary["Reviewed"] += 1

        results.append(
            {
                "input": input_row,
                "corrected_data": {
                    "corrected_bod": corrected_bod,
                    "corrected_site_name": corrected_site_name,
                    "resolved_site_id": resolved_site_id,
                    "match_score": match_score,
                },
                "status": status,
                "notes": notes,
                "suggested_connect_payload": suggested_connect_payload if status == "Reviewed" else {},
                "suggested_commit_request": suggested_commit_request if status == "Reviewed" else {},
                "api_trace": {"logs": trace_logs} if debug else {},
            }
        )

    return {
        "summary": _review_status(summary),
        "results": results,
    }


@app.on_event("startup")
def startup() -> None:
    registry.initialize_database(DB_PATH)
    app.state.client = ConnectQAClient()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process", include_in_schema=False)
async def process(
    file: UploadFile | None = File(default=None),
    rows_json: str | None = Form(default=None),
    created_by: str = Form(default="QA OPI Operator"),
    write_output: bool = Form(default=True),
) -> dict:
    if file is None and not rows_json:
        raise HTTPException(status_code=400, detail="Provide either an input file or rows_json.")

    try:
        if file is not None:
            rows = parse_input_bytes(file.filename, await file.read())
            source_name = file.filename
        else:
            rows = parse_input_records(json.loads(rows_json or "[]"))
            source_name = "manual_rows.json"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = process_rows(
        rows,
        client=app.state.client,
        created_by=created_by,
        db_path=DB_PATH,
        source_name=source_name,
        write_output=write_output,
    )
    return result.to_dict()


@app.post("/process/rows", include_in_schema=False)
async def process_rows_json(request: ProcessRowsRequest) -> dict[str, Any]:
    try:
        return _run_commit_request(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/process/commit")
async def process_commit_json(request: ProcessRowsRequest) -> dict[str, Any]:
    try:
        return _run_commit_request(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/process/review")
async def process_review_json(request: ProcessRowsRequest) -> dict[str, Any]:
    try:
        return _review_rows(request.rows, debug=request.debug)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
