# IRS PIN Management Tool — Full Project Summary & LLM Handoff Document
**Author:** Muhammad Maaz Ahmed | **Company:** Ad Astra, Inc. | **Date:** March 2026  
**PRD Latest Version:** v5.0 (IRS_PIN_Tool_PRD_v5.docx)

---

## SECTION 1: LLM HANDOFF PROMPT

Use this prompt to onboard another LLM to this project:

---

> You are acting as a Principal AI/ML Engineer and Senior Data Engineer mentor for Muhammad Maaz Ahmed at Ad Astra, Inc. He is building an internal web application called the **IRS PIN Management Tool** for the OPI (Over-the-Phone Interpretation) team. The tool automates the creation and management of IRS requestor PINs in the Ad Astra Connect platform.
>
> **Your role:** Be decisive, give one clear path, be technically correct, think end-to-end from input file → API → database → frontend. Prioritize correctness over speed.
>
> **Stack:** Python throughout. Streamlit (frontend), FastAPI (backend), pandas (file parsing), SQL Server (existing DB, STG schema), Docker + docker-compose (containerisation), AWS EC2 + Nginx (hosting).
>
> **Current status:** PRD v5.0 is complete and approved. Two internal backend APIs have been designed and handed to the backend developer. The Connect QA Insert API has been confirmed working. The main open item is confirming the default native language value with Aysha, and the backend dev confirming exact DB table/column names.
>
> **Key people:** Maaz (developer, you are mentoring him), Vadim Petrov (team lead, highly analytical), Aysha El-Sibai (OPI team, subject matter expert — currently does this manually).
>
> Read the full project summary below and treat it as ground truth. Do not ask Maaz to repeat anything already documented here.

---

## SECTION 2: PROJECT BACKGROUND

### What is this?
Ad Astra provides Over-the-Phone Interpretation (OPI) services to IRS (Internal Revenue Service). IRS officers call in to get language interpretation. Each IRS officer needs a unique 9-digit PIN in the Ad Astra Connect platform to authenticate themselves when calling.

### The Problem Being Solved
Currently Aysha El-Sibai (OPI team) does this **completely manually**:
1. IRS sends an Excel file with new officer requests
2. Aysha opens Connect, filters by account, sorts 35,000+ rows by IVR Pin
3. She finds the highest PIN for that site, adds 1, manually creates the user in Connect UI
4. She updates the Excel file with the new PIN and sends it back to IRS

There is **no automation, no audit trail, no validation, no duplicate protection.**

### What We Are Building
A full internal web application that:
- Accepts bulk Excel/CSV file uploads or single manual form entry
- Validates all data
- Calls the Connect API automatically to create/deactivate users
- Maintains a local SQL registry of all PIN assignments
- Returns completed file with PINs filled in for OPI team to send back to IRS

---

## SECTION 3: IRS PIN STRUCTURE — CRITICAL BUSINESS LOGIC

### 9-Digit PIN Format
```
[TEID - 4 digits][SUFFIX - 5 digits]
     5485              27430
= 548527430
```

| Digits | Source | Method |
|--------|--------|--------|
| First 4 | SITE ID (TEID) | Taken from input. If blank, system assigns new TEID. **NEVER from SEID.** |
| Last 5 | Database | MAX(IVR Pin) for that site + 1. Deterministic, not random. |

### CRITICAL DISTINCTION — TEID vs SEID
- **TEID** = 4-digit Site ID code. This is the PIN prefix. Example: `5485`
- **SEID** = IRS Officer unique ID. Example: `Z-1234`. This goes into `firstName` in the Connect payload ONLY. Has NOTHING to do with PIN generation.
- These two fields are completely different. Never confuse them.

### PIN Generation Logic (Final — v5)
1. Get `current_max_pin` from Internal API 1 (MAX of IVR Pin column for that TEID)
2. `new_pin = current_max_pin + 1`
3. If `current_max_pin` is null (brand new site, no users yet): `new_pin = {TEID}00001`
4. Example: TEID=5485, current max=548527429 → new PIN = **548527430**

