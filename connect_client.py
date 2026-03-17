"""
IRS PIN Connect Client — Standalone
All auth, retry, session logic self-contained.
QA credentials pre-loaded for development/testing.
"""

import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Base URLs ─────────────────────────────────────────────────────────────────
AUTH_BASE    = "https://appbe.ad-astrainc.com"           # auth + user search
CONNECT_BASE = "https://connectapiqas.ad-astrainc.com"   # pin check + insert

# ── QA Credentials (override via .env in prod) ────────────────────────────────
DEFAULT_EMAIL    = os.getenv("CONNECT_EMAIL",    "almaskhan@ad-astrainc.com")
DEFAULT_PASSWORD = os.getenv("CONNECT_PASSWORD", "Welcome123!")


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class PinCreationResult:
    success: bool
    pin: Optional[str] = None
    guid: Optional[str] = None
    error_message: Optional[str] = None


# ── Custom exception ──────────────────────────────────────────────────────────
class ConnectAPIError(Exception):
    def __init__(self, message: str, status_code: int = None, body: str = None):
        self.message = message
        self.status_code = status_code
        self.body = body
        super().__init__(str(self))

    def __str__(self):
        s = self.message
        if self.status_code:
            s += f" [HTTP {self.status_code}]"
        if self.body:
            s += f" :: {self.body[:300]}"
        return s


