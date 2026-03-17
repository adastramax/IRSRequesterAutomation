# IRSRequesterAutomation

```

This covers: normal create, same site second user, blank TEID (auto-assign), deactivate, and intra-batch duplicate — all 5 edge cases from the PRD in one file.

---

## Project Structure — Build This First
```
irs-pin-tool/
├── .env                    # never committed
├── docker-compose.yml
├── backend/
│   ├── main.py             # FastAPI app
│   ├── connect_client.py   # all API calls
│   ├── pin_engine.py       # 4-step flow
│   ├── file_parser.py      # pandas, validation
│   ├── registry.py         # SQL Server reads/writes
│   ├── models.py           # Pydantic schemas
│   └── requirements.txt
├── frontend/
│   ├── app.py              # Streamlit
│   └── requirements.txt
└── sql/
    └── create_tables.sql
```

---

## LLM Prompts for Your IDE — Optimized for Minimum Tokens

Use these in order. Each prompt is self-contained and produces a working file. Don't combine them — one file per prompt keeps context tight and output clean.

---

**Prompt 1 — connect_client.py**
```
Build a Python class ConnectClient for the Ad Astra Connect QA API.

Base URLs:
- Auth + search: appbe.ad-astrainc.com
- All other endpoints: connectapiqas.ad-astrainc.com

Credentials from env: CONNECT_EMAIL, CONNECT_PASSWORD

Methods needed:
1. authenticate() → stores bearer token
2. _request(method, url, **kwargs) → auto-refreshes token on 401, retries once
3. search_user_by_seid(seid: str) → paginates POST /api/accounts/exports/filter/CONSUMER/0/?page={n}&items_per_page=50, body={"customers":[],"subAccounts":[],"status":[],"roles":[],"joinDate":null,"loginDate":null}, filters where record["firstName"].lower() == seid.lower(), returns list of matches
4. check_pin_available(pin: str) → GET /api/accounts/check-pin-availablity/{pin} (typo intentional), returns True if available (data=false)
5. confirm_pin(pin: str) → GET /api/accounts/pincode, returns confirmed pin string from response.data
6. insert_user(payload: dict) → POST /api/Accounts/Insert multipart/form-data, returns (success: bool, guid: str, message: str)
7. deactivate_user(guid: str) → POST /api/accounts/Update with code=guid and deactivation flag, returns (success: bool, message: str)

Use httpx with async. Raise custom ConnectAPIError on non-S status.
```

---

**Prompt 2 — pin_engine.py**
```
Build an async Python function run_pin_creation_flow(seid, teid, first_name, last_name, bod, site_name, fk_customer, fk_location, client: ConnectClient) that executes the 4-step IRS PIN flow:

Step 1: Generate candidate PIN = str(teid).zfill(4) + str(random.randint(10000,99999))
Step 2: Call client.check_pin_available(pin). If not available, regenerate suffix and retry. No hard limit. Log warning if >10 attempts.
Step 3: Call client.confirm_pin(pin). Use returned value as final pin.
Step 4: Call client.insert_user() with this multipart payload:
  firstName=seid, lastName=f"{last_name} {first_name}".upper(),
  email=f"{seid.lower()}.{last_name.lower()}{first_name.lower()}@adastrainc.com",
  pinCode=int(confirmed_pin), pinCodeString=str(confirmed_pin),
  fK_Customer=fk_customer, fK_Location=fk_location,
  fk_PreCallPolicy=19, fK_DefaultNativeLanguage="aze",
  fK_DefaultTimeZone="b9efba83-5fb3-11ef-8538-0291956bad29",
  role="User", userType="CONSUMER", code="undefined",
  oPI_ShdTelephonic=true, all other OPI/VRI/OSI flags=false,
  accessBilling=false, recieveAllEmails=false, recieveUserEmails=false,
  setPassword=false, isNewPasswordGenerate=true,
  phoneNumber="", fK_Gender="", password=""

Return PinCreationResult(success, pin, guid, error_message).
Import ConnectClient from connect_client.py.
```

---

**Prompt 3 — registry.py**
```
Build a Python module registry.py for SQL Server using pyodbc + SQLAlchemy.

Connection string from env: DB_CONNECTION_STRING

