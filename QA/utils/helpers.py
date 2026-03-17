"""Small helpers shared across the QA implementation."""

from __future__ import annotations

from typing import Any

from qa_irs_pin.config import BOD_LOOKUP, CUSTOMER_LOOKUP


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_teid(value: Any) -> str:
    digits = "".join(character for character in normalize_text(value) if character.isdigit())
    return digits.zfill(4) if digits else ""


def extract_teid_from_pin(pin_value: Any) -> str:
    digits = "".join(character for character in normalize_text(pin_value) if character.isdigit())
    if len(digits) < 4:
        return ""
    return digits[:4]


def next_pin(max_pin_code: str | None, teid: str) -> str:
    normalized_teid = normalize_teid(teid)
    if not max_pin_code:
        return f"{normalized_teid}00001"
    return str(int(str(max_pin_code)) + 1)


def next_new_site_pin(teid: str) -> str:
    normalized_teid = normalize_teid(teid)
    return f"{normalized_teid}00001"


def coerce_form_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def resolve_customer_context(bod: str, customer_name_override: str | None = None) -> dict[str, Any] | None:
    override = normalize_text(customer_name_override)
    if override:
        alias_match = BOD_LOOKUP.get(override.upper())
        if alias_match is not None:
            return dict(alias_match)
        match = CUSTOMER_LOOKUP.get(override.lower())
        if match is not None:
            return dict(match)
        return {"bod_code": bod.upper(), "customer_name": override, "fk_customer": None}

    lookup_key = normalize_text(bod).upper()
    match = BOD_LOOKUP.get(lookup_key)
    return None if match is None else dict(match)
