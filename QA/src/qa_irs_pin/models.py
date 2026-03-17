"""Typed data models for the QA workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ParsedRow:
    row_number: int
    bod: str
    customer_name: str
    last_name: str
    first_name: str
    seid: str
    site_id: str
    site_name: str
    manual_site_name: str
    user_pin: str
    contact_status: str
    validation_status: str
    notes: list[str] = field(default_factory=list)
    error_fields: list[str] = field(default_factory=list)
    duplicate_in_batch: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RowProcessingOutcome:
    row_number: int
    bod: str
    customer_name: str | None
    seid: str
    action: str
    input_site_name: str
    matched_site_name: str | None
    resolved_site_id: str | None
    generated_pin: str | None
    status: str
    notes: list[str] = field(default_factory=list)
    payload: dict[str, Any] | None = None
    connect_guid: str | None = None
    response: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    manual_selection: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessingRunResult:
    batch_id: str
    payloads: list[dict[str, Any]]
    row_results: list[RowProcessingOutcome]
    logs: list[dict[str, Any]]
    summary: dict[str, int]
    output_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "payloads": self.payloads,
            "row_results": [row.to_dict() for row in self.row_results],
            "logs": list(self.logs),
            "summary": dict(self.summary),
            "output_path": self.output_path,
        }
