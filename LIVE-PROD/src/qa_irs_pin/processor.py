"""Main processor that preserves the validated mock flow and swaps in live QA APIs."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from qa_irs_pin import registry
from qa_irs_pin import sharepoint_lookup
from qa_irs_pin.config import CUSTOMER_CREATE_OVERRIDES, DB_PATH, DEFAULT_NEW_SITE_PIN_SUFFIX, DEFAULT_NEW_SITE_PIN_TOTAL_LENGTH, OUTPUT_DIR, SITE_MATCH_THRESHOLD
from qa_irs_pin.matching import best_site_match, normalize_site_name, requires_explicit_site_confirmation, tokenize, top_site_matches
from qa_irs_pin.models import ParsedRow, ProcessingRunResult, RowProcessingOutcome
from qa_irs_pin.parser import parse_input_file
from qa_irs_pin.payloads import build_create_payload, build_deactivate_payload, build_modify_function_email, build_update_payload
from utils.client import ConnectAPIError, ConnectQAClient
from utils.helpers import is_missing_fk_value, next_new_site_pin, next_pin, normalize_pin_value, normalize_teid, normalize_text, resolve_customer_context


def _build_summary(row_results: list[RowProcessingOutcome]) -> dict[str, int]:
    counts = Counter()

    for row in row_results:
        if row.action == "Modify-Function Change":
            modify = row.modify_function or {}
            deactivate_step = modify.get("deactivate_step") or {}
            create_step = modify.get("create_step") or {}
            if deactivate_step.get("success"):
                counts["Deactivated"] += 1
            if create_step.get("success"):
                counts["Created"] += 1
            if row.status in {"Failed", "Manual Intervention Required"}:
                counts["Failed"] += 1
            continue

        counts[row.status] += 1

    counts["total"] = len(row_results)
    return dict(counts)


def _build_manual_selection_payload(row: ParsedRow, customer_name: str, candidate_sites: list[str]) -> dict:
    return {
        "input_site_name": row.site_name,
        "customer_name": customer_name,
        "top_candidates": top_site_matches(row.site_name, candidate_sites),
        "resume_row": {
            "BOD": row.bod,
            "Customer Name": row.customer_name or customer_name,
            "First Name": row.first_name,
            "Last Name": row.last_name,
            "SEID": row.seid,
            "Site ID": row.site_id,
            "Site Name": row.site_name,
            "Contact Status": row.contact_status,
            "Manual Site Name": "",
        },
    }


def _looks_like_existing_site_reference(input_site_name: str, candidate_sites: list[str]) -> bool:
    normalized_input = normalize_site_name(input_site_name)
    if not normalized_input:
        return False

    input_tokens = tokenize(input_site_name)
    input_token_set = set(input_tokens)

    short_fragment = len(input_tokens) <= 2 or len(normalized_input) <= 12

    for candidate_site in candidate_sites:
        normalized_candidate = normalize_site_name(candidate_site)
        candidate_tokens = set(tokenize(candidate_site))

        if normalized_input == normalized_candidate:
            return True

        if short_fragment:
            if normalized_input in normalized_candidate:
                return True
            if input_token_set and input_token_set.issubset(candidate_tokens):
                return True
            continue

        extra_tokens = input_token_set - candidate_tokens
        if extra_tokens:
            continue

        if input_token_set and input_token_set.issubset(candidate_tokens):
            return True

    return False


def _check_sharepoint_for_new_site(
    site_name: str,
    *,
    notes: list[str],
) -> tuple[str | None, bool]:
    """Check SharePoint for a site Connect says is new. Returns (sp_teid, found_in_sp)."""
    sp_entry = sharepoint_lookup.get_teid_for_site_name(site_name)
    if sp_entry:
        sp_teid = normalize_teid(sp_entry.get("teid"))
        if sp_teid:
            notes.append(
                f"Site '{site_name}' was not found in Connect but was matched in the Master Site Sheet "
                f"(TEID {sp_teid}, state {sp_entry.get('state', 'unknown')}). "
                "Please verify this TEID before committing."
            )
            return sp_teid, True
    return None, False


def resolve_blank_site_id_path(
    row: ParsedRow,
    customer_name: str,
    candidate_sites: list[str],
    *,
    client: ConnectQAClient,
) -> dict[str, object]:
    manual_site_name = row.manual_site_name.strip()
    match_score: float | None = None

    if manual_site_name:
        matched_site_name = manual_site_name
        teid_resolution = client.resolve_teid(customer_name, matched_site_name)
        strategy = "manual"
        notes = ["Using manually selected canonical site string."]
    elif _looks_like_existing_site_reference(row.site_name, candidate_sites):
        match = best_site_match(row.site_name, candidate_sites)
        matched_site_name = match.matched_site_name
        if matched_site_name is None:
            raise ConnectAPIError("Could not resolve a candidate site name from API 3 results.")
        match_score = match.score
        teid_resolution = client.resolve_teid(customer_name, matched_site_name)
        strategy = "existing"
        notes = []
        if match_score < SITE_MATCH_THRESHOLD:
            notes.append(f"Auto-selected top site match below threshold: {matched_site_name} ({match_score}).")
    else:
        matched_site_name = row.site_name.strip()
        teid_resolution = client.resolve_teid(customer_name, matched_site_name)
        strategy = "new"
        notes = ["Treating original site input as a new-site candidate."]

    resolved_teid = normalize_teid(teid_resolution.get("existingTeid"))
    if not resolved_teid and not teid_resolution.get("siteExists"):
        # Before auto-incrementing, check SharePoint master sheet
        sp_teid, found_in_sp = _check_sharepoint_for_new_site(matched_site_name, notes=notes)
        if found_in_sp and sp_teid:
            resolved_teid = sp_teid
            strategy = "sharepoint"
        else:
            current_max_teid = normalize_teid(teid_resolution.get("currentMaxTeid"))
            if not current_max_teid:
                raise ConnectAPIError("API 2 did not return currentMaxTeid for a new site.")
            resolved_teid = _next_four_digit_teid(current_max_teid)

    return {
        "matched_site_name": matched_site_name,
        "match_score": match_score,
        "teid_resolution": teid_resolution,
        "resolved_teid": resolved_teid,
        "strategy": strategy,
        "notes": notes,
    }


def _new_site_pin_settings(customer_name: str) -> dict[str, int]:
    customer_override = CUSTOMER_CREATE_OVERRIDES.get(customer_name.lower(), {})
    if "new_site_pin_total_length" in customer_override:
        return {"total_length": int(customer_override["new_site_pin_total_length"])}
    return {"suffix_width": int(customer_override.get("new_site_pin_suffix", DEFAULT_NEW_SITE_PIN_SUFFIX))}


def _next_four_digit_teid(current_max_teid: str) -> str:
    next_teid = int(current_max_teid) + 1
    if next_teid > 9999:
        raise ConnectAPIError("Cannot assign a new TEID because the 4-digit TEID limit of 9999 has been reached.")
    return str(next_teid).zfill(4)


def _backfill_missing_pin_context(
    *,
    client: ConnectQAClient,
    customer_name: str,
    pin_context: dict[str, object],
    teid_resolution: dict[str, object] | None,
    customer_context: dict[str, object] | None,
) -> dict[str, object]:
    if is_missing_fk_value(pin_context.get("fK_Customer")):
        fallback_teid = normalize_teid((teid_resolution or {}).get("currentMaxTeid"))
        if fallback_teid:
            try:
                fallback_context = client.get_pin_context(customer_name, fallback_teid)
            except ConnectAPIError:
                fallback_context = {}
            if not is_missing_fk_value(fallback_context.get("fK_Customer")):
                pin_context["fK_Customer"] = fallback_context.get("fK_Customer")
            if is_missing_fk_value(pin_context.get("fK_Location")) and not is_missing_fk_value(fallback_context.get("fK_Location")):
                pin_context["fK_Location"] = fallback_context.get("fK_Location")

    if is_missing_fk_value(pin_context.get("fK_Customer")) and (customer_context or {}).get("fk_customer"):
        pin_context["fK_Customer"] = customer_context["fk_customer"]

    return pin_context


def _is_active_match(match: dict[str, object]) -> bool:
    return str(match.get("account_status", "")).lower() == "active"


def _site_matches_modify_request(match: dict[str, object], row: ParsedRow) -> bool:
    requested_pin = normalize_pin_value(row.user_pin)
    match_pin = normalize_pin_value(match.get("pin_code"))
    if requested_pin and match_pin and requested_pin == match_pin:
        return True

    requested_teid = normalize_teid(row.site_id)
    match_teid = normalize_teid(match.get("teid"))
    if requested_teid:
        return requested_teid == match_teid

    requested_site_name = normalize_site_name(row.site_name)
    match_site_name = normalize_site_name((match.get("raw") or {}).get("address"))
    if requested_site_name and match_site_name:
        return requested_site_name == match_site_name
    return False


def _looks_like_duplicate_pin_error(message: str) -> bool:
    normalized = " ".join(str(message).strip().lower().split())
    duplicate_markers = (
        "pin already exists",
        "pin code already exists",
        "pincode already exists",
        "pin already taken",
        "duplicate pin",
        "pin exists",
        "duplicate pincode",
    )
    return any(marker in normalized for marker in duplicate_markers)


def _looks_like_duplicate_email_error(message: str) -> bool:
    normalized = " ".join(str(message).strip().lower().split())
    if "duplicate email" in normalized:
        return True
    if "email" not in normalized:
        return False
    duplicate_markers = (
        "already registered",
        "already exists",
        "is registered",
    )
    return any(marker in normalized for marker in duplicate_markers)


def _find_modify_old_site_user(
    existing: list[dict[str, object]],
    row: ParsedRow,
) -> dict[str, object] | None:
    requested_pin = normalize_pin_value(row.user_pin)
    requested_teid = normalize_teid(row.site_id)

    if requested_pin:
        exact_pin_match = next(
            (
                match
                for match in existing
                if _is_active_match(match) and normalize_pin_value(match.get("pin_code")) == requested_pin
            ),
            None,
        )
        if exact_pin_match is not None:
            return exact_pin_match

    if requested_teid:
        exact_teid_match = next(
            (
                match
                for match in existing
                if _is_active_match(match) and normalize_teid(match.get("teid")) == requested_teid
            ),
            None,
        )
        if exact_teid_match is not None:
            return exact_teid_match

    return next(
        (
            match
            for match in existing
            if _is_active_match(match) and _site_matches_modify_request(match, row)
        ),
        None,
    )


def _find_active_destination_user(
    existing: list[dict[str, object]],
    *,
    destination_teid: str,
    first_choice_pin: str,
) -> dict[str, object] | None:
    normalized_pin = normalize_pin_value(first_choice_pin)
    if normalized_pin:
        exact_pin_match = next(
            (
                match
                for match in existing
                if _is_active_match(match) and normalize_pin_value(match.get("pin_code")) == normalized_pin
            ),
            None,
        )
        if exact_pin_match is not None:
            return exact_pin_match

    return next(
        (
            match
            for match in existing
            if _is_active_match(match) and normalize_teid(match.get("teid")) == normalize_teid(destination_teid)
        ),
        None,
    )


def process_rows(
    rows: Iterable[ParsedRow],
    *,
    client: ConnectQAClient,
    created_by: str = "QA OPI Operator",
    db_path: Path = DB_PATH,
    source_name: str = "manual",
    write_output: bool = True,
) -> ProcessingRunResult:
    registry.initialize_database(db_path)
    batch_id = str(uuid.uuid4())
    payload_list: list[dict] = []
    row_results: list[RowProcessingOutcome] = []
    logs: list[dict] = []

    def log(stage: str, message: str, *, row_number: int | None = None, details: dict | None = None) -> None:
        entry = {"stage": stage, "message": message}
        if row_number is not None:
            entry["row_number"] = row_number
        if details is not None:
            entry["details"] = details
        logs.append(entry)

    with registry.get_connection(db_path) as connection:
        site_cache: dict[str, list[str]] = {}
        run_new_site_teids: dict[str, dict[str, str]] = {}
        run_next_new_teid: dict[str, int] = {}

        def assign_run_new_site_teid(customer_name: str, site_name: str, teid_resolution: dict[str, object]) -> tuple[str, bool]:
            site_key = normalize_site_name(site_name)
            customer_site_teids = run_new_site_teids.setdefault(customer_name, {})
            reused = site_key in customer_site_teids
            if reused:
                return customer_site_teids[site_key], True

            current_max_teid = normalize_teid(teid_resolution.get("currentMaxTeid"))
            if not current_max_teid:
                raise ConnectAPIError("API 2 did not return currentMaxTeid for a new site.")

            next_teid = max(run_next_new_teid.get(customer_name, 0), int(current_max_teid) + 1)
            if next_teid > 9999:
                raise ConnectAPIError("Cannot assign a new TEID because the 4-digit TEID limit of 9999 has been reached.")
            assigned_teid = str(next_teid).zfill(4)
            customer_site_teids[site_key] = assigned_teid
            run_next_new_teid[customer_name] = next_teid + 1
            return assigned_teid, False

        for row in rows:
            row_notes = list(row.notes)
            matched_site_name: str | None = None
            resolved_teid: str | None = normalize_teid(row.site_id) or None
            generated_pin: str | None = None
            verification: dict | None = None
            customer_context = resolve_customer_context(row.bod, row.customer_name)
            modify_function_result: dict | None = None

            log("row_start", "Processing row", row_number=row.row_number, details={"seid": row.seid, "action": row.contact_status})

            if row.validation_status == "Error":
                row_notes.append(f"Missing/invalid fields: {', '.join(row.error_fields)}")
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=row.customer_name or None,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=None,
                        resolved_site_id=None,
                        generated_pin=None,
                        status="Error",
                        notes=row_notes,
                    )
                )
                continue

            if row.duplicate_in_batch:
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=row.customer_name or None,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=None,
                        resolved_site_id=resolved_teid,
                        generated_pin=None,
                        status="Skipped",
                        notes=row_notes,
                    )
                )
                continue

            if customer_context is None:
                row_notes.append("Unknown BOD or customer mapping.")
                registry.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    customer_name=row.customer_name,
                    site_id=resolved_teid or "",
                    site_name=row.site_name,
                    pin_9digit=None,
                    connect_guid=None,
                    status="Failed",
                    batch_id=batch_id,
                    created_by=created_by,
                )
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=row.customer_name or None,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=None,
                        resolved_site_id=resolved_teid,
                        generated_pin=None,
                        status="Failed",
                        notes=row_notes,
                    )
                )
                continue

            customer_name = customer_context["customer_name"]
            customer_ids = [customer_context["fk_customer"]] if customer_context.get("fk_customer") else None
            log("customer_context", "Resolved customer context", row_number=row.row_number, details={"customer_name": customer_name, "fk_customer": customer_context.get("fk_customer")})

            try:
                if row.contact_status == "Deactivate":
                    existing = client.search_user_by_seid(
                        row.seid,
                        customer_ids=customer_ids,
                        active_only=False,
                        allow_export_fallback=False,
                    )
                    latest_user = next(
                        (
                            match
                            for match in reversed(existing)
                            if str(match.get("account_status", "")).lower() != "inactive"
                        ),
                        None,
                    )
                    if latest_user is None:
                        raise ConnectAPIError("SEID not found for deactivate.")
                    requester_detail = client.get_account_detail(latest_user["connect_guid"])
                    payload = build_deactivate_payload(requester_detail)
                    mutation = client.deactivate_user(payload)
                    payload_list.append(payload)

                    status = "Deactivated" if mutation.success else "Failed"
                    row_notes.append(mutation.message)
                    registry.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        customer_name=customer_name,
                        site_id=latest_user.get("teid", ""),
                        site_name=row.site_name,
                        pin_9digit=latest_user.get("pin_code"),
                        connect_guid=mutation.guid,
                        status=status,
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_results.append(
                        RowProcessingOutcome(
                            row_number=row.row_number,
                            bod=row.bod,
                            customer_name=customer_name,
                            seid=row.seid,
                            action="Deactivate",
                            input_site_name=row.site_name,
                            matched_site_name=row.site_name,
                            resolved_site_id=latest_user.get("teid"),
                            generated_pin=latest_user.get("pin_code"),
                            status=status,
                            notes=row_notes,
                            payload=payload,
                            connect_guid=mutation.guid,
                            response=mutation.raw_response,
                            verification=verification,
                        )
                    )
                    continue

                if row.contact_status == "Activate":
                    existing = client.search_user_by_seid(
                        row.seid,
                        customer_ids=customer_ids,
                        active_only=False,
                        allow_export_fallback=False,
                    )
                    requested_pin = normalize_pin_value(row.user_pin)
                    requested_teid = normalize_teid(row.site_id)
                    target_user = None
                    if requested_pin and len(requested_pin) == 9:
                        target_user = next(
                            (m for m in existing if normalize_pin_value(m.get("pin_code")) == requested_pin),
                            None,
                        )
                    if target_user is None and requested_teid:
                        target_user = next(
                            (m for m in existing if normalize_teid(m.get("teid")) == requested_teid),
                            None,
                        )
                    if target_user is None:
                        target_user = next(iter(existing), None)
                    if target_user is None:
                        raise ConnectAPIError("SEID not found for activate.")
                    existing_pin = target_user.get("pin_code") or ""
                    existing_teid = target_user.get("teid") or normalize_teid(row.site_id)
                    requester_detail = client.get_account_detail(target_user["connect_guid"])
                    activate_payload = build_update_payload(requester_detail, account_status_override="Active")
                    mutation = client.update_user(activate_payload)
                    if not mutation.message or mutation.message in ("Successfully updated", "Update failed."):
                        mutation.message = "Successfully activated" if mutation.success else "Activate failed."
                    status = "Activated" if mutation.success else "Failed"
                    row_notes.append(mutation.message)
                    registry.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        customer_name=customer_name,
                        site_id=existing_teid,
                        site_name=row.site_name,
                        pin_9digit=existing_pin,
                        connect_guid=mutation.guid,
                        status=status,
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_results.append(
                        RowProcessingOutcome(
                            row_number=row.row_number,
                            bod=row.bod,
                            customer_name=customer_name,
                            seid=row.seid,
                            action="Activate",
                            input_site_name=row.site_name,
                            matched_site_name=row.site_name,
                            resolved_site_id=existing_teid,
                            generated_pin=existing_pin,
                            status=status,
                            notes=row_notes,
                            payload=activate_payload,
                            connect_guid=mutation.guid,
                            response=mutation.raw_response,
                            verification=verification,
                        )
                    )
                    continue

                if row.contact_status == "Modify-Function Change":
                    # Cross-account modify: resolve destination customer when New BOD differs from source BOD
                    _new_bod = (row.new_bod or "").strip()
                    _new_customer_name_input = (row.new_customer_name or "").strip()
                    destination_customer_context = None
                    if _new_bod and _new_bod.lower() != (row.bod or "").strip().lower():
                        destination_customer_context = resolve_customer_context(_new_bod, _new_customer_name_input)
                        if destination_customer_context is None:
                            raise ConnectAPIError(f"Unknown New BOD or customer mapping for cross-account modify: '{_new_bod}'")
                        log("cross_account_modify", "Cross-account modify detected", row_number=row.row_number, details={"source_bod": row.bod, "destination_bod": _new_bod, "destination_customer": destination_customer_context.get("customer_name")})
                    dest_customer_name = destination_customer_context["customer_name"] if destination_customer_context else customer_name
                    dest_customer_ids = [destination_customer_context["fk_customer"]] if destination_customer_context and destination_customer_context.get("fk_customer") else customer_ids

                    existing = client.search_user_by_seid(
                        row.seid,
                        customer_ids=customer_ids,
                        active_only=False,
                        allow_export_fallback=False,
                        items_per_page=100,
                    )
                    old_site_user = _find_modify_old_site_user(existing, row)
                    if old_site_user is None:
                        existing = client.search_user_by_seid(
                            row.seid,
                            customer_ids=customer_ids,
                            active_only=False,
                            allow_export_fallback=False,
                            items_per_page=100,
                        )
                        old_site_user = _find_modify_old_site_user(existing, row)
                    if old_site_user is None:
                        destination_row = ParsedRow(
                            row_number=row.row_number,
                            bod=row.new_bod if destination_customer_context else row.bod,
                            customer_name=dest_customer_name if destination_customer_context else row.customer_name,
                            last_name=row.last_name,
                            first_name=row.first_name,
                            seid=row.seid,
                            site_id=row.new_site_id,
                            site_name=row.new_site_name,
                            manual_site_name=row.manual_site_name,
                            user_pin=row.user_pin,
                            employee_id=row.employee_id,
                            new_site_id=row.new_site_id,
                            new_site_name=row.new_site_name,
                            contact_status=row.contact_status,
                            validation_status=row.validation_status,
                            notes=list(row.notes),
                            error_fields=list(row.error_fields),
                            duplicate_in_batch=row.duplicate_in_batch,
                        )
                        candidate_sites = site_cache.setdefault(dest_customer_name, client.get_sites_for_customer(dest_customer_name))
                        if not candidate_sites:
                            raise ConnectAPIError("API 3 returned no site strings for the customer.")

                        destination_teid = normalize_teid(destination_row.site_id) or None
                        destination_site_name = destination_row.site_name
                        if not destination_teid:
                            destination_resolution = resolve_blank_site_id_path(destination_row, dest_customer_name, candidate_sites, client=client)
                            destination_site_name = str(destination_resolution["matched_site_name"])
                            destination_teid = str(destination_resolution["resolved_teid"])

                        preserved_employee_id = str(row.employee_id).strip()
                        first_choice_pin = f"{destination_teid}{preserved_employee_id}" if destination_teid and preserved_employee_id else ""
                        destination_existing_user = _find_active_destination_user(
                            existing,
                            destination_teid=destination_teid or "",
                            first_choice_pin=first_choice_pin,
                        )
                        if destination_existing_user is None and normalize_pin_value(row.user_pin):
                            export_pin_match = client.get_export_requester_by_pin(
                                row.user_pin,
                                customer_ids=customer_ids,
                                active_only=False,
                                items_per_page=100,
                            )
                            if export_pin_match is not None and _is_active_match(export_pin_match):
                                old_site_user = export_pin_match
                        if old_site_user is None and destination_existing_user is not None:
                            existing_guid = destination_existing_user.get("connect_guid")
                            existing_pin = destination_existing_user.get("pin_code")
                            existing_detail = client.get_account_detail(existing_guid)
                            email_message = "Requester already exists at the destination site."
                            current_email = normalize_text(existing_detail.get("email"))

                            if preserved_employee_id:
                                for email_suffix in range(0, 4):
                                    candidate_email = build_modify_function_email(row.seid, row.first_name, row.last_name, suffix=email_suffix)
                                    if current_email.lower() == candidate_email.lower():
                                        email_message = f"Requester already existed at the destination site with email {candidate_email}."
                                        break
                                    update_payload = build_update_payload(existing_detail, email_override=candidate_email)
                                    update_mutation = client.update_user(update_payload)
                                    if update_mutation.success:
                                        existing_detail["email"] = candidate_email
                                        if email_suffix == 0:
                                            email_message = f"Requester already existed at the destination site; updated email to {candidate_email}."
                                        else:
                                            email_message = f"Requester already existed at the destination site; updated email to {candidate_email} after duplicate-email retry."
                                        break
                                    if not _looks_like_duplicate_email_error(update_mutation.message):
                                        email_message = f"Requester already exists at the destination site, but email update failed: {update_mutation.message}"
                                        break

                            registry.write_pin_registry(
                                connection,
                                seid=row.seid,
                                first_name=row.first_name,
                                last_name=row.last_name,
                                bod=row.bod,
                                customer_name=customer_name,
                                site_id=destination_teid or "",
                                site_name=destination_site_name or destination_row.site_name,
                                pin_9digit=existing_pin,
                                connect_guid=existing_guid,
                                status="Already Exists",
                                batch_id=batch_id,
                                created_by=created_by,
                            )
                            row_notes.append(email_message)
                            row_results.append(
                                RowProcessingOutcome(
                                    row_number=row.row_number,
                                    bod=row.bod,
                                    customer_name=customer_name,
                                    seid=row.seid,
                                    action=row.contact_status,
                                    input_site_name=row.site_name,
                                    matched_site_name=destination_site_name or destination_row.site_name,
                                    resolved_site_id=destination_teid,
                                    generated_pin=existing_pin,
                                    status="Already Exists",
                                    notes=row_notes,
                                    connect_guid=existing_guid,
                                    verification={"account_detail": existing_detail},
                                    modify_function={
                                        "old_site_name": row.site_name,
                                        "old_site_id": row.site_id,
                                        "old_pin": row.user_pin,
                                        "new_site_name": destination_site_name or destination_row.site_name,
                                        "new_site_id": destination_teid,
                                        "employee_id": preserved_employee_id,
                                        "first_choice_pin": first_choice_pin,
                                        "final_committed_pin": existing_pin,
                                    },
                                )
                            )
                            continue

                        if old_site_user is None:
                            raise ConnectAPIError("Active requester was not found for the current site on the modify-function row.")

                    old_site_id = normalize_teid(old_site_user.get("teid")) or row.site_id
                    old_pin = old_site_user.get("pin_code")
                    old_guid = old_site_user.get("connect_guid")
                    old_site_name = normalize_text((old_site_user.get("raw") or {}).get("address")) or row.site_name
                    deactivate_step = {
                        "old_site_name": old_site_name,
                        "old_site_id": old_site_id,
                        "old_pin": old_pin,
                        "target_guid": old_guid,
                        "status": "Pending",
                        "message": "",
                        "success": False,
                    }
                    create_step = {
                        "new_site_name": row.new_site_name,
                        "new_site_id": normalize_teid(row.new_site_id) or "",
                        "first_choice_pin": "",
                        "fallback_pin": None,
                        "final_pin": None,
                        "status": "Pending",
                        "message": "",
                        "success": False,
                        "guid": None,
                    }
                    modify_function_result = {
                        "old_site_name": old_site_name,
                        "old_site_id": old_site_id,
                        "old_pin": old_pin,
                        "new_site_name": row.new_site_name,
                        "new_site_id": normalize_teid(row.new_site_id) or "",
                        "employee_id": str(row.employee_id).strip(),
                        "first_choice_pin": "",
                        "fallback_pin": None,
                        "reassigned_employee_id": False,
                        "final_committed_pin": None,
                        "deactivate_step": deactivate_step,
                        "create_step": create_step,
                    }

                    old_requester_detail = client.get_account_detail(old_site_user["connect_guid"])
                    deactivate_payload = build_deactivate_payload(old_requester_detail)
                    deactivate_mutation = client.deactivate_user(deactivate_payload)
                    payload_list.append(deactivate_payload)
                    if not deactivate_mutation.success:
                        raise ConnectAPIError(deactivate_mutation.message or "Failed to deactivate the current-site requester.")
                    deactivate_step["status"] = "Deactivated"
                    deactivate_step["message"] = deactivate_mutation.message
                    deactivate_step["success"] = True
                    row_notes.append(deactivate_mutation.message)
                    log(
                        "modify_function_deactivate",
                        "Deactivated current-site requester for modify-function change",
                        row_number=row.row_number,
                        details={
                            "old_site_name": old_site_name,
                            "old_site_id": old_site_id,
                            "old_pin": old_pin,
                            "guid": old_guid,
                        },
                    )

                    destination_row = ParsedRow(
                        row_number=row.row_number,
                        bod=row.new_bod if destination_customer_context else row.bod,
                        customer_name=dest_customer_name if destination_customer_context else row.customer_name,
                        last_name=row.last_name,
                        first_name=row.first_name,
                        seid=row.seid,
                        site_id=row.new_site_id,
                        site_name=row.new_site_name,
                        manual_site_name=row.manual_site_name,
                        user_pin=row.user_pin,
                        employee_id=row.employee_id,
                        new_site_id=row.new_site_id,
                        new_site_name=row.new_site_name,
                        contact_status=row.contact_status,
                        validation_status=row.validation_status,
                        notes=list(row.notes),
                        error_fields=list(row.error_fields),
                        duplicate_in_batch=row.duplicate_in_batch,
                    )

                    candidate_sites = site_cache.setdefault(dest_customer_name, client.get_sites_for_customer(dest_customer_name))
                    if not candidate_sites:
                        raise ConnectAPIError("API 3 returned no site strings for the customer.")
                    address_count_before = len(candidate_sites)
                    teid_resolution = None
                    matched_site_name = destination_row.site_name
                    resolved_teid = normalize_teid(destination_row.site_id) or None

                    if resolved_teid:
                        pin_context = client.get_pin_context(dest_customer_name, resolved_teid)
                        pin_context["siteName"] = matched_site_name
                        log("pin_context", "Loaded pin context for provided modify-function destination TEID", row_number=row.row_number, details={"resolved_teid": resolved_teid, "pin_context": pin_context})
                    else:
                        site_resolution = resolve_blank_site_id_path(destination_row, dest_customer_name, candidate_sites, client=client)
                        matched_site_name = str(site_resolution["matched_site_name"])
                        teid_resolution = dict(site_resolution["teid_resolution"])
                        resolved_teid = str(site_resolution["resolved_teid"])
                        row_notes.extend(str(note) for note in site_resolution["notes"])
                        cached_run_teid = run_new_site_teids.get(dest_customer_name, {}).get(normalize_site_name(matched_site_name))
                        if cached_run_teid:
                            resolved_teid = cached_run_teid
                            row_notes.append("Reused the same in-run TEID for a repeated new site.")
                        elif not teid_resolution.get("siteExists"):
                            resolved_teid, reused_run_teid = assign_run_new_site_teid(dest_customer_name, matched_site_name, teid_resolution)
                            if reused_run_teid:
                                row_notes.append("Reused the same in-run TEID for a repeated new site.")
                            else:
                                row_notes.append("Assigned a unique in-run TEID for a new site.")
                        log("teid_resolution", "Resolved modify-function destination TEID state", row_number=row.row_number, details={"matched_site_name": matched_site_name, "teid_resolution": teid_resolution})
                        pin_context = client.get_pin_context(dest_customer_name, resolved_teid)
                        pin_context["siteName"] = matched_site_name
                        log("pin_context", "Loaded pin context after modify-function destination TEID resolution", row_number=row.row_number, details={"resolved_teid": resolved_teid, "pin_context": pin_context})

                    pin_context = _backfill_missing_pin_context(
                        client=client,
                        customer_name=dest_customer_name,
                        pin_context=pin_context,
                        teid_resolution=teid_resolution,
                        customer_context=destination_customer_context or customer_context,
                    )
                    pin_context["siteName"] = matched_site_name or destination_row.site_name
                    pin_context.setdefault("customerName", dest_customer_name)

                    preserved_employee_id = str(row.employee_id).strip()
                    if not preserved_employee_id:
                        raise ConnectAPIError("Modify-function change requires Employee ID to build the first candidate PIN.")
                    first_choice_pin = f"{resolved_teid}{preserved_employee_id}"
                    create_step["new_site_name"] = matched_site_name or destination_row.site_name
                    create_step["new_site_id"] = resolved_teid
                    create_step["first_choice_pin"] = first_choice_pin
                    modify_function_result["new_site_name"] = matched_site_name or destination_row.site_name
                    modify_function_result["new_site_id"] = resolved_teid
                    modify_function_result["first_choice_pin"] = first_choice_pin
                    generated_pin = first_choice_pin
                    create_row = destination_row
                    modify_email_suffix = 0
                    payload = build_create_payload(create_row, pin_context, generated_pin, modify_email_suffix=modify_email_suffix)
                    log("insert_payload", "Built modify-function requester insert payload", row_number=row.row_number, details=payload)
                    mutation = client.create_user(payload)
                    payload_list.append(payload)

                    while (not mutation.success) and _looks_like_duplicate_email_error(mutation.message) and modify_email_suffix < 3:
                        modify_email_suffix += 1
                        payload = build_create_payload(create_row, pin_context, generated_pin, modify_email_suffix=modify_email_suffix)
                        if modify_email_suffix == 1:
                            row_notes.append("Modify-function base email was already registered; retried with email suffix 1.")
                        else:
                            row_notes.append(f"Modify-function email was already registered; retried with email suffix {modify_email_suffix}.")
                        log(
                            "modify_function_email_retry_payload",
                            "Retrying modify-function requester insert after duplicate email",
                            row_number=row.row_number,
                            details=payload,
                        )
                        mutation = client.create_user(payload)
                        payload_list.append(payload)

                    retried_with_fallback = False
                    fallback_pin: str | None = None
                    if not mutation.success and _looks_like_duplicate_pin_error(mutation.message):
                        if pin_context.get("maxPinCode"):
                            fallback_pin = next_pin(pin_context.get("maxPinCode"), resolved_teid or "", **_new_site_pin_settings(customer_name))
                            row_notes.append("Preserved Employee ID PIN was already in use; retried once with maxPinCode + 1.")
                        else:
                            if address_count_before is None:
                                raise ConnectAPIError("maxPinCode is null for a modify-function row that did not go through destination resolution.")
                            fallback_pin = next_new_site_pin(resolved_teid or "", **_new_site_pin_settings(customer_name))
                            row_notes.append("Preserved Employee ID PIN was already in use; retried once with account-specific new-site PIN formatting.")
                        generated_pin = fallback_pin
                        create_step["fallback_pin"] = fallback_pin
                        modify_function_result["fallback_pin"] = fallback_pin
                        payload = build_create_payload(create_row, pin_context, generated_pin, modify_email_suffix=modify_email_suffix)
                        log("modify_function_retry_payload", "Retrying modify-function requester insert after duplicate PIN", row_number=row.row_number, details=payload)
                        mutation = client.create_user(payload)
                        payload_list.append(payload)
                        retried_with_fallback = True

                        while (not mutation.success) and _looks_like_duplicate_email_error(mutation.message) and modify_email_suffix < 3:
                            modify_email_suffix += 1
                            payload = build_create_payload(create_row, pin_context, generated_pin, modify_email_suffix=modify_email_suffix)
                            if modify_email_suffix == 1:
                                row_notes.append("Modify-function base email was already registered; retried with email suffix 1.")
                            else:
                                row_notes.append(f"Modify-function email was already registered; retried with email suffix {modify_email_suffix}.")
                            log(
                                "modify_function_email_retry_payload",
                                "Retrying modify-function requester insert after duplicate email",
                                row_number=row.row_number,
                                details=payload,
                            )
                            mutation = client.create_user(payload)
                            payload_list.append(payload)

                    if mutation.guid:
                        member_matches = client.search_user_by_seid(
                            row.seid,
                            customer_ids=dest_customer_ids,
                            active_only=False,
                            allow_export_fallback=False,
                        )
                        member_match = next(
                            (match for match in member_matches if match.get("connect_guid") == mutation.guid),
                            None,
                        )
                        account_detail = client.get_account_detail(mutation.guid)
                        verification = {
                            "members_filter": member_match,
                            "account_detail": account_detail,
                        }
                        if teid_resolution and not teid_resolution.get("siteExists"):
                            refreshed_sites = client.get_sites_for_customer(customer_name)
                            verification["addresses_after"] = {
                                "total_count_before": address_count_before,
                                "total_count_after": len(refreshed_sites),
                                "site_present": matched_site_name in refreshed_sites if matched_site_name else False,
                            }

                    if mutation.success:
                        status = "Created"
                        create_step["status"] = "Created"
                        create_step["message"] = mutation.message
                        create_step["success"] = True
                        create_step["guid"] = mutation.guid
                        create_step["final_pin"] = generated_pin
                        modify_function_result["final_committed_pin"] = generated_pin
                    else:
                        status = "Manual Intervention Required"
                        create_step["status"] = "Failed"
                        create_step["message"] = mutation.message
                        create_step["success"] = False
                        create_step["guid"] = mutation.guid
                        create_step["final_pin"] = None
                        row_notes.append("Old site was already deactivated, but the new-site create did not complete. Manual intervention is required.")
                    row_notes.append(mutation.message)
                    modify_function_result["reassigned_employee_id"] = retried_with_fallback
                    registry.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.new_bod if destination_customer_context else row.bod,
                        customer_name=dest_customer_name,
                        site_id=resolved_teid or "",
                        site_name=matched_site_name or destination_row.site_name,
                        pin_9digit=generated_pin if mutation.success else None,
                        connect_guid=mutation.guid,
                        status=status,
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_results.append(
                        RowProcessingOutcome(
                            row_number=row.row_number,
                            bod=row.new_bod if destination_customer_context else row.bod,
                            customer_name=dest_customer_name,
                            seid=row.seid,
                            action=row.contact_status,
                            input_site_name=row.site_name,
                            matched_site_name=matched_site_name or destination_row.site_name,
                            resolved_site_id=resolved_teid,
                            generated_pin=generated_pin,
                            status=status,
                            notes=row_notes,
                            payload=payload,
                            connect_guid=mutation.guid,
                            response=mutation.raw_response,
                            verification=verification,
                            modify_function=modify_function_result,
                        )
                    )
                    continue

                candidate_sites: list[str] = []
                address_count_before: int | None = None
                teid_resolution: dict[str, object] | None = None
                if resolved_teid:
                    candidate_sites = site_cache.setdefault(customer_name, client.get_sites_for_customer(customer_name))
                    if not candidate_sites:
                        raise ConnectAPIError("API 3 returned no site strings for the customer.")
                    address_count_before = len(candidate_sites)
                    log("addresses", "Fetched requester site list", row_number=row.row_number, details={"customer_name": customer_name, "total_count": address_count_before})

                    manual_site_name = row.manual_site_name.strip()
                    pin_context_prefetch: dict[str, Any] | None = None
                    if manual_site_name:
                        matched_site_name = manual_site_name
                        row_notes.append("Using manually selected canonical site string.")
                        log("site_match", "Using manual site override", row_number=row.row_number, details={"matched_site_name": matched_site_name})
                    else:
                        teid_site, pin_context_prefetch = client.pin_context_with_site_name_for_teid(
                            customer_name,
                            resolved_teid,
                            row_site_hint=row.site_name,
                            candidate_addresses=candidate_sites,
                        )
                        if teid_site:
                            matched_site_name = teid_site
                            if requires_explicit_site_confirmation(row.site_name, matched_site_name):
                                row_notes.append(
                                    "CSV site name differs from Connect canonical name; using site from explicit TEID."
                                )
                            log(
                                "site_match",
                                "Using canonical site from pin context for explicit TEID",
                                row_number=row.row_number,
                                details={"matched_site_name": matched_site_name, "resolved_teid": resolved_teid},
                            )
                        else:
                            match = best_site_match(row.site_name, candidate_sites)
                            matched_site_name = match.matched_site_name
                            log(
                                "site_match",
                                "Calculated site match score",
                                row_number=row.row_number,
                                details={"score": match.score, "matched_site_name": matched_site_name},
                            )
                            if matched_site_name is None:
                                raise ConnectAPIError("Could not resolve a candidate site name from API 3 results.")
                            if match.score < SITE_MATCH_THRESHOLD or requires_explicit_site_confirmation(
                                row.site_name, matched_site_name
                            ):
                                manual_selection = _build_manual_selection_payload(row, customer_name, candidate_sites)
                                row_notes.append("Manual site selection is required before processing can continue.")
                                registry.write_pin_registry(
                                    connection,
                                    seid=row.seid,
                                    first_name=row.first_name,
                                    last_name=row.last_name,
                                    bod=row.bod,
                                    customer_name=customer_name,
                                    site_id=resolved_teid or "",
                                    site_name=row.site_name,
                                    pin_9digit=None,
                                    connect_guid=None,
                                    status="Manual Selection Required",
                                    batch_id=batch_id,
                                    created_by=created_by,
                                )
                                row_results.append(
                                    RowProcessingOutcome(
                                        row_number=row.row_number,
                                        bod=row.bod,
                                        customer_name=customer_name,
                                        seid=row.seid,
                                        action=row.contact_status,
                                        input_site_name=row.site_name,
                                        matched_site_name=None,
                                        resolved_site_id=resolved_teid,
                                        generated_pin=None,
                                        status="Manual Selection Required",
                                        notes=row_notes,
                                        manual_selection=manual_selection,
                                    )
                                )
                                continue
                    pin_context = (
                        pin_context_prefetch
                        if pin_context_prefetch is not None
                        else client.get_pin_context(customer_name, resolved_teid)
                    )
                    pin_context["siteName"] = matched_site_name
                    log("pin_context", "Loaded pin context for provided TEID", row_number=row.row_number, details={"resolved_teid": resolved_teid, "pin_context": pin_context})
                else:
                    candidate_sites = site_cache.setdefault(customer_name, client.get_sites_for_customer(customer_name))
                    if not candidate_sites:
                        raise ConnectAPIError("API 3 returned no site strings for the customer.")
                    address_count_before = len(candidate_sites)
                    log("addresses", "Fetched requester site list", row_number=row.row_number, details={"customer_name": customer_name, "total_count": address_count_before})
                    site_resolution = resolve_blank_site_id_path(row, customer_name, candidate_sites, client=client)
                    site_resolution_strategy = str(site_resolution["strategy"])
                    matched_site_name = str(site_resolution["matched_site_name"])
                    match_score = site_resolution["match_score"]
                    teid_resolution = dict(site_resolution["teid_resolution"])
                    resolved_teid = str(site_resolution["resolved_teid"])
                    row_notes.extend(str(note) for note in site_resolution["notes"])
                    cached_run_teid = run_new_site_teids.get(customer_name, {}).get(normalize_site_name(matched_site_name))
                    if cached_run_teid:
                        resolved_teid = cached_run_teid
                        row_notes.append("Reused the same in-run TEID for a repeated new site.")
                    elif not teid_resolution.get("siteExists"):
                        resolved_teid, reused_run_teid = assign_run_new_site_teid(customer_name, matched_site_name, teid_resolution)
                        if reused_run_teid:
                            row_notes.append("Reused the same in-run TEID for a repeated new site.")
                        else:
                            row_notes.append("Assigned a unique in-run TEID for a new site.")
                    if site_resolution["strategy"] == "manual":
                        log("site_match", "Using manual site override", row_number=row.row_number, details={"matched_site_name": matched_site_name})
                    elif site_resolution["strategy"] == "existing":
                        log("site_match", "Calculated site match score", row_number=row.row_number, details={"score": match_score, "matched_site_name": matched_site_name})
                        if requires_explicit_site_confirmation(row.site_name, matched_site_name):
                            manual_selection = _build_manual_selection_payload(row, customer_name, candidate_sites)
                            row_notes.append("Manual site selection is required before processing can continue.")
                            registry.write_pin_registry(
                                connection,
                                seid=row.seid,
                                first_name=row.first_name,
                                last_name=row.last_name,
                                bod=row.bod,
                                customer_name=customer_name,
                                site_id="",
                                site_name=row.site_name,
                                pin_9digit=None,
                                connect_guid=None,
                                status="Manual Selection Required",
                                batch_id=batch_id,
                                created_by=created_by,
                            )
                            row_results.append(
                                RowProcessingOutcome(
                                    row_number=row.row_number,
                                    bod=row.bod,
                                    customer_name=customer_name,
                                    seid=row.seid,
                                    action=row.contact_status,
                                    input_site_name=row.site_name,
                                    matched_site_name=None,
                                    resolved_site_id=None,
                                    generated_pin=None,
                                    status="Manual Selection Required",
                                    notes=row_notes,
                                    manual_selection=manual_selection,
                                )
                            )
                            continue
                    else:
                        log("site_match", "Treating original site string as new-site candidate", row_number=row.row_number, details={"matched_site_name": matched_site_name})

                    log("teid_resolution", "Resolved TEID state for canonical site", row_number=row.row_number, details={"matched_site_name": matched_site_name, "teid_resolution": teid_resolution})
                    if teid_resolution.get("siteExists"):
                        row_notes.append("Resolved TEID from existing QA site.")

                    pin_context = client.get_pin_context(customer_name, resolved_teid)
                    if site_resolution_strategy in ("new", "sharepoint"):
                        pin_context["siteName"] = matched_site_name
                    log("pin_context", "Loaded pin context after TEID resolution", row_number=row.row_number, details={"resolved_teid": resolved_teid, "pin_context": pin_context})

                pin_context = _backfill_missing_pin_context(
                    client=client,
                    customer_name=customer_name,
                    pin_context=pin_context,
                    teid_resolution=teid_resolution,
                    customer_context=customer_context,
                )
                pin_context["siteName"] = matched_site_name or row.site_name
                pin_context.setdefault("customerName", customer_name)

                existing_matches = client.search_user_by_seid(
                    row.seid,
                    customer_ids=customer_ids,
                    active_only=False,
                    allow_export_fallback=False,
                )
                log("existing_requester_search", "Searched existing requester matches", row_number=row.row_number, details={"seid": row.seid, "matches": len(existing_matches)})
                active_same_site = next(
                    (
                        match
                        for match in existing_matches
                        if normalize_teid(match.get("teid")) == normalize_teid(resolved_teid)
                        and str(match.get("account_status", "")).lower() == "active"
                    ),
                    None,
                )
                if active_same_site is not None:
                    row_notes.append("SEID already exists for this TEID.")
                    registry.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        customer_name=customer_name,
                        site_id=resolved_teid or "",
                        site_name=matched_site_name or row.site_name,
                        pin_9digit=active_same_site.get("pin_code"),
                        connect_guid=active_same_site.get("connect_guid"),
                        status="Already Exists",
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_results.append(
                        RowProcessingOutcome(
                            row_number=row.row_number,
                            bod=row.bod,
                            customer_name=customer_name,
                            seid=row.seid,
                            action=row.contact_status,
                            input_site_name=row.site_name,
                            matched_site_name=matched_site_name or row.site_name,
                            resolved_site_id=resolved_teid,
                            generated_pin=active_same_site.get("pin_code"),
                            status="Already Exists",
                            notes=row_notes,
                            connect_guid=active_same_site.get("connect_guid"),
                        )
                    )
                    continue

                if pin_context.get("maxPinCode"):
                    generated_pin = next_pin(pin_context.get("maxPinCode"), resolved_teid or "", **_new_site_pin_settings(customer_name))
                    row_notes.append("Generated PIN using maxPinCode + 1.")
                    log("pin_generation", "Generated PIN from existing maxPinCode", row_number=row.row_number, details={"resolved_teid": resolved_teid, "previous_max_pin": pin_context.get("maxPinCode"), "generated_pin": generated_pin})
                else:
                    if address_count_before is None:
                        raise ConnectAPIError("maxPinCode is null for a requester row that did not go through new-site resolution.")
                    generated_pin = next_new_site_pin(
                        resolved_teid or "",
                        **_new_site_pin_settings(customer_name),
                    )
                    row_notes.append("Generated PIN using account-specific new-site PIN formatting.")
                    log("pin_generation", "Generated PIN using new-site first PIN rule", row_number=row.row_number, details={"resolved_teid": resolved_teid, "generated_pin": generated_pin})

                payload = build_create_payload(row, pin_context, generated_pin)
                log("insert_payload", "Built requester insert payload", row_number=row.row_number, details=payload)
                mutation = client.create_user(payload)
                payload_list.append(payload)
                log("insert_response", "Requester insert completed", row_number=row.row_number, details=mutation.raw_response)

                if mutation.guid:
                    member_matches = client.search_user_by_seid(
                        row.seid,
                        customer_ids=customer_ids,
                        active_only=False,
                        allow_export_fallback=False,
                    )
                    member_match = next(
                        (match for match in member_matches if match.get("connect_guid") == mutation.guid),
                        None,
                    )
                    account_detail = client.get_account_detail(mutation.guid)
                    verification = {
                        "members_filter": member_match,
                        "account_detail": account_detail,
                    }
                    if teid_resolution and not teid_resolution.get("siteExists"):
                        refreshed_sites = client.get_sites_for_customer(customer_name)
                        verification["addresses_after"] = {
                            "total_count_before": address_count_before,
                            "total_count_after": len(refreshed_sites),
                            "site_present": matched_site_name in refreshed_sites if matched_site_name else False,
                        }
                    log("post_create_verification", "Collected post-create verification", row_number=row.row_number, details=verification)

                status = "Created" if mutation.success else "Failed"
                row_notes.append(mutation.message)
                registry.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    customer_name=customer_name,
                    site_id=resolved_teid or "",
                    site_name=matched_site_name or row.site_name,
                    pin_9digit=generated_pin,
                    connect_guid=mutation.guid,
                    status=status,
                    batch_id=batch_id,
                    created_by=created_by,
                )
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=customer_name,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=matched_site_name or row.site_name,
                        resolved_site_id=resolved_teid,
                        generated_pin=generated_pin,
                        status=status,
                        notes=row_notes,
                        payload=payload,
                        connect_guid=mutation.guid,
                        response=mutation.raw_response,
                        verification=verification,
                    )
                )
            except ConnectAPIError as exc:
                row_notes.append(str(exc))
                failure_status = "Failed"
                if row.contact_status == "Modify-Function Change" and modify_function_result:
                    deactivate_step = modify_function_result.get("deactivate_step") or {}
                    create_step = modify_function_result.get("create_step") or {}
                    if deactivate_step.get("success"):
                        failure_status = "Manual Intervention Required"
                        create_step["status"] = "Failed"
                        create_step["message"] = str(exc)
                        create_step["success"] = False
                        create_step["final_pin"] = None
                        row_notes.append("Old site was already deactivated, but the new-site create did not complete. Manual intervention is required.")
                registry.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    customer_name=customer_name,
                    site_id=resolved_teid or "",
                    site_name=matched_site_name or row.site_name,
                    pin_9digit=generated_pin if failure_status != "Manual Intervention Required" else None,
                    connect_guid=None,
                    status=failure_status,
                    batch_id=batch_id,
                    created_by=created_by,
                )
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=customer_name,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=matched_site_name,
                        resolved_site_id=resolved_teid,
                        generated_pin=generated_pin,
                        status=failure_status,
                        notes=row_notes,
                        verification=verification,
                        modify_function=modify_function_result,
                    )
                )

        summary = _build_summary(row_results)
        output_path: str | None = None
        if write_output:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_file = OUTPUT_DIR / f"batch_{batch_id}.json"
            output_file.write_text(
                json.dumps(
                    {
                        "batch_id": batch_id,
                        "summary": summary,
                        "payloads": payload_list,
                        "rows": [row.to_dict() for row in row_results],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            output_path = str(output_file)

        registry.write_batch_audit(
            connection,
            batch_id=batch_id,
            source_name=source_name,
            created_by=created_by,
            total_rows=len(row_results),
            summary=summary,
            output_path=output_path,
        )

    return ProcessingRunResult(
        batch_id=batch_id,
        payloads=payload_list,
        row_results=row_results,
        logs=logs,
        summary=summary,
        output_path=output_path,
    )


def process_input_file(
    input_path: str | Path,
    *,
    client: ConnectQAClient,
    created_by: str = "QA OPI Operator",
    db_path: Path = DB_PATH,
    write_output: bool = True,
) -> ProcessingRunResult:
    rows = parse_input_file(input_path)
    return process_rows(
        rows,
        client=client,
        created_by=created_by,
        db_path=db_path,
        source_name=Path(input_path).name,
        write_output=write_output,
    )
