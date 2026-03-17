"""Main processing engine for the v7 mock IRS PIN flow."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Iterable

from . import database, payloads
from .config import DB_PATH, OUTPUT_DIR, SITE_MATCH_THRESHOLD
from .matching import best_site_match
from .models import ParsedRow, ProcessingRunResult, RowProcessingOutcome
from .parser import parse_input_file
from .services import MockInternalAPI


def next_pin(max_pin_code: str | None, teid: str) -> str:
    if not max_pin_code:
        return f"{teid}00001"
    return str(int(max_pin_code) + 1)


def process_rows(
    rows: Iterable[ParsedRow],
    *,
    created_by: str = "Mock OPI Operator",
    db_path: Path = DB_PATH,
    write_output: bool = True,
) -> ProcessingRunResult:
    if not db_path.exists():
        database.initialize_database(db_path)

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

    with database.get_connection(db_path) as connection:
        api = MockInternalAPI(connection)
        site_cache: dict[str, list[str]] = {}

        for row in rows:
            row_notes = list(row.notes)
            matched_site_name: str | None = None
            resolved_teid: str | None = row.site_id or None
            generated_pin: str | None = None
            customer_name: str | None = None

            log("row_start", "Processing row", row_number=row.row_number, details={"seid": row.seid, "action": row.contact_status})

            if row.validation_status == "Error":
                row_notes.append(f"Missing/invalid fields: {', '.join(row.error_fields)}")
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=None,
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
                log("validation", "Row failed validation", row_number=row.row_number, details={"errors": row.error_fields})
                continue

            if row.duplicate_in_batch:
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=None,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=None,
                        resolved_site_id=row.site_id or None,
                        generated_pin=None,
                        status="Skipped",
                        notes=row_notes,
                    )
                )
                log("duplicate", "Skipped duplicate SEID in batch", row_number=row.row_number)
                continue

            customer = api.get_customer_by_bod(row.bod)
            if customer is None:
                database.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    site_id=row.site_id,
                    site_name=row.site_name,
                    pin_9digit=None,
                    connect_guid=None,
                    status="Failed",
                    batch_id=batch_id,
                    created_by=created_by,
                )
                row_notes.append("Unknown BOD code.")
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=None,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=None,
                        resolved_site_id=row.site_id or None,
                        generated_pin=None,
                        status="Failed",
                        notes=row_notes,
                    )
                )
                log("bod_lookup", "BOD lookup failed", row_number=row.row_number, details={"bod": row.bod})
                continue

            customer_name = customer["customer_name"]
            log("bod_lookup", "Resolved customer name", row_number=row.row_number, details={"customer_name": customer_name})

            if row.contact_status == "Deactivate":
                existing = api.search_user_by_seid(customer_name=customer_name, seid=row.seid)
                if not existing:
                    database.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        site_id=row.site_id,
                        site_name=row.site_name,
                        pin_9digit=None,
                        connect_guid=None,
                        status="Failed",
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_notes.append("SEID not found for deactivate.")
                    row_results.append(
                        RowProcessingOutcome(
                            row_number=row.row_number,
                            bod=row.bod,
                            customer_name=customer_name,
                            seid=row.seid,
                            action="Deactivate",
                            input_site_name=row.site_name,
                            matched_site_name=None,
                            resolved_site_id=row.site_id or None,
                            generated_pin=None,
                            status="Failed",
                            notes=row_notes,
                        )
                    )
                    log("search", "No active user found for deactivate", row_number=row.row_number, details={"seid": row.seid})
                    continue

                latest_user = existing[-1]
                payload = payloads.build_deactivate_payload(latest_user)
                deactivated = database.deactivate_requestor(
                    connection,
                    customer_name=customer_name,
                    seid=row.seid,
                )
                if deactivated is None:
                    continue

                database.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    site_id=deactivated["teid"],
                    site_name=deactivated["site_name"],
                    pin_9digit=deactivated["pin_code"],
                    connect_guid=deactivated["connect_guid"],
                    status="Deactivated",
                    batch_id=batch_id,
                    created_by=created_by,
                )
                payload_list.append(payload)
                row_notes.append("Deactivate payload ready.")
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=customer_name,
                        seid=row.seid,
                        action="Deactivate",
                        input_site_name=row.site_name,
                        matched_site_name=deactivated["site_name"],
                        resolved_site_id=deactivated["teid"],
                        generated_pin=deactivated["pin_code"],
                        status="Deactivated",
                        notes=row_notes,
                        payload=payload,
                    )
                )
                log("deactivate", "Built deactivate payload", row_number=row.row_number, details={"guid": deactivated["connect_guid"]})
                continue

            if row.site_id:
                resolved_teid = row.site_id.zfill(4)
                site_record = api.get_site_by_teid(customer_name, resolved_teid)
                if site_record is None:
                    site_record = api.ensure_direct_teid_placeholder(
                        customer_name=customer_name,
                        bod_code=row.bod,
                        teid=resolved_teid,
                        site_name=row.site_name or f"Legacy TEID {resolved_teid}",
                    )
                    row_notes.append("Seeded placeholder site record for direct TEID.")
                matched_site_name = site_record["site_name"] or row.site_name
                log("site_teid", "Resolved site from direct TEID", row_number=row.row_number, details={"teid": resolved_teid, "site_name": matched_site_name})
            else:
                candidate_sites = site_cache.setdefault(customer_name, api.get_sites_for_customer(customer_name))
                log("api3_sites", "Loaded site list for customer", row_number=row.row_number, details={"site_count": len(candidate_sites)})
                if not candidate_sites:
                    database.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        site_id="",
                        site_name=row.site_name,
                        pin_9digit=None,
                        connect_guid=None,
                        status="Failed",
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_notes.append("No site strings returned for BOD.")
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
                            status="Failed",
                            notes=row_notes,
                        )
                    )
                    continue

                match = best_site_match(row.site_name, candidate_sites)
                matched_site_name = match.matched_site_name
                log("site_match", "Scored site name match", row_number=row.row_number, details={"input_site_name": row.site_name, "matched_site_name": matched_site_name, "score": match.score})
                if matched_site_name is None or match.score < SITE_MATCH_THRESHOLD:
                    database.write_pin_registry(
                        connection,
                        seid=row.seid,
                        first_name=row.first_name,
                        last_name=row.last_name,
                        bod=row.bod,
                        site_id="",
                        site_name=row.site_name,
                        pin_9digit=None,
                        connect_guid=None,
                        status="Failed",
                        batch_id=batch_id,
                        created_by=created_by,
                    )
                    row_notes.append(
                        f"Site match score {match.score} below threshold {SITE_MATCH_THRESHOLD}."
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
                            resolved_site_id=None,
                            generated_pin=None,
                            status="Failed",
                            notes=row_notes,
                        )
                    )
                    continue

                teid_resolution = api.resolve_teid(customer_name, matched_site_name)
                if teid_resolution["siteExists"]:
                    resolved_teid = teid_resolution["existingTeid"]
                    row_notes.append("Resolved TEID from existing site match.")
                else:
                    created_site = api.create_site_for_customer(customer_name, matched_site_name)
                    resolved_teid = created_site["teid"]
                    row_notes.append("Assigned new TEID from customer max TEID.")
                log("api2_teid", "Resolved TEID from site name", row_number=row.row_number, details={"teid": resolved_teid, "site_exists": teid_resolution["siteExists"]})

            existing_matches = api.search_user_by_seid(customer_name=customer_name, seid=row.seid)
            active_same_site = next(
                (match for match in existing_matches if match["teid"] == resolved_teid),
                None,
            )
            if active_same_site is not None:
                database.write_pin_registry(
                    connection,
                    seid=row.seid,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    bod=row.bod,
                    site_id=resolved_teid or "",
                    site_name=active_same_site["site_name"],
                    pin_9digit=active_same_site["pin_code"],
                    connect_guid=active_same_site["connect_guid"],
                    status="Already Exists",
                    batch_id=batch_id,
                    created_by=created_by,
                )
                row_notes.append("SEID already exists for this TEID.")
                row_results.append(
                    RowProcessingOutcome(
                        row_number=row.row_number,
                        bod=row.bod,
                        customer_name=customer_name,
                        seid=row.seid,
                        action=row.contact_status,
                        input_site_name=row.site_name,
                        matched_site_name=matched_site_name or active_same_site["site_name"],
                        resolved_site_id=resolved_teid,
                        generated_pin=active_same_site["pin_code"],
                        status="Already Exists",
                        notes=row_notes,
                    )
                )
                log("search", "SEID already active for resolved TEID", row_number=row.row_number, details={"teid": resolved_teid})
                continue

            pin_context = api.get_pin_context(customer_name, resolved_teid or "")
            generated_pin = next_pin(pin_context["maxPinCode"], resolved_teid or "")
            payload = payloads.build_create_payload(row, pin_context, generated_pin)
            inserted = database.record_created_requestor(
                connection,
                seid=row.seid,
                first_name=row.first_name,
                last_name=row.last_name,
                email=payload["email"],
                pin_code=generated_pin,
                teid=resolved_teid or "",
                site_name=matched_site_name or row.site_name,
                customer_name=customer_name,
                bod_code=row.bod,
            )
            database.write_pin_registry(
                connection,
                seid=row.seid,
                first_name=row.first_name,
                last_name=row.last_name,
                bod=row.bod,
                site_id=resolved_teid or "",
                site_name=matched_site_name or row.site_name,
                pin_9digit=generated_pin,
                connect_guid=inserted["connect_guid"],
                status="Created",
                batch_id=batch_id,
                created_by=created_by,
            )
            payload_list.append(payload)
            row_notes.append("Create payload ready.")
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
                    status="Created",
                    notes=row_notes,
                    payload=payload,
                )
            )
            log("api1_pin", "Resolved pin context and generated PIN", row_number=row.row_number, details={"teid": resolved_teid, "generated_pin": generated_pin, "fk_customer": pin_context["fK_Customer"], "fk_location": pin_context["fK_Location"]})

    output_path: str | None = None
    if write_output:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"payloads_{batch_id}.json"
        path.write_text(json.dumps(payload_list, indent=2), encoding="utf-8")
        output_path = str(path)

    return ProcessingRunResult(
        batch_id=batch_id,
        payloads=payload_list,
        row_results=row_results,
        logs=logs,
        output_path=output_path,
    )


def process_input_file(
    input_path: str | Path,
    *,
    created_by: str = "Mock OPI Operator",
    db_path: Path = DB_PATH,
) -> Path:
    rows = parse_input_file(input_path)
    run_result = process_rows(rows, created_by=created_by, db_path=db_path, write_output=True)
    return Path(run_result.output_path) if run_result.output_path is not None else OUTPUT_DIR
