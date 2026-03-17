"""Streamlit frontend layered on top of the FastAPI QA endpoint."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_irs_pin.config import BOD_LOOKUP
from qa_irs_pin.models import ParsedRow
from qa_irs_pin.parser import parse_input_bytes, parse_input_records

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def ensure_state() -> None:
    st.session_state.setdefault("manual_request", None)
    st.session_state.setdefault("manual_review_result", None)
    st.session_state.setdefault("manual_commit_result", None)
    st.session_state.setdefault("bulk_run_result", None)


def row_to_preview_dict(row: ParsedRow) -> dict:
    payload = row.to_dict()
    payload["notes"] = " | ".join(payload["notes"])
    payload["error_fields"] = ", ".join(payload["error_fields"])
    return payload


def render_manual_entry() -> None:
    bod_options = sorted(BOD_LOOKUP.keys())
    st.subheader("Manual Entry")
    with st.form("manual_entry"):
        bod = st.selectbox("BOD", bod_options, index=bod_options.index("MARKYTECH") if "MARKYTECH" in bod_options else 0)
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name")
            seid = st.text_input("SEID")
            site_id = st.text_input("Site ID (optional)")
        with col2:
            last_name = st.text_input("Last Name")
            site_name = st.text_input("Site Name")
            contact_status = st.selectbox("Contact Status", ["Add", "Deactivate"])
        manual_site_name = st.text_input("Manual Site Name")
        submitted = st.form_submit_button("Review", type="primary")

    if submitted:
        request_row = {
            "BOD": bod,
            "First Name": first_name,
            "Last Name": last_name,
            "SEID": seid,
            "Site ID": site_id,
            "Site Name": site_name,
            "Contact Status": contact_status,
            "Manual Site Name": manual_site_name,
        }
        st.session_state.manual_request = request_row
        st.session_state.manual_commit_result = None
        try:
            st.session_state.manual_review_result = post_review_to_backend(request_row)
        except requests.RequestException as exc:
            st.session_state.manual_review_result = None
            st.error(str(exc))

    if st.session_state.manual_request:
        rows = parse_input_records([st.session_state.manual_request])
        st.dataframe(pd.DataFrame([row_to_preview_dict(row) for row in rows]), use_container_width=True, hide_index=True)
        if st.button("Clear Manual Row", type="secondary"):
            st.session_state.manual_request = None
            st.session_state.manual_review_result = None
            st.session_state.manual_commit_result = None
            st.rerun()


def render_upload_entry() -> tuple[list[ParsedRow], object | None]:
    st.subheader("Bulk Upload")
    st.caption("Legacy bulk processing path using /process for CSV/XLS/XLSX uploads.")
    uploaded = st.file_uploader("Attach a CSV/XLSX/XLS file", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        return [], None

    rows = parse_input_bytes(uploaded.name, uploaded.getvalue())
    st.dataframe(pd.DataFrame([row_to_preview_dict(row) for row in rows]), use_container_width=True, hide_index=True)
    return rows, uploaded


def post_review_to_backend(row: dict) -> dict:
    response = requests.post(
        f"{BACKEND_URL}/process/review",
        json={"rows": [row], "write_output": False, "debug": True},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def post_commit_to_backend(review_result: dict, fallback_row: dict) -> dict:
    result_row = ((review_result.get("results") or [{}])[0]) if review_result else {}
    request_payload = result_row.get("suggested_commit_request") or {
        "rows": [fallback_row],
        "write_output": False,
        "debug": False,
    }
    response = requests.post(
        f"{BACKEND_URL}/process/commit",
        json=request_payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def post_file_to_backend(uploaded_file) -> dict:
    response = requests.post(
        f"{BACKEND_URL}/process",
        data={"write_output": "true"},
        files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def render_manual_review(review_result: dict) -> None:
    st.subheader("Review")
    result_row = ((review_result.get("results") or [{}])[0]) if review_result else {}
    if not result_row:
        st.info("No review result returned.")
        return
    st.json(
        {
            "input": result_row.get("input", {}),
            "corrected_data": result_row.get("corrected_data", {}),
            "notes": result_row.get("notes", []),
        },
        expanded=True,
    )
    if result_row.get("api_trace"):
        st.caption("API Trace")
        st.json(result_row["api_trace"], expanded=False)
    if result_row.get("suggested_connect_payload"):
        st.caption("Suggested Payload")
        st.json(result_row["suggested_connect_payload"], expanded=False)


def render_manual_commit(commit_result: dict) -> None:
    st.subheader("Commit")
    result_row = ((commit_result.get("results") or [{}])[0]) if commit_result else {}
    if not result_row:
        st.info("No commit result returned.")
        return
    st.json(result_row.get("result", {}), expanded=True)
    if result_row.get("connect_payload"):
        st.caption("Posted Payload")
        st.json(result_row["connect_payload"], expanded=False)


def render_bulk_results(run_result: dict) -> None:
    st.subheader("Bulk Results")
    rows = run_result.get("row_results", [])
    if rows:
        result_df = pd.DataFrame(rows)
        result_df["notes"] = result_df["notes"].apply(lambda values: " | ".join(values))
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    st.subheader("Payloads")
    payloads = run_result.get("payloads", [])
    if payloads:
        st.json(payloads, expanded=False)
    else:
        st.info("No payloads were posted for this run.")
    st.json(run_result.get("summary", {}), expanded=True)
    if run_result.get("output_path"):
        st.caption(f"Saved batch output to {run_result['output_path']}")


def main() -> None:
    st.set_page_config(page_title="IRS PIN QA Tool", layout="wide")
    ensure_state()
    st.title("IRS PIN QA Tool")
    st.caption("Review and commit manual rows, or use the legacy bulk upload path for files.")

    with st.sidebar:
        input_mode = st.radio("Input mode", ["Enter Manually", "Attach CSV/XLSX"])

    uploaded_file = None
    if input_mode == "Attach CSV/XLSX":
        rows, uploaded_file = render_upload_entry()
    else:
        render_manual_entry()
        rows = parse_input_records([st.session_state.manual_request]) if st.session_state.manual_request else []

    st.divider()
    if input_mode == "Attach CSV/XLSX":
        st.caption(f"{len(rows)} row(s) ready for bulk processing")
        if st.button("Process Bulk Upload", type="primary", disabled=uploaded_file is None):
            try:
                st.session_state.bulk_run_result = post_file_to_backend(uploaded_file)
            except requests.RequestException as exc:
                st.error(str(exc))

        if st.session_state.bulk_run_result is not None:
            render_bulk_results(st.session_state.bulk_run_result)
    else:
        if st.session_state.manual_review_result is not None:
            render_manual_review(st.session_state.manual_review_result)

        can_commit = st.session_state.manual_review_result is not None and st.session_state.manual_request is not None
        if st.button("Commit", disabled=not can_commit):
            try:
                st.session_state.manual_commit_result = post_commit_to_backend(
                    st.session_state.manual_review_result,
                    st.session_state.manual_request,
                )
            except requests.RequestException as exc:
                st.error(str(exc))

        if st.session_state.manual_commit_result is not None:
            render_manual_commit(st.session_state.manual_commit_result)


if __name__ == "__main__":
    main()
