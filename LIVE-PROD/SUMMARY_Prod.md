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
- Add Requester bulk review/commit now keeps both `Add` and `Modify-Function Change` rows from mixed source files and skips true deactivation rows
- bulk processed-results rendering now uses the commit response shape correctly and no longer drops row-level output after successful bulk uploads
- processed results now show the returned 9-digit PIN for `Already Exists` rows when available
- Add-page summaries distinguish modify-step deactivations (old site turned off as part of a successful modify) from standalone deactivate rows; Deactivate-page summaries label unexpected creates more explicitly (UI copy only; backend behavior unchanged)

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

**Recent round (handoff):** Parser promotion for Add rows with move-in-comments plus populated `Current User PIN`, expanded BOD/customer shorthand resolution, and Add/Deactivate summary labeling clarifications were manually exercised in live-prod and were considered working as expected at handoff.

**Explicit TEID + client site label (handoff — 2026-04-23):** Add rows with a known 4-digit TEID (`Site ID` or derived from `user_pin` / “9-digit User PIN”) no longer depend solely on fuzzy CSV-vs-Connect name matching, which could mark correct TEIDs as `Manual Selection Required` when labels differed (e.g. short “International” client text vs Connect “IDTVA” canonical). Review (`app.py` `_review_rows`) and commit (`processor.py`) now resolve the canonical Connect address by, in order: richer pin-context JSON parsing (`utils.helpers.site_name_from_pin_context_data`), SharePoint workbook `get_site_entry_by_teid` when Graph env is set, then a bounded `resolve_teid` scan over Connect’s address list (hinted by CSV site tokens and capped). `utils.client.ConnectQAClient.pin_context_with_site_name_for_teid` centralizes this; optional kwargs default safely for two-argument callers.

**Latest round (current handoff):** Three major features added and fully live-tested against Z-DEMO and Z-ORIENTATION accounts:

1. **State from SharePoint + smart site-name parsing** — new `src/qa_irs_pin/sharepoint_lookup.py` module fetches the IRS Master Site Sheet via Graph ROPC; provides `get_state_for_teid()` and `get_teid_for_site_name()`; `_build_profile_defaults` in `payloads.py` now uses the SharePoint-derived state; when SharePoint has no match, `extract_state_from_site_name()` parses the 2-letter state abbreviation directly from the site name string (e.g. `Detroit, MI, USA` → `MI`). Jacksonville/Florida is now only a last-resort fallback. Graph env vars (`GRAPH_TENANT`, `GRAPH_CLIENT_ID`, `GRAPH_USERNAME`, `GRAPH_PASSWORD`) added to `config.py`, `docker-compose.yml`, and `.env.example`. SharePoint verification in `processor.py`: when Connect says a site is new, the workbook is checked first; if found, its TEID is used and an operator warning note is added.

2. **Parser and matcher expansion** — `normalize_header` now strips `\n`/`\r` (fixes SBSE multiline headers); new `HEADER_ALIASES` cover `action`, `request type`, `location`, `new location`, `new bod`, `new customer name`, analyst-use columns (`new opi pin`, `date of completion`, `manager` → `_analyst_only` no-op); `normalize_contact_status` now maps `transfer/move → Modify-Function Change`, `remove/terminate/inactive → Deactivate`, `active → Completed` (row silently skipped — these are already-done reference rows). `matching.py` has progressive site-name suffix stripping: tries full string, then strips `(address)` suffix, then strips `, STATE` — best score across all variants returned.

3. **Cross-account Modify-Function Change** — `ParsedRow` gains `new_bod` and `new_customer_name` fields. When `New BOD` column differs from `BOD`, the action is promoted to `Modify-Function Change` and the processor deactivates in the source account and creates in the destination account. `InputRowRequest` in `app.py` now includes `new_bod`/`new_customer_name` fields (was silently dropping them before). Both `_review_rows` and `process_review_file` now resolve destination sites against the destination customer. Frontend `Manual Entry` shows `New BOD` dropdown; when selected, `New Site Name`, `Employee ID`, and `New Site ID` fields appear.

Bug fixed during testing: `InputRowRequest` in `app.py` was silently dropping `New BOD` (Pydantic field missing), so cross-account modify was creating in the source account instead of the destination. Fixed by adding `new_bod`/`new_customer_name` to `InputRowRequest`, `_review_rows`, and `process_review_file`. Also fixed: Manual Entry UI was missing the `Employee ID` field for cross-account modify — added `add_cross_employee_id_input` field that appears when New BOD is selected (required: last 5 digits of current PIN).

