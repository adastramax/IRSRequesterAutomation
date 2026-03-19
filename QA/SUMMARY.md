# QA Summary

This file is the compact but complete handoff for the current QA implementation. A new LLM should be able to continue from this document plus `QA/README_local.md` and `QA/Maste_Prompt_LLM_QA.md` without replaying chat history.

## 1. Goal

Preserve and continue the current live QA IRS PIN workflow in `QA/`:

- parse rows
- resolve customer/BOD
- resolve site string and TEID
- resolve max PIN
- generate deterministic next PIN
- create or deactivate requesters on live QA
- keep one processor shared by CLI, FastAPI, and Streamlit

Current Streamlit UX:

- left sidebar pages:
  - Add Requester
  - Deactivate Requester
  - Dev Use
- Add Requester supports:
  - bulk upload
  - `Manual Entry` inside one workflow
- Add Requester helper copy is:
  - `Upload a file for multiple requesters, or enter one requester below.`
- Deactivate Requester uses the same clean operations-style layout
- Dev Use remains the raw/debug page, but it is now behind a lightweight frontend sign-in gate in `frontend.py`

## 2. Current Code Shape

The active QA codebase is:

- `QA/main.py`
- `QA/app.py`
- `QA/frontend.py`
- `QA/utils/client.py`
- `QA/utils/helpers.py`
- `QA/src/qa_irs_pin/config.py`
- `QA/src/qa_irs_pin/models.py`
- `QA/src/qa_irs_pin/parser.py`
- `QA/src/qa_irs_pin/matching.py`
- `QA/src/qa_irs_pin/payloads.py`
- `QA/src/qa_irs_pin/processor.py`
- `QA/src/qa_irs_pin/registry.py`
- `QA/data/qa_irs_pin.db`

Architecture currently remains split across parser, matching, payloads, and processor:

- parser, matching, payloads, processor stay separated
- service layer uses live QA APIs
- one processor drives CLI, FastAPI, and Streamlit
- local SQLite is still used for audit / registry

Important source-of-truth rule:

- `QA/src/qa_irs_pin/processor.py` is the backend source of truth
- `QA/app.py` should stay a thin wrapper over that backend flow

## 3. Core Contract Discoveries

These are the most important QA truths and must not be regressed.

### Insert vs Update

- `Insert` uses lower-camel browser-style form fields
- `Update` uses fuller PascalCase form fields

### Verification order

Trust in this order:

1. `exports/filter`
2. `GetAccountDetailByID`
3. profile page in Connect QA

`members/filter` is secondary only.

### New-site first PIN rule

- if `maxPinCode` exists: `int(maxPinCode) + 1`
- if `maxPinCode` is null for a new site: `int(f"{teid}00001")`

### Deactivate rule

- resolve requester by SEID
- fetch live `GetAccountDetailByID`
- build `Update` payload from live detail
- refuse deactivate if detail cannot be fetched

## 4. Live QA Proof Baseline

Still-important historical proof records:

- healthy create reference:
  - `QAFIX398649`
  - GUID `37eaa03b-ed9f-47f4-8332-a9723c1f5172`
  - PIN `8178388198`
- healthy deactivate/reactivate reference:
  - `12ED42`
  - GUID `f50972f1-1e27-4180-a107-037b3f64c82b`
- proven earlier new-site 9-digit rule:
  - `MTTPA0316B`
  - GUID `22e278d4-642b-4c7f-a53e-bb77093fa509`
  - site `Tampa, FL, USA`
  - TEID `9969`
  - PIN `996900001`

Known bad exception record:

- `346EDR24`
- GUID `fdf752d3-fdf2-4d9d-838f-1f62a47ba8eb`
- earlier bad deactivate attempt left it inconsistent
- do not use it as a healthy proof target

## 5. Site Resolution Logic As Of Now

### Blank `Site ID`

This was the major backend area recently refined.

Current rule:

- manual canonical site override -> exact API 2 resolution
- else if the input clearly references an existing customer site -> existing-site path
- else -> keep original input and treat it as a new-site candidate

Important:

- local matching decides which site string to send
- API 2 is still the actual authority on whether that final site exists

This behavior lives in:

- `resolve_blank_site_id_path(...)` inside `processor.py`

### Provided `Site ID`

Current rule:

