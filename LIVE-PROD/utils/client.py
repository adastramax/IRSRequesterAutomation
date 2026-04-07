"""Live QA client for the IRS PIN Connect flow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from qa_irs_pin.config import (
    CONNECT_API_BASE,
    CONNECT_AUTH_BASE,
    CONNECT_EMAIL,
    CONNECT_PASSWORD,
    CONNECT_SEARCH_BASE,
    REQUEST_TIMEOUT_SECONDS,
)
from utils.helpers import coerce_form_value, extract_teid_from_pin, normalize_teid, normalize_text


class ConnectAPIError(RuntimeError):
    """Raised when a QA Connect call fails."""

    def __init__(self, message: str, *, status_code: int | None = None, response_text: str | None = None):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


@dataclass
class ConnectMutationResult:
    success: bool
    guid: str | None
    message: str
    raw_response: dict[str, Any]


class ConnectQAClient:
    """Small session-based wrapper around the live QA APIs."""

    def __init__(
        self,
        *,
        auth_base: str = CONNECT_AUTH_BASE,
        api_base: str = CONNECT_API_BASE,
        search_base: str = CONNECT_SEARCH_BASE,
        email: str = CONNECT_EMAIL,
        password: str = CONNECT_PASSWORD,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.auth_base = auth_base.rstrip("/")
        self.api_base = api_base.rstrip("/")
        self.search_base = search_base.rstrip("/")
        self.email = email
        self.password = password
        self.timeout = timeout
        self._token: str | None = None
        self.session = requests.Session()

    def authenticate(self) -> str:
        response = self.session.post(
            f"{self.auth_base}/api/accounts/token",
            json={
                "email": self.email,
                "password": self.password,
                "rememberMe": True,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ConnectAPIError(
                "Authentication failed.",
                status_code=response.status_code,
                response_text=response.text,
            )

        payload = response.json()
        token = normalize_text(payload.get("token"))
        if not token:
            raise ConnectAPIError("Authentication response did not include a token.")

        self._token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def _request(
        self,
        method: str,
        url: str,
        *,
        retry_on_401: bool = True,
        retry_on_5xx: bool = True,
        **kwargs: Any,
    ) -> requests.Response:
        if self._token is None:
            self.authenticate()

        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if response.status_code == 401 and retry_on_401:
            self.authenticate()
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code >= 500 and retry_on_5xx:
            time.sleep(1)
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)

        if response.status_code >= 400:
            raise ConnectAPIError(
                f"{method.upper()} {url} failed.",
                status_code=response.status_code,
                response_text=response.text,
            )
        return response

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self._request(method, url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectAPIError(
                f"{method.upper()} {url} returned non-JSON content.",
                status_code=response.status_code,
                response_text=response.text,
            ) from exc

    @staticmethod
    def _unwrap_data(payload: dict[str, Any]) -> Any:
        return payload.get("data", payload)

    @staticmethod
    def _serialize_export_row(row: dict[str, Any]) -> dict[str, Any]:
        pin_code = normalize_text(row.get("pinCodeString") or row.get("pinCode"))
        return {
            "seid": normalize_text(row.get("firstName")),
            "last_name": normalize_text(row.get("lastName")),
            "email": normalize_text(row.get("email")),
            "pin_code": pin_code,
            "teid": extract_teid_from_pin(pin_code),
            "connect_guid": normalize_text(row.get("code")),
            "account_status": normalize_text(row.get("accountStatus") or row.get("status")),
            "fk_customer": row.get("fK_Customer"),
            "fk_location": row.get("fK_Location"),
            "raw": row,
        }

    @staticmethod
    def _serialize_member_row(row: dict[str, Any]) -> dict[str, Any]:
        pin_code = normalize_text(row.get("pinCodeString") or row.get("pinCode"))
        return {
            "seid": normalize_text(row.get("firstName")),
            "last_name": normalize_text(row.get("lastName")),
            "email": normalize_text(row.get("email")),
            "pin_code": pin_code,
            "teid": extract_teid_from_pin(pin_code),
            "connect_guid": normalize_text(row.get("code")),
            "account_status": normalize_text(row.get("accountStatus") or row.get("status")),
            "fk_customer": row.get("fK_Customer"),
            "fk_location": row.get("fK_Location"),
            "raw": row,
        }

    def _iterate_export_rows(
        self,
        *,
        customer_ids: list[int] | None = None,
        active_only: bool = False,
        items_per_page: int = 50,
    ) -> list[dict[str, Any]]:
        body = {
            "customers": customer_ids or [],
            "subAccounts": [],
            "status": ["ACTIVE"] if active_only else [],
            "roles": [],
            "joinDate": None,
            "loginDate": None,
        }
        page = 1
        rows: list[dict[str, Any]] = []

        while True:
            payload = self._request_json(
                "POST",
                f"{self.search_base}/api/accounts/exports/filter/CONSUMER/0/",
                params={"page": page, "items_per_page": items_per_page},
                json=body,
            )
            rows.extend(payload.get("data", []) or [])
            pagination = (payload.get("payload") or {}).get("pagination") or {}
            last_page = int(pagination.get("last_page") or 0)
            if page >= last_page or last_page == 0:
                break
            page += 1

        return rows

    def _search_members_by_seid(
        self,
        seid: str,
        *,
        customer_ids: list[int] | None = None,
        active_only: bool = False,
        items_per_page: int = 10,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "POST",
            f"{self.search_base}/api/accounts/members/filter/CONSUMER/0/",
            params={"page": 1, "items_per_page": items_per_page, "search": seid},
            json={},
        )
        rows = payload.get("data", []) or []
        matches: list[dict[str, Any]] = []
        target_seid = normalize_text(seid).lower()

        for row in rows:
            first_name = normalize_text(row.get("firstName")).lower()
            if first_name != target_seid:
                continue
            if customer_ids and row.get("fK_Customer") not in customer_ids:
                continue
            if active_only and normalize_text(row.get("accountStatus")).lower() != "active":
                continue
            matches.append(self._serialize_member_row(row))

        return matches

    def _enrich_member_matches(self, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched_matches: list[dict[str, Any]] = []
        for match in matches:
            guid = normalize_text(match.get("connect_guid"))
            if not guid:
                enriched_matches.append(match)
                continue

            try:
                detail = self.get_account_detail(guid)
            except ConnectAPIError:
                enriched_matches.append(match)
                continue

            pin_code = normalize_text(detail.get("pinCodeString") or detail.get("pinCode")) or match.get("pin_code", "")
            enriched_match = dict(match)
            enriched_match.update(
                {
                    "email": normalize_text(detail.get("email")) or match.get("email", ""),
                    "pin_code": pin_code,
                    "teid": extract_teid_from_pin(pin_code),
                    "account_status": normalize_text(detail.get("accountStatus")) or match.get("account_status", ""),
                    "fk_customer": detail.get("fK_Customer") or detail.get("customerId") or match.get("fk_customer"),
                    "fk_location": detail.get("fK_Location") or match.get("fk_location"),
                    "raw": detail,
                }
            )
            enriched_matches.append(enriched_match)

        return enriched_matches

    def get_sites_for_customer(self, customer_name: str) -> list[str]:
        payload = self._request_json(
            "GET",
            f"{self.api_base}/api/accounts/addresses/customer/{customer_name}",
        )
        data = self._unwrap_data(payload) or {}
        addresses = data.get("addresses", [])
        return [normalize_text(address) for address in addresses if normalize_text(address)]

    def resolve_teid(self, customer_name: str, site_name: str) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            f"{self.api_base}/api/accounts/pin/max-teid/customer/{customer_name}",
            params={"siteName": site_name},
        )
        return dict(self._unwrap_data(payload) or {})

    def get_pin_context(self, customer_name: str, teid: str) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            f"{self.api_base}/api/accounts/pin/customer-teid/{customer_name}/{normalize_teid(teid)}",
        )
        return dict(self._unwrap_data(payload) or {})

    def search_user_by_seid(
        self,
        seid: str,
        *,
        customer_ids: list[int] | None = None,
        active_only: bool = False,
        items_per_page: int = 50,
        allow_export_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        try:
            member_matches = self._search_members_by_seid(
                seid,
                customer_ids=customer_ids,
                active_only=active_only,
            )
            if member_matches:
                return self._enrich_member_matches(member_matches)
        except ConnectAPIError:
            pass

        if not allow_export_fallback:
            return []

        matches: list[dict[str, Any]] = []
        target_seid = normalize_text(seid).lower()
        email_prefix = f"{target_seid}."

        for row in self._iterate_export_rows(
            customer_ids=customer_ids,
            active_only=active_only,
            items_per_page=items_per_page,
        ):
            first_name = normalize_text(row.get("firstName")).lower()
            email = normalize_text(row.get("email")).lower()
            if first_name != target_seid and not email.startswith(email_prefix):
                continue
            matches.append(self._serialize_export_row(row))

        return matches

    def get_export_requester_by_guid(
        self,
        guid: str,
        *,
        customer_ids: list[int] | None = None,
        active_only: bool = False,
        items_per_page: int = 50,
    ) -> dict[str, Any] | None:
        target_guid = normalize_text(guid)
        if not target_guid:
            return None

        for row in self._iterate_export_rows(
            customer_ids=customer_ids,
            active_only=active_only,
            items_per_page=items_per_page,
        ):
            if normalize_text(row.get("code")) == target_guid:
                return self._serialize_export_row(row)
        return None

    def get_account_detail(self, guid: str) -> dict[str, Any]:
        payload = self._request_json("GET", f"{self.api_base}/api/accounts/GetAccountDetailByID/{guid}")
        return dict(self._unwrap_data(payload) or {})

    def check_pin_available(self, pin: str) -> bool:
        payload = self._request_json("GET", f"{self.api_base}/api/accounts/check-pin-availablity/{pin}")
        return payload.get("data") is False

    def check_user_email(self, user_type: str, email: str) -> dict[str, Any]:
        return self._request_json("GET", f"{self.api_base}/api/accounts/checkUserEmail/{user_type}/{email}")

    def get_precall_policies(self, customer_id: int) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"{self.api_base}/api/precalls/ddlist/{customer_id}")
        return payload if isinstance(payload, list) else payload.get("data", [])

    def get_active_customer_service_types(self, customer_id: int) -> list[dict[str, Any]]:
        payload = self._request_json(
            "GET",
            f"{self.api_base}/api/master/data/SERVICE_TYPE/active-customer-servicetype-shortlist/{customer_id}",
        )
        return payload.get("data", [])

    def get_customer_locations(self, customer_id: int) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"{self.api_base}/api/customer/{customer_id}/location/getall-shortlist")
        return payload.get("data", [])

    def get_customer_subaccounts(self, customer_id: int) -> list[dict[str, Any]]:
        payload = self._request_json("GET", f"{self.api_base}/api/customer/{customer_id}/sub-accounts")
        return payload.get("data", [])

    def create_user(self, payload: dict[str, Any]) -> ConnectMutationResult:
        form_pairs: list[tuple[str, str]] = []
        for key, value in payload.items():
            if isinstance(value, list):
                for item in value:
                    form_pairs.append((key, coerce_form_value(item)))
                continue
            form_pairs.append((key, coerce_form_value(value)))

        response = self._request("POST", f"{self.api_base}/api/Accounts/Insert", data=form_pairs, retry_on_5xx=False)
        body = response.json()
        success = normalize_text(body.get("status")).upper() == "S"
        return ConnectMutationResult(
            success=success,
            guid=normalize_text(body.get("result")) or None,
            message=normalize_text(body.get("text")) or ("Successfully created" if success else "Create failed."),
            raw_response=body,
        )

    def deactivate_user(self, payload: dict[str, Any]) -> ConnectMutationResult:
        form_pairs: list[tuple[str, str]] = []
        for key, value in payload.items():
            if isinstance(value, list):
                for item in value:
                    form_pairs.append((key, coerce_form_value(item)))
                continue
            form_pairs.append((key, coerce_form_value(value)))

        body = self._request_json("POST", f"{self.api_base}/api/accounts/Update", data=form_pairs)
        success = normalize_text(body.get("status")).upper() == "S"
        return ConnectMutationResult(
            success=success,
            guid=normalize_text(body.get("result")) or normalize_text(payload.get("Code")) or None,
            message=normalize_text(body.get("text")) or ("Successfully deactivated" if success else "Deactivate failed."),
            raw_response=body,
        )
