"""CLI entry point for the QA IRS PIN workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from qa_irs_pin import registry
from qa_irs_pin.config import DB_PATH
from qa_irs_pin.processor import process_input_file
from utils.client import ConnectQAClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QA IRS PIN tool runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Initialize the local QA registry database.")

    process_parser = subparsers.add_parser("process", help="Process an input CSV/XLSX file against QA.")
    process_parser.add_argument("--input", required=True, help="Path to the input file.")
    process_parser.add_argument("--created-by", default="QA OPI Operator", help="Operator name to store in the registry.")

    sites_parser = subparsers.add_parser("sites", help="List the QA site strings for a customer.")
    sites_parser.add_argument("--customer", required=True, help="Customer name such as Markytech or a full IRS account name.")

    search_parser = subparsers.add_parser("search", help="Search QA Connect by SEID.")
    search_parser.add_argument("--seid", required=True, help="SEID to search in QA.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        print(f"Initialized QA registry at {registry.initialize_database(DB_PATH)}")
        return

    client = ConnectQAClient()

    if args.command == "process":
        result = process_input_file(args.input, client=client, created_by=args.created_by)
        print(json.dumps(result.to_dict(), indent=2))
        return

    if args.command == "sites":
        print(json.dumps(client.get_sites_for_customer(args.customer), indent=2))
        return

    if args.command == "search":
        print(json.dumps(client.search_user_by_seid(args.seid), indent=2))
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
