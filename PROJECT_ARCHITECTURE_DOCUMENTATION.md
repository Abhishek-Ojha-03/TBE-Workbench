# Technical Bid Evaluation (TBE) Workbench
## Complete Backend Architecture, Implementation & Verification Guide

---

## 1. Executive Summary & Purpose

The **Technical Bid Evaluation (TBE) Workbench** is an automated, AI-augmented engineering compliance platform designed for utility procurement divisions (e.g., BSES Rajdhani / Yamuna Power Limited).

In commercial and government tenders, technical bid evaluation involves cross-referencing hundreds of pages of technical specifications, Qualifying Requirements (QR), Guaranteed Technical Particulars (GTP), and third-party laboratory test reports across competing bidders. Doing this manually is time-consuming, prone to human error, and vulnerable to trap clauses (e.g., blanket "NIL Deviation" declarations masking missing test certificates).

### Core Capabilities:
1. **Dynamic Ingestion (Zero Hardcoding):** Ingests raw tender specifications (PDF) for *any* commodity (electrical switchgears, IT hardware/laptops, civil supplies, or maintenance contracts) and automatically extracts structured requirements into an immutable baseline.
2. **Multi-Bidder Dossier Processing:** Ingests complete PDF dossiers (technical offers, test certificates, financial sheets, GTP schedules).
3. **Dual-Tier Hybrid OCR & Search:** Digital text extraction via PyMuPDF + scan OCR via Gemini Vision, indexed in SQLite FTS5 with BM25 full-text search.
4. **Deterministic Anti-Hallucination Guardrail (The Golden Rule):** AI can *only* suggest `Complied` if backed by an exact, verbatim quote present on a cited page. A two-pass algorithmic quote verification layer rejects hallucinations.
5. **Parameter Match Accuracy Matrix:** Quantitative scoring displaying exact requirement parameters vs. bidder offered values, computing a real-time compliance percentage ($100\%$ match, $0\%$ deviation).
6. **Human-in-the-Loop & Audit Trail:** Dedicated interfaces for engineers to confirm, override (with mandatory reasons), and log every interaction chronologically.
7. **Utility Deliverables:** One-click generation of formatted `.xlsx` working matrices, official `.docx` Minutes of Meeting (MOM), and Technical Evaluation Reports (TER).

---

## 2. End-to-End System Architecture

```
[ Tender Specification (PDF) ]       [ Bidder Submissions (PDFs) ]
             │                                      │
             ▼                                      ▼
    ┌─────────────────┐                    ┌─────────────────┐
    │  PyMuPDF + LLM  │                    │  PyMuPDF + LLM  │
    │  Dual-Tier OCR  │                    │  Dual-Tier OCR  │
    └────────┬────────┘                    └────────┬────────┘
             │                                      │
             ▼                                      ▼
    ┌─────────────────┐                    ┌─────────────────┐
    │ Spec Extractor  │                    │  SQLite FTS5    │
    │ (Structured     │                    │  Full-Text      │
    │  JSON Schema)   │                    │  BM25 Index     │
    └────────┬────────┘                    └────────┬────────┘
             │                                      │
             ▼                                      ▼
    ┌─────────────────┐                    ┌─────────────────┐
    │ Baseline Store  │───────────────┐    │ Ranked Search   │
    │ (v1, v2 Audit)  │               │    │ (Stop-word      │
    └─────────────────┘               │    │  Filtered)      │
                                      │    └────────┬────────┘
                                      │             │
                                      ▼             ▼
                           ┌───────────────────────────────┐
                           │      Gemini 3.5 LLM           │
                           │   Bidder Verification Engine  │
                           └──────────────┬────────────────┘
                                          │
                                          ▼
                           ┌───────────────────────────────┐
                           │   Algorithmic Quote Checker   │
                           │   (Strict Verbatim Validation)│
                           └──────────────┬────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         [ Complied (100%) ]                           [ Needs Human Review ]
                  │                                               │
                  └───────────────────────┬───────────────────────┘
                                          ▼
                           ┌───────────────────────────────┐
                           │  Interactive Streamlit UI     │
                           │  - Live Excel Grid & KPIs     │
                           │  - Direct Cell Updates        │
                           │  - Formal Letter Preview      │
                           │  - Docx MOM & TER Generation  │
                           └───────────────────────────────┘
```

