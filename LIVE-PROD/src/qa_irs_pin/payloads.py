"""Connect payload builders aligned to the validated mock flow."""

from __future__ import annotations

import re

from .config import (
    CUSTOMER_CREATE_OVERRIDES,
    DEFAULT_NATIVE_LANGUAGE,
    DEFAULT_PRECALL_POLICY,
    DEFAULT_SERVICE_TYPE,
    DEFAULT_TIMEZONE,
    EMAIL_DOMAIN,
    PAYLOAD_DEFAULTS,
    SITE_PROFILE_OVERRIDES,
)


def sanitize_email_part(value: str) -> str:
    lowered = value.strip().lower().replace(" ", ".")
    collapsed = re.sub(r"[^a-z0-9.-]+", ".", lowered)
    collapsed = re.sub(r"\.+", ".", collapsed)
    return collapsed.strip(".")


def build_email(seid: str, first_name: str, last_name: str) -> str:
    name_part = sanitize_email_part(f"{first_name}{last_name}")
    local_part = ".".join(part for part in (sanitize_email_part(seid), name_part) if part)
    return f"{local_part}@{EMAIL_DOMAIN}"


def build_remapped_email(seid: str, first_name: str, last_name: str) -> str:
    local_part = ".".join(
        part
        for part in (
            sanitize_email_part(seid),
            sanitize_email_part(first_name),
            sanitize_email_part(last_name),
        )
        if part
    )
    return f"{local_part}@{EMAIL_DOMAIN}"


def build_modify_function_email(seid: str, first_name: str, last_name: str, *, suffix: int = 1) -> str:
    safe_last_name = sanitize_email_part(last_name)
    if int(suffix) <= 0:
        last_name_part = safe_last_name
    else:
        last_name_part = f"{safe_last_name}{int(suffix)}" if safe_last_name else ""

    local_part = ".".join(
        part
        for part in (
            sanitize_email_part(seid),
            sanitize_email_part(first_name),
            last_name_part,
        )
        if part
    )
    return f"{local_part}@{EMAIL_DOMAIN}"


def _build_profile_defaults(row, site_context: dict) -> dict:
    customer_name = str(site_context.get("accountName") or site_context.get("customerName") or "").strip()
    site_name = str(site_context.get("siteName") or row.site_name or "").strip()
    profile = dict(PAYLOAD_DEFAULTS)

    site_override = SITE_PROFILE_OVERRIDES.get((customer_name.lower(), site_name.lower()))
    if site_override is not None:
        profile.update(site_override)
    elif site_name:
        profile["address"] = site_name

    customer_override = CUSTOMER_CREATE_OVERRIDES.get(customer_name.lower(), {})
    return {
        "profile": profile,
        "default_native_language": customer_override.get("default_native_language", DEFAULT_NATIVE_LANGUAGE),
        "default_timezone": customer_override.get("default_timezone", DEFAULT_TIMEZONE),
        "default_location": customer_override.get("default_location"),
        "opi_scheduled": customer_override.get("opi_scheduled", True),
        "opi_ondemand": customer_override.get("opi_ondemand", True),
        "password": customer_override.get("password", ""),
        "set_password": customer_override.get("set_password", False),
        "precall_policy": customer_override.get("precall_policy", DEFAULT_PRECALL_POLICY),
        "service_type": customer_override.get("service_type", DEFAULT_SERVICE_TYPE),
        "service_types": customer_override.get("service_types", ["Community"]),
        "sub_customer_ids": customer_override.get("sub_customer_ids"),
    }


def build_create_payload(row, site_context: dict, pin_code: str, *, modify_email_suffix: int = 1) -> dict:
    defaults = _build_profile_defaults(row, site_context)
    profile = defaults["profile"]
    fk_customer = site_context["fK_Customer"]
    fk_location = site_context.get("fK_Location")
    if fk_location in (None, "", 0, "0"):
        fk_location = defaults["default_location"]
    service_type = defaults["service_type"]
    sub_customer_ids = defaults["sub_customer_ids"] or [fk_customer]
    if len(sub_customer_ids) == 1:
        sub_customer_ids = sub_customer_ids[0]
    full_name = " ".join(part for part in (row.first_name.strip(), row.last_name.strip()) if part)
    email = (
        build_modify_function_email(row.seid, row.first_name, row.last_name, suffix=modify_email_suffix)
        if getattr(row, "contact_status", "") == "Modify-Function Change"
        else build_remapped_email(row.seid, row.first_name, row.last_name)
    )

    return {
        "firstName": row.seid,
        "lastName": full_name,
        "phoneNumber": "",
        "email": email,
        "fK_Gender": "",
        "fK_Customer": fk_customer,
        "fK_Location": fk_location if fk_location is not None else "",
        "fK_ServiceType": service_type,
        "serviceTypes": defaults["service_types"][0],
        "fk_PreCallPolicy": defaults["precall_policy"],
        "fK_DefaultNativeLanguage": defaults["default_native_language"],
        "fK_DefaultTimeZone": defaults["default_timezone"],
        "role": "User",
        "accessBilling": False,
        "recieveAllEmails": False,
        "recieveUserEmails": False,
        "SubCustomerIds": sub_customer_ids,
        "city": profile["city"],
        "pinCode": int(pin_code),
        "pinCodeString": pin_code,
        "address": profile["address"],
        "street1": "",
        "street2": "",
        "state": profile["state"],
        "country": profile["country"],
        "postalCode": profile["postal_code"],
        "latitude": profile["latitude"],
        "longitude": profile["longitude"],
        "profileImageFile": "",
        "ProfileImage": "",
        "code": "undefined",
        "userType": "CONSUMER",
        "password": defaults["password"],
        "setPassword": defaults["set_password"],
        "isNewPasswordGenerate": True,
        "oPI_ShdTelephonic": defaults["opi_scheduled"],
        "oPI_OndemandTelephonic": defaults["opi_ondemand"],
        "vRI_ShdVideoInteroreting": False,
        "vRI_OndemandVideoInteroreting": False,
        "oSI_OnsiteConsecutive": False,
        "oSI_OnsiteSimultaneous": False,
        "oSI_OnsiteWhisper": False,
        "oSI_Onsite": False,
        "other_3rdPartyPlatform": False,
        "linguistType": 0,
        "payableType": 0,
    }