Live proof (Z-DEMO / Z-ORIENTATION):
- `AATH001` created in Z-DEMO at Silver Spring MD — state `MD` in Connect ✓
- `BRHW002` created in Z-DEMO at Nashville TN (new site) — state `TN` ✓
- `CVAZ003` cross-account moved Orientation→Demo (Charlotte NC → Detroit MI) — Deactivated + Created ✓
- `DMRC004` cross-account moved Demo→Orientation (Arlington VA → Nashville TN) — Deactivated + Created ✓
- `ECLD005` created at brand-new site Raleigh NC — state `NC` extracted from site name ✓
- `FOKF006` created at brand-new site Portland OR — state `OR` extracted from site name ✓

## Workbook Input Compatibility

Current `LIVE-PROD` parser safely accepts the SBSE LB export workbook shape under `LIVE-PROD/data/input/`.

Confirmed normalized workbook headers:

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

Confirmed non-breaking behavior:

- extra optional workbook columns can remain present and blank
- uploaded CSV review now preserves explicit `Customer Name` values when present
- duplicate mapped action columns are coalesced safely
- blank filler rows that only repeat `TS FA` are skipped instead of becoming fake error rows
- only explicit 4-digit numeric TEIDs are accepted as `Site ID` / `New Site:Site ID`
- alphanumeric site-code strings are treated as blank TEIDs and fall back to site-name resolution
- `TS FA` is accepted as the live `FA` alias in current code

Current workbook limitation:

- workbook still does not include explicit `BOD` / `Customer Name`
- IRS customer context must still be supplied separately

Current supported workbook action:

- `Modify-Function Change` is now implemented in live-prod
- the processing flow now uses `Employee ID`, `New Site:Site ID`, and `New Site`
- `New Site:Function` is not yet part of the live-prod action flow
- for IRS FA workbook rows marked `Switch to Ad Astra`, current code translates them into modify-function rows by:
  - treating workbook `Site Name` as `New Site`
  - deriving the old/current-site TEID from `Current User PIN`
  - deriving the 5-digit employee id from the same current PIN
  - keeping those rows in the Add Requester bulk workflow
- niche move-from-comments rule: if `Requested Action` / `contact_status` still normalizes to `Add` but free-text comments indicate the requester is **moving** from one site to another **and** `Current User PIN` is populated, the row is promoted to `Modify-Function Change` and processed as a site move (not a plain add). Example: comment like “EE moving from Santa Rosa to Oakland” with current PIN `6701-87809` yields old TEID `6701`, employee id `87809`, and destination resolved from the new/current site columns (`New Site:Site ID` / `New Site` as applicable)

## BOD / customer name resolution

Customer / BOD selection (manual entry and resolver paths) accepts more than strict exact canonical keys. Shorthand and common IRS-style labels map to the same accounts where unambiguous, which cuts failures from abbreviated or inconsistent client input. Representative mappings include: `LBI` → LB&I, `RICE` → RICS, `TS Media` → MEDIA, `TS RICS` → RICS, `TS SPEC` → SPEC, `W&I FA` → FA, `W&I AM` → AM, `W&I EPSS` → EPSS, plus common Appeals naming variants. Prefer canonical labels in new templates; the resolver is for tolerance of real-world spreadsheets.

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

QA-style live deployment commands to preserve:

- SSH to VM:
  - `ssh -i "E:\ad-astra\jahangeer 1.pem" ubuntu@44.211.141.130`
- stop QA first if reusing the same shared ports:
  cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose down
- pull latest repo on VM:
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
- deploy live from VM:
  - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`
- verify:
  - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose ps`
  - `curl http://127.0.0.1:8000/health`

Expected shared-VM URLs:

- frontend: `http://44.211.141.130:8520`
- API: `http://44.211.141.130:8002`

Latest shared-VM deployment proof:

