# IRS PIN Management Tool — Master Reference Document
**Author:** Muhammad Maaz Ahmed | **Company:** Ad Astra, Inc. | **Updated:** March 2026  
**PRD:** v7.0 (IRS_PIN_Tool_PRD_v7.docx) | **Status:** Development Phase — Local Mock → QA → FastAPI → Streamlit

---

## ═══════════════════════════════════════════════════
## PART 1: LLM MASTER PROMPT (Copy this as system prompt)
## ═══════════════════════════════════════════════════

```
You are acting as a Principal AI/ML Engineer and Senior Data Engineer mentor for Muhammad Maaz Ahmed 
at Ad Astra, Inc. You are helping him build the IRS PIN Management Tool from scratch.

ROLE: Be decisive. One clear path. Think end-to-end. Provide runnable code. No brainstorming lists.

STACK: Python throughout.
- Phase 1: Local Python scripts with mock data (no UI, no server — just logic validation)
- Phase 2: Same scripts pointed at QA Connect APIs (connectapiqas.ad-astrainc.com)
- Phase 3: Wrap logic into FastAPI backend server
- Phase 4: Streamlit frontend connected to FastAPI

DEVELOPMENT ORDER — FOLLOW EXACTLY:
1. Local mock data — validate all logic with hardcoded/fake data, no real APIs
2. QA integration — point at connectapiqas.ad-astrainc.com, test with Markytech account
3. FastAPI server — expose all logic as REST endpoints
4. Streamlit UI — build 5 pages on top of FastAPI

KEY FILES TO INGEST (treat as ground truth):
- IRS_PIN_Tool_PRD_v7.docx — full product requirements, all API specs, all decisions
- IRS_PIN_Tool_Master.md — this file, full project context
- requesters_with_company_details_TEID.xlsx — 23,519 rows: TEID + Site Name + CustomerName (seed data)
- Requesters_List_all_IRS_Users_pins.csv — 32,489 rows: all IRS users with PINs across all 14 BODs
- Requesters_List.csv — 49 rows: recent active users sample
- IRS_All_Sites_Reference.xlsx — 2,246 named sites with TEID, max PIN, next PIN per BOD

DO NOT ask Maaz to repeat anything in this document. 
Retain all context. Be concise and executable.
When giving code, give complete runnable snippets, not pseudocode.
```

---

## ═══════════════════════════════════════════════════
## PART 2: FULL PROJECT CONTEXT (Ingest everything below)
## ═══════════════════════════════════════════════════

---

## 1. WHAT THIS IS

Ad Astra provides Over-the-Phone Interpretation (OPI) to IRS. Each IRS officer needs a unique 9-digit PIN in the Ad Astra Connect platform to authenticate when calling interpreters. Aysha El-Sibai (OPI team) does this manually — opens Connect, scrolls 35,000 rows, finds max PIN, adds 1, creates user. No automation, no audit trail.

We are building an internal web app that automates this entirely.

---

## 2. KEY PEOPLE

| Person | Role | Relevance |
|--------|------|-----------|
| Muhammad Maaz Ahmed | Developer (you) | Building everything |
| Vadim Petrov | Team Lead | Highly analytical. Expects proof, not assumptions |
| Aysha El-Sibai | OPI Team / SME | Does it manually today. Primary user |
| Backend Developer | Built the 3 APIs | APIs are live on QA and Prod |

---

## 3. PIN STRUCTURE — CRITICAL

```
9-digit PIN = [TEID 4 digits] + [SUFFIX 5 digits]

Example:  5485  +  27432  =  548527432
          TEID     suffix
```

- **TEID** = 4-digit Site ID code. PIN prefix. Source: input file or assigned by system.
- **SEID** = IRS Officer unique ID (e.g. `1GNKB`). Goes into `firstName` field in Connect ONLY. Has NOTHING to do with PIN generation.
- **Suffix** = MAX existing PIN for that TEID + 1. Deterministic. No randomness. No availability loop.
- **First PIN at new site** = `{teid}00001`. Example: TEID 5486 → 548600001.