# ── Main client ───────────────────────────────────────────────────────────────
class IRSConnectClient:
    """
    Standalone client for IRS PIN operations against Ad Astra Connect.

    Usage:
        client = IRSConnectClient()   # uses QA creds by default
        client.login()
        available = client.check_pin_available("548512345")
    """

    def __init__(
        self,
        email: str = DEFAULT_EMAIL,
        password: str = DEFAULT_PASSWORD,
        timeout: int = 30,
    ):
        self.email = email
        self.password = password
        self.timeout = timeout
        self._token: Optional[str] = None
        self._session = requests.Session()

    # ── Auth ──────────────────────────────────────────────────────────────────
    def login(self) -> None:
        """Authenticate and store bearer token."""
        url = f"{AUTH_BASE}/api/accounts/token"
        payload = {"email": self.email, "password": self.password, "rememberMe": True}
        logger.info(f"Authenticating as {self.email}")

        resp = self._session.post(url, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise ConnectAPIError("Login failed", resp.status_code, resp.text)

        token = resp.json().get("token")
        if not token:
            raise ConnectAPIError("Login response missing token", body=resp.text)

        self._token = token
        self._session.headers.update({"Authorization": f"Bearer {self._token}"})
        logger.info("Authentication successful")

    # ── Internal request with auto-retry + 401 refresh ───────────────────────
    def _request(self, method: str, url: str, **kwargs) -> dict:
        """Make HTTP request. Auto re-authenticates on 401. Retries once on 5xx."""
        for attempt in range(2):
            resp = self._session.request(method, url, timeout=self.timeout, **kwargs)

            if resp.status_code == 401 and attempt == 0:
                logger.warning("401 received — re-authenticating")
                self.login()
                continue

            if resp.status_code >= 500 and attempt == 0:
                logger.warning(f"5xx received ({resp.status_code}) — retrying once")
                time.sleep(1)
                continue

            if resp.status_code >= 400:
                raise ConnectAPIError(f"{method} {url}", resp.status_code, resp.text)

            try:
                return resp.json()
            except Exception:
                raise ConnectAPIError("Non-JSON response", resp.status_code, resp.text[:300])

        raise ConnectAPIError(f"{method} {url} failed after retries")

    # ── 1. Search user by SEID ────────────────────────────────────────────────
    def search_user_by_seid(self, seid: str) -> list[dict]:
        """
        Paginate filter endpoint, return records where firstName == seid.
        Uses AUTH_BASE (appbe), not CONNECT_BASE.
        """
        body = {
            "customers": [], "subAccounts": [], "status": [],
            "roles": [], "joinDate": None, "loginDate": None
        }
        matches = []
        page = 1

        while True:
            url = f"{AUTH_BASE}/api/accounts/exports/filter/CONSUMER/0/?page={page}&items_per_page=50"
            resp = self._request("POST", url, json=body)
            users = resp.get("data", [])

            for user in users:
                if str(user.get("firstName", "")).lower() == seid.lower():
                    matches.append(user)

            last_page = resp.get("payload", {}).get("pagination", {}).get("last_page", 1)
            if page >= last_page:
                break
            page += 1

        logger.info(f"SEID '{seid}': {len(matches)} match(es) in {page} page(s)")
        return matches

    # ── 2. Check PIN availability ─────────────────────────────────────────────
    def check_pin_available(self, pin: str) -> bool:
        """
        GET check-pin-availablity/{pin}  <- typo in URL is intentional, must match exactly
        Returns True if PIN is FREE (response data == false).
        """
        url = f"{CONNECT_BASE}/api/accounts/check-pin-availablity/{pin}"
        resp = self._request("GET", url)
        is_taken = resp.get("data", True)
        available = not is_taken
        logger.debug(f"PIN {pin} available: {available}")
        return available

    # ── 3. Confirm PIN server-side ────────────────────────────────────────────
    def confirm_pin(self) -> str:
        """
        GET /api/accounts/pincode — registers PIN server-side after availability check.
        Must be called BEFORE insert. Returns confirmed PIN string.
        """
        url = f"{CONNECT_BASE}/api/accounts/pincode"
        resp = self._request("GET", url)
        confirmed = str(resp.get("data", "")).strip()
        if not confirmed:
            raise ConnectAPIError("confirm_pin: empty data in response", body=str(resp))
        logger.info(f"PIN confirmed server-side: {confirmed}")
        return confirmed

    # ── 4. Insert new user ────────────────────────────────────────────────────
    def insert_user(self, payload: dict) -> PinCreationResult:
        """
        POST /api/Accounts/Insert as multipart/form-data.
        Returns PinCreationResult.
        Note: must NOT set Content-Type header — requests sets multipart boundary automatically.
        """
        url = f"{CONNECT_BASE}/api/Accounts/Insert"
        headers = {"Authorization": f"Bearer {self._token}"}

        for attempt in range(2):
            resp = requests.post(url, data=payload, headers=headers, timeout=self.timeout)

            if resp.status_code == 401 and attempt == 0:
                logger.warning("insert_user 401 — re-authenticating")
                self.login()
                headers["Authorization"] = f"Bearer {self._token}"
                continue
            break

        try:
            body = resp.json()
        except Exception:
            return PinCreationResult(success=False, error_message=f"Non-JSON: {resp.text[:300]}")

        if body.get("status") == "S":
            guid = str(body.get("result", ""))
            logger.info(f"insert_user SUCCESS — GUID: {guid}")
            return PinCreationResult(success=True, guid=guid)

        msg = body.get("text", str(body))
        logger.error(f"insert_user FAILED: {msg}")
        return PinCreationResult(success=False, error_message=msg)

    # ── 5. Deactivate user ────────────────────────────────────────────────────
    def deactivate_user(self, guid: str) -> tuple[bool, str]:
        """
        POST /api/accounts/Update with code=guid.
        Returns (success, message).
        """
        url = f"{CONNECT_BASE}/api/accounts/Update"
        resp = self._request("POST", url, json={"code": guid, "isActive": False})

        if resp.get("status") == "S":
            logger.info(f"deactivate_user SUCCESS — GUID: {guid}")
            return True, resp.get("text", "Successfully deactivated")

        msg = resp.get("text", str(resp))
        logger.error(f"deactivate_user FAILED: {msg}")
        return False, msg


# ── Smoke test — run this first before writing anything else ──────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    client = IRSConnectClient()  # QA creds loaded above

    print("\n── Step 1: Login ──────────────────────────────")
    client.login()
    print("✓ Auth OK")

    print("\n── Step 2: Check PIN availability ────────────")
    test_pin = f"5485{random.randint(10000, 99999)}"
    available = client.check_pin_available(test_pin)
    print(f"✓ PIN {test_pin} available: {available}")

    print("\n── Step 3: Confirm PIN server-side ───────────")
    try:
        confirmed = client.confirm_pin()
        print(f"✓ Confirmed PIN: {confirmed}")
    except ConnectAPIError as e:
        print(f"⚠ confirm_pin response (note raw): {e}")

    print("\n── Step 4: Search SEID 'Z-1234' ──────────────")
    results = client.search_user_by_seid("Z-1234")
    print(f"✓ Matches: {len(results)}")
    if results:
        u = results[0]
        print(f"  firstName={u.get('firstName')} PIN={u.get('pinCodeString')}")

    print("\n── All smoke tests complete ✓ ─────────────────\n")