- fetch API 3 address strings for the resolved customer
- match the input site text to a canonical site string
- if `Manual Site Name` is present, use it directly
- otherwise use best canonical match
- then continue using the provided TEID

This logic is enforced in:

- `processor.py` commit path
- `app.py` review path after the review/commit parity fix

## 6. Review / Commit Parity Fix

Earlier problem:

- review in `app.py` was too permissive for provided-`Site ID` inputs
- example:
  - `Site Name = Jacksonville`
  - `Site ID = 8178`
- review looked ready
- commit correctly returned `Manual Selection Required`

Fix:

- `QA/app.py` review path now mirrors the provided-`Site ID` site-match/manual-confirmation logic from `processor.py`

Current result:

- review and commit now agree on readiness for direct-TEID flows

## 7. Commit Response Contract Fix

Earlier problem:

- `/process/commit` returned different shapes depending on `debug`

Fix:

- `QA/app.py` now always formats `/process/commit` into one frontend-friendly shape
- this stays true even when `debug=true`

Current per-row commit response always includes:

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

## 8. Frontend Contract Fix

Earlier frontend state:

- Streamlit used only legacy `/process`
- it had an operator field
- it expected old raw processor output

Current frontend state:

- manual entry uses:
  - `POST /process/review`
  - then `POST /process/commit`
- bulk CSV/XLS/XLSX upload still uses legacy:
  - `POST /process`
- operator field was removed
- Add Requester now has a cleaner two-mode workflow:
  - bulk upload at the top
  - `Manual Entry` below it
- Add Requester helper copy now reads:
  - `Upload a file for multiple requesters, or enter one requester below.`
- normal user views hide raw JSON, match scoring internals, and debug traces
- Dev Use still exposes raw review/commit responses and payload detail
- Dev Use is now gated by a lightweight frontend sign-in screen and relocks on logout
- Deactivate Requester now follows the same operations-style button pattern as Add Requester

Manual UI fields are now only:

- `BOD`
- `First Name`
- `Last Name`
- `SEID`
- `Site Name`
- `Site ID`
- `Contact Status`
- `Manual Site Name`

### Current deactivation UI

Deactivation is now a separate page with the same clean operations pattern:

- `Review`
- `Deactivate`
- `Refresh`

Normal users see polished status cards instead of raw logs.

## 9. Manual-Selection Logic Fix

Earlier helper behavior in `matching.py`:

- if input was not an exact match
- and it had `<= 1` informative token
- require manual confirmation

That was too strict and blocked safe subset matches like:

- `Flat C` -> `Flat 104-C`
- `House 101` -> canonical House 101 site

Current helper rule:

- if normalized input exactly equals matched site -> no manual selection
- else if input tokens are a subset of matched-site tokens -> no manual selection
- else -> manual selection required

Where:

- `QA/src/qa_irs_pin/matching.py`
- function `requires_explicit_site_confirmation(...)`

What this changed:

- `Flat C` now auto-posts to `Flat 104-C`
- `House 101` now auto-posts to the canonical House 101 site

What it does not change:

- API 2 remains the actual existing/new-site authority
- differentiated inputs can still stay on the new-site path for blank-`Site ID`

## 10. Live QA State Caveat Introduced By New Sites

This is important and easy to miss.

After creating new Jacksonville variants in live QA, generic inputs became less deterministic.

Observed live result:

- a generic input like `Jacksonville` may no longer stably mean `Jacksonville, FL, USA`
- because live address space now also contains entries like:
  - `Jacksonville 2`
  - `Jacksonville ATA`
  - `Jacksonville Building 3C, FL, USA`

Implication:

- canonical full site strings are safer than generic fragments
- `Manual Site Name` remains the best deterministic operator override

Do not hardcode old expectations that generic `Jacksonville` must always resolve to the original Jacksonville site.

## 11. Recent Post-Fix Live Tests

These were run through `QA/app.py` after the matcher update.

### Manual/backend proof pack

Fresh SEIDs used:

- `MTQA5201`
- `MTQA5202`
- `MTQA5203`
- `MTQA5204`
- `MTQA5205`

Observed:

- `MTQA5202` / `Flat C` -> `Flat 104-C` -> Created
- `MTQA5203` / `House 101` -> canonical House 101 site -> Created
- `MTQA5204` / `Jacksonville 2` -> stayed differentiated / created
- `MTQA5205` / `Jacksonville ATA` -> stayed differentiated / created