---

## 4. THREE WORKFLOWS

| # | Trigger | Action |
|---|---------|--------|
| 1 | Contact Status = Add, SEID not in Connect | Create new user with calculated PIN |
| 2 | Contact Status = Deactivate | Call Update API to deactivate |
| 3 | Site ID blank in input | Assign new/existing TEID via API 2, then Workflow 1 |

---

## 5. FULL FLOW — STEP BY STEP (v7 CONFIRMED)

```
INPUT ROW
    │
    ▼
Step 0: BOD code → full customerName  [hardcoded lookup table in app]
        "TAS" → "US GSA IRS Taxpayer Advocate Service (TAS)"
    │
    ▼
Step A: GET /api/accounts/addresses/customer/{customerName}
        Returns: flat string array of all site names for that BOD
        ["IRS TAS Area 1, GRP1, Buffalo (130 South Elmwood Avenue)", ...]
        ★ Cache per BOD per batch — call once, reuse for all rows with same BOD
    │
    ▼
Step B: Fuzzy match IRS input site name → confirmed site name string
        Input: "Buffalo Group 1"
        Match: "IRS TAS Area 1, GRP1, Buffalo (130 South Elmwood Avenue)"
        Score ≥80% → auto-select (show to OPI team for confirmation)
        Score <80% → show dropdown of all strings, OPI team selects manually
    │
    ▼
Site ID present in input?
    │
    ├─ YES → skip to Step E (use Site ID directly as TEID)
    │
    └─ NO → Step C: GET /api/accounts/pin/max-teid/customer/{customerName}
                              ?siteName={confirmed site name string}
                  │
                  ├─ siteExists=true  → use existingTeid ──────────────┐
                  └─ siteExists=false → currentMaxTeid + 1 = new TEID ─┘
    │
    ▼
Step E: GET /api/accounts/pin/customer-teid/{customerName}/{teid}
        Returns: maxPinCode, fK_Customer, fK_Location
    │
    ▼
Step F: new_pin = int(maxPinCode) + 1
        If maxPinCode is null → new_pin = int(str(teid) + "00001")
    │
    ▼
Step G: POST /api/Accounts/Insert  (Connect — multipart/form-data)
        status="S" → success → store GUID
        status≠"S" → mark Failed, log response, continue next row
    │
    ▼
Step H: INSERT/UPSERT STG.IRS_PIN_REGISTRY
        Store: SEID, PIN, GUID, BOD, TEID, status, batch_id
END
```

---

## 6. THREE LIVE BACKEND APIs

All confirmed live. QA host: `connectapiqas.ad-astrainc.com`. Prod host: `appbe.ad-astrainc.com`.  
Swagger: `{host}/swagger/index.html`. All require `Authorization: Bearer {token}`.

### API 1 — Get Max PIN for a Site
```
GET /api/accounts/pin/customer-teid/{customerName}/{teid}
```
| | QA (Markytech/8178) | Prod (TAS/5485) |
|--|---------------------|-----------------|
| fK_Customer | 277 | 1219 |
| fK_Location | 13 | 3176 |
| maxPinCode | "8178388191" | "548527431" |

Response fields: `teid`, `accountName`, `fK_Customer`, `fK_Location`, `maxPinCode`

### API 2 — Check Site / Get Max TEID
```
GET /api/accounts/pin/max-teid/customer/{customerName}?siteName={string}
```
Response (site exists):
```json
{ "currentMaxTeid": null, "existingTeid": "5485", "accountName": "...", "siteExists": true, "errorMessage": null }
```
Response (new site):
```json
{ "currentMaxTeid": "5485", "existingTeid": null, "accountName": "...", "siteExists": false, "errorMessage": null }
```
⚠️ `siteName` is a **query param**, not path param.  
⚠️ Field names are camelCase: `siteExists`, `existingTeid`, `currentMaxTeid`.

