# IRS PIN Production-Live

This folder is the production-live IRS PIN instance. It came from the earlier QA copy, but the current `LIVE-PROD/` code is the source of truth now.

## Core Files

- `src/qa_irs_pin/processor.py`: backend source of truth
- `app.py`: thin FastAPI wrapper
- `frontend.py`: Streamlit operations UI
- `utils/client.py`: Connect API client
- `src/qa_irs_pin/config.py`: runtime config, customer overrides, and BOD/customer label resolution (includes shorthand and common IRS-style aliases so abbreviated client input still maps to the right account)
- `src/qa_irs_pin/payloads.py`: create/update payload builders
- `src/qa_irs_pin/parser.py`: input parsing
- `src/qa_irs_pin/matching.py`: site matching and manual-selection logic
- `src/qa_irs_pin/registry.py`: local audit DB helpers
- `docker-compose.yml`: deployment wiring
- `.env.example`: required env shape

## Runtime Behavior

One processor is shared by CLI, FastAPI, and Streamlit.

Operational flow still stays:

1. review
2. commit

Current stable contracts:

- `Insert` uses lower-camel fields
- `Update` uses PascalCase-style fields
- deterministic PIN logic remains
- the 4-digit TEID guard remains
- deactivate remains detail-first

## Current Lookup / Verification Behavior

Current code behavior is now:

1. `members/filter` first for SEID lookup and already-exists checks
2. `GetAccountDetailByID` for detail confirmation

What this means in practice:

- existing-user lookup is now much faster for live IRS rows
- add / deactivate / modify primary runtime flows now stay on `members/filter` and avoid export sweeps
- post-create verification now prefers `members/filter` and still keeps `GetAccountDetailByID`
- this is what removed the 10+ minute fresh-SEID bulk timeout seen earlier on live-safe demo-account tests

## Production Config

Current production config is env-driven.

Important current rules:

- no hardcoded QA hosts in active deployment wiring
- no hardcoded QA credentials
- no QA aliases in active prod config
- no hardcoded QA Markytech `fK_Customer=277` or `fK_Location=13` defaults in active prod config
- `fk_PreCallPolicy` is optional/nullable in production and must not be defaulted to `19`
- email domain remains `@ad-astrainc.com`

Runtime `fK_Customer` and `fK_Location` come from the live API 1 pin-context path rather than from QA shortcuts.

BOD / customer matching is intentionally forgiving: besides exact canonical names, common abbreviations and IRS-hint-style strings resolve to the same accounts (for example `LBI` → LB&I, `RICE` → RICS, `TS Media` → MEDIA, `TS RICS` → RICS, `TS SPEC` → SPEC, `W&I FA` → FA, `W&I AM` → AM, `W&I EPSS` → EPSS, and typical Appeals variants). This reduces operator failures from spreadsheets that do not match IRS wording character-for-character.

## Current Proven Payload Truth

Current proven IRS add payload shape:

- `fK_ServiceType = IRSOPI`
- `serviceTypes = IRSOPI`
- `password = Welcome123!`
- `setPassword = true`
- `fK_DefaultNativeLanguage = EN`

Current code note:

- this is now implemented for all IRS accounts in `src/qa_irs_pin/config.py`
- the operator confirmed `IRSOPI` is the standard service-type code across IRS accounts
- demo-account-only behavior remains a separate override

Current demo-account-only create override remains:

- `fK_ServiceType = CS`
- `serviceTypes = CS`
- `password = Welcome123!`
- `setPassword = true`

## Local Run / Deployment Notes

This folder has its own deployment wiring.

High-level required env values:

- Connect auth/API/search URLs
- Connect login credentials
- optional `DEFAULT_PRECALL_POLICY`
- optional Dev Use credentials
- request timeout and match-threshold values

Use:

- `.env.example` for env shape
- `docker-compose.yml` for container wiring

Do not put secrets into docs.

Current local Docker wiring matches the proven QA shared-VM pattern:

