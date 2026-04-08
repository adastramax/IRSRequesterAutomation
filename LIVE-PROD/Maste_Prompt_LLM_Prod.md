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

Bulk upload truth:
- bulk review now uses `/process/review-file` with the original uploaded file
- bulk upload button uses `/process` with the original uploaded file
- mixed bulk files now preserve original actions and fields through backend parsing
- the earlier fresh-SEID bulk timeout issue was removed by avoiding export-sweep lookup in the primary runtime path
- Add Requester bulk review now falls back to parsed-row review if the first raw-file review request returns a transient 400
- Deactivate Requester bulk CSV review/commit now converts uploaded rows into explicit `Deactivate` requests before sending them to the backend
- Add Requester bulk review/commit now keeps both `Add` and `Modify-Function Change` rows from mixed source files and skips true deactivate rows
- bulk processed-results rendering now uses the commit response shape correctly instead of dropping row-level output after successful bulk uploads
- processed results now show the returned 9-digit PIN for `Already Exists` rows when available

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

`Read LIVE-PROD/README_local_Prod.md and LIVE-PROD/SUMMARY_Prod.md first. Treat LIVE-PROD/src/qa_irs_pin/processor.py as the backend source of truth, keep LIVE-PROD/app.py thin, preserve review -> commit flow, preserve Insert/Update casing contracts, preserve the proven IRS payload shape (IRSOPI + Welcome123! + setPassword=true + EN) for all IRS accounts unless newer live proof disproves it, keep members/filter as the primary SEID lookup path, and preserve the current modify-function flow and bulk raw-file parsing behavior without broad refactors or stale QA assumptions.`