### API 3 — Get All Site Names for a Customer
```
GET /api/accounts/addresses/customer/{customerName}
```
Response:
```json
{ "data": { "addresses": ["IRS TAS Area 1, GRP1, Buffalo (130 South Elmwood Avenue)", ...], "totalCount": 212 }, "payload": null }
```
⚠️ Returns **plain string array only**. No TEID, no coordinates, no structured data.  
⚠️ These strings are passed directly as `siteName` into API 2.

---

## 7. CONNECT API — AUTH + SEID SEARCH + INSERT + DEACTIVATE

### Auth
```
POST https://connectapiqas.ad-astrainc.com/api/accounts/token
Body: { "email": "...", "password": "...", "rememberMe": true }
Response: { "token": "<bearer_jwt>" }
```
Re-auth on any 401. Retry once. Store token in memory.  
QA credentials: `almaskhan@ad-astrainc.com` — in `.env` only, never hardcoded.

### SEID Lookup (Search existing user)
```
POST https://appbe.ad-astrainc.com/api/accounts/exports/filter/CONSUMER/0/?page={n}&items_per_page=50
Body: { "customers": [1219], "subAccounts": [], "status": ["ACTIVE"], "roles": [], "joinDate": null, "loginDate": null }
```
- Filter response where `firstName == SEID`
- Paginate: loop page=1 to `last_page`
- Use **exports** endpoint (not members) — only exports returns `pinCode`

### Create User (Insert)
```
POST https://connectapiqas.ad-astrainc.com/api/Accounts/Insert
Content-Type: multipart/form-data
```

**Full payload — every field:**
```python
payload = {
    # Dynamic fields
    "firstName": seid,                                    # IRS Officer SEID
    "lastName": f"{last_name} {first_name}",              # "KARALUS ERIKA"
    "email": f"{seid.lower()}.{last_name.lower()}.{first_name.lower()}@ad-astrainc.com",
    "pinCode": new_pin,                                   # integer
    "pinCodeString": str(new_pin),                        # string
    "fK_Customer": fk_customer,                           # from API 1
    "fK_Location": fk_location,                           # from API 1
    "SubCustomerIds": fk_customer,                        # same as fK_Customer

    # Fixed fields
    "fK_ServiceType": "SVC_COM",
    "serviceTypes": "SVC_COM",
    "fk_PreCallPolicy": 19,                               # QA confirmed. Prod TBD.
    "fK_DefaultNativeLanguage": None,                     # null — confirmed from live data
    "fK_DefaultTimeZone": "b9efba83-5fb3-11ef-8538-0291956bad29",  # Eastern Time
    "role": "User",
    "userType": "CONSUMER",
    "country": "United States",
    "city": "Jacksonville",
    "address": "400 West Bay Street",
    "state": "Florida",
    "postalCode": "32202",
    "latitude": 30.3269,
    "longitude": -81.6637,
    "code": "undefined",                                  # literal string "undefined"
    "isNewPasswordGenerate": True,
    "oPI_ShdTelephonic": True,                           # CONFIRMED true from live data
    "oPI_OndemandTelephonic": True,                      # CONFIRMED true from live data
    "setPassword": False,
    "accessBilling": False,
    "recieveAllEmails": False,                           # intentional typo — match exactly
    "recieveUserEmails": False,                          # intentional typo — match exactly
    "vRI_ShdVideoInteroreting": False,                   # intentional typo — match exactly
    "vRI_OndemandVideoInteroreting": False,              # intentional typo — match exactly
    "oSI_OnsiteConsecutive": False,
    "oSI_OnsiteSimultaneous": False,
    "oSI_OnsiteWhisper": False,
    "oSI_Onsite": False,
    "other_3rdPartyPlatform": False,
    "linguistType": 0,
    "payableType": 0,
    "password": "",
    "phoneNumber": "",
}
```
Success: `{ "status": "S", "text": "Successfully created", "result": "<guid>" }`  
Store `result` GUID → `STG.IRS_PIN_REGISTRY.CONNECT_GUID`

⚠️ **Email domain: `ad-astrainc.com` WITH hyphen.** Confirmed from live user data.  
⚠️ **Multiple intentional typos in field names** — copy exactly as shown above.