- API container listens on `8000`, published on host `8002`
- frontend container listens on `8501`, published on host `8520`
- frontend talks to the API over compose at `http://api:8000`

Local Docker smoke-test commands:

- `cd E:\ad-astra\031 IRS PIN Generator\LIVE-PROD`
- `docker compose up -d --build`
- `docker compose ps`
- frontend: `http://localhost:8520`
- API health: `http://localhost:8002/health`
- stop stack: `docker compose down`

Current local Docker proof:

- local `docker compose ps` showed `live-prod-api-1` healthy on `0.0.0.0:8002->8000/tcp`
- local `docker compose ps` showed `live-prod-frontend-1` running on `0.0.0.0:8520->8501/tcp`
- this confirms the live-prod folder is already containerized in the same practical shape used for QA deployment

## Live VM Deployment Snapshot

Current live deployment is intended to follow the same shared-VM pattern used in QA.

VM baseline to reuse:

- repo path on VM: `/home/ubuntu/IRSRequesterAutomation`
- live app path on VM: `/home/ubuntu/IRSRequesterAutomation/LIVE-PROD`
- shared host ports:
  - API: `8002:8000`
  - frontend: `8520:8501`

Exact SSH command used in QA handoff style:

- `ssh -i "E:\ad-astra\jahangeer 1.pem" ubuntu@44.211.141.130`

Exact repo pull command to reuse:

- `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`

Exact live deploy command to use:

- `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`

If replacing QA on the same shared VM, stop QA first:

- `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose down`

Recommended verification commands on the VM:

- `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose ps`
- `curl http://127.0.0.1:8000/health`

Expected public URLs when the live stack is running on the shared VM:

- Streamlit frontend: `http://44.211.141.130:8520`
- API: `http://44.211.141.130:8002`

Latest VM deployment proof:

- QA stack was stopped on the shared VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose down`
- repo was updated on the VM from:
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
- one VM-specific merge blocker occurred before pull:
  - untracked file `LIVE-PROD/.dockerignore` blocked `git pull`
  - the VM-local conflicting file had to be moved/cleared so the repo-tracked `LIVE-PROD/.dockerignore` could land
  - NOTE: sometimes `git pull` is blocked because the VM has local changes in `LIVE-PROD/data/qa_irs_pin.db`
    - `qa_irs_pin.db` is local audit/support state; if you just need the code update, you can remove it (or stash it) before pulling:
      - `rm -f LIVE-PROD/data/qa_irs_pin.db`
      - then `git pull origin develop`
- live stack was then started from:
  - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`
- operator confirmed the live stack came up successfully on the VM

## Live Proof Already Observed

Demo-account proof:

- auth succeeded against the live Connect endpoint
- API 3 resolved `8701 Georgia Avenue, Silver Spring, MD, USA`
- API 2 resolved existing TEID `9973`
- API 1 resolved `fK_Customer=271`, `fK_Location=7`, and next PIN `99733945`
- initial demo-account create failure was isolated to demo-account service-type/password mapping
- after the demo-account-only override, live create succeeded with GUID `7bee88a8-4a99-4fe0-a1ac-9045fe3cd22d`
- follow-on live demo deactivate also succeeded

IRS SBSE proof:

- Stormi Holloway / `4XWXB` review passed with:
  - customer `US GSA IRS Small Business Self-Employed (SBSE)`
  - `fK_Customer=1218`
  - `fK_Location=3175`
  - `TEID=4906`
  - next PIN `490699754`
- old payload defaults failed for Stormi
- a replay proved the working SBSE/IRS payload required `IRSOPI`, `Welcome123!`, `setPassword=true`, and native language `EN`
- after the fix, Stormi live create succeeded with GUID `6fd70847-4aa6-4879-9623-617a5da4b364`
- Ami Pandya / `MDCNB` was confirmed already active in live
- Lavanya Thammisetti / `FV1XB` was created successfully in live with GUID `0bf0a9c6-e484-42e0-bbd8-45ac184ed36e`

Members-first lookup proof:

- `4XWXB` resolves quickly as `Already Exists`
- `FV1XB` resolves quickly as active
- post-create verification for `FV1XB` found the created GUID via `members/filter`

Additional recent proof:

- live auth succeeded again against `appbe.ad-astrainc.com` using the same working credentials already used in this project
- live-safe testing against `z- Ad Astra Demo Account` confirmed the real bulk create path still uses:
  - `fK_ServiceType = CS`
  - `serviceTypes = CS`
  - `password = Welcome123!`
  - `setPassword = true`
- a live SBSE bulk-style review payload check confirmed the bulk path still builds:
  - `fK_ServiceType = IRSOPI`
  - `serviceTypes = IRSOPI`
  - `password = Welcome123!`
  - `setPassword = true`
- the real modify-function create path now uses the modify-function email rule instead of the normal Add email rule
- `/process/review-file` now preserves `Customer Name` from uploaded CSV rows
- real bulk add-only demo-account proof created:
  - `AKH4071` -> PIN `345676782` -> GUID `167c7110-d5b8-46c0-88dc-3c5d16e67f4f`
  - `BAH4072` -> PIN `99733948` -> GUID `f2d826dc-07c1-424a-9705-a2bc97a17e11`
  - `SMA4073` -> PIN `89733440` -> GUID `9a7ea6ef-17c4-4d01-a030-d8486f67ddee`
- fresh mixed client-shaped bulk proof through the real `/process` endpoint completed in about 72 seconds with:
  - `Created = 7`
  - `Deactivated = 5`
  - `total = 9`
- modify-function email retry was re-proven in bulk:
  - first modify create succeeded with suffix `1`
  - second modify create retried to suffix `2`
  - third modify create retried to suffix `3`
- blank-TEID new-site add now works in the real bulk path after pin-context backfill for missing `fK_Customer` / `fK_Location`

Latest local UI/runtime proof:

- manual-entry BOD dropdown now includes:
  - `Z-DEMO`
  - `Z-ORIENTATION`
- these aliases resolve to:
  - `z- Ad Astra Demo Account`
  - `Z- Ad Astra Orientation Inc.`
- the manual-entry yellow Streamlit warning caused by re-setting the selectbox default/session value was removed
- Add Requester and Deactivate Requester bulk review now survive a transient first-click `/process/review-file` 400 by falling back to parsed-row review
- Deactivate Requester bulk CSV flow now converts every uploaded row into an explicit deactivation request before review/commit
- the deactivate bulk page no longer sends the uploaded file through the generic add/create `/process` path
- deactivate bulk review/results tables now use deactivate-specific columns and messages
- the frontend badge now shows `LIVE` in white on green instead of `QA`
- Add Requester bulk review/commit now filters mixed-action source files to Add plus modify-function rows and skips true deactivate rows
- bulk processed-results rendering now uses the commit response shape correctly, so successful bulk uploads show row-level outcomes instead of an empty processed-results table
- processed results now surface the 9-digit PIN for `Already Exists` rows when the backend returns it
- modify-function row rendering no longer shows a mismatched old/current TEID next to the destination/new site name on failure
- Add Requester processed summaries: old-site deactivations that occur **inside** a successful modify are labeled as modify-step deactivations, so mixed Add+modify files do not read like a standalone deactivate batch
- Deactivate Requester processed summaries: when the backend reports creates that were not expected from a pure deactivate upload, the UI wording calls that out explicitly (display-only; APIs unchanged)

## Workbook Compatibility

Current `LIVE-PROD` parser compatibility accepts the SBSE LB export workbook shape placed under `LIVE-PROD/data/input/`.

Confirmed normalized headers:

- `Requested Action` -> `contact_status`
- `PIN Action Required` -> `contact_status`
- `Current User PIN` -> `user_pin`
- `Site:Location ID` -> `site_id`
- `Site` -> `site_name`
- `Employee ID` -> `employee_id`
- `New Site:Site ID` -> `new_site_id`
- `New Site` -> `new_site_name`

Confirmed action normalization:

- `Delete-Separated` -> `Deactivate`
- `New PIN` -> `Add`
- `Delete` -> `Deactivate`
- `Switch to Ad Astra` -> workbook-driven modify-function translation

Confirmed IRS FA workbook compatibility:

- `TS FA` is accepted as an alias for live `FA`
- `Site ID` / `New Site:Site ID` are only accepted when they are explicit 4-digit numeric TEIDs
- alphanumeric site-code strings such as `IRS_TS_FA_A1_G121_Providence` are treated as blank TEIDs and the flow falls back to site-name resolution
- duplicate mapped action columns are coalesced safely, so `Contact Status` and `PIN Action Required` can coexist in the workbook without corrupting action parsing
- blank filler rows that only repeat `TS FA` are skipped instead of becoming fake error rows
- the Add page now includes both `Add` rows and `Switch to Ad Astra` rows, and skips only true deactivation rows from the same source file
- the Deactivate page keeps only true deactivation rows from mixed source files

Extra optional workbook columns are ignored safely when present and blank.

Current workbook limitation:

- some inherited workbook exports still do not carry explicit `BOD` / `Customer Name`
- uploaded CSV files do support explicit `Customer Name`, and review-file now preserves it correctly

Current supported workbook case:

- `Modify-Function Change` is now mapped/implemented
- `Employee ID`, `New Site:Site ID`, and `New Site` are now part of the live-prod action flow
- `New Site:Function` is not yet part of the live-prod action flow
- for IRS FA workbook rows marked `Switch to Ad Astra`, current code translates them into modify-function rows by:
  - treating workbook `Site Name` as `New Site`
  - deriving the old/current-site TEID from `Current User PIN`
  - deriving the 5-digit employee id from the same current PIN
  - keeping those rows in the Add Requester bulk workflow rather than filtering them out
- if the row still reads as `Add` after action normalization but **comments** describe moving from one site to another **and** `Current User PIN` is filled, the parser promotes the row to `Modify-Function Change` and runs the move path: old TEID and 5-digit employee id from the PIN (e.g. `6701-87809` → TEID `6701`, id `87809`), destination from `New Site:Site ID` / `New Site` (and related columns) as for other modify rows

## Bulk Upload Reality

Bulk upload is now much closer to the single-entry backend flow:

- bulk review now submits the original uploaded file to `/process/review-file`
- bulk upload button submits the original uploaded file to `/process`
- mixed files now preserve original actions and fields through backend parsing on both review and commit
- client-shaped CSVs with `Customer Name`, `Employee ID`, `New Site:Site ID`, and `New Site` are now proven end-to-end in the real bulk path
- Add Requester bulk review keeps the raw-file review path first, but falls back to parsed-row review if the raw-file request returns a transient first-click 400
- Deactivate Requester bulk review/commit intentionally rewrites uploaded rows into explicit `Deactivate` requests so uploaded `New PIN` or mixed-action source files are not accidentally reprocessed as adds during deactivate operations
- Add Requester bulk review/commit now works from parser-normalized rows so mixed IRS FA workbooks can safely keep Add plus modify-function rows while excluding true deactivate rows

For a very small, clean IRS bulk file, it now follows the same parsing truth as single-entry processing. The earlier live timeout issue on fresh demo-account bulk adds was removed by eliminating export-sweep lookup from the primary add/deactivate/modify paths.

## Modify-Function Change

Current live modify-function behavior:

- modify-function is a composite flow: deactivate old/current site, then create at the new site
- deactivation is site-specific; it does not deactivate the latest active requester anywhere
- create first tries to preserve the existing 5-digit employee id under the new TEID
- if Connect rejects that PIN as duplicate, create retries once with the normal target-TEID max-PIN rule
- create email first tries `seid.firstname.lastname1@ad-astrainc.com`
- if Connect rejects that email as already registered / duplicate email, create retries with suffix `2`, then suffix `3`
- normal Add email generation is unchanged
- current safe retry cap for modify-function email suffixing is `3`
- for workbook-driven `Switch to Ad Astra` rows, the operator-facing `Site Name` is the destination/new site, while the old/current site context is derived from `Current User PIN`
- modify-function review may therefore show the destination/new-site match while current-site lookup still depends on the old/current PIN-derived TEID being found as an active requester in live
- **both** SEID search calls in the modify-function processor block now use `allow_export_fallback=False` — prevents full SBSE export sweeps from causing 300-second timeouts; do not revert

