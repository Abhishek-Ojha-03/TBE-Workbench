# TBE Workbench — User Guide
### Technical Bid Evaluation Platform | Step-by-Step Usage Manual

---

## What Is This Platform?

The **TBE Workbench** is a digital tool that helps engineers evaluate technical bids from suppliers/vendors in a tender. Instead of manually reading hundreds of pages of documents and cross-checking each requirement one by one, this platform:

- Automatically reads and understands the tender specification.
- Evaluates each bidder's submitted documents against every requirement.
- Generates official Excel matrices, Minutes of Meeting, and Technical Evaluation Reports.

> **Who uses it?**
> Equipment Engineers, Procurement Officers, and Technical Evaluation Committees in organizations like BSES, Power Distribution Companies, PSUs, or any organization that runs tenders for equipment, services, or supplies.

---

## Complete Workflow Flowchart

```
┌──────────────────────────────────────────────────────┐
│                  START: Open the App                 │
│          http://localhost:8501                       │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 1 — Home Screen                                │
│  Create a new tender OR select an existing one       │
│  Enter: Tender Name / Description + NIT Number       │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 2 — Specification Screen                       │
│  Upload the Tender Specification PDF                 │
│  Click: "Process Specification with AI"              │
│  → AI reads every page, extracts all requirements    │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 3 — Requirements & Setup Screen                │
│  Tab 1: Review extracted requirements                │
│    → Check QR flags, edit clause text, mark N/A      │
│    → Click "Save as New Version" to approve          │
│  Tab 2: Review mandatory documents list              │
│  Tab 3: Add bidder names (e.g. ABC Switchgear)       │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 4 — TBE Working Excel Screen                   │
│  For each bidder:                                    │
│    → Upload all their PDFs (GTP, Tech Offer,         │
│      Test Reports, Balance Sheets, etc.)             │
│    → Click "Ingest Documents"                        │
│    → Click "Run AI Verification"                     │
│  AI evaluates EVERY requirement vs EVERY bidder      │
│  → Results appear in the Evaluation Matrix           │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 5 — Verification Results Screen                │
│  Review every requirement card:                      │
│    ✅ Confirm AI suggestion                          │
│    🔄 Override with your own decision + reason       │
│    📬 Request Clarification from bidder              │
│    ⚠️ Flag for committee review                      │
└───────────────────────┬──────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
  ┌─────────────────┐   ┌──────────────────────┐
  │ All items       │   │ Some items flagged   │
  │ reviewed ✅     │   │ for clarification    │
  └────────┬────────┘   └──────────┬───────────┘
           │                       │
           │            ┌──────────▼───────────┐
           │            │ STEP 6 — Reports &   │
           │            │ Completion Screen    │
           │            │ Draft Clarification  │
           │            │ Letter via AI        │
           │            │ → Preview clean copy │
           │            │ → Send to bidder     │
           │            │ → Upload their reply │
           │            │ → Re-verify ONLY     │
           │            │   affected rows      │
           │            └──────────┬───────────┘
           │                       │
           └──────────┬────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────┐
│  STEP 7 — Generate Official Deliverables             │
│  → Download Working Excel (.xlsx)                    │
│  → Generate Minutes of Meeting (.docx)               │
│  → Generate Technical Evaluation Report (.docx)      │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│  STEP 8 — Mark Tender as Completed                   │
│  Click "Complete & Archive Tender"                   │
│  → Tender is locked in read-only mode                │
│  → Appears in "Completed Tenders" on Home Screen     │
└──────────────────────────────────────────────────────┘
```

---

## Screen-by-Screen Guide

---

### 🏠 Home Screen

**What you see:** A dashboard with two tabs — "Active Tenders" and "Completed Tenders".

**What to do:**

1. To start a new evaluation, fill in:
   - **Tender Description** — e.g., *"Supply of 11 kV Vacuum Circuit Breakers"*
   - **NIT Number** — e.g., *"NIT-BSES-VCB-2026-001"*
2. Click **"Create New Tender"**.
3. To continue an existing evaluation, click **"Open Tender ➔"** on its card.
4. Completed tenders can be viewed (read-only) by clicking **"View Archive"**.

