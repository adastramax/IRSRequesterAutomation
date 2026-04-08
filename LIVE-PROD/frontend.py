"""Streamlit frontend layered on top of the FastAPI QA endpoint."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_irs_pin.config import BOD_LOOKUP, DEV_USE_PASSWORD, DEV_USE_USERNAME
from qa_irs_pin.models import ParsedRow
from qa_irs_pin.parser import parse_input_bytes, parse_input_records

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEACT_SITE = "__DEACTIVATE_REQUESTER__"
DEV_USE_ENABLED = bool(DEV_USE_USERNAME and DEV_USE_PASSWORD)


def ensure_state() -> None:
    default_bod = "TAS" if "TAS" in BOD_LOOKUP else sorted(BOD_LOOKUP.keys())[0]
    defaults = {
        "page": "Add Requester",
        "add_request": None,
        "add_review": None,
        "add_commit": None,
        "add_active_workflow": "manual",
        "add_bod_input": default_bod,
        "add_first_name_input": "",
        "add_last_name_input": "",
        "add_seid_input": "",
        "add_site_name_input": "",
        "add_site_id_input": "",
        "add_manual_site_name_input": "",
        "add_reset_requested": False,
        "bulk_file_name": None,
        "bulk_file_bytes": None,
        "bulk_file_type": None,
        "bulk_preview_rows": [],
        "bulk_review_result": None,
        "bulk_result": None,
        "bulk_filter_notice": "",
        "bulk_uploader_version": 0,
        "deactivate_request": None,
        "deactivate_ready": None,
        "deactivate_commit": None,
        "deactivate_active_workflow": "manual",
        "deactivate_bod_input": default_bod,
        "deactivate_seid_input": "",
        "deactivate_site_name_input": "",
        "deactivate_site_id_input": "",
        "deactivate_bulk_file_name": None,
        "deactivate_bulk_file_bytes": None,
        "deactivate_bulk_file_type": None,
        "deactivate_bulk_preview_rows": [],
        "deactivate_bulk_review_result": None,
        "deactivate_bulk_result": None,
        "deactivate_bulk_filter_notice": "",
        "deactivate_bulk_uploader_version": 0,
        "deactivate_reset_requested": False,
        "dev_mode": "Enter Manually",
        "dev_request": None,
        "dev_review": None,
        "dev_commit": None,
        "dev_bulk_result": None,
        "dev_authenticated": False,
        "dev_username_input": "",
        "dev_password_input": "",
        "dev_login_error": "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background:#f7f8fc; color:#22324a; }
        [data-testid="stHeader"] { background:transparent; height:0rem; }
        [data-testid="stToolbar"] { display:none; }
        #MainMenu { visibility:hidden; }
        header { visibility:hidden; }
        [data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #e7ebf3; }
        [data-testid="stSidebar"] .block-container { padding-top:0.2rem; padding-left:0; padding-right:0; }
        .aa-brand,.aa-hero,.aa-card,.stForm,[data-testid="stExpander"]{background:#fff;border:1px solid #e7ebf3;border-radius:18px;box-shadow:0 10px 30px rgba(24,39,75,.05);}
        .aa-brand{padding:1.1rem 1.2rem 1rem;margin:0 0 1rem;border:none;border-bottom:1px solid #eef2f7;border-radius:0;box-shadow:none}
        .aa-brand-logo{position:relative;display:inline-block;margin:-.1rem 0 1rem .55rem}
        .aa-brand-mark{position:relative;display:inline-flex;align-items:flex-end;background:#d83b3b;color:#fff;padding:.78rem 1.08rem .5rem;border-radius:0 4px 4px 0;font-size:2.14rem;line-height:1;font-weight:900;letter-spacing:-.06em;text-transform:lowercase}
        .aa-brand-mark::before{content:"";position:absolute;top:0;left:-.9rem;border-top:1.26rem solid transparent;border-bottom:1.26rem solid transparent;border-right:.9rem solid #d83b3b}
        .aa-brand-badge{display:inline-flex;align-items:center;justify-content:center;background:#2f8f4e;color:#fff;border-radius:4px;padding:.24rem .44rem;font-size:.9rem;line-height:1;font-weight:800;letter-spacing:.08em;text-transform:uppercase;position:absolute;top:-.38rem;right:-1.62rem}
        .aa-brand p{margin:.1rem 0 0;color:#6d7a92;font-size:.96rem}
        .aa-nav-label{padding:0 1.2rem .55rem;color:#a7b1c1;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em}
        .aa-hero{padding:1.25rem 1.35rem;margin-bottom:1rem}.aa-hero small{color:#c53d3d;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.aa-hero h1{margin:.35rem 0 0;font-size:1.9rem;color:#22324a}.aa-hero p{margin:.45rem 0 0;color:#6d7a92;max-width:760px}
        .aa-title{font-size:1.05rem;font-weight:750;margin:1rem 0 .2rem;color:#22324a}.aa-copy{color:#6d7a92;font-size:.93rem;margin-bottom:.8rem}
        .aa-status{border-radius:16px;padding:1rem;margin:.8rem 0 1rem;border:1px solid #e7ebf3}.aa-status.success{background:#eef9f2;border-color:#cde8d5}.aa-status.warning{background:#fff8e4;border-color:#f1dfa0}.aa-status.error{background:#fdf1f1;border-color:#efcaca}.aa-status.info{background:#fbf1f1;border-color:#ecd3d3}
        .aa-badge{display:inline-block;border-radius:999px;padding:.35rem .7rem;font-size:.75rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;background:#fff}
        .aa-status h3{display:inline-block;margin:0 0 0 .6rem;font-size:1.05rem;color:#22324a}.aa-status p{margin:.7rem 0 0;color:#415069}.aa-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.65rem;margin-top:.8rem}.aa-item{background:rgba(255,255,255,.88);border:1px solid #e8edf5;border-radius:14px;padding:.75rem .85rem}.aa-item span{display:block;color:#6d7a92;font-size:.74rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em}.aa-item strong{display:block;margin-top:.2rem;font-size:.98rem;color:#22324a;word-break:break-word}
        .aa-metric{background:#fff;border:1px solid #e7ebf3;border-radius:16px;padding:1rem} .aa-metric span{display:block;color:#6d7a92;font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em} .aa-metric strong{display:block;margin-top:.45rem;font-size:1.95rem;color:#22324a}
        .aa-table-wrap{background:#ffffff;border:1px solid #e7ebf3;border-radius:16px;overflow:hidden;margin-top:.5rem}
        .aa-table{width:100%;border-collapse:collapse}
        .aa-table thead th{background:#fafbfe;color:#7b879c;font-size:.76rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:.9rem .85rem;text-align:left;border-bottom:1px solid #e7ebf3}
        .aa-table tbody td{background:#ffffff;color:#22324a;padding:.95rem .85rem;border-bottom:1px solid #eef2f7;vertical-align:top}
        .aa-table tbody tr:last-child td{border-bottom:none}
        .aa-table .aa-status-pill{display:inline-block;padding:.28rem .65rem;border-radius:999px;font-size:.78rem;font-weight:700}
        .aa-table .aa-status-created,.aa-table .aa-status-deactivated{background:#eaf8ef;color:#2b8a57}
        .aa-table .aa-status-active{background:#eaf8ef;color:#2b8a57}
        .aa-table .aa-status-failed{background:#fdf0f0;color:#c84747}
        .aa-table .aa-status-warning,.aa-table .aa-status-manual-selection-required,.aa-table .aa-status-already-exists{background:#fff8e4;color:#a97d10}
        .stForm{padding:1rem 1rem .5rem}.stButton>button,.stDownloadButton>button{border-radius:12px;font-weight:700;min-height:2.7rem}
        .stButton > button[kind="primary"] {
            background:#fb4a4a !important;
            color:#ffffff !important;
            border:1px solid #fb4a4a !important;
        }
        .stButton > button[kind="primary"]:hover {
            background:#ef4040 !important;
            color:#ffffff !important;
            border-color:#ef4040 !important;
        }
        .stButton > button[kind="secondary"],
        .stDownloadButton > button {
            background:#b8b246 !important;
            color:#ffffff !important;
            border:1px solid #b8b246 !important;
        }
        .stButton > button[kind="secondary"]:hover,
        .stDownloadButton > button:hover {
            background:#a8a23a !important;
            color:#ffffff !important;
            border-color:#a8a23a !important;
        }
        .stButton > button:disabled,
        .stDownloadButton > button:disabled {
            background:#eef1f5 !important;
            color:#8b98aa !important;
            border:1px solid #dde4ee !important;
            opacity:1 !important;
        }
        label[data-testid="stWidgetLabel"] p { color:#22324a !important; font-weight:600 !important; }
        .stTextInput input,.stTextArea textarea { background:#ffffff !important; color:#22324a !important; border:1px solid #d9e0ea !important; }
        .stTextInput input::placeholder,.stTextArea textarea::placeholder { color:#93a2b5 !important; }
        div[data-baseweb="select"] > div { background:#ffffff !important; color:#22324a !important; border:1px solid #d9e0ea !important; }
        div[data-baseweb="select"] * { color:#22324a !important; }
        div[data-baseweb="popover"] {
            background:#ffffff !important;
            border:none !important;
            border-radius:14px !important;
            box-shadow:none !important;
            outline:none !important;
        }
        div[data-baseweb="popover"] > div {
            background:#ffffff !important;
            border:1px solid #e7ebf3 !important;
            border-radius:14px !important;
            box-shadow:0 16px 36px rgba(24,39,75,.12) !important;
            outline:none !important;
        }
        div[data-baseweb="popover"] div,
        div[data-baseweb="popover"] ul,
        div[data-baseweb="popover"] li {
            background:#ffffff !important;
        }
        div[data-baseweb="popover"] [role="listbox"] {
            background:#ffffff !important;
            color:#22324a !important;
            border-radius:14px !important;
            padding:.35rem !important;
            box-shadow:none !important;
            outline:none !important;
            scrollbar-color:#d9e0ea #ffffff !important;
            scrollbar-width:thin !important;
        }
        div[data-baseweb="popover"] [role="listbox"]::-webkit-scrollbar {
            width:12px !important;
            background:#ffffff !important;
        }
        div[data-baseweb="popover"] [role="listbox"]::-webkit-scrollbar-track {
            background:#ffffff !important;
            border-radius:12px !important;
        }
        div[data-baseweb="popover"] [role="listbox"]::-webkit-scrollbar-thumb {
            background:#d9e0ea !important;
            border:3px solid #ffffff !important;
            border-radius:12px !important;
        }
        div[data-baseweb="popover"] [role="option"] {
            background:#ffffff !important;
            color:#22324a !important;
            border-radius:8px !important;
            box-shadow:none !important;
            outline:none !important;
        }
        div[data-baseweb="popover"] [role="option"] * {
            color:#22324a !important;
        }
        div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
            background:#fbebeb !important;
            color:#c53d3d !important;
        }
        div[data-baseweb="popover"] [role="option"][aria-selected="true"] * {
            color:#c53d3d !important;
            font-weight:700 !important;
        }
        div[data-baseweb="popover"] [role="option"]:hover {
            background:#f8f9fc !important;
            color:#22324a !important;
        }
        [data-testid="stRadio"] label,
        [data-testid="stRadio"] p,
        [data-testid="stRadio"] span {
            color:#22324a !important;
            opacity:1 !important;
        }
        [data-testid="stRadio"] [role="radiogroup"] label {
            background:transparent !important;
        }
        [data-testid="stAlertContainer"] * {
            color:#22324a !important;
        }
        [data-testid="stAlertContainer"] [data-baseweb="notification"] {
            background:#fff8cf !important;
            border:1px solid #f0e39a !important;
        }
        [data-testid="stSidebar"] .stButton {
            margin:0 !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            background:#ffffff !important;
            color:#22324a !important;
            border:none !important;
            border-left:4px solid transparent !important;
            border-radius:0 !important;
            box-shadow:none !important;
            justify-content:flex-start !important;
            padding:0.95rem 1.2rem !important;
            width:100%;
            min-height:3.2rem;
            font-weight:600 !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background:#fbebeb !important;
            color:#c53d3d !important;
            border-left:4px solid #d94848 !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background:#f8f9fc !important;
            color:#22324a !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
            background:#f8e5e5 !important;
            color:#c53d3d !important;
            border-left:4px solid #d94848 !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            background:#ffffff !important;
            border:1px dashed #d9e0ea !important;
            color:#22324a !important;
        }
        [data-testid="stFileUploaderDropzone"] * {
            color:#22324a !important;
        }
        [data-testid="stFileUploaderDropzone"] button {
            background:#f8f8fb !important;
            color:#c53d3d !important;
            border:1px solid #eadede !important;
        }
        [data-testid="stExpander"] summary {
            background:#fbfbfd !important;
            color:#22324a !important;
            border-radius:12px !important;
        }
        [data-testid="stExpander"] summary * {
            color:#22324a !important;
        }
        [data-testid="stExpander"] details {
            background:#ffffff !important;
        }
        .aa-login-title{margin:0 0 .55rem;font-size:2rem;line-height:1.15;color:#172554;font-weight:800}
        .aa-login-copy{margin:0 0 1.25rem;color:#6d7a92;font-size:.98rem}
        .aa-inline-logo{display:inline-flex;align-items:flex-end;gap:.2rem;vertical-align:middle}
        .aa-inline-logo .aa-brand-mark{font-size:1.6rem;padding:.58rem .88rem .34rem}
        .aa-inline-logo .aa-brand-mark::before{left:-.7rem;border-top:1rem solid transparent;border-bottom:1rem solid transparent;border-right:.7rem solid #d83b3b}
        .aa-inline-logo .aa-brand-badge{position:relative;top:-.55rem;right:auto;margin-left:.12rem;font-size:.72rem;padding:.18rem .34rem}
        .stTextInput div[data-baseweb="input"] button,
        .stTextInput div[data-baseweb="base-input"] button {
            background:#fb4a4a !important;
            color:#ffffff !important;
            border:none !important;
            box-shadow:none !important;
        }
        .stTextInput div[data-baseweb="input"] button:hover,
        .stTextInput div[data-baseweb="base-input"] button:hover {
            background:#ef4040 !important;
            color:#ffffff !important;
        }
        .stTextInput div[data-baseweb="input"] button svg,
        .stTextInput div[data-baseweb="base-input"] button svg {
            fill:#ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand() -> None:
    st.markdown(
        """
        <div class='aa-brand'>
            <div class='aa-brand-logo'>
                <span class='aa-brand-mark'>adastra</span>
                <span class='aa-brand-badge'>LIVE</span>
            </div>
            <p>IRS PIN operations workspace.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_inline_logo() -> str:
    return (
        "<span class='aa-inline-logo'>"
        "<span class='aa-brand-mark'>adastra</span>"
        "<span class='aa-brand-badge'>LIVE</span>"
        "</span>"
    )


