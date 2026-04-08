"""Small helpers shared across the QA implementation."""

from __future__ import annotations

import re
from typing import Any

from qa_irs_pin.config import BOD_LOOKUP, CUSTOMER_LOOKUP


BOD_ALIASES = {
    "TS FA": "FA",
}

BOD_HINT_ALIASES = {
    "FA": "FA",
    "TSFA": "FA",
    "WIFA": "FA",
    "IRSFA": "FA",
    "WIFIELDASSISTANCE": "FA",
    "FIELDASSISTANCE": "FA",
    "TSFIELDASSISTANCE": "FA",
    "AM": "AM",
    "WIAM": "AM",
    "IRSAM": "AM",
    "WIACCOUNTMANAGEMENT": "AM",
    "ACCOUNTMANAGEMENT": "AM",
    "TSACCOUNTMANAGEMENT": "AM",
    "TAS": "TAS",
    "IRSTAS": "TAS",
    "TAXPAYERADVOCATESERVICE": "TAS",
    "SBSE": "SBSE",
    "IRSSBSE": "SBSE",
    "SMALLBUSINESSSELFEMPLOYED": "SBSE",
    "CC": "CC",
    "IRSCC": "CC",
    "CHIEFCOUNSEL": "CC",
    "CI": "CI",
    "IRSCI": "CI",
    "CRIMINALINVESTIGATION": "CI",
    "TEGE": "TEGE",
    "IRSTEGE": "TEGE",
    "TEGEEOG": "TEGE",
    "TEGEOG": "TEGE",
    "TEGEEOG": "TEGE",
    "TEGE": "TEGE",
    "EXEMPTORGANIZATIONSGOVERNMENT": "TEGE",
    "LBI": "LB&I",
    "LBANDI": "LB&I",
    "IRSLBI": "LB&I",
    "LBI": "LB&I",
    "LARGEBUSINESSINTERNATIONAL": "LB&I",
    "EPSS": "EPSS",
    "WIEPSS": "EPSS",
    "IRSEPSS": "EPSS",
    "WIELECTRONICPRODUCTSSERVICESSUPPORT": "EPSS",
    "ELECTRONICPRODUCTSSERVICESSUPPORT": "EPSS",
    "RICS": "RICS",
    "RICE": "RICS",
    "WIRICS": "RICS",
    "IRSRICS": "RICS",
    "WIRETURNINTEGRITYCOMPLIANCESERVICES": "RICS",
    "RETURNINTEGRITYCOMPLIANCESERVICES": "RICS",
    "SPEC": "SPEC",
    "IRSSPEC": "SPEC",
    "TSSPEC": "SPEC",
    "STAKEHOLDERPARTNERSHIPSEDUCATIONCOMMUNICATION": "SPEC",
    "FMSS": "FMSS",
    "IRSFMSS": "FMSS",
    "FACILITIESMANAGEMENTSECURITYSERVICES": "FMSS",
    "APPEALS": "APPEALS",
    "IRSAPPEALS": "APPEALS",
    "INDEPENDENTAPPEALS": "APPEALS",
    "INDEPENDENTOFFICEOFAPPEALS": "APPEALS",
    "MEDIA": "MEDIA",
    "IRSMEDIA": "MEDIA",
    "TSMEDIA": "MEDIA",
    "TSMEDIAPUBLICATIONSDISTRIBUTION": "MEDIA",
    "MEDIAPUBLICATIONSDISTRIBUTION": "MEDIA",
    "ZDEMO": "Z-DEMO",
    "ZORIENTATION": "Z-ORIENTATION",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_lookup_token(value: Any) -> str:
    text = normalize_text(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def infer_bod_key(value: Any) -> str | None:
    normalized = normalize_text(value)
    if not normalized:
        return None

    exact_key = normalized.upper()
    if exact_key in BOD_LOOKUP:
        return exact_key
    if exact_key in BOD_ALIASES:
        return BOD_ALIASES[exact_key]

    token = normalize_lookup_token(normalized)
    if token in BOD_HINT_ALIASES:
        return BOD_HINT_ALIASES[token]

    for bod_key, payload in BOD_LOOKUP.items():
        customer_token = normalize_lookup_token(payload["customer_name"])
        if token == customer_token or token in customer_token or customer_token in token:
            return bod_key

    contains_rules = (
        (("TS", "FA"), "FA"),
        (("WI", "FA"), "FA"),
        (("FIELD", "ASSIST"), "FA"),
        (("TS", "AM"), "AM"),
        (("WI", "AM"), "AM"),
        (("ACCOUNT", "MANAGEMENT"), "AM"),
        (("TAXPAYER", "ADVOCATE"), "TAS"),
        (("SBSE",), "SBSE"),
        (("SMALL", "BUSINESS"), "SBSE"),
        (("CHIEF", "COUNSEL"), "CC"),
        (("CRIMINAL", "INVESTIGATION"), "CI"),
        (("LB", "I"), "LB&I"),
        (("LARGE", "BUSINESS"), "LB&I"),
        (("TE", "GE"), "TEGE"),
        (("EXEMPT", "GOVERNMENT"), "TEGE"),
        (("EXEMPT", "ORGANIZATION"), "TEGE"),
        (("WI", "EPSS"), "EPSS"),
        (("EPSS",), "EPSS"),
        (("WI", "EPSS"), "EPSS"),
        (("RICS",), "RICS"),
        (("RICE",), "RICS"),
        (("RETURN", "INTEGRITY"), "RICS"),
        (("SPEC",), "SPEC"),
        (("STAKEHOLDER", "PARTNERSHIP"), "SPEC"),
        (("FMSS",), "FMSS"),
        (("FACILITIES", "SECURITY"), "FMSS"),
        (("MEDIA",), "MEDIA"),
        (("MEDIA", "PUBLICATION"), "MEDIA"),
        (("INDEPENDENT", "APPEALS"), "APPEALS"),
        (("OFFICE", "APPEALS"), "APPEALS"),
    )
    for fragments, mapped_key in contains_rules:
        if all(fragment in token for fragment in fragments):
            return mapped_key

    return None


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


def extract_employee_id_from_pin(pin_value: Any) -> str:
    digits = "".join(character for character in normalize_text(pin_value) if character.isdigit())
    if len(digits) <= 4:
        return ""
    return digits[4:]


def normalize_pin_value(pin_value: Any) -> str:
    return "".join(character for character in normalize_text(pin_value) if character.isdigit())


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
        inferred_override_key = infer_bod_key(override)
        if inferred_override_key is not None:
            return dict(BOD_LOOKUP[inferred_override_key])
        match = CUSTOMER_LOOKUP.get(override.lower())
        if match is not None:
            return dict(match)
        for customer_name, payload in CUSTOMER_LOOKUP.items():
            override_token = normalize_lookup_token(override)
            customer_token = normalize_lookup_token(customer_name)
            if override_token and (override_token == customer_token or override_token in customer_token or customer_token in override_token):
                return dict(payload)
        return {"bod_code": bod.upper(), "customer_name": override, "fk_customer": None}

    inferred_bod_key = infer_bod_key(bod)
    if inferred_bod_key is not None:
        return dict(BOD_LOOKUP[inferred_bod_key])

    lookup_key = normalize_text(bod).upper()
    lookup_key = BOD_ALIASES.get(lookup_key, lookup_key)
    match = BOD_LOOKUP.get(lookup_key)
    return None if match is None else dict(match)
