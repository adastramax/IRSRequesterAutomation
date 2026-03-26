# IRS PIN QA Tool

This folder is the live QA version of the IRS PIN tool. The QA code in this folder is the current source of truth for QA behavior and it calls live QA Connect APIs on `connectapiqas.ad-astrainc.com`.

## Current Architecture

Core files:

- `main.py`: CLI entry point
- `app.py`: FastAPI wrapper
- `frontend.py`: Streamlit UI
- `utils/client.py`: live QA API client
- `utils/helpers.py`: shared helpers
- `src/qa_irs_pin/config.py`: QA config, aliases, defaults
- `src/qa_irs_pin/parser.py`: CSV/XLS/XLSX/manual row parsing
- `src/qa_irs_pin/matching.py`: fuzzy matching and manual-selection helper logic
- `src/qa_irs_pin/payloads.py`: Connect `Insert` / `Update` payload builders
- `src/qa_irs_pin/processor.py`: source-of-truth backend flow
- `src/qa_irs_pin/registry.py`: local SQLite audit/registry
- `data/qa_irs_pin.db`: local SQLite audit database

Important:

- `processor.py` is the backend source of truth
- one processor still drives CLI, FastAPI, and Streamlit
- `app.py` should stay a thin wrapper over `processor.py`
- use this file together with `QA/SUMMARY.md` and `QA/Maste_Prompt_LLM_QA.md` for QA handoff
- local audit retention cleanup now runs automatically in the registry layer

## Core QA Rules To Preserve

1. Insert vs Update contract
- `Insert` uses lower-camel browser-style form fields
- `Update` uses fuller PascalCase-style form fields

2. Verification sources
- trust `exports/filter`
- then `GetAccountDetailByID`
- profile page in Connect QA is tertiary visual confirmation
- `members/filter` is secondary only

3. New-site first PIN rule
- if `maxPinCode` exists: `int(maxPinCode) + 1`
- if `maxPinCode` is null for a new site:
  - default/non-Esided accounts use 9-digit-total new-site PIN logic
  - `Esided` uses its working account-specific suffix-width rule
  - for current live QA, `Esided` first new-site PIN remains `TEID + 0001`
- new-site TEIDs must remain 4 digits
- if the next new-site TEID would exceed `9999`, the app must fail safely and must not assign `10000`

4. Deactivate is detail-first
- resolve latest valid requester by SEID
- fetch `GetAccountDetailByID`
- build update payload from live detail
- refuse deactivate if detail cannot be fetched

5. QA aliases are not IRS production truth
- QA aliases in config are QA-only conveniences
- current active QA test aliases include:
  - `ES` -> `Esided`
  - `ATC` / `ALMAS` -> `Almas Test Company`
  - `FEDX` / `FCD` -> `FedEx Capital District`

## Current Site-Resolution Flow

### If `Site ID` is provided

1. resolve customer/BOD
2. fetch API 3 address strings for that customer
3. fuzzy match the input site text against those addresses
4. if `Manual Site Name` is present, use it directly
5. otherwise use the best canonical match
6. manual confirmation is only required when the match is genuinely unsafe
7. use the provided TEID for API 1 / PIN context / commit

### If `Site ID` is blank

1. resolve customer/BOD
2. fetch API 3 address strings
3. decide whether the input looks like:
- an existing-site reference
- or a true new-site candidate
4. existing-site reference:
- send the matched canonical site string to API 2
5. new-site candidate:
- send the original input string to API 2
6. API 2 is the actual authority for existing vs new TEID
7. if API 2 says new site:
- assign `currentMaxTeid + 1`
- within one run, distinct new sites must get unique sequential TEIDs
- within one run, repeated same new site must reuse the same TEID

## Current Matching / Manual Selection Behavior

The current matcher intentionally supports these behaviors:

- safe subset existing-site matches auto-proceed
- differentiated inputs do not silently collapse to an older site
- API 2 remains the real final site-existence check

Examples that should auto-proceed:

- `Flat C` -> `Flat 104-C`
- `House 101` -> `House 101, Al Rehman Villas, street 10, BMCHS, 753`

Examples that should stay on the new-site path when `Site ID` is blank:

- `Jacksonville 2`
- `Jacksonville ATA`
- `North River Grove Summit 8, TX, USA`

Manual selection is still required when:

- no candidate is good enough
- multiple plausible existing candidates are ambiguous
- the row is not safe to auto-collapse

Important live QA caveat:

- generic inputs can drift as the live Markytech address list grows
- example: once `Jacksonville 2` and `Jacksonville ATA` exist in QA, a generic input like `Jacksonville` may no longer be deterministic
- for stable/operator-safe behavior, prefer canonical full site strings or use `Manual Site Name`

## FastAPI Contract

Main frontend endpoints:

- `POST /process/review`
- `POST /process/commit`

Legacy bulk endpoint:

- `POST /process`

### `/process/review`

Purpose:

- preview site correction, TEID resolution, notes, and suggested payload
- no Connect mutation

Input:

```json
{
  "rows": [
    {
      "BOD": "MT",
      "First Name": "John",
      "Last Name": "Doe",
      "SEID": "JD1001",
      "Site Name": "Jacksonville, FL, USA",
      "Site ID": "",
      "Contact Status": "Add",
      "Manual Site Name": ""
    }
  ],
  "write_output": false,
  "debug": true
}
```

### `/process/commit`

Purpose:

- run the real backend flow in `processor.py`
- create / deactivate / detect already-exists / manual-selection-required

Current response shape is consistent even when `debug=true`:

- `input`
- `corrected_data`
- `api_trace`
- `connect_payload`
- `result`

`result` includes:

- `status`
- `message`
- `guid`
- `teid`
- `pin`
- `posted_payload_address`

Current add payload identity remap:

- outgoing create payload uses:
  - `firstName = SEID`
  - `lastName = "<First Name> <Last Name>"`
  - `email = "<SEID>.<First Name>.<Last Name>@ad-astrainc.com"` in lowercase

### `/process`

Purpose:

- legacy file/form endpoint
- still used for bulk CSV/XLS/XLSX upload

## Streamlit Contract

Manual path:

- use `/process/review`
- then `/process/commit`

Bulk path:

- keep using legacy `/process`

Deactivate bulk path:

- use `/process/commit`

Current UI rules:

- no operator / created-by field in the UI
- manual entry fields:
  - `BOD`
  - `First Name`
  - `Last Name`
  - `SEID`
  - `Site Name`
  - `Site ID`
  - `Contact Status`
  - `Manual Site Name`
- Add manual entry label now clarifies that `Manual Site Name` is only for manual-selection-required cases
- Add Requester keeps bulk upload above a `Manual Entry` expander
- Add Requester helper copy is:
  - `Upload a file for multiple requesters, or enter one requester below.`
- processed results show full client name like `Markytech` in `BOD`
- manual entry review/processed cards also show the resolved full `BOD`
- Dev Use is protected by a lightweight frontend sign-in gate before raw/debug tools are shown
- Dev Use login constants currently live in `QA/frontend.py`
- Add user-visible reviewed/results/export tables include `GENERATED PIN`
- Deactivate user-visible reviewed/results/export tables do not include `GENERATED PIN`
- Deactivate review tables do not rely on a final `NAME`; they use concise status messaging such as `Ready for deactivate`
- Deactivate processed/results/export `NAME` shows only the real full human name, not `SEID Full Name`

## QA EC2 Deployment Snapshot

Current deployment baseline as of March 18, 2026:

- repo: `https://github.com/adastramax/IRSRequesterAutomation`
- branch: `develop`
- VM OS: Ubuntu EC2
- EC2 public IP: `44.211.141.130`
- EC2 public DNS: `ec2-44-211-141-130.compute-1.amazonaws.com`
- SSH user: `ubuntu`
- working Windows SSH key used: `E:\ad-astra\jahangeer 1.pem`
- confirmed SSH command:
  - `ssh -i "E:\ad-astra\jahangeer 1.pem" ubuntu@44.211.141.130`

VM paths:

- repo path on VM: `/home/ubuntu/IRSRequesterAutomation`
- QA app path on VM: `/home/ubuntu/IRSRequesterAutomation/QA`

Verified on VM:

- Git `2.43.0`
- Docker `27.5.1`
- Docker Compose `2.33.0`

Deployment flow used:

- make deployment changes locally
- push to GitHub `develop`
- pull on VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
- deploy on VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose up -d --build`

Deployment issue encountered on shared VM:

- original API host port `8000` was already allocated
- second attempt with API host port `8001` also failed because `8001` was already in use
- VM port check showed:
  - `8000` occupied by `docker-proxy`
  - `8001` occupied by `gunicorn`
  - `8520` free

Final working host port mappings in `QA/docker-compose.yml`:

- API: `8002:8000`
- frontend: `8520:8501`

Final running state on VM:

- `qa-api-1` healthy on `0.0.0.0:8002->8000/tcp`
- `qa-frontend-1` running on `0.0.0.0:8520->8501/tcp`

Final URLs:

- Streamlit frontend: `http://44.211.141.130:8520`
- API: `http://44.211.141.130:8002`

Important deployment constraint preserved:

- no app redesign
- no QA logic changes
- only deployment-level port mapping changes in `QA/docker-compose.yml`

## QA Handoff Set

If another LLM needs to continue QA work, give it these three files first:

- `QA/README_local.md`
- `QA/SUMMARY.md`
- `QA/Maste_Prompt_LLM_QA.md`

## Current Verified Behaviors

Backend/core is verified for:

- existing site with TEID provided
- existing site with TEID missing
- true new site with TEID missing
- safe failure when a new-site TEID would exceed `9999`
- direct-site-ID canonical override
- detail-first deactivate
- bulk upload through Streamlit legacy `/process`
- review/commit parity for provided `Site ID` cases
- payload-address preservation on new-site blank-`Site ID` commits
- safe-subset auto-match for `Flat C` and `House 101`
- same-run unique sequential TEID allocation for distinct new sites
- same-run TEID reuse for repeated same new site
- review/commit TEID parity for same-run new-site preview
- deactivate bulk CSV/XLS/XLSX handling

