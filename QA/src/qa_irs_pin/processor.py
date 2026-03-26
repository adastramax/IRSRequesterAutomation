"""Main processor that preserves the validated mock flow and swaps in live QA APIs."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Iterable

from qa_irs_pin import registry
from qa_irs_pin.config import DB_PATH, OUTPUT_DIR, SITE_MATCH_THRESHOLD
from qa_irs_pin.matching import best_site_match, normalize_site_name, requires_explicit_site_confirmation, tokenize, top_site_matches
from qa_irs_pin.models import ParsedRow, ProcessingRunResult, RowProcessingOutcome
from qa_irs_pin.parser import parse_input_file
from qa_irs_pin.payloads import build_create_payload, build_deactivate_payload
from utils.client import ConnectAPIError, ConnectQAClient
from utils.helpers import next_new_site_pin, next_pin, normalize_teid, resolve_customer_context


def _build_summary(row_results: list[RowProcessingOutcome]) -> dict[str, int]:
    counts = Counter(row.status for row in row_results)
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
        current_max_teid = normalize_teid(teid_resolution.get("currentMaxTeid"))
        if not current_max_teid:
            raise ConnectAPIError("API 2 did not return currentMaxTeid for a new site.")
        resolved_teid = str(int(current_max_teid) + 1).zfill(4)

    return {
        "matched_site_name": matched_site_name,
        "match_score": match_score,
        "teid_resolution": teid_resolution,
        "resolved_teid": resolved_teid,
        "strategy": strategy,
        "notes": notes,
    }


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
                    existing = client.search_user_by_seid(row.seid, customer_ids=customer_ids, active_only=False)
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
                    if manual_site_name:
                        matched_site_name = manual_site_name
                        row_notes.append("Using manually selected canonical site string.")
                        log("site_match", "Using manual site override", row_number=row.row_number, details={"matched_site_name": matched_site_name})
                    else:
                        match = best_site_match(row.site_name, candidate_sites)
                        matched_site_name = match.matched_site_name
                        log("site_match", "Calculated site match score", row_number=row.row_number, details={"score": match.score, "matched_site_name": matched_site_name})
                        if matched_site_name is None:
                            raise ConnectAPIError("Could not resolve a candidate site name from API 3 results.")
                        if match.score < SITE_MATCH_THRESHOLD or requires_explicit_site_confirmation(row.site_name, matched_site_name):
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
                    pin_context = client.get_pin_context(customer_name, resolved_teid)
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
                    if site_resolution_strategy == "new":
                        pin_context["siteName"] = matched_site_name
                    log("pin_context", "Loaded pin context after TEID resolution", row_number=row.row_number, details={"resolved_teid": resolved_teid, "pin_context": pin_context})

                if not pin_context.get("fK_Customer") and customer_context.get("fk_customer"):
                    pin_context["fK_Customer"] = customer_context["fk_customer"]
                pin_context["siteName"] = matched_site_name or row.site_name
                pin_context.setdefault("customerName", customer_name)

                existing_matches = client.search_user_by_seid(row.seid, customer_ids=customer_ids, active_only=False)
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
                    generated_pin = next_pin(pin_context.get("maxPinCode"), resolved_teid or "")
                    row_notes.append("Generated PIN using maxPinCode + 1.")
                    log("pin_generation", "Generated PIN from existing maxPinCode", row_number=row.row_number, details={"resolved_teid": resolved_teid, "previous_max_pin": pin_context.get("maxPinCode"), "generated_pin": generated_pin})
                else:
                    if address_count_before is None:
                        raise ConnectAPIError("maxPinCode is null for a requester row that did not go through new-site resolution.")
                    generated_pin = next_new_site_pin(resolved_teid or "")
                    row_notes.append("Generated PIN using new-site first PIN rule: TEID + 00001.")
                    log("pin_generation", "Generated PIN using new-site first PIN rule", row_number=row.row_number, details={"resolved_teid": resolved_teid, "generated_pin": generated_pin})

                payload = build_create_payload(row, pin_context, generated_pin)
                log("insert_payload", "Built requester insert payload", row_number=row.row_number, details=payload)
                mutation = client.create_user(payload)
                payload_list.append(payload)
                log("insert_response", "Requester insert completed", row_number=row.row_number, details=mutation.raw_response)

                if mutation.guid:
                    export_match = client.get_export_requester_by_guid(mutation.guid, customer_ids=customer_ids, active_only=False)
                    account_detail = client.get_account_detail(mutation.guid)
                    verification = {
                        "exports_filter": export_match,
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
                    connect_guid=None,
                    status="Failed",
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
                        status="Failed",
                        notes=row_notes,
                        verification=verification,
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