**No randomness. No availability check loop. DB is the source of truth.**

---

## SECTION 4: THREE CORE WORKFLOWS

| # | Workflow | Trigger | Outcome |
|---|----------|---------|---------|
| 1 | Create User + PIN | Contact Status = Add / SEID not in Connect | New user created in Connect with calculated PIN |
| 2 | Deactivate User | Contact Status = Deactivate | User deactivated via Update API |
| 3 | New Site / TEID Assignment | Site ID blank in input | New TEID assigned via Internal API 2, then Workflow 1 |

---

## SECTION 5: INPUT FILE SPECIFICATION

### Accepted Formats
`.xlsx`, `.xls`, `.csv` — column order may vary between IRS affiliates. Parser must match by column header name (case-insensitive), not position.

### Required Columns
| Column | Required | Notes |
|--------|----------|-------|
| BOD | Yes | IRS affiliate/department. e.g. TAS, CI, Field Assistance |
| Last Name | Yes | |
| First Name | Yes | |
| SEID | Yes | Unique Officer ID. Goes into `firstName` in Connect. Primary lookup key. |
| Site ID / TEID | Conditional | 4-digit code. If blank, system assigns via Internal API 2 |
| Site Name | Yes | Used in API 2 LIKE filter when Site ID blank |
| 9-digit User PIN | Output only | Empty on input. App populates after creation |
| Contact Status | Yes | Add = create. Deactivate = disable |

---

## SECTION 6: COMPLETE PIN CREATION FLOW (3 STEPS)

```
INPUT ROW RECEIVED
      |
      v
Site ID in input?
      |
      |-- YES ─────────────────────────────────────────────────────────┐
      |                                                                 |
      └-- NO → Internal API 2 (GET /internal/teid/next)                |
                    |                                                   |
                    |-- site_already_exists=true → use existing_teid ──┤
                    |                                                   |
                    └-- site_already_exists=false → increment          |
                        current_max_teid + 1 → new TEID ──────────────┤
                                                                       |
                                                                       v
                                          STEP 1: Internal API 1 (GET /internal/pins/next)
                                          Returns current_max_pin
                                          App calculates: new_pin = current_max_pin + 1
                                          If null: new_pin = {teid}00001
                                          API 1 also returns fk_customer + fk_location
                                                      |
                                                      v
                                          STEP 2: POST /api/Accounts/Insert (Connect)
                                          Create user with new_pin + all fields
                                                      |
                                                      |── status='S' → SUCCESS
                                                      └── status≠'S' → FAILED (log, continue)
                                                      |
                                                      v
                                          STEP 3: Write to STG.IRS_PIN_REGISTRY
END
```

### REMOVED from flow (important):
- ❌ `GET /api/accounts/pincode` — was for random PIN generation server-side. NOT needed. We calculate PIN ourselves.
- ❌ `GET /api/accounts/check-pin-availablity/{pin}` — was for availability loop. NOT needed. MAX+1 from DB is deterministic.

---

## SECTION 7: INTERNAL APIs (Backend Developer to Build)

These are two read-only GET APIs the backend developer builds against the Connect database. **No writes, just selects.**

### Internal API 1 — Get Max PIN for a Site

**Endpoint:** `GET /internal/pins/next`

**Purpose:** Find highest IVR Pin for a given site. Also return fK_Customer and fK_Location since they are required for the Connect Insert payload and exist in the same table.

**Required Parameters:**
| Parameter | Type | Example |
|-----------|------|---------|
| `site_id` | string | `5485` |

> Note: BOD filter was originally included but team lead confirmed TEID alone is sufficient since TEID is unique. BOD filter removed from API 1.

**What backend does:**
| Step | Action |
|------|--------|
| 1 | Filter table where `TEID = {site_id}` |
| 2 | Run `MAX(IVR Pin)` on filtered records |
| 3 | From same records pull `fK_Customer` and `fK_Location` |
| 4 | If no records found, return `null` for `current_max_pin` |

