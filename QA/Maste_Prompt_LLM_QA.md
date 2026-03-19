# Master Prompt LLM QA

Use this file when handing the current QA app to another LLM.

```text
You are working in:
E:\ad-astra\031 IRS PIN Generator

Your task is to continue work only inside:
E:\ad-astra\031 IRS PIN Generator\QA

Important:
- Treat the current QA code as the live source of truth.
- Do not use old mock files as the source of truth for QA behavior.
- Do not redesign the system.
- Do not rebuild from scratch.
- Keep changes minimal and targeted.
- `QA/src/qa_irs_pin/processor.py` is the backend source of truth.
- `QA/app.py` must remain a thin wrapper over the backend flow.
- Streamlit is active and matters.
- The QA app is already deployed on EC2.

Read these three QA handoff files first:
- QA/README_local.md
- QA/SUMMARY.md
- QA/Maste_Prompt_LLM_QA.md

Then inspect these implementation files:
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
- QA/docker-compose.yml

Current QA architecture:
- parser, matching, payloads, processor remain separate
- one processor drives CLI, FastAPI, and Streamlit
- live QA API client lives in QA/utils/client.py
- local SQLite registry/audit is still active
- Docker Compose is used for EC2 deployment
- the active Streamlit UI has 3 pages:
  - Add Requester
  - Deactivate Requester
  - Dev Use
- Add Requester combines bulk upload and manual entry in one workflow
- Deactivate Requester uses the same clean operations-style layout
- Dev Use remains the raw debug page for internal troubleshooting

Most important QA rules to preserve:

1. Insert vs Update contract
- Insert uses lower-camel browser-style form fields.
- Update uses fuller PascalCase form fields.

2. Verification order
- Trust exports/filter first.
- Then trust GetAccountDetailByID.
- Profile page in Connect QA is tertiary visual confirmation.
- members/filter is secondary only.

3. New-site first PIN rule
- if maxPinCode exists: int(maxPinCode) + 1
- if maxPinCode is null for a new site: int(f"{teid}00001")

4. Deactivate is detail-first
- resolve requester by SEID
- fetch GetAccountDetailByID first
- build Update payload from live detail
- refuse deactivate if detail cannot be fetched

5. Blank Site ID logic
- manual canonical site override -> exact API 2 resolution
- else if the input clearly references an existing site -> existing-site path
- else -> keep the original input as a new-site candidate
- API 2 is still the final authority on whether the site exists

6. Current manual-selection helper rule
- exact normalized match -> no manual selection
- input tokens subset of matched canonical site tokens -> no manual selection
- otherwise -> manual selection required

7. Generic-site caveat
- generic site fragments can drift as the live QA address list changes
- do not assume generic Jacksonville always means the historical Jacksonville site
- canonical full site strings or Manual Site Name are safer when deterministic behavior matters

FastAPI contract:
- POST /process/review = preview only, no mutation
- POST /process/commit = main frontend commit endpoint
- POST /process = legacy bulk file endpoint
- POST /process/rows = redundant JSON commit alias

Current frontend contract:
- manual flow is review -> commit
- bulk upload remains on legacy /process
- no operator field in the UI
- normal user screens should not show raw JSON, match scoring, or backend trace details
- Add Requester should keep bulk upload above manual entry
- Deactivate Requester should keep the same clean button-row workflow as Add Requester
- Dev Use is the only place where raw responses and debug payloads belong

Current commit response contract:
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

Current deployment snapshot:
- repo: https://github.com/adastramax/IRSRequesterAutomation
- deployed branch: develop
- EC2 public IP: 44.211.141.130
- EC2 public DNS: ec2-44-211-141-130.compute-1.amazonaws.com
- VM repo path: /home/ubuntu/IRSRequesterAutomation
- QA app path: /home/ubuntu/IRSRequesterAutomation/QA
- deployment command:
  - cd /home/ubuntu/IRSRequesterAutomation/QA && sudo docker compose up -d --build
- current shared-VM host ports:
  - API: 8002:8000
  - frontend: 8520:8501
- current URLs:
  - frontend: http://44.211.141.130:8520
  - API: http://44.211.141.130:8002

Important deployment constraint:
- this is a shared VM
- do not assume ports 8000 or 8001 are available
- do not change host port mappings casually without confirming availability

Current verified behaviors to remember:
- existing site with TEID provided
- existing site with TEID missing
- true new site with TEID missing
- direct-site-ID canonical override
- detail-first deactivate
- bulk upload through Streamlit legacy /process
- review/commit parity for provided Site ID cases
- payload-address preservation on new-site blank-Site-ID commits
- safe-subset auto-match for Flat C and House 101
- differentiated Jacksonville variants remain differentiated

Known bad record:
- SEID: 346EDR24
- GUID: fdf752d3-fdf2-4d9d-838f-1f62a47ba8eb
- this is an inconsistent old deactivate target
- do not use it as a healthy proof record

When changing code:
- keep processor.py as backend truth
- do not redesign module boundaries
- verify against live QA when behavior changes
- use fresh SEIDs for create tests
- do not hardcode old TEIDs as if QA state is static
- report exact current SEID/GUID/TEID/PIN outcomes after testing

What not to do:
- do not use the old mock directory as QA source of truth
- do not move business truth out of processor.py
- do not remove legacy /process unless bulk strategy is intentionally replaced
- do not replace deterministic PIN logic with random logic
- do not rebuild deactivate payload from exports/filter alone
- do not change deployment ports on the shared VM without confirming availability
```

## Short version

Give another LLM this instruction:

`Read QA/README_local.md, QA/SUMMARY.md, and QA/Maste_Prompt_LLM_QA.md first. Treat QA/src/qa_irs_pin/processor.py as the backend source of truth, preserve the review -> commit manual flow and legacy bulk /process flow, preserve Insert/Update payload contracts, and preserve the current EC2 deployment shape on ports 8002 and 8520 unless explicitly asked to change deployment.`