def build_deactivate_payload(requester_detail: dict) -> dict:
    service_types = requester_detail.get("serviceTypes") or []
    if service_types and isinstance(service_types[0], dict):
        service_types = [item.get("value") for item in service_types if item.get("value")]
    service_types = service_types or ([requester_detail.get("fK_ServiceType")] if requester_detail.get("fK_ServiceType") else [])
    sub_customer_ids = [
        item.get("code")
        for item in requester_detail.get("requesterSubcustomrs") or []
        if item.get("code") is not None
    ]
    if not sub_customer_ids and requester_detail.get("fK_Customer") is not None:
        sub_customer_ids = [requester_detail["fK_Customer"]]
    access_billing = any(
        (feature.get("feature") or {}).get("code") == "billing"
        for feature in requester_detail.get("userFeatures") or []
    )

    return {
        "Code": requester_detail.get("code"),
        "FirstName": requester_detail.get("firstName") or "",
        "LastName": requester_detail.get("lastName") or "",
        "Email": requester_detail.get("email") or "",
        "FK_Customer": requester_detail.get("fK_Customer") or requester_detail.get("customerId"),
        "FK_Location": requester_detail.get("fK_Location") or "",
        "AccountStatus": "Not Active",
        "PinCode": requester_detail.get("pinCode"),
        "PinCodeString": requester_detail.get("pinCodeString") or "",
        "Role": requester_detail.get("role") or "User",
        "PhoneNumber": requester_detail.get("phoneNumber") or "",
        "LockoutEnabled": True,
        "SetPassword": False,
        "Password": requester_detail.get("password") or "",
        "Street1": requester_detail.get("street1") or "",
        "Street2": requester_detail.get("street2") or "",
        "State": requester_detail.get("state") or PAYLOAD_DEFAULTS["state"],
        "City": requester_detail.get("city") or PAYLOAD_DEFAULTS["city"],
        "PostalCode": requester_detail.get("postalCode") or PAYLOAD_DEFAULTS["postal_code"],
        "Address": requester_detail.get("address") or PAYLOAD_DEFAULTS["address"],
        "AccessBilling": access_billing,
        "FK_Gender": requester_detail.get("fK_Gender") or "",
        "FK_ServiceType": requester_detail.get("fK_ServiceType") or DEFAULT_SERVICE_TYPE,
        "FK_DefaultNativeLanguage": requester_detail.get("fK_DefaultNativeLanguage") or DEFAULT_NATIVE_LANGUAGE,
        "FK_DefaultTimeZone": requester_detail.get("fK_DefaultTimeZone") or DEFAULT_TIMEZONE,
        "OPI_ShdTelephonic": bool(requester_detail.get("opI_ShdTelephonic")),
        "OPI_OndemandTelephonic": bool(requester_detail.get("opI_OndemandTelephonic")),
        "VRI_ShdVideoInteroreting": bool(requester_detail.get("vrI_ShdVideoInteroreting")),
        "VRI_OndemandVideoInteroreting": bool(requester_detail.get("vrI_OndemandVideoInteroreting")),
        "OSI_OnsiteConsecutive": bool(requester_detail.get("osI_OnsiteConsecutive")),
        "OSI_OnsiteSimultaneous": bool(requester_detail.get("osI_OnsiteSimultaneous")),
        "OSI_OnsiteWhisper": bool(requester_detail.get("osI_OnsiteWhisper")),
        "OSI_Onsite": bool(requester_detail.get("osI_Onsite")),
        "FK_PreCallPolicy": requester_detail.get("fK_PreCallPolicy") or DEFAULT_PRECALL_POLICY,
        "Other_3rdPartyPlatform": bool(requester_detail.get("other_3rdPartyPlatform")),
        "RecieveAllEmails": bool(requester_detail.get("recieveAllEmails")),
        "RecieveUserEmails": bool(requester_detail.get("recieveUserEmails")),
        "Latitude": requester_detail.get("latitude") or PAYLOAD_DEFAULTS["latitude"],
        "Longitude": requester_detail.get("longitude") or PAYLOAD_DEFAULTS["longitude"],
        "Country": requester_detail.get("country") or PAYLOAD_DEFAULTS["country"],
        "SubCustomerIds": sub_customer_ids,
        "ServiceTypes": service_types,
        "LinguistType": requester_detail.get("linguistType") or 0,
        "PayableType": requester_detail.get("payableType") or 0,
    }


