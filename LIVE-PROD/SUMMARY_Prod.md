# Production Summary

`LIVE-PROD/` is the active production-live IRS PIN codebase. Treat the current code in this folder as primary truth over inherited QA docs.

## Current Shape

Active runtime files:

- `app.py`
- `frontend.py`
- `utils/client.py`
- `src/qa_irs_pin/config.py`
- `src/qa_irs_pin/parser.py`
- `src/qa_irs_pin/matching.py`
- `src/qa_irs_pin/payloads.py`
- `src/qa_irs_pin/processor.py`
- `src/qa_irs_pin/registry.py`
- `docker-compose.yml`
- `.env.example`

Architecture rules:

- `src/qa_irs_pin/processor.py` is the backend source of truth
- `app.py` stays a thin wrapper
- parser, matching, payloads, and processor stay split
- one processor is shared by FastAPI, Streamlit, and CLI
- local SQLite is audit/support state only

## Operating Flow

Manual runtime flow remains:

1. review
2. commit

Current API surface:

- `POST /process/review`
- `POST /process/review-file`
- `POST /process/commit`
- `POST /process`
- `POST /process/rows`
- `GET /health`

Important current behavior:

- manual single-row flow uses review, then commit
- bulk review now uses `/process/review-file` with the original uploaded file
- bulk upload button uses `/process` with the original uploaded file
- mixed bulk files now preserve original actions and fields through backend parsing
- Add Requester bulk review now falls back to parsed-row review if the first raw-file review request returns a transient 400
- Deactivate Requester bulk CSV flow now rewrites uploaded rows into explicit `Deactivate` requests for both review and commit

## Contracts To Preserve

Payload contracts:

- `Insert` uses lower-camel field names
- `Update` uses PascalCase-style field names

Behavior rules:

- deterministic PIN logic remains
- new-site TEIDs remain 4 digits
- fail safely if the next new-site TEID would exceed `9999`
- deactivate remains detail-first

## Current Verification / Lookup Behavior

Current live code now uses:

1. `members/filter` first for SEID lookup / dedup / already-exists checks
2. `GetAccountDetailByID` for detail confirmation when GUID detail is needed

Important nuance:

- this change is now implemented in code
- for existing users, the new members-first path is fast and works
- normal add / deactivate / modify-function flows now avoid `exports/filter` sweeps in the primary runtime path
- post-create verification now uses `members/filter` plus `GetAccountDetailByID`
- this removed the long fresh-SEID bulk timeout behavior that came from export sweeps on live data

## Current Payload Truth

Current production payload guidance from code plus live proof:

- create payloads keep `@ad-astrainc.com`
- runtime `fK_Customer` and `fK_Location` come from the live API 1 pin-context path
- `fk_PreCallPolicy` is optional/nullable in production
- do not default `fk_PreCallPolicy` to `19`
- demo-account-only proof does not rewrite IRS payload rules

Current proven IRS create payload pattern:

- `fK_ServiceType = IRSOPI`
- `serviceTypes = IRSOPI`
- `password = Welcome123!`
- `setPassword = true`
- `fK_DefaultNativeLanguage = EN`

Current code state:

- the proven IRS override is now applied uniformly to every IRS account in `BOD_LOOKUP`
- the user confirmed that `IRSOPI` is the standard service-type code across IRS accounts
- demo-account-only create behavior remains a separate override

Current demo-account-only create override remains:

- `fK_ServiceType = CS`
- `serviceTypes = CS`
- `password = Welcome123!`
- `setPassword = true`

## Live Proof Observed

Demo-account smoke-test proof:

- live auth succeeded
- API 3, API 2, and API 1 review-side resolution succeeded for `z- Ad Astra Demo Account`
- API 1 returned runtime `fK_Customer=271`, `fK_Location=7`
- `fk_PreCallPolicy` stayed nullable in the reviewed create payload
- initial live create failure was isolated to demo-account service-type/password mapping
- after the demo-account-only override was applied, live create succeeded with GUID `7bee88a8-4a99-4fe0-a1ac-9045fe3cd22d`
- follow-on live demo deactivate succeeded

IRS SBSE live proof:

- Stormi Holloway / `4XWXB` review passed with:
  - customer `US GSA IRS Small Business Self-Employed (SBSE)`
  - `fK_Customer=1218`
  - `fK_Location=3175`
  - `TEID=4906`
  - next PIN `490699754`
- initial Stormi create failed when payload used old default service-type behavior
- replay proved the working SBSE/IRS create shape required:
  - `IRSOPI`
  - `Welcome123!`
  - `setPassword=true`
  - native language `EN`
- after the fix, Stormi live create succeeded with GUID `6fd70847-4aa6-4879-9623-617a5da4b364`
- Lavanya Thammisetti / `FV1XB` was then created successfully in live with GUID `0bf0a9c6-e484-42e0-bbd8-45ac184ed36e`
- Ami Pandya / `MDCNB` was confirmed already active in live

Members-first verification proof:

- `4XWXB` resolves quickly as `Already Exists`
- `FV1XB` resolves quickly as active
- post-create verification for `FV1XB` found the created GUID through `members/filter`

Recent live-safe demo-account bulk proof:

- `/process/review-file` now correctly preserves `Customer Name` from uploaded CSV rows
- mixed client-shaped CSV with headings:
  - `Customer Name`
  - `First Name`
  - `Last Name`
  - `SEID`
  - `Requested Action`
  - `Site:Location ID`
  - `Employee ID`
  - `Site`
  - `New Site:Site ID`
  - `New Site`
  was reviewed successfully through the real bulk review endpoint