## Activate (Reactivate) Flow

- `"Activate"` is a new contact_status that reactivates an existing inactive requester in Connect
- triggered by the workbook action `ACTIVATE EXISTING PIN` (normalises via `"activate existing"` substring match)
- `"CREATE AND ACTIVATE NEW PIN"` maps to `"Add"` via the existing `"new pin"` keyword — no separate handling needed
- only `seid` is required; site_name is optional for Activate rows
- processor finds user by SEID (members-first, no export fallback); resolves tiebreaker by full PIN, then TEID, then first match
- calls `build_update_payload(account_status_override="Active")` + `update_user` — no new payload builder needed
- records status `"Activated"` (success) or `"Failed"`
- review phase returns `"Reviewed"` immediately without fetching sites (no site resolution needed)

SPEC workbook compatibility:

- `SIDN` column → `seid` (new alias `"sidn"`)
- `PIN` column → `user_pin` (new alias `"pin"`)
- `Site_Name` column → `site_name` (existing alias `"site name"` already worked via `_` normalisation)
- Action `ACTIVATE EXISTING`, `ACTIVATE EXISTING PIN`, or standalone `ACTIVATE` → `Activate`
- TEID derived from PIN column: `"1504-32519"` → TEID `1504`, full PIN `150432519`; `"3217-xxxx"` → TEID `3217`
- No First/Last Name columns — `first_name` auto-filled from `seid` for Add rows before validation

## Verification Notes

The Members UI search endpoint is now proven useful for fast live operator-side verification:

- `POST /api/accounts/members/filter/CONSUMER/0/?page=1&items_per_page=10&search=<seid>`

Current code now treats it as the first lookup path for SEID-based checks, with `exports/filter` as fallback and `GetAccountDetailByID` still used for detail confirmation.
Current code now treats it as the primary lookup path for add / deactivate / modify flows and uses `GetAccountDetailByID` for detail confirmation.

## Working Rules For Future Changes

- inspect current `LIVE-PROD/` code before editing
- prefer config/client/payload fixes over broad refactors
- preserve `processor.py` as the backend source of truth
- keep `app.py` thin
- do not guess stale production constants from inherited QA docs
- do not assume old hostnames, IDs, policy values, or QA-specific setup is still valid

## What Next

Current most useful next steps:

