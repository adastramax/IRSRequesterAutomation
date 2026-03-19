# Master Prompt For Another LLM

Use this prompt when asking another LLM to convert the mock IRS PIN tool into QA or production code.

```text
You are working in:
E:\ad-astra\031 IRS PIN Generator

Your task is to evolve the existing mock IRS PIN tool into real QA-ready or production-ready code without breaking the validated business logic.

You must not redesign the system from scratch. Start from the existing mock implementation and replace the mocked layers carefully.

Ground truth documents:
- prd/IRS_PIN_Tool_PRD_v7.docx
- prd/IRS_PIN_Tool_Master_V7.md
- mock/MOCK_Project_Summary.md

Code you must inspect first:
- mock/src/mock_irs_pin/config.py
- mock/src/mock_irs_pin/database.py
- mock/src/mock_irs_pin/parser.py
- mock/src/mock_irs_pin/matching.py
- mock/src/mock_irs_pin/services.py
- mock/src/mock_irs_pin/payloads.py
- mock/src/mock_irs_pin/processor.py
- mock/streamlit_app.py
- mock/run_mock.py

Real reference data used by the mock:
- Imp Data Regarding Customers and Requesters/Customers_List.csv
- Imp Data Regarding Customers and Requesters/Requesters_List.csv
- Imp Data Regarding Customers and Requesters/QA_Requesters_List.csv
- Imp Data Regarding Customers and Requesters/Requesters_List_all_IRS_Users_pins.csv
- Imp Data Regarding Customers and Requesters/IRS_All_Sites_Reference.xlsx
- Imp Data Regarding Customers and Requesters/IRS_report_monthly_2026-03-01.xlsx
- Imp Data Regarding Customers and Requesters/requesters_with_company_details_TEID.xlsx

Current validated behavior in the mock:
1. Parse CSV/XLSX input and validate rows.
2. Resolve BOD -> customerName.
3. Load API 3 style site strings for the customer.
4. Fuzzy match the incoming site name to the API 3 site string.
5. If Site ID is blank, resolve TEID using API 2 semantics.
6. Resolve max PIN using API 1 semantics.
7. Generate the new PIN deterministically as maxPin + 1, or TEID00001 if none exists.
8. Build the Connect-ready payload.
9. For deactivate rows, build the update payload.

Important constraints:
- Preserve the validated business logic and payload shape.
- Do not remove the Streamlit app; upgrade it to call real backend logic.
- Keep parser, matching, payload-building, and processor concerns separated.
- Replace mocked services with real HTTP client layers incrementally.
- Do not assume fK_Location from source files; fetch it from API 1 in QA/prod.
- Do not change the email domain or payload field spellings.

Payload facts that must remain correct:
- email domain: ad-astrainc.com
- fK_DefaultNativeLanguage: null
- oPI_ShdTelephonic: true
- oPI_OndemandTelephonic: true
- code: literal string "undefined"
- typo fields must remain exact:
  - recieveAllEmails
  - recieveUserEmails
  - vRI_ShdVideoInteroreting
  - vRI_OndemandVideoInteroreting

QA migration target:
- Replace local API 3 site lookup with GET /api/accounts/addresses/customer/{customerName}
- Replace local API 2 TEID resolution with GET /api/accounts/pin/max-teid/customer/{customerName}?siteName=
- Replace local API 1 pin context with GET /api/accounts/pin/customer-teid/{customerName}/{teid}
- Replace local create/deactivate operations with real Connect Insert/Update calls
- Add bearer token auth and 401 retry logic
- Keep local or SQL registry writes

Production migration target:
- Same logic as QA, but use the production hosts and production credentials/secrets
- Keep all environment-specific values configurable
- Do not hardcode secrets

Current QA deployment snapshot to know before changing deployment behavior:
- repo: `https://github.com/adastramax/IRSRequesterAutomation`
- branch currently deployed to QA EC2: `develop`
- QA EC2 public IP: `44.211.141.130`
- QA EC2 public DNS: `ec2-44-211-141-130.compute-1.amazonaws.com`
- QA VM repo path: `/home/ubuntu/IRSRequesterAutomation`
- QA app path on VM: `/home/ubuntu/IRSRequesterAutomation/QA`
- deployed with Docker Compose on Ubuntu
- final shared-VM host port mappings are:
  - API: `8002:8000`
  - frontend: `8520:8501`
- final QA URLs are:
  - frontend: `http://44.211.141.130:8520`
  - API: `http://44.211.141.130:8002`
- these port changes were deployment-only changes
- do not assume host ports `8000` or `8001` are available on the shared VM
- deployment pull command used:
  - `cd /home/ubuntu/IRSRequesterAutomation && git pull origin develop`
- deployment start command used:
  - `cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose up -d --build`

Expected implementation order:
1. Read the PRD and master doc first.
2. Read the mock code and preserve its structure.
3. Extract the mocked service boundaries from services.py/database.py.
4. Introduce real API client modules for auth, API 1, API 2, API 3, Insert, Update, and SEID search.
5. Change processor.py to depend on interfaces or service functions, not direct SQLite-only assumptions.
6. Keep the Streamlit app using the same processor contract.
7. Verify on a small QA batch before attempting broader changes.

When you answer or make changes:
- Be concrete.
- Prefer code changes over high-level advice.
- Explain which files you changed and why.
- Preserve the current working behavior unless a PRD-confirmed correction is required.
```

## Short version to tell another LLM

If you want a shorter instruction, tell it this:

`Read PRD v7, read mock/MOCK_Project_Summary.md, inspect mock/src/mock_irs_pin/* and mock/streamlit_app.py, then replace the mock service/database lookups with real QA or production Connect/API calls while preserving the validated processor flow and payload shape. If touching QA deployment, preserve the current EC2 shared-VM host ports unless explicitly asked to change them: API 8002, frontend 8520.`

## Minimum files it must analyze

- [prd/IRS_PIN_Tool_PRD_v7.docx](/E:/ad-astra/031 IRS PIN Generator/prd/IRS_PIN_Tool_PRD_v7.docx)
- [prd/IRS_PIN_Tool_Master_V7.md](/E:/ad-astra/031 IRS PIN Generator/prd/IRS_PIN_Tool_Master_V7.md)
- [mock/MOCK_Project_Summary.md](/E:/ad-astra/031 IRS PIN Generator/mock/MOCK_Project_Summary.md)
- [mock/src/mock_irs_pin/processor.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/processor.py)
- [mock/src/mock_irs_pin/payloads.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/payloads.py)
- [mock/src/mock_irs_pin/services.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/services.py)
- [mock/src/mock_irs_pin/database.py](/E:/ad-astra/031 IRS PIN Generator/mock/src/mock_irs_pin/database.py)
- [mock/streamlit_app.py](/E:/ad-astra/031 IRS PIN Generator/mock/streamlit_app.py)

## What it should not do

- do not rewrite the whole tool from scratch
- do not throw away the current payload builder
- do not replace deterministic PIN generation with random logic
- do not infer `fK_Location` from guesswork once real API 1 is available
- do not change the user-facing behavior before matching the current mock output
- do not casually reset shared-VM QA host ports to `8000` / `8501` without verifying availability