def build_update_payload(
    requester_detail: dict,
    *,
    email_override: str | None = None,
    account_status_override: str | None = None,
) -> dict:
    service_types = requester_detail.get("serviceTypes") or []
    if service_types and isinstance(service_types[0], dict):
        service_types = [item.get("value") for item in service_types if item.get("value")]
    service_types = service_types or ([requester_detail.get("fK_ServiceType")] if requester_detail.get("fK_ServiceType") else [])
    sub_customer_ids = [
        item.get("code")
        for item in requester_detail.get("requesterSubcustomrs") or []
        if item.get("code") is not None
    ]
    if not sub_customer_ids and requester_detail.get("fK_Customer") is not None:
        sub_customer_ids = [requester_detail["fK_Customer"]]
    access_billing = any(
        (feature.get("feature") or {}).get("code") == "billing"
        for feature in requester_detail.get("userFeatures") or []
    )
    account_status = account_status_override or requester_detail.get("accountStatus") or "Active"

    return {
        "Code": requester_detail.get("code"),
        "FirstName": requester_detail.get("firstName") or "",
        "LastName": requester_detail.get("lastName") or "",
        "Email": email_override if email_override is not None else (requester_detail.get("email") or ""),
        "FK_Customer": requester_detail.get("fK_Customer") or requester_detail.get("customerId"),
        "FK_Location": requester_detail.get("fK_Location") or "",
        "AccountStatus": account_status,
        "PinCode": requester_detail.get("pinCode"),
        "PinCodeString": requester_detail.get("pinCodeString") or "",
        "Role": requester_detail.get("role") or "User",
        "PhoneNumber": requester_detail.get("phoneNumber") or "",
        "LockoutEnabled": bool(requester_detail.get("lockoutEnabled")),
        "SetPassword": False,
        "Password": requester_detail.get("password") or "",
        "Street1": requester_detail.get("street1") or "",
        "Street2": requester_detail.get("street2") or "",
        "State": requester_detail.get("state") or PAYLOAD_DEFAULTS["state"],
        "City": requester_detail.get("city") or PAYLOAD_DEFAULTS["city"],
        "PostalCode": requester_detail.get("postalCode") or PAYLOAD_DEFAULTS["postal_code"],
        "Address": requester_detail.get("address") or PAYLOAD_DEFAULTS["address"],
        "AccessBilling": access_billing,
        "FK_Gender": requester_detail.get("fK_Gender") or "",
        "FK_ServiceType": requester_detail.get("fK_ServiceType") or DEFAULT_SERVICE_TYPE,
        "FK_DefaultNativeLanguage": requester_detail.get("fK_DefaultNativeLanguage") or DEFAULT_NATIVE_LANGUAGE,
        "FK_DefaultTimeZone": requester_detail.get("fK_DefaultTimeZone") or DEFAULT_TIMEZONE,
        "OPI_ShdTelephonic": bool(requester_detail.get("opI_ShdTelephonic")),
        "OPI_OndemandTelephonic": bool(requester_detail.get("opI_OndemandTelephonic")),
        "VRI_ShdVideoInteroreting": bool(requester_detail.get("vrI_ShdVideoInteroreting")),
        "VRI_OndemandVideoInteroreting": bool(requester_detail.get("vrI_OndemandVideoInteroreting")),
        "OSI_OnsiteConsecutive": bool(requester_detail.get("osI_OnsiteConsecutive")),
        "OSI_OnsiteSimultaneous": bool(requester_detail.get("osI_OnsiteSimultaneous")),
        "OSI_OnsiteWhisper": bool(requester_detail.get("osI_OnsiteWhisper")),
        "OSI_Onsite": bool(requester_detail.get("osI_Onsite")),
        "FK_PreCallPolicy": requester_detail.get("fK_PreCallPolicy") or DEFAULT_PRECALL_POLICY,
        "Other_3rdPartyPlatform": bool(requester_detail.get("other_3rdPartyPlatform")),
        "RecieveAllEmails": bool(requester_detail.get("recieveAllEmails")),
        "RecieveUserEmails": bool(requester_detail.get("recieveUserEmails")),
        "Latitude": requester_detail.get("latitude") or PAYLOAD_DEFAULTS["latitude"],
        "Longitude": requester_detail.get("longitude") or PAYLOAD_DEFAULTS["longitude"],
        "Country": requester_detail.get("country") or PAYLOAD_DEFAULTS["country"],
        "SubCustomerIds": sub_customer_ids,
        "ServiceTypes": service_types,
        "LinguistType": requester_detail.get("linguistType") or 0,
        "PayableType": requester_detail.get("payableType") or 0,
    }