---

## 3. Directory Structure & Key Modules

```
TBE 2/
├── ai/                         # AI & LLM Integration Layer
│   ├── client.py               # Google GenAI client initialization & model resolution
│   ├── extractor.py            # Specification parsing & JSON requirement extraction
│   ├── verifier.py             # Core verification engine with candidate retrieval
│   ├── clarification_service.py# AI drafting of formal clarification letters & delta re-check
│   ├── prompts.py              # Strict system prompts with anti-trap guardrails
│   └── schemas.py              # Pydantic validation models for structured outputs
├── db/                         # Database & Persistence Layer
│   ├── connection.py           # SQLAlchemy SQLite connection & session management
│   ├── models.py               # Database ORM models (Tender, Baseline, Requirement, Finding, etc.)
│   ├── repository.py           # CRUD operations and data access functions
│   ├── baseline_service.py     # Versioned baseline freezing and retrieval
│   └── audit_service.py        # Complete immutable audit log (Confirm/Override)
├── reading/                    # Document Processing & Search Layer
│   ├── ingest.py               # Dual-tier PDF ingestion (PyMuPDF digital + Gemini Vision scan)
│   └── fts_indexer.py          # SQLite FTS5 BM25 search indexer with stop-word filtering
├── rules/                      # Deterministic Business Rules
│   ├── quote_checker.py        # Two-pass verbatim quote verification algorithm
│   └── rule_engine.py          # Disqualification rules (QR failure, blacklisting, etc.)
├── outputs/                    # Export & Deliverable Generators
│   ├── excel_generator.py      # Working Excel builder using openpyxl & template mapping
│   └── docx_generator.py       # Utility MOM and Technical Evaluation Report (.docx) generator
├── templates/                  # Base document templates (.xlsx, .docx)
├── ui/                         # Streamlit User Interface
│   ├── app.py                  # Main navigation & application router
│   ├── home_view.py            # Screen 1: Tender dashboard & status overview
│   ├── baseline_view.py        # Screen 2: Specification parsing & baseline approval
│   ├── bidder_view.py          # Screen 4: Bidder registry & document upload
│   ├── working_excel_view.py   # Screen 5: Core TBE Matrix, Parameter Accuracy & Human Verification
│   ├── review_view.py          # Screen 6: Detailed finding review with side-by-side scan view
│   └── reports_view.py         # Screen 7/8: Letter preview, MOM/TER download, Tender completion
├── tests/                      # Automated Test Suite (18 tests covering all 17 workflow steps)
└── tbe_workbench.db            # Local SQLite database (includes FTS5 virtual tables)
```

---

## 4. Deep Dive: Backend Implementation Details

### A. Dynamic Specification Extraction (Zero Hardcoded Parameters)
- **Files:** `ai/extractor.py`, `ai/schemas.py`
- **How it works:** When a tender specification is uploaded, the document is sent page-by-page to Gemini with structured output validation (`response_schema=SpecificationExtractionResult`).
- **Capability:** Extracts technical parameters, numerical ratings, units, Qualifying Requirements (QR), and mandatory submissions dynamically. The same pipeline works without code changes for:
  - $11\text{ kV}$ Switchgears ($25\text{ kA}$, $50\text{ Hz}$, $\text{IP }4\text{X}$)
  - Commercial Laptops ($16\text{ GB RAM}$, $1\text{ TB SSD}$, Intel Core i7)
  - Commercial Tyres (Radial, $295/80\text{ R}22.5$, Load Index 152)

### B. Dual-Tier PDF Ingestion (Fast Digital + Vision OCR)
- **File:** `reading/ingest.py`
- **How it works:**
  1. *Tier 1 (Digital Text):* Uses PyMuPDF (`fitz`) to extract native text in milliseconds.
  2. *Tier 2 (Scanned Pages):* If extracted text is under 40 characters (scanned test reports, stamped certificates), the page is rendered as an image and processed via Gemini Vision.
  3. All extracted text is indexed into SQLite FTS5 for rapid local retrieval.

