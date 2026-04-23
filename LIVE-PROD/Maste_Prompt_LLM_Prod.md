# Master Prompt LLM - LIVE-PROD

Use this file when handing the current production-live app to another LLM.

```text
You are working in:
E:\ad-astra\031 IRS PIN Generator

Your task is to continue work only inside:
E:\ad-astra\031 IRS PIN Generator\LIVE-PROD

Truth order:
1. Current LIVE-PROD code
2. Explicit live production proof already observed
3. Inherited QA docs only for stable architecture/contracts
4. PRD / master docs only where they do not conflict with current code or live proof

Core rules:
- Treat LIVE-PROD code as primary truth.
- Do not guess stale production constants.
- Do not reintroduce QA hosts, QA aliases, QA credentials, or QA test-account assumptions.
- Do not redesign the system.
- Do not broadly refactor.
- Keep changes minimal and targeted.

Source-of-truth files:
- LIVE-PROD/src/qa_irs_pin/processor.py is the backend source of truth.
- LIVE-PROD/app.py must remain a thin wrapper.
- One processor is shared by CLI, FastAPI, and Streamlit.

Read these files first:
- LIVE-PROD/README_local_Prod.md
- LIVE-PROD/SUMMARY_Prod.md
- LIVE-PROD/Maste_Prompt_LLM_Prod.md

Then inspect these implementation files as needed:
- LIVE-PROD/src/qa_irs_pin/config.py
- LIVE-PROD/src/qa_irs_pin/payloads.py
- LIVE-PROD/src/qa_irs_pin/processor.py
- LIVE-PROD/src/qa_irs_pin/parser.py
- LIVE-PROD/src/qa_irs_pin/matching.py
- LIVE-PROD/src/qa_irs_pin/sharepoint_lookup.py
- LIVE-PROD/src/qa_irs_pin/registry.py
- LIVE-PROD/utils/client.py
- LIVE-PROD/utils/helpers.py
- LIVE-PROD/app.py
- LIVE-PROD/frontend.py
- LIVE-PROD/main.py
- LIVE-PROD/docker-compose.yml
- LIVE-PROD/.env.example

Architecture and contracts to preserve:
- parser, matching, payloads, and processor remain separate
- manual flow remains review -> commit
- Insert uses lower-camel form fields
- Update uses PascalCase-style form fields
- deterministic PIN logic remains
- the 4-digit TEID guard at 9999 remains
- deactivate remains detail-first

Current lookup / verification behavior to preserve:
- current code now uses:
  1. members/filter first for SEID lookup and already-exists checks
  2. GetAccountDetailByID for detail confirmation
- add / deactivate / modify runtime paths now avoid export sweeps in the normal flow
- post-create verification now prefers members/filter and still keeps GetAccountDetailByID

Production payload/config truth:
- runtime fK_Customer / fK_Location come from the API 1 pin-context path
- fk_PreCallPolicy is optional/nullable in production
- do not default fk_PreCallPolicy to 19
- keep the @ad-astrainc.com email domain
- current production config is env-driven
- do not hardcode Connect hosts or credentials
- no QA aliases are active production truth in config

Current proven IRS payload truth:
- current proven IRS create shape is:
  - `fK_ServiceType = IRSOPI`
  - `serviceTypes = IRSOPI`
  - `password = Welcome123!`
  - `setPassword = true`
  - `fK_DefaultNativeLanguage = EN`
- current code now applies that uniformly to all IRS accounts in `BOD_LOOKUP`

Current demo-account-only create override remains:
- `fK_ServiceType = CS`
- `serviceTypes = CS`
- `password = Welcome123!`
- `setPassword = true`

Safe live testing guidance:
- z- Ad Astra Demo Account may be used for live-safe create/deactivate smoke tests
- it is an operational test account only
- it is not IRS business truth
- do not use demo-account behavior to rewrite IRS-specific payload rules

Latest live proof already observed:
- auth to the live Connect endpoint succeeded
- demo-account smoke test succeeded for create and deactivate after demo-only payload override
- Stormi Holloway / `4XWXB` review proved:
  - customer `US GSA IRS Small Business Self-Employed (SBSE)`
  - `fK_Customer=1218`
  - `fK_Location=3175`
  - `TEID=4906`
  - next PIN `490699754`
- old default payload behavior failed for Stormi
- replay proved the working SBSE/IRS payload required IRSOPI + Welcome123! + setPassword=true + native language EN
- after the fix, Stormi live create succeeded with GUID `6fd70847-4aa6-4879-9623-617a5da4b364`
- Ami Pandya / `MDCNB` was confirmed already active in live
- Lavanya Thammisetti / `FV1XB` was created successfully in live with GUID `0bf0a9c6-e484-42e0-bbd8-45ac184ed36e`
- members-first lookup was verified to resolve existing live users quickly
- post-create verification for `FV1XB` found the created GUID through members/filter and did not need exports/filter

Current workbook/parser proof:
- the SBSE LB export workbook format under `LIVE-PROD/data/input/` is accepted for:
  - `Requested Action` -> `contact_status`
  - `PIN Action Required` -> `contact_status`
  - `Current User PIN` -> `user_pin`
  - `Site:Location ID` -> `site_id`
  - `Site` -> `site_name`
  - `Employee ID` -> `employee_id`
  - `New Site:Site ID` -> `new_site_id`
  - `New Site` -> `new_site_name`
- action normalization currently accepts:
  - `Delete-Separated` -> `Deactivate`
  - `New PIN` -> `Add`
- `Delete` -> `Deactivate`
- `Switch to Ad Astra` -> workbook-driven modify-function translation
- extra optional workbook columns can remain present and blank without breaking parsing
- duplicate mapped action columns can coexist and are coalesced safely
- blank filler rows that only repeat `TS FA` are skipped
- only explicit 4-digit numeric TEIDs are accepted as `Site ID` / `New Site:Site ID`
- alphanumeric site-code strings are treated as blank TEIDs and fall back to site-name resolution
- current code accepts `TS FA` as the live `FA` alias
- uploaded CSV rows can carry explicit `Customer Name`, and review-file now preserves it correctly
- `Modify-Function Change` is now implemented in live-prod
- `Employee ID`, `New Site:Site ID`, and `New Site` are now part of the live-prod action flow
- `New Site:Function` is not yet part of the live-prod action flow
- for IRS FA workbook rows marked `Switch to Ad Astra`, current code translates them into modify-function rows by:
  - treating workbook `Site Name` as `New Site`
  - deriving the old/current-site TEID from `Current User PIN`
  - deriving the 5-digit employee id from the same current PIN
  - keeping those rows in the Add Requester bulk workflow instead of filtering them out
- niche move-from-comments rule: if the normalized action is still `Add` but comments indicate a site-to-site move and `Current User PIN` is populated, promote to `Modify-Function Change` and process as a move (old TEID + employee id from PIN; destination from new-site fields)

BOD / customer resolution truth:
- resolver tolerates shorthand and common IRS-style labels beyond exact canonical keys (examples: LBI→LB&I, RICE→RICS, TS Media→MEDIA, TS RICS→RICS, TS SPEC→SPEC, W&I FA→FA, W&I AM→AM, W&I EPSS→EPSS, common Appeals variants)
- do not remove this tolerance when tightening validation unless product asks for strict-only matching

Frontend summary labeling (UI only):
- Add flow: deactivations that are part of a successful modify are shown as modify-step deactivations, not as if a separate deactivate row was processed
- Deactivate flow: unexpected creates are labeled explicitly; backend behavior unchanged

Bulk upload truth:
- bulk review now uses `/process/review-file` with the original uploaded file
- bulk upload button uses `/process` with the original uploaded file
- mixed bulk files now preserve original actions and fields through backend parsing
- the earlier fresh-SEID bulk timeout issue was removed by avoiding export-sweep lookup in the primary runtime path
- Add Requester bulk review now falls back to parsed-row review if the first raw-file review request returns a transient 400
- Deactivate Requester bulk CSV review/commit now converts uploaded rows into explicit `Deactivate` requests before sending them to the backend
- Add Requester bulk review/commit now keeps `Add`, `Modify-Function Change`, and `Activate` rows from mixed source files and skips true deactivate rows
- bulk processed-results rendering now uses the commit response shape correctly instead of dropping row-level output after successful bulk uploads
- processed results now show the returned 9-digit PIN for `Already Exists` rows when available
- `post_commit` frontend timeout is 600 seconds (raised from 300 to handle large live IRS batches)

Modify-Function Change timeout fix:
- the second `search_user_by_seid` call in the Modify-Function processor block now uses `allow_export_fallback=False`
- this prevents a full paginated export sweep of the entire SBSE/IRS account when `members/filter` returns empty
- do not revert this to `allow_export_fallback=True` — that caused 300-second timeouts on live SBSE batches

Frontend timeout increases for large batches:
- all HTTP timeouts in `frontend.py` increased to 1200 seconds (20 minutes):
  - manual review: 300s → 1200s
  - bulk review: 300s → 1200s
  - review-file: 300s → 1200s
  - commit: 600s → 1200s (was increased to 600s previously, now 1200s)
  - file upload: 300s → 1200s
- system now supports up to ~170 Add rows or 100-row mixed batches comfortably
- live proof showed 3 Add users = 22 seconds (~7 sec/user); 100-row mixed batch estimated at ~11 minutes
- do not reduce these timeouts — IRS workbooks regularly contain 100+ rows across multiple accounts

Current Activate flow truth:
- `"Activate"` is a new contact_status for reactivating an existing inactive requester in Connect
- triggered by action keyword `"activate existing"` (case-insensitive, substring match) OR standalone `"activate"` (exact match after lowercasing)
- parser accepts: `"Activate Existing"`, `"Activate Existing PIN"`, or just `"Activate"` (SPEC compatibility)
- `"create and activate new pin"` maps to `"Add"` (already matched by `"new pin"` keyword)
- only `seid` is required (`ACTIVATE_REQUIRED_FIELDS`); site_name is optional
- processor: finds user by SEID via members-first (no export fallback); uses full 9-digit PIN as tiebreaker, then TEID, then first match
- calls `build_update_payload(account_status_override="Active")` + `update_user`; records status `"Activated"` or `"Failed"`
- review path skips `get_sites_for_customer` (no site resolution needed for activate)
- SPEC workbook compatibility: `"sidn"` column → seid; `"pin"` column → user_pin; `"Site_Name"` → site_name (existing alias)
- TEID derived from PIN column value via `extract_teid_from_pin` (e.g. `"1504-32519"` → TEID `1504`, full PIN `150432519`; `"3217-xxxx"` → TEID `3217`)
- for Add rows with no first_name column, first_name is auto-filled from seid before validation
- `_build_trimmed_summary` exposes `"activated"` key; `render_bulk_result` shows Activated metric card when Activate rows are present
- `"create and activate new pin"` maps to `"Add"` (already matched by `"new pin"` keyword)
- only `seid` is required (`ACTIVATE_REQUIRED_FIELDS`); site_name is optional
- processor: finds user by SEID via members-first (no export fallback); uses full 9-digit PIN as tiebreaker, then TEID, then first match
- calls `build_update_payload(account_status_override="Active")` + `update_user`; records status `"Activated"` or `"Failed"`
- review path skips `get_sites_for_customer` (no site resolution needed for activate)
- SPEC workbook compatibility: `"sidn"` column → seid; `"pin"` column → user_pin; `"Site_Name"` → site_name (existing alias)
- TEID derived from PIN column value via `extract_teid_from_pin` (e.g. `"1504-32519"` → TEID `1504`, full PIN `150432519`; `"3217-xxxx"` → TEID `3217`)
- for Add rows with no first_name column, first_name is auto-filled from seid before validation
- `_build_trimmed_summary` exposes `"activated"` key; `render_bulk_result` shows Activated metric card when Activate rows are present

Current modify-function truth:
- modify-function is a composite flow: deactivate old/current site, then create at the new site
- modify-function deactivation is site-specific
- create first tries `new_teid + existing_employee_id`
- if Connect rejects that PIN as duplicate, create retries once with the normal target-TEID max-PIN rule
- modify-function create email first tries `seid.firstname.lastname1@ad-astrainc.com`
- if Connect rejects that email as already registered / duplicate email, create retries with suffix `2`, then suffix `3`
- do not change normal Add email behavior when touching modify-function code
- for workbook-driven `Switch to Ad Astra` rows, the operator-facing `Site Name` is the destination/new site, while the old/current site context is derived from `Current User PIN`
- when touching UI/result rendering, do not show the old/current TEID beside the destination/new site on failed modify-function rows

Latest live proof (2026-04-18 — v3 bulk test pack):
- v3_bulk_test01: Z-ORIENTATION adds (`AATH201`–`FOKF206`, `KDNE211`, `LBRN212`) all created; same-account modifies (`AATH101` Silver Spring→Nashville, `BRHW102` Nashville→Chicago) succeeded
- v3_bulk_test02b (after frontend fix): Z-ORIENTATION adds (`SMOR301`–`MRYE306`, `KDNE311`, `LBRN312`) created; `CVAZ103`/`DMRC104` deactivated; `ECLD105` Transfer Z-ORIENTATION Austin→Z-DEMO Jacksonville created correctly in Z-DEMO ✓; `FOKF106` Move Z-ORIENTATION Flower Mound→Z-DEMO Silver Spring created correctly in Z-DEMO ✓
- v3_bulk_test03b: Z-DEMO adds (`TADR401`–`GFLT406`, `SKIM401`, `FLAR402`) created; `EWA4082`/`HRE4087` deactivated; `ABR4085` cross-account Z-DEMO Anaheim→Z-ORIENTATION Nashville created PIN `974676422` ✓; `LBE4086` deactivated Z-DEMO Denver ✓ but create Z-ORIENTATION Chicago failed `Pin Code Setup Failed` → manually recovered
- UI BOD column now correctly shows destination account for cross-account modify rows after `build_commit_results_table` fix

Duplicate TEID handling:
- system correctly handles sites sharing the same TEID (e.g., multiple IRS Counsel sites in Boston with TEID 5776)
- PIN generation uses shared TEID max across all sites with that TEID
- sites are differentiated by `address` field (exact site name string) in the payload
- API 1 `get_pin_context(teid)` returns shared max PIN + `fK_Location` for that TEID
- Connect distinguishes sites by address string, not TEID alone
- as long as CSV contains correct, specific site name from master sheet, system handles duplicate TEIDs correctly
- example: TEID 5776 shared by "IRS Counsel SB1, Boston" and "IRS Counsel L&A1, Boston" — both get sequential PINs, differentiated by address field

Explicit TEID + short client site label (Add review and commit — handoff 2026-04-23):
- symptom fixed: Add rows with a valid 4-digit `Site ID` / TEID (often from client `9-digit User PIN` shaped like `5888-`) still showed `Manual Selection Required` because fuzzy `best_site_match` + `requires_explicit_site_confirmation` compared the CSV `Site Name` to Connect’s long canonical string (e.g. `International` vs `IDTVA`) even when TEID was already correct
- resolution order when TEID is explicit and `Manual Site Name` is blank: (1) broader site string extraction from `get_pin_context` via `utils.helpers.site_name_from_pin_context_data`, (2) `sharepoint_lookup.get_site_entry_by_teid` when Graph workbook lookup is configured, (3) bounded scan of Connect address list using CSV token hints and/or `top_site_matches` then `resolve_teid` until `existingTeid` matches the row TEID (default cap 48 checks per row — only when `candidate_addresses` is passed from `app.py` / `processor.py`)
- `ConnectQAClient.pin_context_with_site_name_for_teid(customer, teid, *, row_site_hint=..., candidate_addresses=..., max_resolve_checks=48)` implements the above; two-arg calls still work; extra `resolve_teid` traffic applies only when the optional address list is supplied
- `processor.py` (commit) and `app.py` `_review_rows` (review) both pass `row.site_name` and `get_sites_for_customer` results into that helper so bulk and single-row review stay aligned
- preserve existing behavior when manual site override is set, when TEID is blank (name-only resolution path), and when none of the above yields a site string (fall back to prior fuzzy + manual gate)

Latest additional live proof already observed:
- live auth to `appbe.ad-astrainc.com` succeeded with the current working credentials already used in this project
- live-safe bulk and mixed-action smoke testing was run against `z- Ad Astra Demo Account`
- the real bulk create path for the demo account used:
  - `fK_ServiceType = CS`
  - `serviceTypes = CS`
  - `password = Welcome123!`
  - `setPassword = true`
- a live SBSE bulk-style review payload check still used:
  - `fK_ServiceType = IRSOPI`
  - `serviceTypes = IRSOPI`
  - `password = Welcome123!`
  - `setPassword = true`
- the real bulk modify-function create path now uses the modify-function email rule rather than the normal Add email rule
- real demo-account bulk add-only proof created:
  - `AKH4071` -> PIN `345676782` -> GUID `167c7110-d5b8-46c0-88dc-3c5d16e67f4f`
  - `BAH4072` -> PIN `99733948` -> GUID `f2d826dc-07c1-424a-9705-a2bc97a17e11`
  - `SMA4073` -> PIN `89733440` -> GUID `9a7ea6ef-17c4-4d01-a030-d8486f67ddee`
- fresh mixed client-shaped bulk proof file `bulk_mixed_client_shape_fresh_2026-04-07.csv` completed with:
  - `Created = 7`
  - `Deactivated = 5`
  - `total = 9`
- modify-function email retry was re-proven in the real bulk path:
  - suffix `1` success on the first modify create
  - suffix `2` success on the second modify create
  - suffix `3` success on the third modify create
- blank-TEID new-site add now works in the real bulk path after backfilling missing `fK_Customer` / `fK_Location`
- manual-entry BOD dropdown now includes `Z-DEMO` and `Z-ORIENTATION` aliases for the two operational test accounts
- the frontend badge now shows `LIVE`
- local docker smoke-test succeeded with the current `LIVE-PROD/docker-compose.yml` on:
  - API `8002:8000`
  - frontend `8520:8501`
- QA-style VM deployment command pattern to preserve is:
  - `ssh -i "E:\ad-astra\jahangeer 1.pem" ubuntu@44.211.141.130`
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
  - `cd /home/ubuntu/IRSRequesterAutomation/LIVE-PROD && sudo docker compose up -d --build`
  - if reusing the same shared ports, stop QA first with:
    - `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose down`
- latest real VM deployment also hit one git hygiene issue before pull:
  - untracked `LIVE-PROD/.dockerignore` on the VM blocked merge
  - clear or move that VM-local file if the same conflict appears again
- recent handoff: move-from-comments parser promotion, BOD shorthand mapping, and Add/Deactivate summary labeling were manually verified in live-prod and treated as working at that time

Latest bug fix (current handoff — 2026-04-18):
- `frontend.py` `parsed_row_to_request_dict` was missing `new_bod` / `new_customer_name` — bulk cross-account modify was always creating in the source account because the backend never received `new_bod`; fixed by adding both fields to the returned dict
- `frontend.py` `build_commit_results_table` now shows destination account in BOD column for cross-account modify rows (was showing source account)
- live proof: `ABR4085` cross-account Z-DEMO→Z-ORIENTATION succeeded after fix; `LBE4086` deactivation succeeded but create failed `Pin Code Setup Failed` (PIN collision at destination TEID) → recovered manually as plain Add in Z-ORIENTATION
- known recovery pattern for cross-account modify PIN collision: if create step fails after old site is deactivated, use Manual Entry to create as plain Add directly in destination account (deactivation already done)
- v3 bulk test pack (`v3_bulk_test01`, `v3_bulk_test02b`, `v3_bulk_test03b`) exercised and confirmed working in `LIVE-PROD/data/input/`
- confirmed real site lists for Z-DEMO (14 sites) and Z-ORIENTATION (11 sites) now documented in SUMMARY_Prod.md

Latest feature additions (previous handoff):
- `src/qa_irs_pin/sharepoint_lookup.py` is a new module — Graph ROPC + SharePoint workbook lookup for TEID→state and site_name→TEID; `extract_state_from_site_name()` parses 2-letter US state from site name string as fallback
- `payloads.py` `_build_profile_defaults` now derives state from SharePoint/site-name — Jacksonville/Florida is last resort only
- `processor.py` checks SharePoint before auto-assigning a new TEID when Connect says site is new; adds operator warning note
- `parser.py`: `normalize_header` strips `\n`/`\r`; new aliases for SBSE/CI/FA/cross-account columns; `active` → skip (Completed); `transfer/move` → Modify-Function Change; `remove/terminate/inactive` → Deactivate
- `matching.py`: progressive site-name suffix stripping for SBSE-style names with parenthetical addresses
- `models.py` `ParsedRow` gains `new_bod`, `new_customer_name` fields
- `app.py` `InputRowRequest` gains `new_bod` (alias `New BOD`), `new_customer_name`; `_review_rows` and `process_review_file` resolve destination sites against destination customer for cross-account modify
- `processor.py` cross-account modify: deactivates in source account, creates in destination account using `dest_customer_name`/`dest_customer_ids`
- `frontend.py` Manual Entry: `New BOD` dropdown; `New Site Name`, `Employee ID`, `New Site ID` fields appear when New BOD is selected
- New env vars: `GRAPH_TENANT`, `GRAPH_CLIENT_ID`, `GRAPH_USERNAME`, `GRAPH_PASSWORD` in `config.py`, `docker-compose.yml`, `.env.example`
- Live-tested against Z-DEMO and Z-ORIENTATION: Add bulk/manual, cross-account modify bulk/manual, new-new site bulk/manual — all passed with correct state in Connect
- Bug fixed: `InputRowRequest` in `app.py` was missing `new_bod`/`new_customer_name` fields so Pydantic silently dropped `New BOD` — cross-account modify was creating in source account. Fixed in `InputRowRequest`, `_review_rows`, and `process_review_file`
- Bug fixed: Manual Entry UI missing `Employee ID` field for cross-account modify — added `add_cross_employee_id_input` that appears when New BOD is selected (last 5 digits of current PIN, maps to `Employee ID` in row dict)
- Known open items: modify-function email retry still capped at suffix 3; repeat cross-account moves for same SEID may need operator monitoring

When changing code:
- inspect current code first
- prefer config/client/payload fixes over business-logic rewrites
- preserve processor/app/contracts
- avoid broad refactors
- verify against live production proof when behavior is time-sensitive
- use fresh test identifiers for live testing
- report exact current outcomes if testing is performed
- if updating IRS payload rules, preserve the proven live shape above unless new live proof disproves it

Do not do these things:
- do not treat inherited QA wording as current production truth
- do not assume old hostnames, ports, paths, customer IDs, location IDs, service-type values, or policy IDs are still valid
- do not move business truth out of processor.py
- do not change payload field casing contracts
- do not document secrets
- do not reintroduce export-sweep lookup into the primary add / deactivate / modify runtime path unless new live proof requires it
```

## Short Version

`Read LIVE-PROD/README_local_Prod.md and LIVE-PROD/SUMMARY_Prod.md first. Treat LIVE-PROD/src/qa_irs_pin/processor.py as the backend source of truth, keep LIVE-PROD/app.py thin, preserve review -> commit flow, preserve Insert/Update casing contracts, preserve the proven IRS payload shape (IRSOPI + Welcome123! + setPassword=true + EN) for all IRS accounts unless newer live proof disproves it, keep members/filter as the primary SEID lookup path, preserve modify-function flow and bulk parsing including Add rows promoted to modify when comments indicate a move and Current User PIN is present, preserve tolerant BOD/customer shorthand resolution, and preserve Add/Deactivate summary UI semantics (modify-step vs standalone deactivate; explicit unexpected-create wording) without broad refactors or stale QA assumptions. For Add with explicit Site ID/TEID, resolve canonical Connect site via pin-context JSON (helpers), optional SharePoint get_site_entry_by_teid, then bounded resolve_teid over customer addresses before falling back to fuzzy manual selection (2026-04-23 handoff).`
