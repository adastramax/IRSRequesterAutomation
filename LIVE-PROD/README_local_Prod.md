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

1. keep generating fresh proof-pack CSVs for UI testing because earlier demo-account proof users now already exist or have been deactivated
2. decide whether modify-function email retry should remain capped at suffix `3` or expand by policy
3. create a dedicated proof pack if the team wants repeated forced evidence of suffix `2` and suffix `3`
4. keep the current members-first runtime contract documented if no business rule changes it later

## Latest verification note

As of the most recent handoff, the move-from-comments promotion rule, expanded BOD/customer shorthand handling, and Add/Deactivate summary labeling updates were manually tested or reviewed in live-prod and were considered correct at that time. Re-verify after any parser, config resolver, or frontend summary changes.