Three functions:
1. upsert_pin_record(seid, first_name, last_name, bod, site_id, site_name, pin_9digit, connect_guid, status, batch_id, created_by) → upsert into STG.IRS_PIN_REGISTRY on SEID
2. lookup_teid(site_name: str) -> Optional[str] → query STG.IRS_TEID_REGISTRY by SITE_NAME (case-insensitive), return TEID or None
3. assign_new_teid(site_name: str, fk_customer: int, fk_location: int) → find lowest unused 4-digit int (1000-9999) not in STG.IRS_TEID_REGISTRY.TEID, insert new row, return new TEID as zero-padded 4-char string

Also include create_tables_sql: str constant with the CREATE TABLE IF NOT EXISTS statements for all 3 tables (IRS_PIN_REGISTRY, IRS_TEID_REGISTRY, IRS_ACCOUNT_MAP) matching the PRD schema exactly.
```

---

**Prompt 4 — file_parser.py**
```
Build parse_and_validate(file_bytes: bytes, filename: str) -> list[dict] using pandas.

Accept .xlsx, .xls, .csv. Match columns by header name case-insensitive.

Required columns: BOD, Last Name, First Name, SEID, Site Name, Contact Status
Optional: Site ID (TEID), 9-digit User PIN

Per-row validation:
- Missing required field → status="Error", error_fields=[field_names]
- Blank Site ID → status="Warning", note="TEID will be auto-assigned"
- Contact Status not in ["Add","Deactivate",""] → status="Error"
- Duplicate SEID within file → second+ occurrences status="Warning", note="Duplicate SEID - will be skipped"
- Valid row → status="Valid"

Return list of dicts with original fields + _status, _notes, _row_index.
```

---

**Prompt 5 — main.py (FastAPI)**
```
Build a FastAPI app with these endpoints. Import from connect_client, pin_engine, file_parser, registry.

POST /upload: accepts UploadFile, calls parse_and_validate, returns preview rows with validation status
POST /process: accepts batch (list of validated rows) + created_by. Generates batch_id=uuid4. Runs each row async:
  - Skip Error/Duplicate rows
  - For Add: search SEID in Connect → if found check TEID match → if same confirm Active → else run pin_engine flow
  - For Deactivate: search SEID → get GUID → deactivate → update registry
  - Write every result to registry
  Returns batch_id immediately. Stores results in in-memory dict keyed by batch_id.
GET /batch/{batch_id}: return current results for batch (for polling)
GET /users/search?seid=: proxy search_user_by_seid
GET /pins/next?teid=: run Steps 1-2 loop, return available candidate PIN (does not confirm — just checks)
GET /teid/lookup?site_name=: registry.lookup_teid
POST /teid/create: body {site_name, fk_customer, fk_location} → registry.assign_new_teid
GET /registry: query STG.IRS_PIN_REGISTRY with optional filters: bod, status, date_from, date_to

Use lifespan to initialize ConnectClient and authenticate on startup. Store as app.state.connect_client.
```

---

**Prompt 6 — Streamlit app.py**
```
Build a Streamlit app with 6 pages using st.navigation / st.sidebar radio.

Page 1 "Upload & Process":
- st.file_uploader for xlsx/xls/csv
- On upload: POST to http://localhost:8000/upload, show preview dataframe with color-coded _status column (green=Valid, yellow=Warning, red=Error)
- "Process Batch" button: POST to /process with valid rows + st.session_state.get("username","OPI Team")
- Poll GET /batch/{batch_id} every 3 seconds using st.rerun(), show live progress bar

Page 2 "Results": poll /batch/{batch_id} if active, show results table with status badges, Download Results button (original df + PIN + Status columns appended), Retry Failed button

Page 3 "PIN Registry": GET /registry with filter sidebar (BOD, Status, date range), show searchable table, CSV export

Page 4 "TEID Manager": table from /teid/lookup, Add New Site form → POST /teid/create

Page 5 "Account Mapping": static table display + note to update STG.IRS_ACCOUNT_MAP directly in DB for now

Page 6 "Audit Log": GET /audit/batches, drill-down by batch_id

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000"). Use requests library (not httpx) for all calls.
```

---

**Prompt 7 — Docker**
```
Write docker-compose.yml for two services:
1. backend: build from ./backend, port 8000, env_file .env
2. frontend: build from ./frontend, port 8501, env_file .env, env BACKEND_URL=http://backend:8000, depends_on backend

Write Dockerfile for each service using python:3.11-slim, pip install -r requirements.txt, appropriate CMD.

Write nginx.conf for reverse proxy on EC2: / → frontend:8501, /api → backend:8000, HTTPS redirect stub.