### C. Candidate Retrieval & Stop-Word Filtering
- **File:** `reading/fts_indexer.py`
- **Challenge Solved:** Boilerplate clauses (e.g., *"The equipment shall comply with the following technical parameters: Rated frequency: 50 Hz"*) previously diluted BM25 scoring with words like `the`, `shall`, `equipment`. These generic words appear on every page, causing irrelevant documents to rank higher than the actual Guaranteed Technical Particulars (GTP).
- **Solution:** A two-stage tokenizer:
  1. **Stage 1 — Extract all tokens** from the requirement clause using a simple regex: `re.findall(r'[a-zA-Z0-9]+', query_text)`. This is fully dynamic and domain-agnostic.
  2. **Stage 2 — Remove generic English stop words** (e.g. `the`, `shall`, `equipment`, `comply`, `following`, `parameters`). This list contains only standard grammar/filler words applicable to *any* language and *any* domain.

> **Nothing about the actual technical values is hardcoded.** The tokens `50`, `hz`, `25`, `ka`, `ip`, `4x`, `110`, `dc` are not predefined anywhere — they are parsed dynamically at runtime from whatever the tender clause says. This means the same code automatically handles:
> - Electrical equipment: extracts `25 kA`, `50 Hz`, `IP 4X`, `110 V DC`
> - Laptop tenders: extracts `16 GB`, `512 GB`, `i7`
> - Tyre tenders: extracts `295`, `80`, `R22`
>
> The only hardcoded part is the generic English stop-word list — the same standard technique used by Google, Elasticsearch, and all major search engines to remove noise words that carry no search value.

### D. Anti-Hallucination Verification & Quote Verification Algorithm
- **Files:** `rules/quote_checker.py`, `ai/verifier.py`
- **The Golden Rule:** The AI cannot mark a clause as `Complied` without supplying an exact verbatim quote and page reference.
- **Verification Logic:**
  1. Strict string search confirms the quote exists on the specified page.
  2. Normalized fallback handles minor OCR character artifacts or non-breaking spaces.
  3. If the quote cannot be verified in the submitted documents, the status automatically degrades to `Needs Human Review`.

### E. Parameter Match Accuracy Matrix
- **File:** `ui/working_excel_view.py`
- **Calculation:**
  $$\text{Parameter Accuracy (\%)} = \left( \frac{\text{Complied Parameters}}{\text{Total Evaluated Parameters}} \right) \times 100$$
- **Display:** Executive KPI cards (Accuracy %, Complied, Not Complied, Needs Review) plus per-clause color badges and quoted values.

### F. Official Clarification Management & Delta Re-Verification
- **Files:** `ai/clarification_service.py`, `ui/reports_view.py`
- **Formal Letter Preview:** Renders an executive letterhead card parsing all markdown cleanly, avoiding raw asterisks or formatting symbols for clients.
- **Delta Re-Verification:** When a clarification response PDF is uploaded, only affected findings are flagged (`needs_recheck = True`) and re-evaluated, keeping unaffected rows and audit history intact.

---

## 5. Complete 17-Step Workflow & Working of the System

This section explains the complete operational workflow of the TBE Workbench — **what happens in each step, who does it, what code runs, and what the output is.**

---

### PHASE 1 — TENDER SETUP

---

#### Step 1 — Create Tender (DB Setup)
**Who:** Procurement Engineer  
**Where:** Screen 1 — Home Dashboard (`ui/home_view.py`)  
**What happens:**
- Engineer creates a new tender by entering the **NIT Number** and **Description** (e.g., "Supply of 11 kV VCBs, NIT-BSES-VCB-2026-LIVE").
- The system creates a `Tender` record in SQLite (`db/models.py`) with status `open`.
- The tender is immediately visible on the Home Dashboard with its status card.

**Code:** `db/repository.py → create_tender()`, `db/models.py → Tender`  
**Output:** A new tender row saved in database, ready for specification upload.