Latest live QA verification on March 27, 2026:

- manual add passed for:
  - `Esided`
  - `Almas Test Company`
  - `FedEx Capital District`
- bulk add passed for:
  - `Esided`
  - `Almas Test Company`
  - `FedEx Capital District`
- manual deactivate passed
- bulk deactivate passed
- current live existing-site TEIDs used in the latest proof run:
  - `Esided` -> `9963`
  - `Almas Test Company` -> `7583`
  - `FedEx Capital District` -> `5872`
- latest live create/deactivate proof run:
  - `ESL0327021919` -> Created -> GUID `de275244-8805-4d48-8bfe-c0a8a5a5bca7` -> TEID `9963` -> PIN `99636404` -> later Deactivated
  - `ATL0327021919` -> Created -> GUID `0c265865-2d04-465c-b23a-bc01acbb7810` -> TEID `9922` -> PIN `992200001` -> later Deactivated
  - `FDL0327021919` -> Created -> GUID `3d855d81-1362-4d37-9c8f-ea65a0c59ecf` -> TEID `7396` -> PIN `739600001` -> later Deactivated
  - `ESB0327021919` -> bulk Created -> GUID `a37e92a3-9938-4b05-bbd3-cf2d90d8cdf4` -> TEID `9963` -> PIN `99636405` -> later Deactivated
  - `ATB0327021919` -> bulk Created -> GUID `4584263f-19cc-4f89-a398-0a99e422807e` -> TEID `7583` -> PIN `75833757` -> later Deactivated
  - `FDB0327021919` -> bulk Created -> GUID `169cc964-b8ed-48e8-8c42-ed635631ae22` -> TEID `5872` -> PIN `58722156` -> later Deactivated
- current Esided live new-site guard proof:
  - review for `ESN0327021648` failed with `Cannot assign a new TEID because the 4-digit TEID limit of 9999 has been reached.`
  - commit for the same case returned row status `Failed` with the same message

Recent live QA bulk proof:

- uploaded `8` rows through Streamlit bulk upload
- batch file saved under `QA/data/output/`
- all `8` rows were `Created`
- proof SEIDs:
  - `MTQA5501`
  - `MTQA5502`
  - `MTQA5503`
  - `MTQA5504`
  - `MTQA5505`
  - `MTQA5506`
  - `MTQA5507`
  - `MTQA5508`

True new-site examples now proven in current QA state:

- `North River Grove Summit 8, TX, USA` -> new TEID `9979` -> PIN `997900001`
- `Jacksonville Building 3C, FL, USA` -> new TEID `9980` -> PIN `998000001`
- `Idaho library 2nd room` / `Esided` -> new TEID `9989` -> first PIN `99890001` -> next created proof `yyyy12345` with PIN `99890002`
- `Esided Fixback Site 26 Mar 2026 B` / `Esided` -> new TEID `9997` -> first PIN `99970001`
- `Codex ATC New Site 0327021648` / `Almas Test Company` -> new TEID `9920` -> PIN `992000001`
- `Codex FCD New Site 0327021648` / `FedEx Capital District` -> new TEID `7395` -> PIN `739500001`

## Known Caveats

Known bad inconsistent deactivate proof target:

- Markytech / `346EDR24`
- GUID `fdf752d3-fdf2-4d9d-838f-1f62a47ba8eb`

State:

- earlier bad deactivate attempt left it inconsistent
- `exports/filter` showed `Active`
- `GetAccountDetailByID` failed
- current code correctly refuses detail-less deactivate on such records

Important project caveat:

- QA state changes over time
- TEIDs, max PINs, and address lists are live and unstable
- never hardcode old TEID expectations for fresh new-site proofs

## What To Preserve

- thin `app.py`
- `processor.py` as backend source of truth
- lower-camel `Insert`
- detail-first `Update`
- deterministic PIN logic
- hybrid new-site first PIN logic:
  - default/non-Esided accounts use 9-digit-total new-site PIN logic
  - `Esided` keeps its working account-specific first-PIN format
- 4-digit TEID guard:
  - never assign a new-site TEID above `9999`
  - fail safely instead
- API 2 as final existing/new-site authority
- minimal changes over redesign
- local SQLite audit/registry is supporting state only, not live QA business truth

## Local Audit DB Retention

- active local audit DB path:
  - `QA/data/qa_irs_pin.db`
- purpose:
  - local audit trail
  - batch history
  - row-level tracking
- it is not the source of truth for live create/deactivate/site/TEID decisions
- automatic cleanup now removes old audit data
- default retention:
  - `7` days
- env var:
  - `QA_AUDIT_RETENTION_DAYS`
- cleanup deletes:
  - old `batch_audit` rows
  - matching `stg_irs_pin_registry` rows for those batch ids