### Deactivate User
```
POST https://connectapiqas.ad-astrainc.com/api/accounts/Update
```
Key field: `code = <user GUID from search result>`  
Success: `{ "status": "S", "text": "Successfully deactivated" }`

---

## 8. BOD CODE → CUSTOMER NAME → fK_CUSTOMER LOOKUP TABLE

Hardcoded in app. Never changes unless IRS adds a new BOD.

```python
BOD_LOOKUP = {
    "TAS":     {"customerName": "US GSA IRS Taxpayer Advocate Service (TAS)",                                       "fk_customer": 1219},
    "FA":      {"customerName": "US GSA IRS TS Field Assistance (FA)",                                              "fk_customer": 1222},
    "SBSE":    {"customerName": "US GSA IRS Small Business Self-Employed (SBSE)",                                   "fk_customer": 1218},
    "AM":      {"customerName": "US GSA IRS TS Account Management (AM)",                                            "fk_customer": 1220},
    "CC":      {"customerName": "US GSA IRS Chief Counsel (CC)",                                                    "fk_customer": 1213},
    "CI":      {"customerName": "US GSA IRS Criminal Investigation (CI)",                                           "fk_customer": 1214},
    "TEGE":    {"customerName": "US GSA IRS Exempt Organizations & Government (TEGE)",                              "fk_customer": 1215},
    "LB&I":    {"customerName": "US GSA IRS Large Business & International (LB&I)",                                 "fk_customer": 1217},
    "EPSS":    {"customerName": "US GSA IRS TS Electronic Products & Services Support (EPSS)",                      "fk_customer": 1221},
    "RICS":    {"customerName": "US GSA IRS TS Return Integrity & Compliance Services (RICS)",                      "fk_customer": 1223},
    "SPEC":    {"customerName": "US GSA IRS TS Stakeholder Partnerships, Education & Communication (SPEC)",         "fk_customer": 1224},
    "FMSS":    {"customerName": "US GSA IRS Facilities Management & Security Services (FMSS)",                      "fk_customer": 1216},
    "APPEALS": {"customerName": "US GSA IRS Independent Office of Appeals",                                         "fk_customer": 1225},
    "MEDIA":   {"customerName": "US GSA IRS TS Media & Publications - Distribution",                                "fk_customer": 1226},
}
```

⚠️ APPEALS and MEDIA short codes need confirmation from Aysha — those are assumed codes.

---

## 9. INPUT FILE SPECIFICATION

Accepted: `.xlsx`, `.xls`, `.csv`. Match columns by header name (case-insensitive), not position.

| Column | Required | Notes |
|--------|----------|-------|
| BOD | Yes | Short code. e.g. TAS, CI, FA |
| Last Name | Yes | |
| First Name | Yes | |
| SEID | Yes | Primary key. Goes into `firstName` in Connect |
| Site ID | Conditional | 4-digit TEID. If blank → system resolves via API 2 |
| Site Name | Yes | Used in fuzzy match against API 3 results |
| 9-digit User PIN | Output | Empty on input. App fills after creation |
| Contact Status | Yes | Add = create. Deactivate = disable |

**Verified real input example:**
```
BOD=TAS | Last Name=KARALUS | First Name=ERIKA | SEID=1GNKB | Site ID=5485 | Site Name=Buffalo Group 1 | Status=Add
```
Resolves to: TEID=5485 → Site="IRS TAS Area 1, GRP1, Buffalo (130 South Elmwood Avenue)" → PIN=548527432

---

## 10. ROW PROCESSING PIPELINE

| Step | Action | Rule |
|------|--------|------|
| 1 | Parse & validate | Flag missing SEID/Name/Site Name as Error. Block row. |
| 2 | Duplicate SEID in batch | Process first occurrence only. Skip rest with reason shown. |
| 3 | SEID lookup in Connect | POST exports/filter. Paginate all pages. Filter firstName==SEID. |
| 4A | SEID not found | New user → full flow Steps 0→H |
| 4B | SEID found, same TEID | Mark "Already Exists". Skip. |
| 4B | SEID found, different TEID | Treat as new user → full flow |
| 5 | Contact Status = Deactivate | Call Update API with GUID from search |
| 6 | Write result | STG.IRS_PIN_REGISTRY regardless of success/failure |