---

#### Step 2 — Upload & AI-Extract Tender Specification
**Who:** Engineer uploads PDF; AI processes it automatically  
**Where:** Screen 2 — Specification Upload (`ui/specification_view.py`)  
**What happens:**
1. Engineer uploads the Tender Specification PDF (e.g., BSES Equipment Technical Specification).
2. **Dual-Tier Ingestion** begins (`reading/ingest.py`):
   - Every page is read by **PyMuPDF** first (digital text, instant).
   - If a page has fewer than 40 characters of text, it is a **scanned image** → Gemini Vision reads it.
   - All page text is stored in the `Pages` table and indexed in **SQLite FTS5**.
3. **AI Extraction** runs (`ai/extractor.py`):
   - Each page is sent to Gemini with a structured schema prompt (`ai/prompts.py → SPEC_EXTRACTION_PROMPT`).
   - Gemini identifies: Technical Requirements, Qualification Requirements (QR), Mandatory Documents, Standards.
   - Output is validated against `SpecificationExtractionResult` Pydantic schema (`ai/schemas.py`).
4. All extracted requirements are saved as `Requirement` records linked to **Baseline Version 1**.

**Code:** `reading/ingest.py`, `ai/extractor.py`, `ai/prompts.py`, `db/baseline_service.py`  
**Output:** Structured list of all clauses, QR items, and mandatory documents — **completely dynamic, zero hardcoded parameters**.

---

#### Step 3 — Engineer Reviews & Approves Baseline
**Who:** Lead Engineer  
**Where:** Screen 3 — Requirements Baseline (`ui/baseline_view.py`)  
**What happens:**
1. All extracted requirements are shown in an **editable grid** (`st.data_editor`).
2. QR (Qualifying Requirements) rows are shown first, highlighted in gold.
3. Engineer can:
   - Edit clause text or clause numbers.
   - Check/uncheck a row as a Qualification Requirement.
   - Mark rows as N/A (not applicable to this tender).
   - Add or remove rows dynamically.
4. Clicking **"Save as New Version"** creates **Baseline Version 2** while preserving Version 1 as history.
5. The approved baseline is **immutably frozen** — no AI evaluation runs against an unapproved baseline.

**Code:** `db/baseline_service.py → save_baseline_edits()`, `db/models.py → BaselineVersion`  
**Output:** Approved, versioned requirements baseline that all bidder evaluation runs against.

---

#### Step 4 — Register Bidders
**Who:** Engineer  
**Where:** Screen 3 (Tab: Bidder Setup) (`ui/baseline_view.py`)  
**What happens:**
- Engineer adds bidder names (e.g., "ABC Switchgear", "PQR Power", "XYZ Electricals").
- Each bidder gets a `Bidder` record in the database with initial status `Pending`.
- Bidders can be removed before evaluation begins.

**Code:** `db/baseline_service.py → add_bidder()`, `db/models.py → Bidder`  
**Output:** Bidder registry ready for document upload.

---

### PHASE 2 — BIDDER DOCUMENT PROCESSING

---

#### Step 5 — Upload & Ingest Bidder Documents
**Who:** Engineer uploads PDFs  
**Where:** Screen 5 — TBE Working Excel (`ui/working_excel_view.py`)  
**What happens:**
- Engineer uploads all PDFs for one bidder at a time (Technical Offer, Deviation Sheet, GTP Schedule, Type Test Reports, Financial Statements, QAP, etc.).
- Each PDF goes through the same **Dual-Tier Ingestion** as the specification:
  - Digital text → PyMuPDF.
  - Scanned certificates → Gemini Vision OCR.
  - All pages indexed into **SQLite FTS5** under the bidder's ID.
- `Document` and `Page` records are created and linked to the bidder.

**Code:** `reading/ingest.py → ingest_pdf_document()`, `reading/fts_indexer.py`  
**Output:** All bidder pages stored and searchable. Ready for AI verification.

---