**Response:**
```json
{
  "current_max_pin": "548527428",
  "site_id": "5485",
  "account_name": "USA GA IRS Taxpayer Advocate Service (TAS)",
  "fk_customer": 277,
  "fk_location": 13
}
```

**Response when no records exist (new site):**
```json
{
  "current_max_pin": null,
  "site_id": "5485",
  "account_name": "USA GA IRS Taxpayer Advocate Service (TAS)",
  "fk_customer": 277,
  "fk_location": 13
}
```

> When `current_max_pin` is null: app builds first PIN as `{site_id}00001`. Example: TEID 5486 → PIN = `548600001`

---

### Internal API 2 — Get Max TEID for a BOD (New Site Assignment)

**Endpoint:** `GET /internal/teid/next`

**Purpose:** Used ONLY when Site ID is blank in input. Checks if site already exists. Returns existing TEID or current max TEID so app can assign next one.

**Required Parameters:**
| Parameter | Type | Example |
|-----------|------|---------|
| `bod` | string | `TAS` |
| `site_name` | string | `Buffalo Area 1` |

**What backend does:**
| Step | Action |
|------|--------|
| 1 | Filter table where `Account Name LIKE '%{bod}%'` |
| 2 | Check if any record has `Site Name LIKE '%{site_name}%'` |
| 3 | If site found → return its TEID as `existing_teid`, set `site_already_exists: true` |
| 4 | If site not found → run `MAX(TEID)` across filtered records, return as `current_max_teid`, set `site_already_exists: false` |

**Response (new site):**
```json
{
  "current_max_teid": "5485",
  "existing_teid": null,
  "account_name": "USA GA IRS Taxpayer Advocate Service (TAS)",
  "site_already_exists": false
}
```

**Response (site exists):**
```json
{
  "current_max_teid": null,
  "existing_teid": "5485",
  "account_name": "USA GA IRS Taxpayer Advocate Service (TAS)",
  "site_already_exists": true
}
```

### Additional API (New — Backend Dev Confirmed Building)
**BOD → All Site Locations API:** Send BOD, get back all site names + TEID + address details (city, state, postal code, lat, long) for that account. This solves two problems:
1. Lets OPI team map an incoming site name to the correct DB site name via dropdown
2. Provides all address fields needed for the Connect Insert payload

**⚠️ Backend Dev Note:** Before building any of the above, confirm exact **table name** and exact **column names** for: Account Name, TEID, IVR Pin, Site Name.

---

## SECTION 8: CONNECT API REFERENCE

### Environments
| Environment | Base URL | When Used |
|-------------|----------|-----------|
| Local | Mocked | Development |
| QA | `connectapiqas.ad-astrainc.com` | Testing |
| Production | Same as QA URL | Live — controlled by `CONNECT_ENV` env variable |
| Auth + Search | `appbe.ad-astrainc.com` | Token + user search only |

### Authentication
- **Endpoint:** `POST https://connectapiqas.ad-astrainc.com/api/accounts/token`
- **Body:** `{ email: CONNECT_EMAIL, password: CONNECT_PASSWORD, rememberMe: true }`
- **Response:** `{ token: "<bearer_jwt>" }`
- **Usage:** `Authorization: Bearer <token>` on all calls
- **Refresh:** Re-auth on any 401, retry once
- **QA credentials:** `almaskhan@ad-astrainc.com` — stored in `.env` only

### Search Users (SEID Lookup)
- **Endpoint:** `POST https://appbe.ad-astrainc.com/api/accounts/exports/filter/CONSUMER/0/?page={n}&items_per_page=50`
- **Body:** `{ customers: [], subAccounts: [], status: [], roles: [], joinDate: null, loginDate: null }`
- **Key fields in response:** `firstName` (=SEID), `pinCode`, `code` (GUID), `accountStatus`
- **Pagination:** Loop page=1 to `last_page`