---

## 11. DATABASE TABLES

### STG.IRS_PIN_REGISTRY
```sql
CREATE TABLE STG.IRS_PIN_REGISTRY (
    ID           INT IDENTITY PRIMARY KEY,
    SEID         VARCHAR(20)  UNIQUE NOT NULL,
    FIRST_NAME   VARCHAR(100),
    LAST_NAME    VARCHAR(100),
    BOD          VARCHAR(20),
    SITE_ID      VARCHAR(10),   -- TEID
    SITE_NAME    VARCHAR(200),
    PIN_9DIGIT   VARCHAR(9),
    CONNECT_GUID VARCHAR(50),   -- UUID from Insert result field
    STATUS       VARCHAR(20),   -- Active / Inactive / Pending / Failed
    BATCH_ID     VARCHAR(50),
    CREATED_BY   VARCHAR(100),
    CREATED_DT   DATETIME DEFAULT GETDATE(),
    UPDATED_DT   DATETIME
);
```

### STG.IRS_TEID_REGISTRY
```sql
CREATE TABLE STG.IRS_TEID_REGISTRY (
    TEID         VARCHAR(4)   UNIQUE NOT NULL,
    SITE_NAME    VARCHAR(200),
    SITE_ADDRESS VARCHAR(500),
    FK_CUSTOMER  INT,
    FK_LOCATION  INT,
    CREATED_DT   DATETIME DEFAULT GETDATE()
);
```

---

## 12. QA ENVIRONMENT — ALL CONFIRMED VALUES

| Field | QA Value | Prod Value |
|-------|----------|------------|
| Host | connectapiqas.ad-astrainc.com | appbe.ad-astrainc.com |
| Test account | Markytech | IRS BOD accounts |
| fK_Customer | 277 | From API 1 (e.g. 1219 for TAS) |
| fK_Location | 13 | From API 1 (e.g. 3176 for TAS/5485) |
| TEID tested | 8178 | 5485 |
| maxPinCode | 8178388191 | 548527431 |
| fK_DefaultNativeLanguage | null | null |
| fK_DefaultTimeZone | b9efba83-5fb3-11ef-8538-0291956bad29 | same |
| fk_PreCallPolicy | 19 | TBD — confirm with Vadim |

---

## 13. DEVELOPMENT PHASES — BUILD IN THIS ORDER

### Phase 1 — Local Mock (Start Here)
**Goal:** Validate all business logic with no real API calls.

What to build:
- File parser: read xlsx/csv, detect columns by header, validate rows
- Mock BOD lookup: use hardcoded `BOD_LOOKUP` dict
- Mock API 3: return hardcoded list of site name strings
- Fuzzy match engine: token-based matching, return score + matched string
- Mock API 2: return hardcoded `siteExists=True/False`
- Mock API 1: return hardcoded `maxPinCode`
- PIN calculator: `int(maxPinCode) + 1`, handle null case
- Mock Insert: print payload, return fake GUID
- Registry writer: write to local SQLite or CSV for now

Done when: Feed a 10-row test file → all rows process correctly → results CSV produced with PINs filled in.

---

### Phase 2 — QA Integration
**Goal:** Point Phase 1 logic at real QA APIs. Use Markytech account.

What changes:
- Replace mock API 3 with real `GET /addresses/customer/Markytech`
- Replace mock API 2 with real `GET /pin/max-teid/customer/Markytech?siteName=`
- Replace mock API 1 with real `GET /pin/customer-teid/Markytech/{teid}`
- Replace mock Insert with real `POST /api/Accounts/Insert` on QA
- Add token auth: `POST /api/accounts/token` → store token → re-auth on 401
- Connect to real SQL Server for registry writes