#### Step 6 — Generate Working TBE Excel (Matrix Template)
**Who:** System (auto-generated on demand)  
**Where:** Screen 5 (`ui/working_excel_view.py`)  
**What happens:**
- The system opens a pre-built `.xlsx` template (`templates/`).
- It fills in: Tender metadata, QR requirements (gold rows first), Technical requirements, one bidder column group per bidder (Offered Value | Compliance Status | Evidence/Remarks).
- Any existing evaluation findings already in the database are pre-filled into cells.

**Code:** `outputs/excel_generator.py → WorkingExcelGenerator`, `templates/make_template.py`  
**Output:** A structured `.xlsx` TBE Working Matrix ready for download or printing.

---

### PHASE 3 — AI-POWERED BIDDER EVALUATION (The Core Engine)

---

#### Step 7 — AI Verification Engine (One Cell at a Time)
**Who:** System — Gemini LLM with Algorithmic Safety Layer  
**Where:** Triggered by "Run AI Verification" button (`ui/working_excel_view.py`)  
**What happens (for EACH requirement × EACH bidder cell):**

**Sub-step 7a — Candidate Page Retrieval (FTS5 Search):**
1. Take the requirement's clause text (e.g., *"Rated short circuit breaking current: 25 kA for 3 seconds"*).
2. Tokenize it — strip generic English stop words (`the`, `shall`, `equipment`).
3. Search the bidder's FTS5 index using BM25 ranking.
4. Retrieve Top-5 most relevant pages from bidder documents.

**Sub-step 7b — Gemini Evaluation:**
1. The 5 candidate page texts are assembled into a structured prompt (`ai/prompts.py → BIDDER_VERIFICATION_PROMPT`).
2. The prompt includes strict rules:
   - **Golden Rule:** AI can ONLY suggest `Complied` with an exact verbatim quote.
   - **Anti-Trap Guard:** A blanket "NIL Deviations" statement is NOT proof of compliance for specific parameters.
3. Gemini returns a structured JSON: `{ status, document, page, quote, reason }`.
4. Output is validated by Pydantic schema (`ai/schemas.py → VerificationFinding`).

**Sub-step 7c — Algorithmic Quote Verification (Anti-Hallucination Layer):**
1. The system looks up the exact page and document Gemini cited.
2. **Pass 1:** Strict string search — is the exact quote present in the page text?
3. **Pass 2 (Fallback):** Normalized check — strip OCR artifacts, collapse whitespace, lowercase both sides and check again.
4. **If quote not found on the cited page → Status forced to `Needs Human Review`** regardless of what Gemini said.

**Sub-step 7d — Finding & Evidence Saved:**
- A `Finding` record is updated with the AI's suggested status.
- An `Evidence` record is created with the cited quote, document name, and page number.

**Code:** `ai/verifier.py`, `reading/fts_indexer.py`, `rules/quote_checker.py`, `ai/prompts.py`  
**Output:** Every cell in the TBE matrix has a status — `Complied` / `Not Complied` / `Needs Human Review` — each backed by a verifiable quote and page citation.

---

#### Step 8 — Deterministic Rule Engine (Qualification Verdict)
**Who:** System (automatic, no AI)  
**Code:** `rules/rule_engine.py`  
**What happens immediately after Step 7:**
- The rule engine scans all `Finding` rows for a bidder and applies deterministic business logic:
  - **Any row `Not Complied`** → Bidder status = `Not Qualified`
  - **Any row `Needs Human Review`** → Bidder status = `Pending`
  - **All rows `Complied` or `N/A`** → Bidder status = `Qualified`
- Bidder's `final_status` in the database is updated.
- **No AI involvement here** — this is pure Python business logic.

---

### PHASE 4 — HUMAN REVIEW & AUDIT MANAGEMENT

---

#### Step 9 — Engineer Review, Confirm, or Override
**Who:** Lead Engineer  
**Where:** Screen 6 — Verification Review (`ui/review_view.py`)  
**What happens:**
- Every finding is shown as an expandable card with:
  - Full requirement text.
  - AI recommendation badge (green / red / amber).
  - The exact verbatim evidence quote.
  - The cited page number.
  - If the page was Vision-OCR'd, the original page scan image is shown side-by-side.