### Create User (Insert) — CONFIRMED WORKING ON QA
- **Endpoint:** `POST https://connectapiqas.ad-astrainc.com/api/Accounts/Insert`
- **Content-Type:** `multipart/form-data`
- **Success:** `{ "status": "S", "text": "Successfully created", "result": "<user-guid>" }`
- **Store:** Save `result` GUID in `IRS_PIN_REGISTRY.CONNECT_GUID`

### Deactivate User (Update)
- **Endpoint:** `POST https://connectapiqas.ad-astrainc.com/api/accounts/Update`
- **Key field:** `code: <user-guid from search>`
- **Success:** `{ "status": "S", "text": "Successfully deactivated" }`

---

## SECTION 9: FULL INSERT PAYLOAD — CONFIRMED FROM QA

All fields confirmed from two live QA test calls:

| Field | Value / Source | Fixed or Dynamic |
|-------|---------------|-----------------|
| firstName | SEID from input | Dynamic |
| lastName | LastName + ' ' + FirstName from input | Dynamic |
| email | `SEID.Name@adastrainc.com` (lowercase, no spaces) | Dynamic — constructed |
| phoneNumber | (empty) | Fixed |
| fK_Gender | (empty) | Fixed |
| fK_Customer | From Internal API 1 response | Dynamic |
| fK_Location | From Internal API 1 response | Dynamic |
| fK_ServiceType | SVC_COM | Fixed |
| serviceTypes | SVC_COM | Fixed |
| fk_PreCallPolicy | 19 (QA) | Fixed — prod TBD |
| fK_DefaultNativeLanguage | **⚠️ PENDING — ask Aysha** | TBD |
| fK_DefaultTimeZone | b9efba83-5fb3-11ef-8538-0291956bad29 | Fixed — Eastern Time |
| role | User | Fixed |
| accessBilling | false | Fixed |
| recieveAllEmails | false | Fixed — typo intentional |
| recieveUserEmails | false | Fixed — typo intentional |
| SubCustomerIds | Same as fK_Customer | Dynamic |
| city | From BOD→site locations API | Dynamic |
| pinCode | Calculated new_pin (integer) | Dynamic |
| pinCodeString | Calculated new_pin (string) | Dynamic |
| address | From BOD→site locations API | Dynamic |
| state | From BOD→site locations API | Dynamic |
| country | United States | Fixed |
| postalCode | From BOD→site locations API | Dynamic |
| latitude | From BOD→site locations API | Dynamic |
| longitude | From BOD→site locations API | Dynamic |
| code | undefined (literal string) | Fixed |
| userType | CONSUMER | Fixed |
| password | (empty) | Fixed |
| setPassword | false | Fixed |
| isNewPasswordGenerate | true | Fixed |
| oPI_ShdTelephonic | true | Fixed |
| oPI_OndemandTelephonic | false | Fixed |
| vRI_ShdVideoInteroreting | false | Fixed — typo intentional |
| vRI_OndemandVideoInteroreting | false | Fixed — typo intentional |
| oSI_OnsiteConsecutive | false | Fixed |
| oSI_OnsiteSimultaneous | false | Fixed |
| oSI_OnsiteWhisper | false | Fixed |
| oSI_Onsite | false | Fixed |
| other_3rdPartyPlatform | false | Fixed |
| linguistType | 0 | Fixed |
| payableType | 0 | Fixed |

> **Email domain is `adastrainc.com` — NO hyphen.** Confirmed from QA payload: `Z-1234.Test@adastrainc.com`
> **Multiple field names have intentional typos** (recieveAllEmails, vRI_ShdVideoInteroreting) — match exactly.