Done when: A file with 3 rows (one Add, one Deactivate, one blank TEID) processes correctly end-to-end against `connectapiqas.ad-astrainc.com`.

---

### Phase 3 — FastAPI Server
**Goal:** Expose all Phase 2 logic as REST endpoints.

Endpoints to build:
```
POST /upload              → parse file, return preview + validation
POST /process             → async batch, returns batch_id immediately
GET  /batch/{batch_id}    → poll status + per-row results
GET  /users/search?seid=  → search SEID in Connect
GET  /pins/resolve?customerName=&teid=   → proxy API 1
GET  /teid/resolve?customerName=&siteName= → proxy API 2
GET  /sites/list?customerName=           → proxy API 3 + cache
GET  /registry            → list STG.IRS_PIN_REGISTRY with filters
GET  /audit/batches       → all processed batches
```

Done when: All endpoints callable via Postman. Batch of 5 rows processes correctly.

---

### Phase 4 — Streamlit Frontend
**Goal:** Build 5 pages on top of FastAPI.

**Page 1: Upload & Process**
- File uploader (xlsx, xls, csv) + manual entry toggle
- Preview table with colour-coded rows: green=Valid, yellow=Warning (blank TEID), red=Error
- Duplicate SEID highlighted before processing
- Process button → async → live polling every 3s via `GET /batch/{id}`

**Page 2: Results**
- Row table: SEID | Name | TEID | PIN Assigned | Action | Status | Notes
- Badges: Created (green) | Deactivated (orange) | Already Exists (blue) | Skipped (yellow) | Failed (red)
- Download Results: original file + PIN column + Status column appended
- Retry Failed button

**Page 3: PIN Registry**
- Searchable `STG.IRS_PIN_REGISTRY` with filters (BOD, TEID, Status, Date)
- CSV export

**Page 4: TEID Manager**
- Table of `STG.IRS_TEID_REGISTRY`
- Add New Site form, edit existing

**Page 5: Audit Log**
- All batches: ID | File | Date | Operator | Total | Created | Failed
- Drill into batch for per-row detail

---

## 14. FILE REFERENCE — WHAT EACH FILE IS FOR

| File | What It Contains | When LLM Needs It |
|------|-----------------|-------------------|
| `IRS_PIN_Tool_PRD_v7.docx` | Full PRD — all API specs, flows, decisions | Always — ground truth |
| `IRS_PIN_Tool_Master.md` | This file | Always — context |
| `requesters_with_company_details_TEID.xlsx` | 23,519 rows: TEID + Site Name + CustomerName + PinCode | Phase 1 mock data. Phase 2 seed data for STG.IRS_TEID_REGISTRY |
| `Requesters_List_all_IRS_Users_pins.csv` | 32,489 rows: all IRS users, all 14 BODs, all PINs | Verify PIN ranges, understand structure |
| `Requesters_List.csv` | 49 rows: recent active users sample | Quick reference for field formats |
| `IRS_All_Sites_Reference.xlsx` | 2,246 named sites: TEID, site name, state, max PIN, next PIN | Phase 1 mock data reference |

### Key facts from data analysis:
- **PIN structure verified**: First 4 digits = TEID, last 5 = suffix. 100% match on 23,519 records.
- **TEID is always 4 digits** — confirmed across entire dataset.
- **fK_Customer per BOD confirmed** from live API response + CSV data cross-reference.
- **2,246 sites with names** + 237 unnamed legacy TEIDs (mostly old SBSE). Unnamed ones cannot be matched by name — only by direct TEID input.
- **Max PIN per TEID example**: TEID 5485 (TAS Buffalo) → max PIN 548527431 → next PIN 548527432.

---

## 15. ERROR HANDLING RULES

