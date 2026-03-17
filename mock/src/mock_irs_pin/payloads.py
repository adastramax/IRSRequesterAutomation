"""Connect payload builders for the mock flow."""

from __future__ import annotations

import re

from .config import (
    DEFAULT_NATIVE_LANGUAGE,
    DEFAULT_PRECALL_POLICY,
    DEFAULT_SERVICE_TYPE,
    DEFAULT_TIMEZONE,
    EMAIL_DOMAIN,
    PAYLOAD_DEFAULTS,
)


def sanitize_email_part(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace(" ", ".")
    collapsed = re.sub(r"[^a-z0-9.-]+", ".", lowered)
    collapsed = re.sub(r"\.+", ".", collapsed)
    return collapsed.strip(".")


def build_email(seid: str, first_name: str, last_name: str) -> str:
    parts = [
        sanitize_email_part(seid),
        sanitize_email_part(last_name),
        sanitize_email_part(first_name),
    ]
    local_part = ".".join(part for part in parts if part)
    return f"{local_part}@{EMAIL_DOMAIN}"


def build_create_payload(row, site_context: dict, pin_code: str) -> dict:
    return {
        "firstName": row.seid,
        "lastName": f"{row.last_name} {row.first_name}",
        "email": build_email(row.seid, row.first_name, row.last_name),
        "pinCode": int(pin_code),
        "pinCodeString": pin_code,
        "fK_Customer": site_context["fK_Customer"],
        "fK_Location": site_context["fK_Location"],
        "SubCustomerIds": site_context["fK_Customer"],
        "fK_ServiceType": DEFAULT_SERVICE_TYPE,
        "serviceTypes": DEFAULT_SERVICE_TYPE,
        "fk_PreCallPolicy": DEFAULT_PRECALL_POLICY,
        "fK_DefaultNativeLanguage": DEFAULT_NATIVE_LANGUAGE,
        "fK_DefaultTimeZone": DEFAULT_TIMEZONE,
        "role": "User",
        "userType": "CONSUMER",
        "country": PAYLOAD_DEFAULTS["country"],
        "city": PAYLOAD_DEFAULTS["city"],
        "address": PAYLOAD_DEFAULTS["address"],
        "state": PAYLOAD_DEFAULTS["state"],
        "postalCode": PAYLOAD_DEFAULTS["postal_code"],
        "latitude": PAYLOAD_DEFAULTS["latitude"],
        "longitude": PAYLOAD_DEFAULTS["longitude"],
        "code": "undefined",
        "isNewPasswordGenerate": True,
        "oPI_ShdTelephonic": True,
        "oPI_OndemandTelephonic": True,
        "setPassword": False,
        "accessBilling": False,
        "recieveAllEmails": False,
        "recieveUserEmails": False,
        "vRI_ShdVideoInteroreting": False,
        "vRI_OndemandVideoInteroreting": False,
        "oSI_OnsiteConsecutive": False,
        "oSI_OnsiteSimultaneous": False,
        "oSI_OnsiteWhisper": False,
        "oSI_Onsite": False,
        "other_3rdPartyPlatform": False,
        "linguistType": 0,
        "payableType": 0,
        "password": "",
        "phoneNumber": "",
    }


def build_deactivate_payload(existing_user: dict) -> dict:
    return {
        "code": existing_user["connect_guid"],
        "accountStatus": "Inactive",
        "isActive": False,
    }