> ⚠️ **Note:** Each NIT Number must be unique. You cannot create two tenders with the same NIT number.

---

### 📄 Specification Screen

**What you see:** A file uploader on the left and a status panel on the right.

**What to do:**

1. Click **"Browse files"** and select the tender specification PDF.
2. Click **"Process Specification with AI"**.
3. Wait for the spinner — the AI is reading every page and extracting all requirements. This takes 30–90 seconds depending on document size.
4. When done, you will see:
   - Total pages ingested.
   - Number of requirements extracted.
5. Proceed to the next screen.

> 💡 **Tip:** This works for any type of tender — electrical equipment, IT hardware (laptops, servers), tyres, civil supplies, maintenance contracts. No need to configure anything for the type of tender.

---

### 📋 Requirements & Setup Screen

This screen has **3 tabs**:

---

#### Tab 1: Requirements & QR Baseline

**What you see:** An editable table of all extracted requirements.

**What to do:**
- Rows highlighted in **gold** are Qualification Requirements (QR) — these are the go/no-go criteria.
- Review each row. You can:
  - **Edit the text** if the AI missed a word.
  - **Check/uncheck "Qualification Req (QR)"** to reclassify a requirement.
  - **Check "Mark N/A"** for requirements that don't apply to this particular tender.
  - **Add new rows** using the + button at the bottom.
  - **Delete rows** that are duplicates or irrelevant.
- Click **"Save as New Version"** when done. This creates a new version (e.g. v2) while keeping v1 as backup.

> ⚠️ **Important:** The approved baseline is the foundation of the entire evaluation. All bidder results are evaluated against this baseline. Take time to review it carefully.

---

#### Tab 2: Mandatory Documents Checklist

Shows the standard mandatory documents every bidder must submit (Technical Offer, Deviation Sheet, Type Test Certificates, etc.). This is for your reference.

---

#### Tab 3: Bidder Setup

**What to do:**
1. Type a bidder's company name in the text box.
2. Click **"Add Bidder"**.
3. Repeat for all participating bidders.
4. You can remove a bidder using the 🗑️ button (only before running verification).

---

### 📊 TBE Working Excel Screen

This is the **core evaluation screen**. It has two main sections:

---

#### Section 1: Generate Working Excel

Click **"Generate & Download Working Excel"** to download the TBE matrix template pre-filled with all requirements. This is your working spreadsheet.

---

#### Section 2: Bidder Tabs (one tab per bidder)

For **each bidder**, do the following:

**Step A — Upload Documents:**
1. Click the file uploader.
2. Select ALL of the bidder's PDFs at once (Ctrl+Click to select multiple).
3. Click **"Ingest X Documents for [Bidder Name]"**.
4. Wait for the spinner — documents are being read and indexed.

**Step B — Run AI Verification:**
1. Click **"Run AI Verification for [Bidder Name]"**.
2. Wait — AI is evaluating every requirement against every page of the bidder's documents. This takes 1–3 minutes.
3. When done, the **Evaluation & Accuracy Matrix** appears below.

**Reading the Matrix:**

| Column | What it means |
|--------|---------------|
| Clause | The clause number from the tender spec |
| Category | QR (Qualifying Requirement) or Technical |
| Specification Requirement | What the tender demands |
| Bidder Offered Quote | The exact text found in the bidder's documents |
| Status | Complied / Not Complied / Needs Human Review |
| Parameter Accuracy | 100% (exact match) / 0% (deviation) / Pending Review |

**Status colour codes:**
- 🟢 **Green = Complied** — AI found exact proof in the bidder's documents.
- 🔴 **Red = Not Complied** — AI found evidence the bidder fails this requirement.
- 🟡 **Amber = Needs Human Review** — AI could not find clear proof either way. Engineer must decide.

**KPI Cards at the top:**
- **Parameter Match Accuracy %** — Overall score for this bidder.
- **Complied count** — How many requirements are confirmed.
- **Not Complied count** — How many requirements are failed.
- **Needs Review count** — How many still need engineer input.