| Scenario | Action |
|----------|--------|
| Missing required field | Error badge in preview. Block row. Show exact field name. |
| Duplicate SEID in batch | Process first. Skip rest. Show reason. |
| SEID found, same TEID | Mark Already Exists. Skip Insert. |
| SEID found, different TEID | Treat as new user. Full flow. |
| Site ID blank | Auto-resolve via API 2 + API 3 fuzzy match |
| Fuzzy match score <80% | Show dropdown. Do not auto-proceed. |
| API 1/2/3 error | Mark row Failed. Log full response. Continue. |
| Connect Insert non-S | Mark Failed. Log full response. Continue. |
| Connect 401 | Re-auth. Retry once. If still 401 → pause batch, alert user. |
| Contact Status unrecognised | Warn. Best-guess: contains 'add' → Create, 'deactivat' → Deactivate |
| API 3 returns 0 strings | Flag BOD as unresolvable. Mark all rows for that BOD as Error. |

---

## 16. ARCHITECTURE

```
[OPI Team Browser]
      │ HTTPS
[Nginx on EC2]
      │
      ├── :8501 → [Streamlit Container]    UI only
      └── :8000 → [FastAPI Container]      All logic
                        │
                        ├── API 1/2/3 (connectapiqas / appbe)
                        ├── Connect Insert/Update (connectapiqas)
                        ├── Connect Auth + Search (appbe)
                        └── SQL Server (STG.IRS_PIN_REGISTRY, STG.IRS_TEID_REGISTRY)
```

**Docker Compose:**
```yaml
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
  frontend:
    build: ./frontend
    ports: ["8501:8501"]
    environment:
      API_URL: http://api:8000
  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
```

---

## 17. OPEN ITEMS

| # | Item | Owner | Blocking |
|---|------|-------|---------|
| 1 | Confirm BOD code for Appeals and Media in IRS files | Aysha | BOD lookup table |
| 2 | Production `fk_PreCallPolicy` value | Vadim / Aysha | Prod go-live only |

Everything else is resolved. Zero other blockers for development start.

---

## 18. CONFIRMED DECISIONS — ALL RESOLVED

| # | Decision | Resolution |
|---|----------|-----------|
| 1 | PIN generation method | DB-driven. API 1 → maxPinCode + 1. No randomness. |
| 2 | GET /pincode needed? | No. Removed. |
| 3 | Availability loop needed? | No. Removed. Deterministic. |
| 4 | fK_Customer/fK_Location source | API 1 response. Dynamic per site. |
| 5 | STG.IRS_ACCOUNT_MAP needed? | No. Removed. |
| 6 | PIN prefix — TEID or SEID? | TEID always. SEID = firstName only. |
| 7 | Email domain | ad-astrainc.com WITH hyphen. Confirmed live. |
| 8 | fK_DefaultNativeLanguage | null. Confirmed on all live IRS users. |
| 9 | oPI_ShdTelephonic | true. Confirmed from live active user data. |
| 10 | oPI_OndemandTelephonic | true. Confirmed from live active user data. |
| 11 | fK_Customer for TAS | 1219. (277 = Markytech QA only) |
| 12 | fK_Location populated? | Yes. 3176 for TAS/5485. 13 for Markytech/8178. |
| 13 | API 3 response structure | Plain string array only. No TEID or coordinates. |
| 14 | API 2 siteName parameter | Query param, not path param. |
| 15 | API 2 response fields | camelCase: siteExists, existingTeid, currentMaxTeid. |
| 16 | Site name matching | Token-based fuzzy. ≥80% auto. <80% manual dropdown. |
| 17 | API 3 caching | Once per BOD per batch. Do not call per row. |
| 18 | SEID search endpoint | exports (not members). Only exports returns pinCode. |
| 19 | Default fallback address | 400 West Bay Street, Jacksonville, FL 32202. |
| 20 | Lat/Long default | 30.3269, -81.6637 (Jacksonville HQ). |
| 21 | Frontend framework | Streamlit. |
| 22 | Backend framework | FastAPI. |
| 23 | Hosting | AWS EC2 + Docker + Nginx. |
| 24 | Development order | Local mock → QA → FastAPI → Streamlit. |

---

*Document generated March 2026 | Ad Astra, Inc. | CONFIDENTIAL*  
*Cross-reference: IRS_PIN_Tool_PRD_v7.docx for full technical specifications*
