# Mock IRS PIN Project

This folder is a self-contained mock implementation of the IRS PIN workflow. It now follows the v7 PRD and seeds the local SQLite database from the real IRS reference files in `Imp Data Regarding Customers and Requesters`.

- BOD -> customerName lookup from the v7 mapping
- API 3 style site-string lookup
- fuzzy matching from IRS input site names to API 3 site strings
- API 2 style TEID resolution for blank Site ID rows
- API 1 style max PIN lookup and deterministic `MAX(pin) + 1`
- payload-only JSON output for what would be posted to Connect

The mock uses `pandas`/`openpyxl` for the workbook and CSV inputs.

## Layout

- `data/input/requesters_batch.csv`: sample upload file
- `data/mock_irs_pin.db`: SQLite database created from the seed CSVs
- `data/output/payloads_*.json`: payload-only batch outputs
- `src/mock_irs_pin/`: parser, database, service, payload, and processor modules
- `run_mock.py`: CLI entry point
- `streamlit_app.py`: local Streamlit UI for upload/manual entry and payload review
- `MOCK_Project_Summary.md`: detailed summary of what this mock does and how it is structured
- `MASTER_PROMPT_QA_PROD.md`: handoff prompt for another LLM to evolve this mock into QA or production code

## Commands

Initialize the local database:

```powershell
python .\mock\run_mock.py init-db
```

Return the mock API 3 response for a BOD:

```powershell
python .\mock\run_mock.py sites --bod TAS
```

Process the sample CSV and write only the Connect payload JSON:

```powershell
python .\mock\run_mock.py process --input .\mock\data\input\requesters_batch.csv
```

Reset the database to the original seed state before processing:

```powershell
python .\mock\run_mock.py process --input .\mock\data\input\requesters_batch.csv --reset-db
```

Run the Streamlit app:

```powershell
streamlit run .\mock\streamlit_app.py
```

## Mock behavior

- `IRS_All_Sites_Reference.xlsx` seeds the TEID/site/max-pin reference.
- `requesters_with_company_details_TEID.xlsx` seeds existing SEID/TEID/PIN records.
- `Requesters_List_all_IRS_Users_pins.csv` is used to enrich live-style status and requester IDs.
- `IRS_report_monthly_2026-03-01.xlsx` supplements API 3 site strings so the mock can cover "site string exists but TEID does not" scenarios.
- Blank `Site ID` rows use fuzzy matching first, then API 2 style TEID resolution.
- The output file contains only the payload objects that would be posted to Connect.

## Streamlit workflow

- Input mode 1: attach a CSV/XLSX/XLS file
- Input mode 2: enter rows manually
- Preview stage: shows the parsed rows before processing
- Process stage: runs the mock API 3 -> API 2 -> API 1 flow and builds Connect-ready payloads
- Output stage: shows row-by-row results and a payload dropdown so you can inspect the exact payload object
- Developer section: click `For Developer` in the sidebar to show internal stage logs and the structured run result

### UI terms

- `Warning`: the row is still processable, but one value must be resolved automatically, usually a blank `Site ID`
- `Operator`: the person or team member running the batch; stored in the mock registry as `CREATED_BY`
- `Already Exists`: the SEID already exists in the mock Connect data for the same resolved TEID, so no insert payload is created
- `Skipped`: later duplicate SEID inside the same uploaded batch

## SQLite database

`mock/data/mock_irs_pin.db` is a real SQLite database.

Raw source tables loaded from the reference directory:

- `raw_customers_list`
- `raw_requesters_list`
- `raw_qa_requesters`
- `raw_requesters_all_irs`
- `raw_requesters_teid`

Derived mock tables used by the processor:

- `bod_lookup`
- `site_catalog`
- `site_reference`
- `requestor_reference`
- `stg_irs_pin_registry`
- `stg_irs_teid_registry`

Recommended VS Code extension:

- `SQLite` by `alexcvzz`

Open the database in VS Code:

1. Open the Command Palette
2. Run `SQLite: Open Database`
3. Select `mock/data/mock_irs_pin.db`

## What this mock is good for

- validate parsing and row classification
- validate BOD -> customer name lookup
- validate site name fuzzy matching
- validate TEID resolution and new-site assignment
- validate deterministic PIN generation
- inspect the final Connect-ready payload before real API integration

## What is still mocked

- `fK_Location` is exact only where the PRD or data gave a confirmed real value
- most `fK_Location` values are deterministic mock values because the provided source exports do not contain the real numeric `fK_Location`
- no real Connect auth, search, insert, or update call is made in this folder

## Handoff docs

If you want another LLM to convert this mock into QA or production code, start with:

- [MOCK_Project_Summary.md](/E:/ad-astra/031 IRS PIN Generator/mock/MOCK_Project_Summary.md)
- [MASTER_PROMPT_QA_PROD.md](/E:/ad-astra/031 IRS PIN Generator/mock/MASTER_PROMPT_QA_PROD.md)

## Important assumptions

- Latest PRD guidance is used for the email domain: `ad-astrainc.com`.
- `fK_DefaultNativeLanguage` is `null`, per v7.
- Address, city, state, postal code, and coordinates use the confirmed Jacksonville fallback from v7.
- `fK_Location` is deterministic in the mock database; known real values are used where the PRD provided them explicitly.