**Step C — Direct Engineer Verification (Quick Cell Update):**
- Expand **"Direct Engineer Human Verification (Quick Cell Update)"**.
- Select a clause from the dropdown.
- Set the Engineer Status.
- Click **"Save Cell Status"**.

---

### 🔍 Verification Results Screen

**What you see:** A detailed card for each requirement with the AI's recommendation, the evidence quote, and action buttons.

**What to do for each card:**

| Button | When to use |
|--------|-------------|
| ✅ **Confirm** | You agree with the AI's suggestion |
| 🔄 **Override** | You disagree — select a different status and type a reason (mandatory) |
| 📬 **Request Clarification** | You need more information from the bidder |
| ⚠️ **Flag for Review** | Mark for secondary committee review |

> 💡 **Tip:** If a page was scanned (not digital text), the original scanned image is shown next to the quote so you can visually verify the numbers yourself.

> 💡 **Tip:** Every action you take (confirm, override, flag) is permanently logged in the Audit Trail with your name, the old status, the new status, and the reason. This cannot be deleted.

---

### 📬 Reports & Completion Screen

This screen has three sections:

---

#### Section 1: Generate TBE MOM (.docx)

1. Click **"Edit Committee Members & Venue"** to customize member names and meeting venue.
2. Click **"Generate TBE MOM"**.
3. Download the official Minutes of Meeting Word document.

---

#### Section 2: Generate TBE Report (.docx)

1. Click **"Generate TER Report"**.
2. Download the full Technical Evaluation Report Word document.

---

#### Section 3: Clarification Management & Delta Re-Verification

**Use this when a bidder's documents are incomplete and you need to ask them for more information:**

1. Select the bidder from the dropdown.
2. The system automatically lists all flagged items.
3. Click **"Draft Official Clarification Letter via Gemini"**.
4. A formal letter is generated. Use the two tabs:
   - **👁️ Formal Letter Preview** — Clean, professional view (no asterisks, ready to send).
   - **✏️ Edit Letter Content** — Edit the text if needed before sending.
5. After the bidder replies, expand **"Upload Clarification Reply & Delta Re-Verify"**.
6. Upload their response PDF.
7. Click **"Run Delta Re-Verification on Affected Rows Only"**.
8. Only the rows that were flagged are re-evaluated — all other results stay unchanged.

---

#### Section 4: Mark Tender as Completed

When the entire evaluation is done:
1. Click **"Complete & Archive Tender"**.
2. The tender moves to read-only "Completed" status.
3. All documents and results are permanently preserved.

---

## Understanding Bidder Qualification Status

At any point, each bidder shows one of three statuses:

| Status | What it means |
|--------|---------------|
| ✅ **Qualified** | All requirements are Complied or N/A, confirmed by engineer |
| ❌ **Not Qualified** | At least one requirement is confirmed Not Complied |
| ⏳ **Pending** | One or more requirements still need human review |

> ⚠️ **Important Rule:** Only the **engineer's confirmed decision** determines the final qualification status. The AI's suggestion alone does not qualify or disqualify a bidder.

---

## Quick Reference: What Each Document Means

| Document Name in System | What It Is |
|------------------------|------------|
| Technical Offer | The signed, stamped specification accepted by the bidder |
| Deviation Sheet | List of deviations — must state "NIL" to pass |
| Guaranteed Technical Particulars (GTP) | Table of exact technical values offered by bidder |
| Type Test Reports | Third-party lab certificates proving equipment performance |
| Audited Balance Sheets | Financial proof of annual turnover for QR |
| Quality Assurance Plan (QAP) | Manufacturing quality process document |
| Performance Bank Guarantee | Financial security document (10% of contract value) |

---

## Launching the Application

```powershell
# Open PowerShell or Terminal
# Navigate to the project folder
cd "path\to\TBE 2"

# Run the app
python -m streamlit run app.py
```

Then open your browser and go to: **http://localhost:8501**

---

*This document is intended for engineers and procurement staff using the TBE Workbench for technical bid evaluation.*

