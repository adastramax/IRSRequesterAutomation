# Master LLM Prompt For QA Continuation

Use this prompt to continue QA development without replaying earlier chats.

```text
You are working in:
E:\ad-astra\031 IRS PIN Generator

Your task is to continue development of the QA version under:
E:\ad-astra\031 IRS PIN Generator\QA

Important:
- Do not redesign the system.
- Do not rebuild from scratch.
- Work QA-first.
- Preserve the current processor/module boundaries.
- Make minimal changes and verify with live QA evidence.
- `processor.py` is the backend source of truth.
- `app.py` should remain a thin wrapper over the backend flow.
- Streamlit now matters because the manual flow and legacy bulk path are active.

Read first:
- QA/README.md
- QA/SUMMARY.md
- prd/IRS_PIN_Tool_Master_V7.md

Minimum code files to inspect first:
- QA/utils/client.py
- QA/utils/helpers.py
- QA/src/qa_irs_pin/config.py
- QA/src/qa_irs_pin/parser.py
- QA/src/qa_irs_pin/matching.py
- QA/src/qa_irs_pin/payloads.py
- QA/src/qa_irs_pin/processor.py
- QA/src/qa_irs_pin/registry.py
- QA/app.py
- QA/frontend.py
- QA/main.py

Current architecture:
- parser, matcher, payloads, processor remain separate
- one processor drives CLI, FastAPI, and Streamlit
- live QA API client lives in QA/utils/client.py
- local SQLite registry/audit still uses QA/data/qa_irs_pin.db

Most important QA rules to preserve:

1. Insert vs Update contract:
- Insert uses lower-camel browser-style form payload.
- Update uses fuller PascalCase form payload.

2. Verification sources:
- Trust exports/filter and GetAccountDetailByID first.
- members/filter is secondary only.

3. New-site first PIN rule:
- if maxPinCode exists: int(maxPinCode) + 1
- if maxPinCode is null for a new site: int(f"{teid}00001")

4. Deactivate is detail-first:
- resolve GUID by search
- fetch GetAccountDetailByID for that GUID first
- build Update payload from live detail
- change only deactivate state fields
- if live detail cannot be fetched, refuse deactivate

5. Current blank-Site-ID logic in processor.py:
- manual canonical site override -> exact API 2 resolution
- else if input clearly references an existing site -> existing-site path
- else -> keep original input as new-site candidate and send it to API 2
- API 2 remains the actual authority on whether the site exists

6. Current manual-selection helper rule:
- exact normalized match -> no manual selection
- input tokens subset of matched canonical site tokens -> no manual selection
- otherwise -> require explicit confirmation
- this lives in QA/src/qa_irs_pin/matching.py

7. Live QA caveat:
- generic site fragments can drift as the live address list changes
- do not assume a generic input like "Jacksonville" will always resolve to the historical Jacksonville site once new Jacksonville variants exist
- use canonical site strings or Manual Site Name when deterministic behavior matters

8. Frontend/API contract:
- POST /process/review = preview endpoint
- POST /process/commit = main frontend commit endpoint
- POST /process = legacy bulk upload endpoint for CSV/XLS/XLSX only
- manual Streamlit flow is review -> commit
- bulk Streamlit flow stays on legacy /process
- no operator/created-by field in the frontend UI

Current FastAPI expectations:
- /process/commit must always return one consistent frontend-friendly shape
- even when debug=true
- per row include:
  - input
  - corrected_data
  - api_trace
  - connect_payload
  - result
- result includes:
  - status
  - message
  - guid
  - teid
  - pin
  - posted_payload_address

Recent QA proof records to remember:

Healthy create reference:
- SEID: QAFIX398649
- GUID: 37eaa03b-ed9f-47f4-8332-a9723c1f5172
- PIN: 8178388198

Healthy deactivate/reactivate reference:
- SEID: 12ED42
- GUID: f50972f1-1e27-4180-a107-037b3f64c82b

Known bad exception:
- SEID: 346EDR24
- GUID: fdf752d3-fdf2-4d9d-838f-1f62a47ba8eb
- inconsistent old deactivate target
- do not use as healthy proof

Recent live proofs after matcher/frontend/app fixes:
- MTQA5202: Flat C -> Flat 104-C -> Created
- MTQA5203: House 101 -> canonical House 101 site -> Created
- MTQA5204: Jacksonville 2 -> differentiated site -> Created
- MTQA5205: Jacksonville ATA -> differentiated site -> Created

Recent Streamlit bulk proof:
- batch file: QA/data/output/batch_b25d4bc6-0df7-4eeb-ab9c-c6171c8ede01.json
- all 8 rows created successfully
- proof SEIDs:
  - MTQA5501
  - MTQA5502
  - MTQA5503
  - MTQA5504
  - MTQA5505
  - MTQA5506
  - MTQA5507
  - MTQA5508
- notable new-site outcomes:
  - MTQA5507 -> North River Grove Summit 8, TX, USA -> TEID 9979 -> PIN 997900001
  - MTQA5508 -> Jacksonville Building 3C, FL, USA -> TEID 9980 -> PIN 998000001

What not to do:
- do not revert to mock-style Insert payloads
- do not replace deterministic PIN logic with random logic
- do not rebuild deactivate payload from exports/filter alone
- do not move backend truth out of processor.py
- do not remove legacy /process unless bulk upload strategy is explicitly replaced
- do not present QA-only aliases as IRS/prod truth
- do not hardcode historical TEIDs as if QA state is static

When changing code:
- explain which files changed
- preserve the proven QA payload contracts
- validate with live QA when behavior is touched
- use fresh SEIDs for create tests
- report exact SEID/GUID/TEID/PIN outcomes after testing
- if date-sensitive or state-sensitive, use concrete current values and dates
```