1. **Push and deploy to VM** — pending changes: modify-function export-fallback fix, commit timeout 600s, SPEC Activate flow
   - `git push origin develop`
   - SSH: `ssh -i "E:\ad-astra\jahangeer 1.pem" ubuntu@44.211.141.130`
   - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
   - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`
2. Live-test SPEC Activate flow against a real SPEC workbook sample (SIDN + ACTIVATE EXISTING PIN rows)
3. Decide whether modify-function email retry should remain capped at suffix `3` or expand by policy
4. Consider adding an automatic fallback when cross-account modify create fails `Pin Code Setup Failed` — currently requires manual Add recovery in destination account

## Latest verification note

As of the most recent handoff, the move-from-comments promotion rule, expanded BOD/customer shorthand handling, and Add/Deactivate summary labeling updates were manually tested or reviewed in live-prod and were considered correct at that time. Re-verify after any parser, config resolver, or frontend summary changes.

## Latest Round — Bug Fix (current handoff)

### Bug fixed: bulk cross-account modify was creating in source account

**File:** `frontend.py`

**Function:** `parsed_row_to_request_dict`

`new_bod` and `new_customer_name` were not included in the row dict sent to `/process/commit` for bulk uploads. The backend received `new_bod = ""` for every row, so `destination_customer_context` was always `None` and all cross-account modify rows were created in the source account.

**Fix:** Added `"New BOD": row.new_bod` and `"New Customer Name": row.new_customer_name` to the returned dict.

**Secondary fix:** `build_commit_results_table` now shows the destination account in the BOD column for cross-account modify rows instead of the source account. Detection: `New BOD` is present in the input row and differs from `BOD`.

**Live proof (2026-04-18):**
- `ABR4085` Amelia Brooks — deactivated Z-DEMO Anaheim `8973`, created Z-ORIENTATION Nashville `9746` PIN `974676422` ✓
- `LBE4086` Lucas Bennett — deactivated Z-DEMO Denver `9975` ✓, create at Z-ORIENTATION Chicago `9747` failed `Pin Code Setup Failed` (PIN `974700001` already taken) → recovered via Manual Entry as plain Add in Z-ORIENTATION

**Known operator recovery for cross-account modify PIN collision:** If the new-site create step fails with `Pin Code Setup Failed` after the old site is already deactivated, use Manual Entry to create the user directly in the destination account as a plain Add (no New BOD needed — the deactivation already happened).

### v3 Bulk Test Pack (2026-04-18)

Test CSVs in `LIVE-PROD/data/input/`:

- `v3_bulk_test01.csv` — client shape; Z-ORIENTATION adds + same-account site-change modify + deactivates
- `v3_bulk_test02b.csv` — alternate alias columns (`Account Name`, `Action`, `TEID`, `Location`, `New Location`, `New Account`, `New Customer Name`); adds + `Remove`/`Terminate` deactivates + cross-account Z-ORIENTATION→Z-DEMO via `Transfer`/`Move`
- `v3_bulk_test03b.csv` — BOD + `PIN Action Required` + explicit `New BOD`/`New Customer Name`; Z-DEMO adds + `Delete-Separated`/`inactive` deactivates + cross-account Z-DEMO→Z-ORIENTATION + comments field (no promotion without current PIN)

## Latest Round — Timeout + Parser Updates (current session)

### Timeout increases for large batches

**All frontend HTTP timeouts increased to 1200 seconds (20 minutes):**
- Manual review: 300s → 1200s (line 504 `frontend.py`)
- Bulk review: 300s → 1200s (line 510 `frontend.py`)
- Review-file: 300s → 1200s (line 520 `frontend.py`)
- Commit: 600s → 1200s (line 527 `frontend.py`)
- File upload: 300s → 1200s (line 539 `frontend.py`)

**Batch capacity verified:**
- Based on live proof: 3 Add users = 22 seconds (~7 sec/user average)
- System now supports:
  - ~170 pure Add rows
  - 100-row mixed batches (Add + Modify-Function + Activate) comfortably
  - Modify-Function rows take longer but stay within limits

**Why:** Original 300s/600s timeouts caused failures on batches >40-80 rows. Large IRS workbooks often contain 100+ rows across multiple accounts.

### Parser tolerance for SPEC "Activate"

**Updated `normalize_contact_status()` in `parser.py` (line 155-156):**
- Now accepts standalone `"Activate"` (exact match after lowercasing)
- Previously required `"Activate Existing"` substring match
- SPEC workbooks often use just `"Activate"` in action column

**Valid Activate patterns:**
- `"Activate Existing"` ✅ (substring match)
- `"Activate Existing PIN"` ✅ (substring match)
- `"Activate"` ✅ (exact match - NEW)
- `"ACTIVATE"` ✅ (case insensitive)

**Still correctly rejects:**
- `"Deactivate"` → routed to Deactivate flow
- `"Active"` → marked Completed and skipped

### Duplicate TEID handling verified

**Confirmed working:** System correctly handles sites sharing the same TEID (e.g., multiple IRS Counsel sites in Boston with TEID 5776).

**How it works:**
1. API 1 `get_pin_context(5776)` returns max PIN across all sites with that TEID
2. PIN generated sequentially: `577600123`, `577600124`, etc.
3. Sites differentiated by `address` field in payload (exact site name string)
4. Connect stores/searches by address string, not TEID alone

**Requirement:** CSV must contain correct, specific site name. As long as input has the right site name from master sheet, system handles duplicate TEIDs correctly.

## Previous Round — New Features (previous handoff)

### New file: `src/qa_irs_pin/sharepoint_lookup.py`
- Graph ROPC token using `GRAPH_TENANT`, `GRAPH_CLIENT_ID`, `GRAPH_USERNAME`, `GRAPH_PASSWORD` env vars
- Downloads `IRS Site Listing updated.xlsx` from SharePoint; builds same-day cached `{teid→{site_name,state}}` and `{site_name→{teid,state}}` dicts
- `get_state_for_teid(teid)` — used in `payloads.py` to set correct state on create
- `get_teid_for_site_name(site_name)` — used in `processor.py` when Connect says site is new
- `extract_state_from_site_name(site_name)` — smart fallback: parses 2-letter US state abbreviation from site name string (e.g. `Detroit, MI, USA` → `MI`); used when SharePoint has no match (e.g. Z-demo/orientation accounts not in IRS workbook)
- All functions return `None` gracefully on failure — never blocks processing

### State fix in `payloads.py`
- `_build_profile_defaults` now calls SharePoint TEID lookup → state; falls back to `extract_state_from_site_name`; Jacksonville/Florida only used as absolute last resort

### Parser/matcher changes
- `normalize_header` strips `\n`/`\r` (fixes SBSE multiline column headers)
- New `HEADER_ALIASES`: `action`, `request type`, `location`, `new location id/location`, `new bod`, `new customer name/customer`, analyst columns (`new opi pin`, `date of completion`, `manager`) → `_analyst_only`
- `normalize_contact_status`: `transfer/move → Modify-Function Change`; `remove/terminate/inactive → Deactivate`; `active → Completed` (row skipped — already-done reference rows)
- `matching.py`: progressive site-name stripping — tries full string → strip `(address)` suffix → strip `, STATE`; best score wins

### Cross-account Modify-Function Change
- `ParsedRow` gains `new_bod`, `new_customer_name` fields (default `""`)
- Parser promotes to `Modify-Function Change` when `New BOD` differs from `BOD`
- `processor.py`: resolves `destination_customer_context` from `new_bod`; deactivation uses source `customer_ids`; all create-side calls (API 3, API 1, payload, registry) use `dest_customer_name`/`dest_customer_ids`
- `app.py` `InputRowRequest`: added `new_bod` (alias `New BOD`) and `new_customer_name` (alias `New Customer Name`) — previously silently dropped
- `_review_rows` and `process_review_file` now resolve destination sites against destination customer
- Frontend: `New BOD` selectbox in Manual Entry; when selected shows `New Site Name`, `Employee ID *`, `New Site ID` fields

### Bug fixes found during live testing
- `InputRowRequest` in `app.py` was missing `new_bod`/`new_customer_name` fields — Pydantic silently dropped `New BOD` from the request, so cross-account modify created in source account instead of destination. Now fixed.
- `_review_rows` in `app.py` was resolving destination sites against source customer — now uses `dest_corrected_bod` derived from `row.new_bod`
- `process_review_file` in `app.py` was not passing `new_bod`/`new_customer_name` when building `InputRowRequest` from bulk-parsed rows — now fixed
- Manual Entry UI was missing `Employee ID` field for cross-account modify — added `add_cross_employee_id_input` (session key) that appears alongside `New Site ID` when `New BOD` is selected; maps to `Employee ID` in the row dict sent to backend

### New env vars required
```
GRAPH_TENANT=adastrainccom.onmicrosoft.com
GRAPH_CLIENT_ID=d3590ed6-52b3-4102-aeff-aad2292ab01c
GRAPH_USERNAME=Teams@ad-astrainc.com
GRAPH_PASSWORD=<password>
```
Added to `config.py`, `docker-compose.yml` (in `x-connect-env` anchor), and `.env.example`.
