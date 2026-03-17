"""Streamlit UI for the IRS PIN mock workflow."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mock_irs_pin import database
from mock_irs_pin.config import DB_PATH
from mock_irs_pin.models import ParsedRow
from mock_irs_pin.parser import parse_input_bytes
from mock_irs_pin.processor import process_rows
from mock_irs_pin.services import MockInternalAPI


def ensure_state() -> None:
    st.session_state.setdefault("manual_rows", [])
    st.session_state.setdefault("parsed_rows", [])
    st.session_state.setdefault("run_result", None)
    st.session_state.setdefault("show_developer_panel", False)


def load_bod_options() -> list[str]:
    if not DB_PATH.exists():
        database.initialize_database(DB_PATH)
    with database.get_connection(DB_PATH) as connection:
        rows = connection.execute("SELECT bod_code FROM bod_lookup ORDER BY bod_code").fetchall()
    return [row[0] for row in rows]


def row_to_preview_dict(row: ParsedRow) -> dict:
    payload = row.to_dict()
    payload["notes"] = " | ".join(payload["notes"])
    payload["error_fields"] = ", ".join(payload["error_fields"])
    return payload


def filter_rows(rows: list[ParsedRow], mode: str) -> list[ParsedRow]:
    if mode == "Both":
        return rows
    if mode == "Add only":
        return [row for row in rows if row.contact_status == "Add"]
    return [row for row in rows if row.contact_status == "Deactivate"]


def build_manual_row(
    *,
    bod: str,
    first_name: str,
    last_name: str,
    seid: str,
    site_name: str,
    site_id: str,
    contact_status: str,
    row_number: int,
) -> ParsedRow:
    notes: list[str] = []
    error_fields: list[str] = []
    if not bod:
        error_fields.append("bod")
    if not first_name:
        error_fields.append("first_name")
    if not last_name:
        error_fields.append("last_name")
    if not seid:
        error_fields.append("seid")
    if not site_name:
        error_fields.append("site_name")
    if not site_id:
        notes.append("Site ID blank; mock API 2 will resolve TEID after site matching.")

    validation_status = "Valid"
    if error_fields:
        validation_status = "Error"
    elif not site_id:
        validation_status = "Warning"

    return ParsedRow(
        row_number=row_number,
        bod=bod.strip(),
        last_name=last_name.strip(),
        first_name=first_name.strip(),
        seid=seid.strip(),
        site_id=site_id.strip(),
        site_name=site_name.strip(),
        user_pin="",
        contact_status=contact_status,
        validation_status=validation_status,
        notes=notes,
        error_fields=error_fields,
        duplicate_in_batch=False,
    )


def render_manual_entry(bod_options: list[str]) -> list[ParsedRow]:
    st.subheader("Manual Entry")
    with st.form("manual_entry_form", clear_on_submit=True):
        bod = st.selectbox("BOD", bod_options, index=0 if bod_options else None)
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("First Name")
            seid = st.text_input("SEID")
            site_id = st.text_input("Site ID (optional)")
        with col2:
            last_name = st.text_input("Last Name")
            site_name = st.text_input("Site Name")
            contact_status = st.selectbox("Contact Status", ["Add", "Deactivate"])
        submitted = st.form_submit_button("Add Row")

    if submitted:
        row_number = len(st.session_state.manual_rows) + 2
        st.session_state.manual_rows.append(
            build_manual_row(
                bod=bod,
                first_name=first_name,
                last_name=last_name,
                seid=seid,
                site_name=site_name,
                site_id=site_id,
                contact_status=contact_status,
                row_number=row_number,
            )
        )

    rows = list(st.session_state.manual_rows)
    if rows:
        preview_df = pd.DataFrame([row_to_preview_dict(row) for row in rows])
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Clear Manual Rows", type="secondary"):
                st.session_state.manual_rows = []
                st.rerun()
        with col_b:
            st.caption(f"{len(rows)} manual row(s) queued")
    return rows


def render_upload_entry() -> list[ParsedRow]:
    st.subheader("Upload CSV or Excel")
    uploaded = st.file_uploader("Attach a CSV/XLSX/XLS file", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        return []

    rows = parse_input_bytes(uploaded.name, uploaded.getvalue())
    preview_df = pd.DataFrame([row_to_preview_dict(row) for row in rows])
    st.dataframe(preview_df, use_container_width=True, hide_index=True)
    st.caption(
        "Warning means the row is still processable, but it needs an extra step such as TEID resolution from the site name."
    )
    return rows


def render_results(run_result) -> None:
    st.subheader("Processed Output")
    result_df = pd.DataFrame([row.to_dict() for row in run_result.row_results])
    if not result_df.empty:
        result_df["notes"] = result_df["notes"].apply(lambda value: " | ".join(value))
        st.dataframe(result_df, use_container_width=True, hide_index=True)
    else:
        st.info("No processed rows yet.")

    st.subheader("Connect Payloads")
    if run_result.payloads:
        payload_options = [
            f"{index + 1}. {payload.get('firstName', payload.get('code', 'payload'))}"
            for index, payload in enumerate(run_result.payloads)
        ]
        selected_index = st.selectbox("View payload", range(len(payload_options)), format_func=lambda idx: payload_options[idx])
        st.json(run_result.payloads[selected_index], expanded=True)
        st.download_button(
            "Download payload JSON",
            data=json.dumps(run_result.payloads, indent=2),
            file_name=f"payloads_{run_result.batch_id}.json",
            mime="application/json",
        )
        if run_result.output_path:
            st.caption(f"Saved to {run_result.output_path}")
    else:
        st.warning("No payloads were produced for this run.")


def render_developer_panel(run_result) -> None:
    if not st.session_state.get("show_developer_panel") or run_result is None:
        return
    with st.expander("Developer Diagnostics", expanded=False):
        st.caption("Internal stage-by-stage logs and structured run output.")
        log_df = pd.DataFrame(run_result.logs)
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        st.json(run_result.to_dict(), expanded=False)


def main() -> None:
    st.set_page_config(page_title="IRS PIN Mock Tool", layout="wide")
    ensure_state()

    st.title("IRS PIN Mock Tool")
    st.caption("Streamlit shell for the SQLite-backed IRS PIN mock workflow.")

    bod_options = load_bod_options()

    with st.sidebar:
        st.header("Controls")
        input_mode = st.radio("Input mode", ["Attach CSV/XLSX", "Enter Manually"])
        process_mode = st.selectbox("Rows to process", ["Both", "Add only", "Deactivate only"])
        created_by = st.text_input(
            "Operator",
            value="Mock OPI Operator",
            help="The person processing the batch. This is stored in the mock registry as CREATED_BY.",
        )
        reset_db = st.checkbox("Reset mock database before processing", value=False)
        st.caption("Operator means the user or team member running this batch.")
        st.caption("Warning means the row is valid, but some value still has to be resolved automatically.")
        st.markdown("<div style='height: 18rem;'></div>", unsafe_allow_html=True)
        developer_label = (
            "Hide Developer"
            if st.session_state.get("show_developer_panel")
            else "For Developer"
        )
        if st.button(developer_label, use_container_width=True):
            st.session_state.show_developer_panel = not st.session_state.get(
                "show_developer_panel"
            )
            st.rerun()

    rows = render_upload_entry() if input_mode == "Attach CSV/XLSX" else render_manual_entry(bod_options)
    st.session_state.parsed_rows = rows

    filtered_rows = filter_rows(rows, process_mode)
    st.divider()
    st.subheader("Process")
    st.caption(f"{len(filtered_rows)} row(s) selected for processing")

    if st.button("Process Data", type="primary", disabled=not filtered_rows):
        if reset_db or not DB_PATH.exists():
            database.initialize_database(DB_PATH)
        st.session_state.run_result = process_rows(
            filtered_rows,
            created_by=created_by,
            db_path=DB_PATH,
            write_output=True,
        )

    if st.session_state.run_result is not None:
        render_results(st.session_state.run_result)
        render_developer_panel(st.session_state.run_result)


if __name__ == "__main__":
    main()