def lock_dev_use() -> None:
    st.session_state.dev_authenticated = False
    st.session_state.dev_username_input = ""
    st.session_state.dev_password_input = ""
    st.session_state.dev_login_error = ""


def hero(title: str, copy: str, eyebrow: str = "Operations") -> None:
    st.markdown(f"<div class='aa-hero'><small>{html.escape(eyebrow)}</small><h1>{html.escape(title)}</h1><p>{html.escape(copy)}</p></div>", unsafe_allow_html=True)


def heading(title: str, copy: str) -> None:
    st.markdown(f"<div class='aa-title'>{html.escape(title)}</div><div class='aa-copy'>{html.escape(copy)}</div>", unsafe_allow_html=True)


def status_card(title: str, message: str, tone: str, fields: list[tuple[str, Any]] | None = None, next_step: str | None = None) -> None:
    grid = "".join(
        f"<div class='aa-item'><span>{html.escape(str(k))}</span><strong>{html.escape(str(v))}</strong></div>"
        for k, v in (fields or [])
        if v not in (None, "", [])
    )
    extra = f"<p><strong>Suggested next action:</strong> {html.escape(next_step)}</p>" if next_step else ""
    st.markdown(
        f"<div class='aa-status {tone}'><span class='aa-badge'>{html.escape(title)}</span><h3>{html.escape(title)}</h3><p>{html.escape(message)}</p>{extra}<div class='aa-grid'>{grid}</div></div>",
        unsafe_allow_html=True,
    )


