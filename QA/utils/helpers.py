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


def teid_digits(value: Any) -> str:
    digits = "".join(character for character in normalize_text(value) if character.isdigit())
    return digits or normalize_teid(value)


def extract_teid_from_pin(pin_value: Any) -> str:
    digits = "".join(character for character in normalize_text(pin_value) if character.isdigit())
    if len(digits) < 4:
        return ""
    return digits[:4]


def next_pin(
    max_pin_code: str | None,
    teid: str,
    *,
    suffix_width: int | None = None,
    total_length: int | None = None,
) -> str:
    if not max_pin_code:
        return next_new_site_pin(teid, suffix_width=suffix_width, total_length=total_length)
    return str(int(str(max_pin_code)) + 1)


def next_new_site_pin(
    teid: str,
    *,
    suffix_width: int | None = None,
    total_length: int | None = None,
) -> str:
    teid_seed = teid_digits(teid)
    if total_length is not None:
        safe_total_length = max(int(total_length), len(teid_seed) + 1)
        safe_suffix_width = max(safe_total_length - len(teid_seed), 1)
    else:
        safe_suffix_width = max(int(suffix_width or 5), 1)
    return f"{teid_seed}{1:0{safe_suffix_width}d}"


def coerce_form_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def is_missing_fk_value(value: Any) -> bool:
    return value in (None, "", 0, "0")


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