### QA Hardcoded Test Values (MarkyTech Account)
| Field | Value |
|-------|-------|
| fK_Customer | 277 |
| fK_Location | 13 |
| fk_PreCallPolicy | 19 |
| fK_DefaultNativeLanguage | aze (QA test 1) / cre (QA test 2) — PENDING confirmation |
| fK_DefaultTimeZone | b9efba83-5fb3-11ef-8538-0291956bad29 |

---

## SECTION 10: ROW PROCESSING PIPELINE

Every row from file upload or manual form goes through these steps:

| Step | Action | Detail |
|------|--------|--------|
| 1 | Parse & Validate | Check required fields. Flag missing SEID/Name/Site Name as Error. Do not process error rows. |
| 2 | Intra-batch Duplicate Check | Same SEID in batch: process first occurrence, skip rest. Show in preview. |
| 3 | SEID Lookup in Connect | Search firstName=SEID via filter API. Paginate all pages. |
| 4A | SEID not found | New user. Proceed to TEID resolution then 3-step flow. |
| 4B | SEID found | Compare first 4 digits of existing pinCode vs incoming TEID. Same TEID: confirm Active, skip. Different TEID: treat as new user. |
| 5 | Contact Status routing | Add/blank → creation. Deactivate → Update API. Unrecognised → best-guess. |
| 6 | Execute 3-step flow | Internal API 1 → Insert → Registry |
| 7 | Write result | IRS_PIN_REGISTRY + UI display |

---

## SECTION 11: DATABASE TABLES

### STG.IRS_PIN_REGISTRY
| Column | Type | Description |
|--------|------|-------------|
| ID | INT IDENTITY PK | |
| SEID | VARCHAR(20) UNIQUE NOT NULL | Primary lookup key |
| FIRST_NAME | VARCHAR(100) | |
| LAST_NAME | VARCHAR(100) | |
| BOD | VARCHAR(100) | IRS affiliate |
| SITE_ID | VARCHAR(10) | TEID — 4-digit code |
| SITE_NAME | VARCHAR(200) | |
| PIN_9DIGIT | VARCHAR(9) | Final assigned PIN |
| CONNECT_GUID | VARCHAR(50) | UUID from Insert result field |
| STATUS | VARCHAR(20) | Active / Inactive / Pending / Failed |
| BATCH_ID | VARCHAR(50) | Links row to upload batch |
| CREATED_BY | VARCHAR(100) | OPI team member who processed |
| CREATED_DT | DATETIME DEFAULT GETDATE() | |
| UPDATED_DT | DATETIME | |

### STG.IRS_TEID_REGISTRY
| Column | Type | Description |
|--------|------|-------------|
| TEID | VARCHAR(4) UNIQUE NOT NULL | 4-digit site code |
| SITE_NAME | VARCHAR(200) | |
| SITE_ADDRESS | VARCHAR(500) | |
| FK_CUSTOMER | INT | Connect account ID |
| FK_LOCATION | INT | Connect location ID |
| CREATED_DT | DATETIME DEFAULT GETDATE() | |

> **Note:** STG.IRS_ACCOUNT_MAP was in earlier PRD versions but has been **removed in v5**. fK_Customer and fK_Location come from Internal API 1 directly. No separate mapping table needed.

---

## SECTION 12: TECHNICAL ARCHITECTURE

```
[OPI Team Browser]
      | HTTPS
[Nginx on EC2]
      |
      |── :8501 → [Streamlit Container]    (UI only — Python)
      |── :8000 → [FastAPI Container]      (all logic — Python)
                        |
                        |── Internal API 1 + 2  (backend dev's DB APIs)
                        |── connectapiqas        (Insert, Update — Connect)
                        |── appbe                (Auth, Search — Connect)
                        |── SQL Server           (STG.IRS_PIN_REGISTRY, STG.IRS_TEID_REGISTRY)
```

### Stack
| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | Streamlit (Python) | No separate JS build |
| Backend | FastAPI (Python) | Async, clean REST |
| File parsing | pandas | xlsx, xls, csv |
| Database | SQL Server (existing) | STG schema, 2 new tables |
| Container | Docker + docker-compose | Streamlit + FastAPI separate services |
| Hosting | AWS EC2 | Single instance |
| Reverse proxy | Nginx | HTTPS termination |
| Secrets | .env file | Never committed to repo |