- QA containers were intentionally shut down first so `LIVE-PROD` could reuse the same shared ports
- `git pull origin develop` on the VM initially failed because an untracked `LIVE-PROD/.dockerignore` would have been overwritten
- after clearing that VM-local conflict, the repo updated successfully
- `LIVE-PROD` was then started on the VM with:
  - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`
- operator confirmed the live deployment is working

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

## Bug Fixed — Bulk Cross-Account Modify (frontend.py)

**Root cause:** `parsed_row_to_request_dict` in `frontend.py` was not including `new_bod` / `new_customer_name` in the row dicts sent to `/process/commit` for bulk uploads. This caused the backend to receive `new_bod = ""` for every bulk row, so `destination_customer_context` was always `None` and cross-account modify rows were created in the source account instead of the destination.

**Fix:** `parsed_row_to_request_dict` now includes `"New BOD": row.new_bod` and `"New Customer Name": row.new_customer_name`.

**Secondary fix:** `build_commit_results_table` now shows the destination account in the BOD column for cross-account modify rows (previously showed source account).

**Live proof:** `v3_bulk_test03b.csv` run after fix confirmed:
- `ABR4085` Amelia Brooks — deactivated from Z-DEMO Anaheim `8973`, created in Z-ORIENTATION Nashville `9746`, PIN `974676422` ✓
- `LBE4086` Lucas Bennett — deactivated from Z-DEMO Denver `9975` ✓, new-site create at Z-ORIENTATION Chicago `9747` failed with `Pin Code Setup Failed` (PIN `974700001` already taken) → manually recovered via Manual Entry as a plain Add in Z-ORIENTATION

## v3 Bulk Test Pack Summary (2026-04-18)

Three test CSVs created and exercised in `LIVE-PROD/data/input/`:

- `v3_bulk_test01.csv` — client shape columns; Z-ORIENTATION adds + same-account modify + deactivates
- `v3_bulk_test02b.csv` — alternate alias columns (`Account Name`, `Action`, `TEID`, `Location`, `New Location`, `New Account`, `New Customer Name`); Z-ORIENTATION adds + deactivates via `Remove`/`Terminate` keywords + cross-account modify Z-ORIENTATION→Z-DEMO via `Transfer`/`Move` keywords
- `v3_bulk_test03b.csv` — BOD column + `PIN Action Required` + `New BOD`/`New Customer Name` explicit columns; Z-DEMO adds + deactivates via `Delete-Separated`/`inactive` keywords + cross-account modify Z-DEMO→Z-ORIENTATION + comments-promote verification

**Confirmed real site lists used:**

Z-DEMO (14 sites): `8701 Georgia Avenue Silver Spring MD`, `400 Bay Point Way North Jacksonville FL`, `1 North Wacker Drive Chicago IL`, `House of Blues Anaheim CA`, `700 Market Street St. Louis MO`, `1550 Crystal Drive Arlington VA`, `500 Woodward Avenue Detroit MI`, `250 Peachtree Street Atlanta GA`, `900 Innovation Drive Denver CO`, `1201 Elm Street Dallas TX`, `1600 Broadway Denver CO`, `123 Fake Street Oak Lawn IL`, `801 Broad Street Nashville TN`, `225 Ponce de Leon Atlanta GA`

Z-ORIENTATION (11 sites): `400 Bay Point Way North Jacksonville FL`, `8701 Georgia Avenue Silver Spring MD`, `801 Broad Street Nashville TN`, `999 Pine Street Raleigh NC`, `2001 Lakeside Parkway Flower Mound TX`, `77 West Wacker Drive Chicago IL`, `100 North Tryon Street Charlotte NC`, `600 Congress Avenue Austin TX`, `42 Harbor View Road Portland OR`, `K4 IRS ACS Kansas City MO`, `201 Monroe Street Montgomery AL`

## Practical Risks / Open Items

Current real open items:

- live deployment still requires real env values outside the repo
- DNS / network reachability to `appbe.ad-astrainc.com` is sometimes unstable from this workstation/session
- repeated live modify-function changes for the same requester may still need careful operator monitoring because Connect enforces email uniqueness and the current safe retry cap stops at suffix `3`
- fresh CSVs are still required for repeat UI testing because the demo-account proof users now exist or have been deactivated during live-safe verification
- cross-account modify PIN collision (`Pin Code Setup Failed`) at destination TEID can occur when employee ID from source PIN is already taken at destination — operator must manually retry as plain Add in the destination account in that case

Current note on bulk paths:

- Add Requester bulk commit now passes `new_bod` / `new_customer_name` through the full bulk path after the `parsed_row_to_request_dict` fix
- Deactivate Requester bulk commit uses explicit parsed deactivate rows through `/process/commit` to avoid accidental add/create behavior

## Latest Round — Timeout Fix + SPEC Activate Flow (current handoff)

### Modify-Function Change timeout fix

**Root cause:** For large IRS accounts (SBSE), the second `search_user_by_seid` call in the Modify-Function Change processor block used `allow_export_fallback=True`. If the `members/filter` API returned empty for any reason, the fallback iterated every user in the entire SBSE account page by page — easily exceeding the 300-second frontend timeout.

**Fix 1 — `processor.py`:** Changed the second SEID search in the Modify-Function block from `allow_export_fallback=True` → `allow_export_fallback=False`. Members-first is sufficient for existing users; the export sweep fallback is now blocked in this path to prevent silent hangs.

**Fix 2 — `frontend.py`:** All HTTP timeouts raised to 1200 seconds (20 minutes) to support large batches:
- Manual review: 300s → 1200s
- Bulk review: 300s → 1200s
- Review-file: 300s → 1200s
- Commit: 600s → 1200s
- File upload: 300s → 1200s

**Capacity:** System now supports up to ~170 Add rows or 100-row mixed batches (Add + Modify-Function + Activate) comfortably within timeout limits.

### SPEC Activate flow

**New `"Activate"` contact status** — handles SPEC workbook rows with action `ACTIVATE EXISTING PIN` (reactivate an existing inactive requester) and `CREATE AND ACTIVATE NEW PIN` (standard Add, already covered by `"new pin"` keyword).

**Parser changes (`parser.py`):**
- `"sidn" → "seid"` header alias (SPEC workbook identifier column)
- `"pin" → "user_pin"` header alias (SPEC workbook PIN column)
- `"activate existing" → "Activate"` (substring match) OR standalone `"activate" → "Activate"` (exact match) in `normalize_contact_status` — accepts both `"Activate Existing"` and just `"Activate"` for SPEC compatibility
- `ACTIVATE_REQUIRED_FIELDS = ("seid",)` — only SEID required
- For `Activate` and `Add` rows: TEID derived from PIN column value via `extract_teid_from_pin` (e.g. `"3217-xxxx"` → TEID `3217`; `"1504-32519"` → TEID `1504`)
- For `Add` rows with no `first_name`: auto-filled from `seid` (SPEC workbooks have no First/Last Name columns)

**Processor changes (`processor.py`):**
- New `Activate` block between Deactivate and Modify-Function Change
- Searches by SEID; uses full 9-digit PIN as tiebreaker, then TEID, then first result
- Calls `build_update_payload(account_status_override="Active")` + `update_user`
- Records status `"Activated"` or `"Failed"`

**App changes (`app.py`):**
- `_build_trimmed_summary` now includes `"activated"` key
- `_review_rows` short-circuits `Activate` rows before `get_sites_for_customer` (no site resolution needed)

**Frontend changes (`frontend.py`):**
- `filter_rows_for_action` now includes `"Activate"` in the Add-page allowed set (was silently dropped before)
- `render_bulk_result` shows an "Activated" metric card when Activate rows are present in the batch

**SPEC workbook compatibility confirmed:**
- Column `SIDN` → `seid`; column `Site_Name` (or `site name`) → `site_name` (already worked via existing alias)
- Action `ACTIVATE EXISTING PIN` or `ACTIVATE EXISTING` or standalone `ACTIVATE` → `Activate`; action `CREATE AND ACTIVATE NEW PIN` → `Add`
- PIN column value `"1504-32519"` → user_pin `150432519`; TEID `1504` derived automatically
- No First/Last Name columns — first_name auto-filled from SEID for Add rows

## Duplicate TEID Handling

**Current behavior:** System correctly handles sites that share the same TEID (e.g., multiple Boston Counsel sites with TEID 5776).

**How it works:**
- PIN generation uses shared TEID max across all sites with that TEID
- Sites are differentiated by `address` field (exact site name string)
- API 1 `get_pin_context(teid)` returns shared max PIN + `fK_Location` for that TEID
- Payload includes specific site name in `address` field

**Example:**
- TEID 5776: `"IRS Counsel SB1, Boston"` and `"IRS Counsel L&A1, Boston"` share same TEID
- Both get sequential PINs: `577600123`, `577600124`
- Connect distinguishes by `address` field, not TEID alone

**Requirement:** CSV must contain correct, specific site name. System relies on site name string for differentiation when TEIDs are shared.

## What Next

Highest-value next steps:

1. **Push and deploy to VM** — `git push origin develop` → SSH to VM → `git pull origin develop` → `docker compose up -d --build`
2. Live-test SPEC Activate flow against a real SPEC workbook sample with standalone `"Activate"` action
3. Test large batch capacity: 100-row mixed CSV (Add + Modify-Function + Activate) to verify 1200s timeout is sufficient
4. Decide whether modify-function email retry should remain capped at suffix `3` or expand by policy
5. Consider adding a retry/fallback path when cross-account modify create fails with `Pin Code Setup Failed` — currently requires manual Add recovery