def metric_cards(cards: list[tuple[str, Any, str]]) -> None:
    cols = st.columns(len(cards))
    for col, (label, value, note) in zip(cols, cards):
        with col:
            st.markdown(f"<div class='aa-metric'><span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong><div class='aa-copy'>{html.escape(note)}</div></div>", unsafe_allow_html=True)


def first_result(payload: dict[str, Any] | None) -> dict[str, Any]:
    results = (payload or {}).get("results") or []
    return results[0] if results else {}


def last_note(notes: list[str] | None) -> str:
    notes = [str(x).strip() for x in (notes or []) if str(x).strip()]
    return notes[-1] if notes else ""


def clean_site(value: Any) -> str:
    site = str(value or "").strip()
    return "" if site == DEACT_SITE else site


def requester_name(row: dict[str, Any]) -> str:
    return f"{row.get('First Name', '').strip()} {row.get('Last Name', '').strip()}".strip()


def safe_deactivate_name(first_name: Any, last_name: Any, fallback: str = "") -> str:
    sentinels = {"__DEACTIVATE__", "__REQUESTER__"}
    first = str(first_name or "").strip()
    last = str(last_name or "").strip()
    parts = [part for part in (first, last) if part and part not in sentinels]
    if parts:
        return " ".join(parts)
    return fallback


def row_to_preview_dict(row: ParsedRow) -> dict[str, Any]:
    payload = row.to_dict()
    payload["notes"] = " | ".join(payload["notes"])
    payload["error_fields"] = ", ".join(payload["error_fields"])
    return payload


def parsed_row_to_request_dict(row: ParsedRow) -> dict[str, Any]:
    return {
        "BOD": row.bod,
        "Customer Name": row.customer_name,
        "First Name": row.first_name,
        "Last Name": row.last_name,
        "SEID": row.seid,
        "Site Name": row.site_name,
        "Site ID": row.site_id,
        "Current User PIN": row.user_pin,
        "Employee ID": row.employee_id,
        "New Site:Site ID": row.new_site_id,
        "New Site": row.new_site_name,
        "Contact Status": row.contact_status,
        "Manual Site Name": row.manual_site_name,
    }


def parsed_row_to_deactivate_request_dict(row: ParsedRow) -> dict[str, Any]:
    bod_value = row.bod.strip()
    customer_name = row.customer_name.strip()
    if bod_value and bod_value not in BOD_LOOKUP and not customer_name:
        customer_name = bod_value
        bod_value = ""
    return {
        "BOD": bod_value,
        "Customer Name": customer_name,
        "First Name": row.first_name,
        "Last Name": row.last_name,
        "SEID": row.seid,
        "Site Name": row.site_name,
        "Site ID": row.site_id,
        "Contact Status": "Deactivate",
        "Manual Site Name": row.manual_site_name,
    }


def add_row(bod: str, first: str, last: str, seid: str, site_name: str, site_id: str, manual_site_name: str) -> dict[str, str]:
    return {"BOD": bod, "First Name": first.strip(), "Last Name": last.strip(), "SEID": seid.strip(), "Site Name": site_name.strip(), "Site ID": site_id.strip(), "Contact Status": "Add", "Manual Site Name": manual_site_name.strip()}


def deactivate_row(bod: str, seid: str, site_name: str, site_id: str, first_name: str = "", last_name: str = "") -> dict[str, str]:
    return {"BOD": bod, "First Name": first_name.strip(), "Last Name": last_name.strip(), "SEID": seid.strip(), "Site Name": site_name.strip() or DEACT_SITE, "Site ID": site_id.strip(), "Contact Status": "Deactivate", "Manual Site Name": ""}


def deactivate_bulk_row(raw_row: ParsedRow) -> dict[str, str]:
    return deactivate_row(raw_row.bod, raw_row.seid, raw_row.site_name, raw_row.site_id, raw_row.first_name, raw_row.last_name)


def filter_rows_for_action(rows: list[ParsedRow], action: str) -> tuple[list[ParsedRow], str]:
    allowed_actions = {action}
    action_label = "Add" if action == "Add" else "Deactivate"
    if action == "Add":
        allowed_actions.add("Modify-Function Change")
        action_label = "Add / Modify"

    filtered_rows = [row for row in rows if row.contact_status in allowed_actions]
    skipped_rows = [row for row in rows if row.contact_status not in allowed_actions]
    if not skipped_rows:
        return filtered_rows, ""

    skipped_actions = sorted({row.contact_status or "Blank" for row in skipped_rows})
    return filtered_rows, (
        f"Using only {action_label} rows from the uploaded file. "
        f"Skipped {len(skipped_rows)} row(s) with action(s): {', '.join(skipped_actions)}."
    )


def _raise_for_status_with_detail(response: requests.Response) -> None:
    if response.ok:
        return
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if isinstance(payload, dict):
        detail = str(payload.get("detail") or "").strip()
    if detail:
        raise requests.HTTPError(f"{response.status_code} {response.reason}: {detail}", response=response)
    response.raise_for_status()


