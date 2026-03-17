"""Service layer that mimics the v7 backend APIs using SQLite data."""

from __future__ import annotations

import sqlite3

from . import database


class MockInternalAPI:
    """API-like facade around the local SQLite store."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get_customer_by_bod(self, bod: str) -> dict | None:
        return database.get_customer_by_bod(self.connection, bod)

    def get_sites_for_customer(self, customer_name: str) -> list[str]:
        return database.get_site_strings(self.connection, customer_name)

    def resolve_teid(self, customer_name: str, site_name: str) -> dict:
        return database.resolve_teid(self.connection, customer_name, site_name)

    def create_site_for_customer(self, customer_name: str, site_name: str) -> dict:
        return database.create_site_for_customer(self.connection, customer_name, site_name)

    def ensure_direct_teid_placeholder(
        self, *, customer_name: str, bod_code: str, teid: str, site_name: str
    ) -> dict:
        return database.ensure_direct_teid_placeholder(
            self.connection,
            customer_name=customer_name,
            bod_code=bod_code,
            teid=teid,
            site_name=site_name,
        )

    def get_site_by_teid(self, customer_name: str, teid: str) -> dict | None:
        return database.get_site_by_teid(self.connection, customer_name, teid)

    def get_pin_context(self, customer_name: str, teid: str) -> dict:
        return database.get_pin_context(self.connection, customer_name, teid)

    def search_user_by_seid(
        self, *, customer_name: str, seid: str, active_only: bool = True
    ) -> list[dict]:
        return database.search_requestors_by_seid(
            self.connection,
            customer_name=customer_name,
            seid=seid,
            active_only=active_only,
        )