### Docker Compose Structure
```yaml
services:
  api:
    build: ./backend
    ports: ['8000:8000']
    env_file: .env
  frontend:
    build: ./frontend
    ports: ['8501:8501']
    environment:
      API_URL: http://api:8000
  nginx:
    image: nginx:alpine
    ports: ['80:80', '443:443']
```

### FastAPI Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /upload | Parse file. Return preview with validation. |
| POST | /process | Run pipeline async. Returns batch_id immediately. |
| GET | /batch/{batch_id} | Poll status + per-row results. |
| GET | /users/search?seid= | Search Connect by SEID. |
| GET | /pins/resolve?site_id= | Proxy to Internal API 1. Returns calculated new_pin. |
| GET | /teid/resolve?bod=&site_name= | Proxy to Internal API 2. Returns TEID to use. |
| GET | /registry | List IRS_PIN_REGISTRY with filters. |
| GET | /audit/batches | All processed batches. |

---

## SECTION 13: FRONTEND — STREAMLIT PAGES

**Page 1: Upload & Process**
- File uploader (xlsx, xls, csv) + manual entry toggle
- Preview table after upload: green=Valid, yellow=Warning (blank TEID), red=Error (missing field)
- Duplicate SEID highlighted in preview before processing
- Process button → async → live polling every 3 seconds

**Page 2: Results**
- Row table: SEID | Name | TEID | PIN Assigned | Action | Status | Notes
- Badges: Created (green) | Deactivated (orange) | Already Exists (blue) | Skipped (yellow) | Failed (red)
- Download Results button: original file + PIN column + Status column appended
- Retry Failed button: re-queues failed rows only

**Page 3: PIN Registry**
- Searchable STG.IRS_PIN_REGISTRY with filters (BOD, TEID, Status, Date, Created By)
- Export to CSV

**Page 4: TEID Manager**
- Table of STG.IRS_TEID_REGISTRY
- Add New Site form + Edit existing records

**Page 5: Audit Log**
- All batches: ID | File | Date | Operator | Total | Created | Failed
- Drill into batch for per-row detail

---

## SECTION 14: ERROR HANDLING

| Scenario | Handling |
|----------|----------|
| Missing required field | Error in preview. Block row. Show exact field name. |
| Duplicate SEID in batch | Process first. Skip rest with reason. Show in preview. |
| SEID found, same TEID | Confirm Active. Mark Already Exists. |
| SEID found, different TEID | Treat as new user. Full creation flow. |
| TEID blank in input | Auto-resolve via Internal API 2. |
| Internal API returns error | Mark row Failed. Log. Continue to next row. |
| Connect Insert non-'S' response | Mark Failed. Log full response. Continue. |
| Connect 401 | Re-auth. Retry once. If still 401, pause batch, alert user. |
| Unrecognised Contact Status | Warn. Best-guess: contains 'add' → Create, 'deactivat' → Deactivate. |
| File parse error | Error at upload stage. Ask user to re-upload. |

---

## SECTION 15: OUT OF SCOPE — v1

- Bulk retroactive PIN cleanup for 35,000+ existing users in Connect
- Automated email of completed file to IRS affiliate (OPI team sends manually)
- Role-based access control (all OPI team same access)
- ETL sync to populate REQUESTOR_PIN in TRN.OPI_FULL
- USCIS PIN management (architecture supports it — IRS only for v1)

---

## SECTION 16: EFFORT ESTIMATE