def post_review(row: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(f"{BACKEND_URL}/process/review", json={"rows": [row], "write_output": False, "debug": True}, timeout=300)
    _raise_for_status_with_detail(r)
    return r.json()


def post_bulk_review(rows: list[dict[str, Any]]) -> dict[str, Any]:
    r = requests.post(f"{BACKEND_URL}/process/review", json={"rows": rows, "write_output": False, "debug": True}, timeout=300)
    _raise_for_status_with_detail(r)
    return r.json()


def post_bulk_review_file(uploaded_file) -> dict[str, Any]:
    r = requests.post(
        f"{BACKEND_URL}/process/review-file",
        data={"debug": "true"},
        files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")},
        timeout=300,
    )
    _raise_for_status_with_detail(r)
    return r.json()


def post_commit(payload: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(f"{BACKEND_URL}/process/commit", json=payload, timeout=300)
    _raise_for_status_with_detail(r)
    return r.json()


def commit_from_review(review: dict[str, Any], fallback_row: dict[str, Any]) -> dict[str, Any]:
    row = first_result(review)
    payload = row.get("suggested_commit_request") or {"rows": [fallback_row], "write_output": False, "debug": False}
    return post_commit(payload)


def post_file(uploaded_file) -> dict[str, Any]:
    r = requests.post(f"{BACKEND_URL}/process", data={"write_output": "true"}, files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}, timeout=300)
    _raise_for_status_with_detail(r)
    return r.json()


def processed_result_columns() -> list[str]:
    return ["BOD", "SITE Name", "TEID", "SEID", "NAME", "STATUS", "MESSAGE", "GENERATED PIN"]


def deactivate_result_columns() -> list[str]:
    return ["BOD", "SITE Name", "TEID", "SEID", "NAME", "STATUS", "MESSAGE"]


def processed_result_row(*, bod: Any, site_name: Any, teid: Any, seid: Any, name: Any, status: Any, message: Any, generated_pin: Any) -> dict[str, Any]:
    return {
        "BOD": bod or "",
        "SITE Name": clean_site(site_name),
        "TEID": teid or "",
        "SEID": seid or "",
        "NAME": name or "",
        "STATUS": status or "",
        "MESSAGE": message or "",
        "GENERATED PIN": generated_pin or "",
    }


def commit_result_pin(result: dict[str, Any], connect_payload: dict[str, Any] | None = None) -> str:
    connect_payload = connect_payload or {}
    for value in (
        result.get("pin"),
        result.get("generated_pin"),
        connect_payload.get("pinCodeString"),
        connect_payload.get("PinCodeString"),
        connect_payload.get("pinCode"),
        connect_payload.get("PinCode"),
    ):
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""


def commit_result_site_and_teid(input_row: dict[str, Any], corrected: dict[str, Any], output: dict[str, Any]) -> tuple[str, str]:
    action = str(input_row.get("Contact Status", "")).strip()
    modify = corrected.get("modify_function") or {}

    if action == "Modify-Function Change":
        site_name = (
            output.get("posted_payload_address")
            or modify.get("new_site_name")
            or input_row.get("New Site")
            or corrected.get("corrected_site_name")
            or input_row.get("Site Name", "")
        )
        teid = ""
        if str(output.get("status", "")).strip() in {"Created", "Already Exists", "Manual Intervention Required"}:
            teid = output.get("teid") or modify.get("new_site_id") or ""
        return clean_site(site_name), teid

    site_name = output.get("posted_payload_address") or corrected.get("corrected_site_name") or input_row.get("Site Name", "")
    teid = output.get("teid", "")
    return clean_site(site_name), teid


def empty_processed_results_df() -> pd.DataFrame:
    return pd.DataFrame(columns=processed_result_columns())


def empty_deactivate_results_df() -> pd.DataFrame:
    return pd.DataFrame(columns=deactivate_result_columns())


def render_add_review(review: dict[str, Any], row: dict[str, Any]) -> None:
    r = first_result(review)
    corrected = r.get("corrected_data") or {}
    bod_value = corrected.get("corrected_bod") or row.get("BOD")
    status = str(r.get("status", "")).strip()
    msg = last_note(r.get("notes")) or "The request could not be reviewed."
    if status == "Reviewed":
        msg = " ".join(x for x in [f"Site resolved to {clean_site(corrected.get('corrected_site_name'))}." if clean_site(corrected.get("corrected_site_name")) else "", f"TEID resolved to {corrected.get('resolved_site_id')}." if corrected.get("resolved_site_id") else "", "Review looks ready for commit."] if x)
        status_card("Ready for review", msg, "info", [("BOD", bod_value), ("Requester Name", requester_name(row)), ("SEID", row.get("SEID")), ("Site", clean_site(corrected.get("corrected_site_name")) or row.get("Site Name")), ("TEID", corrected.get("resolved_site_id"))], "If the details look correct, select Upload To Connect.")
    elif status == "Manual Selection Required":
        status_card("Manual input required", msg or "Manual input is required before processing can continue.", "warning", [("BOD", bod_value), ("Requester Name", requester_name(row)), ("SEID", row.get("SEID")), ("Site", row.get("Site Name"))], "Provide a more specific Site ID or Manual Site Name, then review again.")
    else:
        status_card("Failed", msg, "error", [("BOD", bod_value), ("Requester Name", requester_name(row)), ("SEID", row.get("SEID"))], "Check the form values and try again.")


def render_add_commit(commit: dict[str, Any], row: dict[str, Any]) -> None:
    c = first_result(commit)
    corrected = c.get("corrected_data") or {}
    result = c.get("result") or {}
    connect_payload = c.get("connect_payload") or {}
    site_name, teid = commit_result_site_and_teid(c.get("input") or row, corrected, result)
    status = str(result.get("status", "")).strip()
    fields = [("BOD", corrected.get("corrected_bod") or row.get("BOD")), ("Requester Name", requester_name(row)), ("SEID", row.get("SEID")), ("Site", site_name), ("TEID", teid), ("Generated PIN", commit_result_pin(result, connect_payload))]
    message = str(result.get("message", "")).strip() or "The request finished without a detailed message."
    if status == "Created":
        status_card("Created successfully", message, "success", fields)
    elif status in {"Manual Selection Required", "Already Exists"}:
        warn = "A requester with this SEID already exists for the resolved site." if status == "Already Exists" else message
        status_card("Manual input required", warn, "warning", fields + [("GUID", result.get("guid"))], "Review the site or SEID details and try again.")
    else:
        status_card("Failed", message, "error", fields[:3], "Check the request details or use Dev Use for raw backend output.")


def render_bulk_result(result: dict[str, Any], preview_rows: list[ParsedRow]) -> None:
    summary = result.get("summary") or {}
    preview_actions = {str(row.contact_status or "").strip() for row in preview_rows}
    has_modify_rows = "Modify-Function Change" in preview_actions
    has_deactivate_rows = "Deactivate" in preview_actions
    deactivated_title = "Deactivated"
    deactivated_caption = "Requesters deactivated"
    if has_modify_rows and not has_deactivate_rows:
        deactivated_title = "Modify Steps"
        deactivated_caption = "Current sites deactivated during modify changes"
    metric_cards([
        ("Total rows", summary.get("total", len(preview_rows)), "Rows received"),
        ("Created", summary.get("Created", summary.get("created", 0)), "Requesters created"),
        (deactivated_title, summary.get("Deactivated", summary.get("deactivated", 0)), deactivated_caption),
        ("Failed", summary.get("Failed", summary.get("failed", 0)), "Rows not completed"),
    ])
    if result.get("results") is not None:
        df = build_commit_results_table(result)
    else:
        df = build_raw_processed_results_table(result, preview_rows)
    heading("Processed results", "Review row-level outcomes without raw logs.")
    render_clean_results_table(df)
    if not df.empty:
        st.download_button("Download processed results", df.to_csv(index=False).encode("utf-8"), "irs_pin_bulk_results.csv", "text/csv")


def build_bulk_preview_table(rows: list[ParsedRow]) -> pd.DataFrame:
    preview_rows: list[dict[str, Any]] = []
    for row in rows:
        preview_rows.append(
            {
                "BOD": row.bod,
                "Name": f"{row.first_name} {row.last_name}".strip(),
                "SEID": row.seid,
                "Site Name": row.site_name,
                "Site ID": row.site_id,
                "Generated PIN": "Will be assigned on upload",
            }
        )
    return pd.DataFrame(preview_rows)


def build_deactivate_bulk_preview_table(rows: list[ParsedRow]) -> pd.DataFrame:
    preview_rows: list[dict[str, Any]] = []
    for row in rows:
        preview_rows.append(
            {
                "BOD": row.bod,
                "NAME": safe_deactivate_name(row.first_name, row.last_name),
                "SEID": row.seid,
                "SITE Name": clean_site(row.site_name),
                "TEID": row.site_id,
                "STATUS": "Ready for review",
                "MESSAGE": "",
            }
        )
    return pd.DataFrame(preview_rows, columns=deactivate_result_columns())


def build_bulk_review_table(review_result: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in review_result.get("results", []):
        input_row = result.get("input") or {}
        corrected = result.get("corrected_data") or {}
        rows.append(
            {
                "BOD": corrected.get("corrected_bod") or input_row.get("BOD", ""),
                "Name": f"{input_row.get('First Name', '').strip()} {input_row.get('Last Name', '').strip()}".strip(),
                "SEID": input_row.get("SEID", ""),
                "Site Name": clean_site(corrected.get("corrected_site_name")) or input_row.get("Site Name", ""),
                "Site ID": corrected.get("resolved_site_id") or input_row.get("Site ID", ""),
                "Status": result.get("status", ""),
                "Generated PIN": "Will be assigned on upload",
            }
        )
    return pd.DataFrame(rows)


def build_deactivate_bulk_review_table(review_result: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in review_result.get("results", []):
        input_row = result.get("input") or {}
        corrected = result.get("corrected_data") or {}
        rows.append(
            {
                "BOD": corrected.get("corrected_bod") or input_row.get("BOD", ""),
                "SITE Name": clean_site(corrected.get("corrected_site_name")) or input_row.get("Site Name", ""),
                "TEID": corrected.get("resolved_site_id") or input_row.get("Site ID", ""),
                "SEID": input_row.get("SEID", ""),
                "NAME": "",
                "STATUS": result.get("status", ""),
                "MESSAGE": "Ready for deactivate" if str(result.get("status", "")).strip() == "Reviewed" else (last_note(result.get("notes")) if isinstance(result.get("notes"), list) else ""),
            }
        )
    return pd.DataFrame(rows, columns=deactivate_result_columns()) if rows else empty_deactivate_results_df()


def build_raw_processed_results_table(result: dict[str, Any], preview_rows: list[ParsedRow]) -> pd.DataFrame:
    preview_map = {r.row_number: r for r in preview_rows}
    rows: list[dict[str, Any]] = []
    for row in result.get("row_results", []):
        preview = preview_map.get(row.get("row_number"))
        rows.append(
            processed_result_row(
                bod=row.get("customer_name") or row.get("bod", ""),
                site_name=row.get("matched_site_name") or row.get("input_site_name") or (preview.site_name if preview else ""),
                teid=row.get("resolved_site_id", ""),
                seid=row.get("seid", ""),
                name=f"{preview.first_name} {preview.last_name}".strip() if preview else "",
                status=row.get("status", ""),
                message=str((row.get("response") or {}).get("text", "")).strip() or last_note(row.get("notes")),
                generated_pin=row.get("generated_pin", ""),
            )
        )
    return pd.DataFrame(rows, columns=processed_result_columns()) if rows else empty_processed_results_df()


def build_commit_results_table(commit_result: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in commit_result.get("results", []):
        input_row = result.get("input") or {}
        corrected = result.get("corrected_data") or {}
        output = result.get("result") or {}
        connect_payload = result.get("connect_payload") or {}
        site_name, teid = commit_result_site_and_teid(input_row, corrected, output)
        rows.append(
            processed_result_row(
                bod=corrected.get("corrected_bod") or input_row.get("BOD", ""),
                site_name=site_name,
                teid=teid,
                seid=input_row.get("SEID", ""),
                name=f"{input_row.get('First Name', '').strip()} {input_row.get('Last Name', '').strip()}".strip(),
                status=output.get("status", ""),
                message=output.get("message", ""),
                generated_pin=commit_result_pin(output, connect_payload),
            )
        )
    return pd.DataFrame(rows, columns=processed_result_columns()) if rows else empty_processed_results_df()


def build_deactivate_commit_results_table(commit_result: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in commit_result.get("results", []):
        input_row = result.get("input") or {}
        corrected = result.get("corrected_data") or {}
        output = result.get("result") or {}
        connect_payload = result.get("connect_payload") or {}
        rows.append(
            {
                "BOD": corrected.get("corrected_bod") or input_row.get("BOD", ""),
                "SITE Name": output.get("posted_payload_address") or corrected.get("corrected_site_name") or input_row.get("Site Name", ""),
                "TEID": output.get("teid", ""),
                "SEID": input_row.get("SEID", ""),
                "NAME": safe_deactivate_name(
                    "",
                    connect_payload.get("LastName", ""),
                    fallback=safe_deactivate_name("", input_row.get("Last Name", "")),
                ),
                "STATUS": output.get("status", ""),
                "MESSAGE": output.get("message", ""),
            }
        )
    return pd.DataFrame(rows, columns=deactivate_result_columns()) if rows else empty_deactivate_results_df()


def render_clean_results_table(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No row-level results were returned for this upload.")
        return

    display_df = df.fillna("")
    headers = "".join(f"<th>{html.escape(str(column))}</th>" for column in display_df.columns)
    body_rows: list[str] = []
    for _, row in display_df.iterrows():
        cells: list[str] = []
        for column in display_df.columns:
            value = row[column]
            if column == "STATUS":
                status_text = str(value)
                status_class = status_text.strip().lower().replace(" ", "-")
                cells.append(
                    f"<td><span class='aa-status-pill aa-status-{html.escape(status_class)}'>{html.escape(status_text)}</span></td>"
                )
            else:
                cells.append(f"<td>{html.escape(str(value))}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(
        f"""
        <div class="aa-table-wrap">
            <table class="aa-table">
                <thead>
                    <tr>{headers}</tr>
                </thead>
                <tbody>
                    {''.join(body_rows)}
                </tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_add_requester_page() -> None:
    bods = sorted(BOD_LOOKUP.keys())
    default_bod_key = "TAS" if "TAS" in bods else bods[0]

    if st.session_state.add_reset_requested:
        st.session_state.add_request = None
        st.session_state.add_review = None
        st.session_state.add_commit = None
        st.session_state.add_active_workflow = "manual"
        st.session_state.add_bod_input = default_bod_key
        st.session_state.add_first_name_input = ""
        st.session_state.add_last_name_input = ""
        st.session_state.add_seid_input = ""
        st.session_state.add_site_name_input = ""
        st.session_state.add_site_id_input = ""
        st.session_state.add_manual_site_name_input = ""
        st.session_state.bulk_file_name = None
        st.session_state.bulk_file_bytes = None
        st.session_state.bulk_file_type = None
        st.session_state.bulk_preview_rows = []
        st.session_state.bulk_review_result = None
        st.session_state.bulk_result = None
        st.session_state.bulk_filter_notice = ""
        st.session_state.bulk_uploader_version += 1
        st.session_state.add_reset_requested = False

    hero("Add Requester", "Upload a file for multiple requesters, or enter one requester below.")

    heading("Bulk upload", "Upload the file, review the rows, then upload them to Connect.")
    uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"], key=f"add_bulk_uploader_{st.session_state.bulk_uploader_version}")
    if uploaded is not None:
        st.session_state.bulk_file_name = uploaded.name
        st.session_state.bulk_file_bytes = uploaded.getvalue()
        st.session_state.bulk_file_type = uploaded.type or "application/octet-stream"

    with st.expander("Manual Entry", expanded=False):
        heading("Manual upload", "Key fields are shown first. Optional fields are clearly marked.")
        if st.session_state.add_bod_input not in bods:
            st.session_state.add_bod_input = default_bod_key
        st.selectbox("BOD / Test Account *", bods, key="add_bod_input")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("First Name *", key="add_first_name_input")
            st.text_input("SEID *", help="Must be unique for new requester creation.", key="add_seid_input")
            st.text_input("Site Name *", key="add_site_name_input")
        with c2:
            st.text_input("Last Name *", key="add_last_name_input")
            st.text_input("Site ID (Optional)", key="add_site_id_input")
            st.text_input("Manual Site Name (Only if Manual Selection Required)", key="add_manual_site_name_input")
        st.caption("Required fields are marked with *")
        st.caption("Site ID: only provide if the exact site is already known.")
        st.caption("Use Manual Site Name only when the review flow asks for manual site selection.")

    manual_row = add_row(
        st.session_state.add_bod_input,
        st.session_state.add_first_name_input,
        st.session_state.add_last_name_input,
        st.session_state.add_seid_input,
        st.session_state.add_site_name_input,
        st.session_state.add_site_id_input,
        st.session_state.add_manual_site_name_input,
    )
    has_bulk_file = st.session_state.bulk_file_bytes is not None
    has_manual_input = any(
        manual_row[field].strip()
        for field in ["First Name", "Last Name", "SEID", "Site Name", "Site ID", "Manual Site Name"]
    )
    can_manual_upload = bool(st.session_state.add_request and str(first_result(st.session_state.add_review).get("status", "")) == "Reviewed")
    active_mode = st.session_state.add_active_workflow
    if has_manual_input or st.session_state.add_review or st.session_state.add_commit:
        active_mode = "manual"
    elif has_bulk_file:
        active_mode = "bulk"

    result_container = st.container()

    c1, c2, c3 = st.columns([1, 1, 0.8])
    with c1:
        if st.button("Review", use_container_width=True, disabled=not (has_bulk_file or has_manual_input), key="add_shared_review"):
            if active_mode == "bulk" and has_bulk_file:
                try:
                    st.session_state.add_active_workflow = "bulk"
                    with st.spinner("Reviewing uploaded file..."):
                        parsed_rows = parse_input_bytes(
                            st.session_state.bulk_file_name,
                            st.session_state.bulk_file_bytes,
                        )
                        filtered_rows, filter_notice = filter_rows_for_action(parsed_rows, "Add")
                        if not filtered_rows:
                            raise ValueError("No Add rows were found in the uploaded file.")
                        st.session_state.bulk_preview_rows = filtered_rows
                        st.session_state.bulk_filter_notice = filter_notice
                        st.session_state.bulk_review_result = post_bulk_review(
                            [parsed_row_to_request_dict(row) for row in filtered_rows]
                        )
                        st.session_state.bulk_result = None
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.session_state.bulk_preview_rows = []
                    st.session_state.bulk_review_result = None
                    st.session_state.bulk_filter_notice = ""
                    st.error(f"Could not review the file: {exc}")
            else:
                st.session_state.add_active_workflow = "manual"
                st.session_state.add_request = manual_row
                st.session_state.add_commit = None
                st.session_state.bulk_result = None
                try:
                    with st.spinner("Reviewing requester..."):
                        st.session_state.add_review = post_review(st.session_state.add_request)
                    st.rerun()
                except requests.RequestException as exc:
                    st.session_state.add_review = None
                    st.error(f"Review failed: {exc}")
    with c2:
        if st.button(
            "Upload To Connect",
            type="primary",
            use_container_width=True,
            disabled=(active_mode == "bulk" and st.session_state.bulk_file_bytes is None) or (active_mode == "manual" and not can_manual_upload),
            key="add_shared_upload",
        ):
            if active_mode == "bulk" and has_bulk_file:
                try:
                    st.session_state.add_active_workflow = "bulk"
                    with st.spinner("Uploading file to Connect..."):
                        rows = st.session_state.bulk_preview_rows
                        if not rows:
                            parsed_rows = parse_input_bytes(
                                st.session_state.bulk_file_name,
                                st.session_state.bulk_file_bytes,
                            )
                            rows, filter_notice = filter_rows_for_action(parsed_rows, "Add")
                            if not rows:
                                raise ValueError("No Add rows were found in the uploaded file.")
                            st.session_state.bulk_preview_rows = rows
                            st.session_state.bulk_filter_notice = filter_notice
                        st.session_state.bulk_result = post_commit(
                            {
                                "rows": [parsed_row_to_request_dict(row) for row in rows],
                                "created_by": "IRS PIN Operator",
                                "write_output": False,
                                "debug": False,
                            }
                        )
                    st.rerun()
                except (requests.RequestException, ValueError) as exc:
                    st.error(f"Bulk processing failed: {exc}")
            else:
                try:
                    st.session_state.add_active_workflow = "manual"
                    with st.spinner("Uploading requester to Connect..."):
                        st.session_state.add_commit = commit_from_review(st.session_state.add_review, st.session_state.add_request)
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Commit failed: {exc}")
    with c3:
        if st.button("Refresh", use_container_width=True, key="add_shared_refresh"):
            st.session_state.add_reset_requested = True
            st.rerun()

    with result_container:
        if st.session_state.bulk_preview_rows:
            metric_cards([("Rows detected", len(st.session_state.bulk_preview_rows), "Ready for upload")])
            if st.session_state.bulk_filter_notice:
                st.info(st.session_state.bulk_filter_notice)
            with st.expander("See reviewed rows", expanded=False):
                review_df = build_bulk_review_table(st.session_state.bulk_review_result) if st.session_state.bulk_review_result else build_bulk_preview_table(st.session_state.bulk_preview_rows)
                render_clean_results_table(review_df)

        if st.session_state.bulk_result:
            render_bulk_result(st.session_state.bulk_result, st.session_state.bulk_preview_rows)

        if st.session_state.add_review and st.session_state.add_request:
            render_add_review(st.session_state.add_review, st.session_state.add_request)

        if st.session_state.add_commit and st.session_state.add_request:
            render_add_commit(st.session_state.add_commit, st.session_state.add_request)


def render_deactivate_requester_page() -> None:
    bods = sorted(BOD_LOOKUP.keys())
    default_bod_key = "TAS" if "TAS" in bods else bods[0]

    if st.session_state.deactivate_reset_requested:
        st.session_state.deactivate_request = None
        st.session_state.deactivate_ready = None
        st.session_state.deactivate_commit = None
        st.session_state.deactivate_active_workflow = "manual"
        st.session_state.deactivate_bod_input = default_bod_key
        st.session_state.deactivate_seid_input = ""
        st.session_state.deactivate_site_name_input = ""
        st.session_state.deactivate_site_id_input = ""
        st.session_state.deactivate_bulk_file_name = None
        st.session_state.deactivate_bulk_file_bytes = None
        st.session_state.deactivate_bulk_file_type = None
        st.session_state.deactivate_bulk_preview_rows = []
        st.session_state.deactivate_bulk_review_result = None
        st.session_state.deactivate_bulk_result = None
        st.session_state.deactivate_bulk_filter_notice = ""
        st.session_state.deactivate_bulk_uploader_version += 1
        st.session_state.deactivate_reset_requested = False

    hero("Deactivate Requester", "Deactivate an existing requester using a focused workflow built for operations users.")
    heading("Bulk upload", "Upload the file, review the rows, then deactivate them in Connect.")
    uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"], key=f"deactivate_bulk_uploader_{st.session_state.deactivate_bulk_uploader_version}")
    if uploaded is not None:
        st.session_state.deactivate_bulk_file_name = uploaded.name
        st.session_state.deactivate_bulk_file_bytes = uploaded.getvalue()
        st.session_state.deactivate_bulk_file_type = uploaded.type or "application/octet-stream"

    with st.expander("Manual Entry", expanded=False):
        heading("Requester details", "Provide the requester identifier and optional site context if you have it.")
        if st.session_state.deactivate_bod_input not in bods:
            st.session_state.deactivate_bod_input = default_bod_key
        st.selectbox("BOD / Test Account *", bods, key="deactivate_bod_input")
        st.text_input("SEID *", key="deactivate_seid_input")
        with st.expander("Optional details"):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Site Name (Optional)", key="deactivate_site_name_input")
            with c2:
                st.text_input("Site ID (Optional)", key="deactivate_site_id_input")

    request = deactivate_row(
        st.session_state.deactivate_bod_input,
        st.session_state.deactivate_seid_input,
        st.session_state.deactivate_site_name_input,
        st.session_state.deactivate_site_id_input,
    )
    ready = {
        "BOD": st.session_state.deactivate_bod_input,
        "SEID": st.session_state.deactivate_seid_input.strip(),
        "Site Name": st.session_state.deactivate_site_name_input.strip(),
        "Site ID": st.session_state.deactivate_site_id_input.strip(),
    }
    has_bulk_file = st.session_state.deactivate_bulk_file_bytes is not None
    has_manual_input = any(ready[field].strip() for field in ["SEID", "Site Name", "Site ID"])
    active_mode = st.session_state.deactivate_active_workflow
    if has_manual_input or st.session_state.deactivate_ready or st.session_state.deactivate_commit:
        active_mode = "manual"
    elif has_bulk_file:
        active_mode = "bulk"

    result_container = st.container()
    c1, c2, c3 = st.columns([1, 1, 0.8])
    with c1:
        if st.button("Review", use_container_width=True, key="deactivate_review_button"):
            if active_mode == "bulk" and has_bulk_file:
                try:
                    st.session_state.deactivate_active_workflow = "bulk"
                    with st.spinner("Reviewing uploaded file..."):
                        parsed_rows = parse_input_bytes(
                            st.session_state.deactivate_bulk_file_name,
                            st.session_state.deactivate_bulk_file_bytes,
                        )
                        filtered_rows, filter_notice = filter_rows_for_action(parsed_rows, "Deactivate")
                        if not filtered_rows:
                            raise ValueError("No Delete/Deactivate rows were found in the uploaded file.")
                        st.session_state.deactivate_bulk_preview_rows = filtered_rows
                        st.session_state.deactivate_bulk_filter_notice = filter_notice
                        deactivate_rows = [parsed_row_to_deactivate_request_dict(row) for row in filtered_rows]
                        st.session_state.deactivate_bulk_review_result = post_bulk_review(deactivate_rows)
                        st.session_state.deactivate_bulk_result = None
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.session_state.deactivate_bulk_preview_rows = []
                    st.session_state.deactivate_bulk_review_result = None
                    st.session_state.deactivate_bulk_filter_notice = ""
                    st.error(f"Could not review the file: {exc}")
            else:
                st.session_state.deactivate_active_workflow = "manual"
                st.session_state.deactivate_request = request
                st.session_state.deactivate_ready = ready
                st.session_state.deactivate_commit = None
                st.session_state.deactivate_bulk_result = None
                if not ready["BOD"].strip() or not ready["SEID"].strip():
                    st.error("BOD and SEID are required before deactivation can be reviewed.")
                else:
                    st.rerun()
    with c2:
        if st.button("Deactivate", type="primary", use_container_width=True, key="deactivate_commit_button"):
            if active_mode == "bulk" and has_bulk_file:
                try:
                    st.session_state.deactivate_active_workflow = "bulk"
                    with st.spinner("Deactivating uploaded rows..."):
                        rows = st.session_state.deactivate_bulk_preview_rows
                        if not rows:
                            parsed_rows = parse_input_bytes(
                                st.session_state.deactivate_bulk_file_name,
                                st.session_state.deactivate_bulk_file_bytes,
                            )
                            rows, filter_notice = filter_rows_for_action(parsed_rows, "Deactivate")
                            if not rows:
                                raise ValueError("No Delete/Deactivate rows were found in the uploaded file.")
                            st.session_state.deactivate_bulk_preview_rows = rows
                            st.session_state.deactivate_bulk_filter_notice = filter_notice
                        st.session_state.deactivate_bulk_result = post_commit(
                            {
                                "rows": [parsed_row_to_deactivate_request_dict(row) for row in rows],
                                "created_by": "IRS PIN Operator",
                                "write_output": False,
                                "debug": False,
                            }
                        )
                    st.rerun()
                except (requests.RequestException, ValueError) as exc:
                    st.error(f"Bulk deactivation failed: {exc}")
            else:
                st.session_state.deactivate_active_workflow = "manual"
                st.session_state.deactivate_request = request
                st.session_state.deactivate_ready = ready
                try:
                    with st.spinner("Deactivating requester..."):
                        st.session_state.deactivate_commit = post_commit({"rows": [request], "write_output": False, "debug": False})
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Deactivation failed: {exc}")
    with c3:
        if st.button("Refresh", use_container_width=True, key="deactivate_refresh_button"):
            st.session_state.deactivate_reset_requested = True
            st.rerun()

    with result_container:
        if st.session_state.deactivate_bulk_preview_rows:
            metric_cards([("Rows detected", len(st.session_state.deactivate_bulk_preview_rows), "Ready for upload")])
            if st.session_state.deactivate_bulk_filter_notice:
                st.info(st.session_state.deactivate_bulk_filter_notice)
            with st.expander("See reviewed rows", expanded=False):
                review_df = (
                    build_deactivate_bulk_review_table(st.session_state.deactivate_bulk_review_result)
                    if st.session_state.deactivate_bulk_review_result
                    else build_deactivate_bulk_preview_table(st.session_state.deactivate_bulk_preview_rows)
                )
                render_clean_results_table(review_df)

        if st.session_state.deactivate_bulk_result:
            summary = st.session_state.deactivate_bulk_result.get("summary") or {}
            metric_cards([
                ("Total rows", summary.get("total", len(st.session_state.deactivate_bulk_preview_rows)), "Rows received"),
                ("Created", summary.get("Created", summary.get("created", 0)), "Unexpected creates"),
                ("Deactivated", summary.get("Deactivated", summary.get("deactivated", 0)), "Requesters deactivated"),
                ("Failed", summary.get("Failed", summary.get("failed", 0)), "Rows not completed"),
            ])
            df = build_deactivate_commit_results_table(st.session_state.deactivate_bulk_result)
            heading("Processed results", "Review row-level deactivation outcomes.")
            render_clean_results_table(df)
            if not df.empty:
                st.download_button("Download processed results", df.to_csv(index=False).encode("utf-8"), "irs_pin_bulk_deactivate_results.csv", "text/csv")

        if st.session_state.deactivate_ready:
            if not st.session_state.deactivate_ready.get("BOD") or not st.session_state.deactivate_ready.get("SEID"):
                status_card("Failed", "BOD and SEID are required before deactivation can continue.", "error")
            elif st.session_state.deactivate_commit is None:
                status_card(
                    "Ready for review",
                    "The requester is ready for deactivation. The backend will resolve the active requester by SEID during deactivation.",
                    "info",
                    [
                        ("BOD", st.session_state.deactivate_ready.get("BOD")),
                        ("SEID", st.session_state.deactivate_ready.get("SEID")),
                        ("Site Name", st.session_state.deactivate_ready.get("Site Name")),
                        ("Site ID", st.session_state.deactivate_ready.get("Site ID")),
                    ],
                    "Select Deactivate to submit the request.",
                )

        if st.session_state.deactivate_commit and st.session_state.deactivate_request:
            row = first_result(st.session_state.deactivate_commit)
            result = row.get("result") or {}
            fields = [
                ("SEID", st.session_state.deactivate_request.get("SEID")),
                ("Site", clean_site((row.get("corrected_data") or {}).get("corrected_site_name")) or clean_site(st.session_state.deactivate_request.get("Site Name"))),
                ("GUID / TEID", result.get("guid") or result.get("teid")),
            ]
            if str(result.get("status", "")) == "Deactivated":
                status_card("Deactivated successfully", str(result.get("message", "")).strip() or "Requester deactivated successfully.", "success", fields)
            else:
                status_card("Failed", str(result.get("message", "")).strip() or "The requester could not be deactivated.", "error", fields, "Verify the SEID and use Dev Use if you need raw backend details.")


def render_dev_use_page() -> None:
    hero("Dev Use", "Internal debugging workspace with raw review and commit responses, payload details, and legacy output views.", "Internal Only")
    if not DEV_USE_ENABLED:
        st.info("Dev Use is disabled until credentials are configured in the environment.")
        return
    if not st.session_state.dev_authenticated:
        left, center, right = st.columns([1, 1.55, 1])
        with center:
            with st.form("dev_login_form"):
                st.markdown(
                    "<h2 class='aa-login-title'>Sign In</h2><p class='aa-login-copy'>Dev Use is locked. Sign in with the configured credentials to continue.</p>",
                    unsafe_allow_html=True,
                )
                st.text_input("Username", key="dev_username_input")
                st.text_input("Password", type="password", key="dev_password_input")
                submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)
            if submitted:
                if (
                    st.session_state.dev_username_input.strip() == DEV_USE_USERNAME
                    and st.session_state.dev_password_input == DEV_USE_PASSWORD
                ):
                    st.session_state.dev_authenticated = True
                    st.session_state.dev_login_error = ""
                    st.rerun()
                else:
                    st.session_state.dev_login_error = "Invalid username or password."
            if st.session_state.dev_login_error:
                st.error(st.session_state.dev_login_error)
        return

    c1, c2 = st.columns([1, 0.25])
    with c1:
        st.warning("This page exposes raw backend responses and should be used for internal debugging only.")
    with c2:
        if st.button("Log Out", use_container_width=True, key="dev_logout_button"):
            lock_dev_use()
            st.rerun()

    st.session_state.dev_mode = st.radio("Input mode", ["Enter Manually", "Attach CSV/XLSX"], horizontal=True, index=0 if st.session_state.dev_mode == "Enter Manually" else 1)
    if st.session_state.dev_mode == "Enter Manually":
        bods = sorted(BOD_LOOKUP.keys())
        default_bod_key = "TAS" if "TAS" in bods else bods[0]
        with st.form("dev_form"):
            bod = st.selectbox("BOD / Test Account", bods, index=bods.index(default_bod_key))
            c1, c2 = st.columns(2)
            with c1:
                first = st.text_input("First Name")
                seid = st.text_input("SEID")
                site_id = st.text_input("Site ID")
            with c2:
                last = st.text_input("Last Name")
                site_name = st.text_input("Site Name")
                contact_status = st.selectbox("Contact Status", ["Add", "Deactivate"])
            manual_site_name = st.text_input("Manual Site Name")
            review = st.form_submit_button("Review", type="primary")
        if review:
            st.session_state.dev_request = {"BOD": bod, "First Name": first, "Last Name": last, "SEID": seid, "Site Name": site_name, "Site ID": site_id, "Contact Status": contact_status, "Manual Site Name": manual_site_name}
            st.session_state.dev_commit = None
            try:
                st.session_state.dev_review = post_review(st.session_state.dev_request)
            except requests.RequestException as exc:
                st.session_state.dev_review = None
                st.error(f"Review failed: {exc}")
        if st.session_state.dev_request:
            st.dataframe(pd.DataFrame([row_to_preview_dict(r) for r in parse_input_records([st.session_state.dev_request])]), use_container_width=True, hide_index=True)
        if st.session_state.dev_review is not None:
            st.subheader("Raw review response")
            st.json(st.session_state.dev_review, expanded=False)
            dev_row = first_result(st.session_state.dev_review)
            if dev_row.get("api_trace"):
                st.caption("API trace")
                st.json(dev_row["api_trace"], expanded=False)
            if dev_row.get("suggested_connect_payload"):
                st.caption("Suggested payload")
                st.json(dev_row["suggested_connect_payload"], expanded=False)
        if st.button("Commit", disabled=not (st.session_state.dev_review and st.session_state.dev_request)):
            try:
                st.session_state.dev_commit = commit_from_review(st.session_state.dev_review, st.session_state.dev_request)
            except requests.RequestException as exc:
                st.error(f"Commit failed: {exc}")
        if st.session_state.dev_commit is not None:
            st.subheader("Raw commit response")
            st.json(st.session_state.dev_commit, expanded=False)
            payload = first_result(st.session_state.dev_commit).get("connect_payload")
            if payload:
                st.caption("Posted payload")
                st.json(payload, expanded=False)
    else:
        uploaded = st.file_uploader("Attach a CSV/XLSX/XLS file", type=["csv", "xlsx", "xls"], key="dev_bulk_upload")
        rows: list[ParsedRow] = []
        if uploaded is not None:
            rows = parse_input_bytes(uploaded.name, uploaded.getvalue())
            st.dataframe(pd.DataFrame([row_to_preview_dict(r) for r in rows]), use_container_width=True, hide_index=True)
        if st.button("Process Bulk Upload", type="primary", disabled=uploaded is None):
            try:
                st.session_state.dev_bulk_result = post_file(uploaded)
            except requests.RequestException as exc:
                st.error(f"Bulk processing failed: {exc}")
        if st.session_state.dev_bulk_result is not None:
            st.subheader("Bulk results")
            st.json(st.session_state.dev_bulk_result, expanded=False)


def render_sidebar() -> None:
    with st.sidebar:
        render_brand()
        st.markdown("<div class='aa-nav-label'>Navigation</div>", unsafe_allow_html=True)
        for page in ["Add Requester", "Deactivate Requester", "Dev Use"]:
            if st.button(
                page,
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if st.session_state.page == page else "secondary",
            ):
                st.session_state.page = page
                st.rerun()


def main() -> None:
    st.set_page_config(page_title="IRS PIN QA Tool", layout="wide")
    ensure_state()
    inject_styles()
    render_sidebar()
    if st.session_state.page == "Add Requester":
        render_add_requester_page()
    elif st.session_state.page == "Deactivate Requester":
        render_deactivate_requester_page()
    else:
        render_dev_use_page()


if __name__ == "__main__":
    main()
