"""Local SQLite registry for QA processing runs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import AUDIT_RETENTION_DAYS, DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stg_irs_pin_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seid TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    bod TEXT,
    customer_name TEXT,
    site_id TEXT,
    site_name TEXT,
    pin_9digit TEXT,
    connect_guid TEXT,
    status TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_dt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_dt TEXT
);

CREATE TABLE IF NOT EXISTS batch_audit (
    batch_id TEXT PRIMARY KEY,
    source_name TEXT,
    created_by TEXT NOT NULL,
    total_rows INTEGER NOT NULL,
    summary_json TEXT NOT NULL,
    output_path TEXT,
    created_dt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        purge_old_audit_data(connection)
        connection.commit()
    return db_path


def purge_old_audit_data(
    connection: sqlite3.Connection,
    *,
    retention_days: int = AUDIT_RETENTION_DAYS,
) -> None:
    if retention_days <= 0:
        return

    batch_rows = connection.execute(
        """
        SELECT batch_id
        FROM batch_audit
        WHERE created_dt < datetime('now', ?)
        """,
        (f"-{retention_days} days",),
    ).fetchall()
    batch_ids = [str(row["batch_id"]) for row in batch_rows if row["batch_id"]]
    if not batch_ids:
        return

    placeholders = ",".join("?" for _ in batch_ids)
    connection.execute(
        f"DELETE FROM stg_irs_pin_registry WHERE batch_id IN ({placeholders})",
        batch_ids,
    )
    connection.execute(
        f"DELETE FROM batch_audit WHERE batch_id IN ({placeholders})",
        batch_ids,
    )


def write_pin_registry(
    connection: sqlite3.Connection,
    *,
    seid: str,
    first_name: str,
    last_name: str,
    bod: str,
    customer_name: str,
    site_id: str,
    site_name: str,
    pin_9digit: str | None,
    connect_guid: str | None,
    status: str,
    batch_id: str,
    created_by: str,
) -> None:
    connection.execute(
        """
        INSERT INTO stg_irs_pin_registry (
            seid, first_name, last_name, bod, customer_name, site_id, site_name,
            pin_9digit, connect_guid, status, batch_id, created_by, updated_dt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            seid,
            first_name,
            last_name,
            bod,
            customer_name,
            site_id,
            site_name,
            pin_9digit,
            connect_guid,
            status,
            batch_id,
            created_by,
        ),
    )
    connection.commit()


def write_batch_audit(
    connection: sqlite3.Connection,
    *,
    batch_id: str,
    source_name: str,
    created_by: str,
    total_rows: int,
    summary: dict[str, int],
    output_path: str | None,
) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO batch_audit (
            batch_id, source_name, created_by, total_rows, summary_json, output_path
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            source_name,
            created_by,
            total_rows,
            json.dumps(summary),
            output_path,
        ),
    )
    connection.commit()