| Phase | Deliverables | Estimate |
|-------|-------------|----------|
| 1 — Foundation | DB tables, Internal API 1+2 integration, Connect client (auth + search + insert + update) | 3–4 days |
| 2 — Backend | All FastAPI endpoints, file parser, async batch, error handling | 5–6 days |
| 3 — Frontend | All 5 Streamlit pages | 4–5 days |
| 4 — Docker & EC2 | docker-compose, Nginx, EC2, HTTPS | 2 days |
| 5 — QA Testing | End-to-end on connectapiqas, MarkyTech account, edge cases | 3 days |
| **TOTAL** | | **17–20 working days (~4 weeks)** |

---

## SECTION 17: ALL DECISIONS — FINAL STATUS

| # | Decision | Resolution |
|---|----------|-----------|
| 1 | PIN last 5 digits: random or DB-driven? | DB-driven. Internal API 1 returns MAX(IVR Pin). App does +1. |
| 2 | GET /api/accounts/pincode needed? | NO — removed. Not needed. |
| 3 | check-pin-availability loop needed? | NO — removed. MAX+1 is deterministic. |
| 4 | How to get fK_Customer and fK_Location? | Internal API 1 returns them from DB. |
| 5 | STG.IRS_ACCOUNT_MAP needed? | NO — removed in v5. |
| 6 | PIN prefix: TEID or SEID? | TEID always. SEID = firstName in payload only. |
| 7 | Email domain? | adastrainc.com (no hyphen). |
| 8 | QA test account? | MarkyTech. fK_Customer=277, fK_Location=13. |
| 9 | Deployment order? | Local → QA → Prod. CONNECT_ENV variable. |
| 10 | Frontend framework? | Streamlit. |
| 11 | Hosting? | AWS EC2 + Docker + Nginx. |
| 12 | BOD needed in API 1? | NO — TEID alone sufficient for API 1. BOD only needed in API 2. |
| 13 | Default native language value? | **⚠️ PENDING — ask Aysha** |
| 14 | Exact DB table/column names? | **⚠️ PENDING — backend dev to confirm** |

---

## SECTION 18: OPEN ITEMS — MUST RESOLVE BEFORE DEVELOPMENT

| # | Item | Owner | Impact |
|---|------|-------|--------|
| 1 | `fK_DefaultNativeLanguage` default value for IRS users | Aysha El-Sibai | Required for Insert payload |
| 2 | Exact table name and column names (Account Name, TEID, IVR Pin, Site Name) | Backend Developer | Blocks Internal API 1 and 2 |
| 3 | Address fields (city, state, postal, lat, long) format in BOD→sites API | Backend Developer | Required for Insert payload |
| 4 | Production `fk_PreCallPolicy` value | Vadim / Aysha | QA value is 19 — prod may differ |

---

## SECTION 19: KEY TECHNICAL NOTES FOR NEW DEVELOPER

1. **Intentional typos in Connect API field names** — these are real field names, not mistakes. Always match exactly:
   - `recieveAllEmails` (not receiveAllEmails)
   - `recieveUserEmails` (not receiveUserEmails)
   - `vRI_ShdVideoInteroreting` (not Interpreting)
   - `vRI_OndemandVideoInteroreting`
   - `check-pin-availablity` (not availability) — this endpoint is no longer used but note for reference

2. **`code` field in Insert payload** = literal string `"undefined"` — not null, not empty, the word undefined

3. **SEID in firstName** — IRS convention stores officer ID in firstName field in Connect. When searching for a user by SEID, filter where `firstName == SEID`

4. **Token auth** — use `appbe.ad-astrainc.com` for auth and search, `connectapiqas.ad-astrainc.com` for Insert and Update

5. **All processing is async** — POST /process returns batch_id immediately, frontend polls GET /batch/{id} every 3 seconds

6. **Idempotency** — if batch crashes mid-run, resuming must check registry + Connect before re-creating a user

7. **SubCustomerIds** — always set equal to `fK_Customer` value

8. **STG.OPI_IRS_Site_Info** — existing table in SQL Server with TEID/site data. Seed IRS_TEID_REGISTRY from this at app launch.

---

*Document generated March 2026 | Ad Astra, Inc. | CONFIDENTIAL*