- bulk add-only demo-account proof created 3 users in about 22 seconds:
  - `AKH4071` -> PIN `345676782` -> GUID `167c7110-d5b8-46c0-88dc-3c5d16e67f4f`
  - `BAH4072` -> PIN `99733948` -> GUID `f2d826dc-07c1-424a-9705-a2bc97a17e11`
  - `SMA4073` -> PIN `89733440` -> GUID `9a7ea6ef-17c4-4d01-a030-d8486f67ddee`
- mixed bulk proof then confirmed:
  - add
  - deactivate
  - modify-function change
  - blank-TEID true new-site add
  all work through the real `/process` CSV endpoint
- fresh mixed proof file `bulk_mixed_client_shape_fresh_2026-04-07.csv` completed with:
  - `Created = 7`
  - `Deactivated = 5`
  - `total = 9`
- modify-function email retry was proven again in the real bulk path:
  - first modify create succeeded with suffix `1`
  - second modify create retried and succeeded with suffix `2`
  - third modify create retried and succeeded with suffix `3`
- blank-TEID new-site add was fixed by backfilling missing `fK_Customer` / `fK_Location` from the customer's current max existing TEID context

Latest local UI proof:

- manual-entry test-account aliases `Z-DEMO` and `Z-ORIENTATION` are now available in the BOD dropdown
- the manual-entry selectbox warning from double-setting session/default state was removed
- deactivate bulk CSV processing no longer reuses add/create semantics from the uploaded file during deactivation
- local docker smoke-test succeeded with:
  - `live-prod-api-1` healthy on `0.0.0.0:8002->8000/tcp`
  - `live-prod-frontend-1` running on `0.0.0.0:8520->8501/tcp`
- the frontend badge now reads `LIVE`

## Workbook Input Compatibility

Current `LIVE-PROD` parser safely accepts the SBSE LB export workbook shape under `LIVE-PROD/data/input/`.

Confirmed normalized workbook headers:

- `Requested Action` -> `contact_status`
- `Site:Location ID` -> `site_id`
- `Site` -> `site_name`
- `Employee ID` -> `employee_id`
- `New Site:Site ID` -> `new_site_id`
- `New Site` -> `new_site_name`

Confirmed action normalization:

- `Delete-Separated` -> `Deactivate`
- `New PIN` -> `Add`

Confirmed non-breaking behavior:

- extra optional workbook columns can remain present and blank
- uploaded CSV review now preserves explicit `Customer Name` values when present

Current workbook limitation:

- workbook still does not include explicit `BOD` / `Customer Name`
- IRS customer context must still be supplied separately

Current supported workbook action:

- `Modify-Function Change` is now implemented in live-prod
- the processing flow now uses `Employee ID`, `New Site:Site ID`, and `New Site`
- `New Site:Function` is not yet part of the live-prod action flow

## Config And Deployment

Current production config philosophy:

- env-driven connection settings
- no hardcoded QA hosts in active deployment wiring
- no hardcoded QA credentials
- no QA aliases in active prod config

Deployment/config truth lives in:

- `src/qa_irs_pin/config.py`
- `docker-compose.yml`
- `.env.example`

Required env values at a high level:

- Connect auth/API/search base URLs
- Connect email and password
- optional `DEFAULT_PRECALL_POLICY`
- optional Dev Use credentials
- request timeout / match threshold

Current container/runtime mapping:

- API host port `8002` -> container `8000`
- frontend host port `8520` -> container `8501`
- this mirrors the proven QA shared-VM deployment pattern and is now locally smoke-tested for `LIVE-PROD`

## Modify-Function Change

Current modify-function behavior:

- modify-function is a composite flow: deactivate old/current site, then create at the new site
- deactivation is site-specific; it does not deactivate the latest active requester anywhere
- create first tries to preserve the existing 5-digit employee id under the new TEID
- if Connect rejects that candidate PIN as duplicate, create retries once with the normal target-TEID max-PIN rule
- create email first tries `seid.firstname.lastname1@ad-astrainc.com`
- if Connect rejects that email as already registered / duplicate email, create retries with suffix `2`, then suffix `3`
- normal Add email generation is unchanged

## Practical Risks / Open Items

Current real open items:

- live deployment still requires real env values outside the repo
- DNS / network reachability to `appbe.ad-astrainc.com` is sometimes unstable from this workstation/session
- repeated live modify-function changes for the same requester may still need careful operator monitoring because Connect enforces email uniqueness and the current safe retry cap stops at suffix `3`
- fresh CSVs are still required for repeat UI testing because the demo-account proof users now exist or have been deactivated during live-safe verification

Current note on bulk paths:

- Add Requester bulk commit still uses `/process` with the original uploaded file by design
- Deactivate Requester bulk commit now uses explicit parsed deactivate rows through `/process/commit` to avoid accidental add/create behavior from uploaded source actions

## What Next

Highest-value next steps:

1. Keep using fresh SEIDs and fresh site strings for live-safe demo-account verification packs
2. Decide whether modify-function email retry should remain capped at suffix `3` or expand by policy
3. If needed, add one more dedicated proof pack for forced modify email suffix `2` and `3` retries
4. Update any deployment docs if the current local default Connect host fallback strategy changes later
