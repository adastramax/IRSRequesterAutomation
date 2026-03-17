# Mock IRS PIN Tool Summary

## Purpose

This mock project is a local validation layer for the IRS PIN Management Tool. It exists to prove the business logic before wiring the app to the real QA or production Connect APIs.

The mock covers:

- parsing CSV/XLSX input
- manual row entry
- BOD to customer name lookup
- API 3 style site-string retrieval
- token-based fuzzy site matching
- API 2 style TEID resolution
- API 1 style max PIN lookup
- deterministic PIN generation using `MAX(pin) + 1`
- Connect-ready payload generation
- local registry writes
- a Streamlit UI for preview, processing, payload inspection, and developer diagnostics

## Reference inputs used

The mock SQLite database is seeded from real IRS-related source files in:

`E:\ad-astra\031 IRS PIN Generator\Imp Data Regarding Customers and Requesters`

Files used:

- `Customers_List.csv`
- `Requesters_List.csv`
- `QA_Requesters_List.csv`
- `Requesters_List_all_IRS_Users_pins.csv`
- `IRS_All_Sites_Reference.xlsx`
- `IRS_report_monthly_2026-03-01.xlsx`
- `requesters_with_company_details_TEID.xlsx`

What each contributes:

- `IRS_All_Sites_Reference.xlsx`: canonical customer/BOD mapping, TEIDs, site names, max pin, next pin
- `Requesters_List_all_IRS_Users_pins.csv`: production-shaped requester inventory and active/inactive state
- `requesters_with_company_details_TEID.xlsx`: TEID/site enrichment for requester records
- `IRS_report_monthly_2026-03-01.xlsx`: additional site strings for API 3 style lookup coverage
- `Customers_List.csv`: raw customer/account source table
- `Requesters_List.csv` and `QA_Requesters_List.csv`: smaller raw source snapshots preserved in SQLite

## Current architecture

Main files:

- [config.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/config.py)
- [database.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/database.py)
- [parser.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/parser.py)
- [matching.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/matching.py)
- [services.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/services.py)
- [payloads.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/payloads.py)
- [processor.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/processor.py)
- [streamlit_app.py](/E:/ad-astra/031 IRS PIN Generator/mock/streamlit_app.py)
- [run_mock.py](/E:/ad-astra/031 IRS PIN Generator/mock/run_mock.py)

High-level flow:

1. Input rows are parsed and validated.
2. BOD resolves to `customer_name`.
3. Site strings for that customer are loaded from the local DB.
4. Input site name is fuzzy matched to the API 3 style site string.
5. If `Site ID` is blank, TEID is resolved or assigned from the local DB.
6. The max PIN for the TEID is read from the local DB.
7. The next PIN is generated deterministically.
8. The Connect payload is built.
9. The requestor and registry tables are updated locally.

## SQLite schema

Raw imported tables:

- `raw_customers_list`
- `raw_requesters_list`
- `raw_qa_requesters`
- `raw_requesters_all_irs`
- `raw_requesters_teid`

Mock operational tables:

- `bod_lookup`
- `site_catalog`
- `site_reference`
- `requestor_reference`
- `stg_irs_pin_registry`
- `stg_irs_teid_registry`

Key meanings:

- `bod_lookup`: BOD code -> customer name -> `fk_customer`
- `site_catalog`: API 3 style site string list for a customer
- `site_reference`: TEID + site + max pin + next pin + `fk_customer` + mocked/confirmed `fk_location`
- `requestor_reference`: production-shaped requester inventory used for SEID search and existing-user checks

## Streamlit UI behavior

The Streamlit app supports:

- upload CSV/XLSX/XLS
- manual row entry
- preview before processing
- process filtering for `Both`, `Add only`, `Deactivate only`
- row-by-row output table
- payload dropdown showing the exact object that would be posted to Connect
- developer diagnostics via the `For Developer` sidebar button

Important UI meanings:

- `Warning`: valid row, but requires automatic resolution, usually blank `Site ID`
- `Already Exists`: the SEID was found in the mock DB for the same resolved TEID, so no insert payload is generated
- `Skipped`: later duplicate of the same SEID in the same batch

## What is exact vs mocked

Exact or near-exact:

- BOD mapping from the reference workbook
- TEID and site name relationships from the reference workbook
- large requester population from the real IRS requester CSV
- deterministic next PIN behavior
- payload field names and main payload structure from PRD v7

Still mocked:

- most `fK_Location` values
- all actual HTTP calls to Connect
- auth token flow
- real multipart submission
- real deactivation/update payload validation against the live endpoint

`fK_Location` note:

The provided source files do not contain a real numeric per-TEID `fK_Location` field. The mock uses real confirmed values where available and deterministic placeholder values elsewhere.

## How to run

CLI:

```powershell
python .\mock\run_mock.py init-db
python .\mock\run_mock.py sites --bod TAS
python .\mock\run_mock.py process --input .\mock\data\input\requesters_batch.csv --reset-db
```

Streamlit:

```powershell
streamlit run .\mock\streamlit_app.py
```

## What another LLM needs to know

If another LLM will upgrade this mock into QA or production code, it should treat:

- [prd/IRS_PIN_Tool_PRD_v7.docx](/E:/ad-astra/031 IRS PIN Generator/prd/IRS_PIN_Tool_PRD_v7.docx)
- [prd/IRS_PIN_Tool_Master_V7.md](/E:/ad-astra/031 IRS PIN Generator/prd/IRS_PIN_Tool_Master_V7.md)
- [database.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/database.py)
- [processor.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/processor.py)
- [payloads.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/payloads.py)
- [streamlit_app.py](/E:/ad-astra/031 IRS PIN Generator/mock/streamlit_app.py)

as the minimum starting set.

It should preserve the processor flow and replace the local service/database lookups with real API clients in layers, not by rewriting the whole app from scratch.