### Streamlit bulk proof

Bulk upload file was generated and uploaded through Streamlit.

Fresh bulk SEIDs:

- `MTQA5501`
- `MTQA5502`
- `MTQA5503`
- `MTQA5504`
- `MTQA5505`
- `MTQA5506`
- `MTQA5507`
- `MTQA5508`

Saved batch proof:

- `QA/data/output/batch_b25d4bc6-0df7-4eeb-ab9c-c6171c8ede01.json`

Observed:

- summary `Created = 8`, `total = 8`
- all eight rows were posted successfully
- verification data exists in the batch file

Notable results:

- `MTQA5507` -> `North River Grove Summit 8, TX, USA`
  - Created
  - TEID `9979`
  - PIN `997900001`
  - `addresses_after.site_present = true`
- `MTQA5508` -> `Jacksonville Building 3C, FL, USA`
  - Created
  - TEID `9980`
  - PIN `998000001`
  - `addresses_after.site_present = true`

## 12. Current FastAPI Surface

Routes currently present in `QA/app.py`:

- `GET /health`
- `POST /process`
- `POST /process/rows`
- `POST /process/commit`
- `POST /process/review`

Current meaning:

- `/process/review`: review / preview endpoint
- `/process/commit`: main frontend commit endpoint
- `/process`: legacy file/form endpoint for bulk upload
- `/process/rows`: redundant JSON commit alias

## 13. Current Cleanup State

Old proof/test SQLite files were removed.

The active QA DB is now:

- `QA/data/qa_irs_pin.db`

## 14. EC2 Deployment Snapshot

Current QA deployment baseline as of March 18, 2026:

- repo: `https://github.com/adastramax/IRSRequesterAutomation`
- branch deployed: `develop`
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

Initial `QA/docker-compose.yml` host port mappings were:

- API: `8000:8000`
- frontend: `8501:8501`

Deployment issues encountered:

- first `docker compose up -d --build` failed because host port `8000` was already allocated
- second deployment attempt with API host port `8001` also failed because `8001` was already in use
- VM port check showed:
  - `8000` occupied by `docker-proxy`
  - `8001` occupied by `gunicorn`
  - `8520` not occupied

Final working host port mappings in `QA/docker-compose.yml`:

- API: `8002:8000`
- frontend: `8520:8501`

Git / deployment flow used:

- changes made locally
- pushed to GitHub `develop`
- pulled on VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
- deployed from VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose up -d --build`

Final running state:

- `sudo docker compose ps` showed `qa-api-1` healthy on `0.0.0.0:8002->8000/tcp`
- `sudo docker compose ps` showed `qa-frontend-1` running on `0.0.0.0:8520->8501/tcp`

Final URLs:

- Streamlit frontend: `http://44.211.141.130:8520`
- API: `http://44.211.141.130:8002`

Important deployment constraints preserved:

- no app redesign
- no QA logic changes
- only deployment-level port mapping changes in `QA/docker-compose.yml`

## 15. What To Preserve

- thin wrapper `app.py`
- `processor.py` as source of truth
- lower-camel `Insert`
- detail-first `Update`
- deterministic PIN logic
- API 2 as final existing/new-site authority
- frontend manual review -> commit split
- legacy `/process` bulk upload path
- minimal changes over redesign
- clean Streamlit operations UI with Add Requester, Deactivate Requester, and Dev Use pages

## 17. Current Streamlit Testing Inputs

Bulk QA inputs live under the repo-level `input/` folder.

Current intent:

- mixed add-case CSVs for bulk upload testing
- separate deactivate CSV coverage
- English requester names with unique SEIDs
- no manual-entry rows in the bulk packs

## 16. Next-Agent Guidance

When continuing from here:

- read `QA/README_local.md`
- read this file
- read `QA/Maste_Prompt_LLM_QA.md`
- inspect `processor.py`, `matching.py`, `app.py`, and `frontend.py`

When changing behavior:

- verify against live QA, not memory
- use fresh SEIDs for create tests
- do not assume historical TEIDs still represent current QA state
- use absolute current outputs and dates in explanations
- preserve the current shared-VM host port mappings unless explicitly changed by the team:
  - API host port `8002`
  - frontend host port `8520`
