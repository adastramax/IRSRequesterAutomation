"""CLI entry point for the mock IRS PIN project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mock_irs_pin import database
from mock_irs_pin.config import DB_PATH
from mock_irs_pin.processor import process_input_file
from mock_irs_pin.services import MockInternalAPI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mock IRS PIN tool runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create the SQLite mock database from CSV seed files.")

    sites_parser = subparsers.add_parser("sites", help="Return the mock API 3 response for a BOD.")
    sites_parser.add_argument("--bod", required=True, help="BOD code such as TAS or CI")

    process_parser = subparsers.add_parser(
        "process", help="Process an input CSV and emit Connect-ready JSON payloads."
    )
    process_parser.add_argument("--input", required=True, help="Path to the CSV input file")
    process_parser.add_argument(
        "--created-by",
        default="Mock OPI Operator",
        help="Operator name written into the mock registry",
    )
    process_parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Recreate the SQLite database from seed files before processing.",
    )

    return parser


def command_init_db() -> None:
    db_path = database.initialize_database(DB_PATH)
    print(f"Initialized mock database at {db_path}")


def command_sites(bod: str) -> None:
    if not DB_PATH.exists():
        database.initialize_database(DB_PATH)
    with database.get_connection(DB_PATH) as connection:
        api = MockInternalAPI(connection)
        customer = api.get_customer_by_bod(bod)
        if customer is None:
            print(json.dumps({"data": {"addresses": [], "totalCount": 0}, "payload": None}, indent=2))
            return
        addresses = api.get_sites_for_customer(customer["customer_name"])
    print(json.dumps({"data": {"addresses": addresses, "totalCount": len(addresses)}, "payload": None}, indent=2))


def command_process(input_path: str, created_by: str, reset_db: bool) -> None:
    if reset_db or not DB_PATH.exists():
        database.initialize_database(DB_PATH)
    output_path = process_input_file(input_path, created_by=created_by, db_path=DB_PATH)
    print(f"Wrote payload-only JSON to {output_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        command_init_db()
        return
    if args.command == "sites":
        command_sites(args.bod)
        return
    if args.command == "process":
        command_process(args.input, args.created_by, args.reset_db)
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