- Engineer has 4 action buttons per finding:
  1. **✅ Confirm** — Accepts AI's suggestion. Audit log entry written.
  2. **🔄 Override** — Changes status. A mandatory written reason is required before saving.
  3. **📬 Request Clarification** — Flags the row for a formal clarification letter to the bidder.
  4. **⚠️ Flag for Review** — Marks the row for a secondary committee review.

**Every action writes an immutable row to `AuditLog`:**
```
who | what_changed | old_value | new_value | reason | timestamp
```

**Code:** `db/audit_service.py → confirm_finding(), override_finding(), flag_for_review()`  
**Output:** All findings confirmed by a named engineer. Full regulatory audit trail captured.

---

#### Step 10 — Parameter Match Accuracy Matrix (Live KPI Dashboard)
**Who:** Auto-computed, visible on Screen 5  
**Where:** `ui/working_excel_view.py`  
**What happens:**
- After verification, the evaluation grid shows 4 real-time KPI cards:
  - **Parameter Match Accuracy %** = `(Complied ÷ Total) × 100`
  - **Complied count** (100% parameter match)
  - **Not Complied count** (0% match — deviation confirmed)
  - **Needs Review count** (pending)
- The full matrix table shows: Specification Requirement | Bidder Offered Quote | Status (color-coded) | Parameter Accuracy Badge.

---

### PHASE 5 — CLARIFICATION & DELTA RE-VERIFICATION

---

#### Step 11 — Draft Official Clarification Letter
**Who:** Engineer triggers, Gemini drafts  
**Where:** Screen 7 & 8 (`ui/reports_view.py`)  
**What happens:**
- Engineer selects a bidder. System lists all flagged/review items.
- Engineer clicks "Draft Official Clarification Letter via Gemini".
- `ai/clarification_service.py → generate_clarification_letter()` calls Gemini to compose a formal utility-grade letter addressing each flagged clause with specific query points.
- The letter is displayed in two views:
  - **👁️ Formal Letter Preview:** Clean rendered letterhead — no raw markdown symbols.
  - **✏️ Edit Letter Content:** Editable raw text for final customization.

---

#### Step 12 — Upload Clarification Response & Delta Re-Verification
**Who:** Engineer uploads new PDF; System re-verifies selectively  
**What happens:**
1. Engineer uploads the bidder's clarification response PDF.
2. The new PDF is ingested and indexed into FTS5.
3. **ONLY the rows originally flagged** have `needs_recheck = True` set.
4. `recheck_flagged_findings()` runs AI verification **exclusively on those affected rows** — all other cells are untouched.
5. Old audit trail and previous results are preserved in `AuditLog`.

**Code:** `ai/clarification_service.py → handle_clarification_response(), recheck_flagged_findings()`  
**Output:** Targeted re-evaluation of only the queried clauses. Full audit continuity maintained.

---

### PHASE 6 — OFFICIAL DELIVERABLES & COMPLETION

---

#### Step 13 — Generate Official TBE Working Excel Download
- Full evaluation matrix exported as `.xlsx` with proper formatting, color coding, bidder column groups, and evidence citations.

#### Step 14 — Generate TBE Minutes of Meeting (.docx)
- Formal MOM with committee members, meeting venue, AI-synthesized proceedings summary, and qualification outcomes table.

#### Step 15 — Generate Technical Evaluation Report (.docx)
- Full TER with cover page, executive summary, detailed clause-by-clause matrix, and final qualification recommendation.

#### Step 16 — Complete & Archive Tender
- Tender status updated to `completed` in the database.
- The tender moves to read-only archived status on the Home Dashboard.
- No further edits permitted — the evaluation baseline is permanently locked.

---

### Summary Workflow Diagram (17 Steps)

```
TENDER SETUP
├── Step 1 → Create Tender (NIT No + Description)
├── Step 2 → Upload Specification PDF → Dual-Tier OCR → AI Extraction → Baseline v1
├── Step 3 → Engineer Reviews & Approves Baseline (edit clauses, QR flags, N/A marks)
└── Step 4 → Register Bidders

BIDDER PROCESSING
├── Step 5 → Upload Bidder PDFs → Dual-Tier OCR → FTS5 Index
└── Step 6 → Generate Working TBE Excel Template

AI EVALUATION (Core Engine)
├── Step 7 → For each (Requirement × Bidder):
│            ├── FTS5 BM25 Search → Top-5 Candidate Pages
│            ├── Gemini Evaluates with Anti-Trap Prompt
│            └── Algorithmic Quote Verification → Save Finding + Evidence
└── Step 8 → Rule Engine → Bidder Qualification Verdict

HUMAN REVIEW
├── Step 9 → Engineer Reviews Each Finding Card
│            ├── Confirm AI Suggestion → Audit Log
│            ├── Override with Mandatory Reason → Audit Log
│            └── Flag for Clarification
└── Step 10 → Live Parameter Accuracy Matrix Dashboard

CLARIFICATION LOOP
├── Step 11 → Draft Formal Clarification Letter (Gemini) → Clean Preview
└── Step 12 → Upload Response → Delta Re-Verify ONLY Affected Rows

DELIVERABLES
├── Step 13 → Download TBE Working Excel (.xlsx)
├── Step 14 → Download Minutes of Meeting (.docx)
├── Step 15 → Download Technical Evaluation Report (.docx)
└── Step 16 → Complete & Archive Tender (Read-Only Lock)
```

---

## 6. Verification & Test Evidence

All 18 automated end-to-end tests pass cleanly:

| Test Module | Coverage / Workflow Activity | Result |
|-------------|------------------------------|:------:|
| `test_db_step1.py` | Database schema initialization & table relations | ✅ Passed |
| `test_home_step2.py` | Tender creation, listing & status lifecycle | ✅ Passed |
| `test_reading_step3.py` | Dual-tier PyMuPDF and scan OCR ingestion | ✅ Passed |
| `test_extractor_step4.py` | Dynamic specification extraction & schema validation | ✅ Passed |
| `test_baseline_step5.py` | Baseline versioning (v1, v2) & approval freezing | ✅ Passed |
| `test_excel_step6.py` | Template-based openpyxl generation & cell mapping | ✅ Passed |
| `test_verifier_step7.py` | Gemini verification & quote checking | ✅ Passed |
| `test_rules_step8.py` | Disqualification rules, QR checks & anti-trap guards | ✅ Passed |
| `test_audit_step9.py` | Confirm, override, reason tracking & audit logging | ✅ Passed |
| `test_clarification_step10.py` | Letter drafting, response ingestion & delta re-check | ✅ Passed |
| `test_deliverables_step11.py` | Full MOM and Technical Evaluation Report (.docx) exports | ✅ Passed |

**Command to run test suite:**
```powershell
python -m pytest tests/
```
*(Result: 18 passed in ~19 seconds)*

---

## 6. How to Run the Application

### Prerequisites
- Python 3.10+
- Google Gemini API Key configured in `.env` (`GEMINI_API_KEY=...`)

### Launch Command
```powershell
python -m streamlit run ui/app.py
```

### Quick Walkthrough for Reviewers:
1. **Screen 1 (Home):** Select or create a tender (e.g. `NIT-BSES-VCB-2026-LIVE`).
2. **Screen 2 (Baseline):** Review dynamically extracted clauses and approve Baseline v1.
3. **Screen 4 (Bidders):** Check registered bidders (ABC Switchgear, PQR Power, XYZ Electricals).
4. **Screen 5 (TBE Working Excel):**
   - Click *Run AI Verification* to see the **Parameter Match Accuracy Matrix** and live evaluation grid.
   - Use *Direct Engineer Human Verification* to update cell statuses.
   - Click *Download Working Excel* to verify un-truncated requirement texts and cell mappings.
5. **Screen 7 & 8 (Reports & Clarifications):**
   - Select a bidder and click *Draft Official Clarification Letter* to view the clean **Formal Letter Preview**.
   - Generate official `.docx` Minutes of Meeting and Technical Evaluation Report.

