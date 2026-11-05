# TBE Workbench

AI-augmented Technical Bid Evaluation (TBE) platform for utility/government procurement. Ingests a tender specification, extracts technical requirements clause by clause into an immutable baseline, then verifies each bidder's submitted documents against those requirements using Gemini with mandatory verbatim-quote evidence, human override, commercial ranking, accuracy scoring, clarification-letter workflow, and formal `.xlsx`/`.docx` report generation.

See `PROJECT_ARCHITECTURE_DOCUMENTATION.md` for the full backend architecture and `frontend/ARCHITECTURE.md` for the frontend/API design. `USER_GUIDE.md` has a usage walkthrough.

---

## 1. Project Identity & Context

- **Name:** TBE Workbench
- **Repository:** `TBE-Workbench` ([company org](https://github.com/Exascale-Deeptech-and-AI-Pvt-Ltd/TBE-Workbench))
- **Status:** Active development / client testing phase — no tagged releases yet, no CI pipeline configured.
- **What it does:** Automates technical bid evaluation — cross-referencing hundreds of pages of tender specifications, Qualifying Requirements (QR), and Guaranteed Technical Particulars (GTP) against competing bidders' submissions, which is normally done manually and is error-prone and slow.
- **Why it exists:** Manual TBE is time-consuming and vulnerable to trap clauses (e.g. a blanket "NIL Deviation" declaration masking a missing test certificate). This platform makes the process faster and auditable, with every AI verdict backed by a cited, verbatim quote from the bidder's own document.
- **Target users:** Utility/government procurement engineers performing technical bid evaluation (e.g. BSES Rajdhani / Yamuna Power Limited-style tenders).

### Key features

- Dynamic, zero-hardcoding ingestion of any tender specification (PDF) into a structured, versioned requirement baseline.
- Multi-bidder document ingestion with dual-tier OCR (PyMuPDF digital text extraction + Gemini Vision for scans).
- AI verification engine with a deterministic anti-hallucination guardrail — Gemini may only mark a clause "Complied" if backed by an exact quote present on a cited page, checked by an algorithmic quote-verification pass.
- Human-in-the-loop override with mandatory reason + full audit trail.
- Commercial evaluation (L1/L2/L3 price ranking).
- Accuracy Matrix (AI verdict vs. ground truth) with a downloadable formal audit report.
- Clarification-letter drafting and delta re-verification (only re-checks previously flagged clauses after a bidder reply).
- One-click `.xlsx` Working Excel, `.docx` Minutes of Meeting (MOM) and Technical Evaluation Report (TER) generation.
- Read-only Archive view for completed tenders.
- Two frontends: the original Streamlit app (`ui/`) and a newer Next.js + FastAPI app (`frontend/` + `api/`), both driven by the same unmodified backend logic.

---

## 2. Getting Started

### 2.1 Prerequisites

- Python 3.11+
- Node.js 20+ and `pnpm` (for the Next.js frontend only)
- A Gemini API key (`google-genai`)
- SQLite (bundled, no install needed) — or a Postgres/Supabase instance if you prefer

### 2.2 Installation

```bash
git clone https://github.com/Exascale-Deeptech-and-AI-Pvt-Ltd/TBE-Workbench.git
cd TBE-Workbench
pip install -r requirements.txt
```

There is no `requirements-dev.txt` — `pytest` is already listed in `requirements.txt`.

### 2.3 Environment setup

There is currently no `.env.example` committed — create a `.env` file in the project root with:

```
GEMINI_API_KEY=your_key_here
# Optional extra keys for round-robin/failover:
GEMINI_API_KEY_2=...
GEMINI_API_KEY_5=...

MODEL_NAME=gemini-3.1-flash-lite
DB_PATH=tbe_workbench.db
DATABASE_URL=sqlite:///tbe_workbench.db
# SUPABASE_DATABASE_URL=...   (set DATABASE_URL to a Postgres/Supabase URL instead to use it)
```

> Consider adding a `.env.example` (keys only, no values) to the repo so this section can just point to it.

### 2.4 Running the application locally

**Backend (FastAPI — used by the Next.js frontend):**
```bash
uvicorn api.main:app --reload --port 8000
```
API docs: `http://localhost:8000/docs`. CORS is currently hardcoded to allow `http://localhost:3000` and `http://localhost:3100` (see `api/main.py`) — update this before any real deployment.

**Frontend (Next.js):**
```bash
cd frontend
pnpm install
pnpm dev
```
Runs at `http://localhost:3000`. Check `frontend/src/lib/api.ts` for the backend base URL.

**Or, the original all-in-one Streamlit app:**
```bash
streamlit run app.py
```

### 2.5 Initial setup & initialization

No separate migration step is required — `init_db()` (called automatically on FastAPI startup, and at Streamlit app start) creates all tables and the SQLite FTS5 index idempotently on first run. There is no seed-data script; the first real step is uploading a tender specification through the UI.

---

## 3. System Requirements & Compatibility

- **OS:** Developed and tested on Windows; no OS-specific code paths, should run on Linux/macOS.
- **Browser (frontend):** Latest Chrome, Edge, or Firefox. Not optimized for mobile.
- **Network:** Backend listens on port 8000, frontend dev server on 3000 (both configurable). Outbound HTTPS access to the Gemini API is required.
- **Database:** SQLite (file-based, default) or Postgres/Supabase via `DATABASE_URL`.

No formal hardware minimums or compatibility matrix are defined — this is a single-tenant internal/test tool, not a packaged product.

---

## 4. Environment Configuration Management

| Variable | Required | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | Primary Gemini API key |
| `GEMINI_API_KEY_2`, `GEMINI_API_KEY_5`, ... | No | Additional keys for round-robin/failover across quota limits (`ai/client.py`) |
| `MODEL_NAME` | Yes | Gemini model id, e.g. `gemini-3.1-flash-lite` |
| `DB_PATH` | Yes (SQLite) | Path to the local SQLite file |
| `DATABASE_URL` | Yes | SQLAlchemy connection string (SQLite or Postgres) |
| `SUPABASE_DATABASE_URL` | No | Alternative Postgres connection string when using Supabase |
| `SUPABASE_URL` | No (required on hosts with no persistent disk, e.g. Render) | Supabase project URL, used by `db/storage.py` to store page preview images + cached bidder ZIPs so they survive a restart |
| `SUPABASE_SERVICE_KEY` | No (required alongside `SUPABASE_URL`) | Supabase service-role key for Storage access — keep private, never expose to the frontend |
| `SUPABASE_STORAGE_BUCKET` | No | Storage bucket name (default `tbe-files`); create it as a **private** bucket in the Supabase dashboard — the backend proxies file bytes, so it never needs to be public |

There are no separate per-environment config profiles (dev/staging/prod) — the same `.env` mechanism is used everywhere; only the values change. Secrets live only in `.env` (gitignored) — there is no secret rotation tooling or vault integration.

---

## 5. Development Workflow

- Make changes, run the backend with `--reload` (auto-restarts on file change) and the frontend with `pnpm dev` (hot reload built in).
- No enforced pre-commit hooks or formatter configuration beyond the frontend's ESLint (`frontend/package.json` → `pnpm lint`).
- Both the Streamlit UI (`ui/`) and the Next.js+FastAPI stack (`frontend/`+`api/`) run against the same database and business logic, so you can use either during development.

---

## 6. Testing & Quality Assurance

```bash
pytest              # run the full suite
pytest tests/test_verifier_step7.py   # run one file
```

Test files live in `tests/` and are organized by build step (`test_db_step1.py` … `test_deliverables_step11.py`, plus `test_clarification_step10.py`). No formal coverage threshold or coverage-reporting tool is configured.

**Frontend:**
```bash
cd frontend
pnpm lint
```
No frontend unit/e2e test suite is set up yet; TypeScript type-checking is done via `tsc --noEmit` (not wired as a package script — run it directly: `npx tsc --noEmit`).

> **Note on live testing:** do not run tests that make real Gemini API calls or hit a running production/shared database without checking with the team first — see the free-tier quota note in §21.

---

## 7. Technology Stack

**Backend:** Python, FastAPI, SQLAlchemy, SQLite (FTS5) / PostgreSQL (Supabase-compatible), Pydantic, `google-genai` (Gemini), PyMuPDF (PDF text extraction), Pillow, `openpyxl` (Excel), `python-docx` (Word), `pytest`.

**Frontend:** Next.js 16 (App Router), React 19, TypeScript, TanStack React Query, Zustand, Tailwind CSS v4, ESLint, pnpm.

**Alternative UI:** Streamlit (`ui/`) — the original single-process app, still functional alongside the API.

**AI/LLM:** Google Gemini (model configurable via `MODEL_NAME`), with a multi-key client pool for round-robin and quota failover, plus a deterministic verbatim-quote verification layer as an anti-hallucination guardrail.

**Infrastructure:** No containerization or cloud infra is committed yet — see the separate deployment plan artifact for the Render/Oracle/Vercel hosting options under evaluation.

---

## 8. System Architecture

```
[ Tender Specification (PDF) ]        [ Bidder Submissions (PDFs) ]
             |                                       |
             v                                       v
     PyMuPDF + Gemini Vision OCR            PyMuPDF + Gemini Vision OCR
             |                                       |
             v                                       v
     Spec Extractor (structured          SQLite FTS5 full-text index
     JSON requirement schema)            (BM25-ranked search)
             |                                       |
             v                                       v
     Baseline Store (versioned,     ------->  Ranked clause search
     audit-logged)                                   |
                                                       v
                                     Gemini verification engine
                                     (batched, up to 12 clauses/call)
                                                       |
                                                       v
                                     Algorithmic quote checker
                                     (strict verbatim validation)
                                                       |
                         -----------------------------+-----------------------------
                         |                                                         |
                  Complied / Not Complied                              Needs Human Review
                         |                                                         |
                         -----------------------------+-----------------------------
                                                       v
                                 Streamlit UI  *or*  Next.js + FastAPI UI
                                 - Working Excel / KPIs      - Verification Results
                                 - Clarification letters      - Commercial ranking
                                 - .xlsx / .docx deliverables - Accuracy Matrix / Archive
```

### Component overview

- **`ai/`** — Gemini client pool (round-robin + quota failover), batched requirement verification, clarification-reply handling.
- **`db/`** — SQLAlchemy models, repository/service functions (baseline, accuracy, commercial), connection setup (SQLite WAL mode / Postgres).
- **`rules/`** — Qualification and risk-scoring rule engine (QR-failure = High Risk, etc.).
- **`reading/`** — PDF ingestion and dual-tier OCR.
- **`outputs/`** — Excel/Docx generation for Working Excel, MOM, TER.
- **`templates/`** — `.xlsx`/`.docx` templates consumed by `outputs/`.
- **`api/`** — FastAPI HTTP layer; every route wraps the modules above unchanged (`api/routes/*.py`), request/response shapes in `api/schemas.py`.
- **`frontend/`** — Next.js app calling the API (`frontend/src/lib/api.ts`).
- **`ui/`** — Original Streamlit app, calling the same backend modules directly (no HTTP layer).

### Application workflow (per tender)

1. Create tender → upload specification → background ingestion + requirement extraction.
2. Review/edit requirements → save as a new baseline version.
3. Add bidders → upload bidder documents.
4. Run AI verification (single bidder or all, batched up to 12 clauses/Gemini call) → clause-level verdicts with cited evidence + page-image preview.
5. Engineer reviews, overrides where needed (reason logged to audit trail).
6. Commercial evaluation (pricing/ranking) and Accuracy Matrix (if ground truth available).
7. Clarification letters for flagged/not-complied clauses → bidder reply upload → delta re-verification (only affected clauses re-checked, live progress).
8. Mark tender complete → moves to read-only Archive.

### Known architectural limitations

- In-memory progress trackers (`api/progress.py`, `api/clarification_progress.py`) require the FastAPI backend to run as exactly **one process/instance** — horizontal scaling would break live progress polling without moving this state to a shared store (Redis, DB row, etc.).
- SQLite with WAL mode + a 60s busy timeout is used for local/single-writer use; under concurrent heavy-write load (e.g. many bidders verified simultaneously) this is the main scaling bottleneck — Postgres/Supabase is the documented upgrade path.
- Background work runs on raw `threading.Thread`, not a task queue — acceptable for the current traffic level, not for high concurrency.

---

## 9. Project Directory Structure

```
ai/             Gemini client, verification logic, clarification handling
api/            FastAPI backend — routes/, schemas.py, deps.py, main.py (entry point)
db/             SQLAlchemy models, repository/service functions, connection.py
rules/          Rule engine (qualification status, risk scoring)
outputs/        .xlsx / .docx report generation (Working Excel, MOM, TER)
reading/        PDF ingestion & OCR
templates/      .xlsx / .docx templates used by outputs/
ui/             Original Streamlit app
frontend/       Next.js frontend (App Router) — src/app, src/lib/api.ts
scripts/        One-off / maintenance scripts
tests/          Pytest suite (one file per build step)
data/           Local data (tender/bidder files, as ingested)
test_data/      Sample/synthetic tender + bidder packs for testing
app.py          Streamlit entry point
requirements.txt  Python dependencies
tbe_workbench.db  Default local SQLite database file
```

Key entry points: `app.py` (Streamlit), `api/main.py` (FastAPI, run via `uvicorn api.main:app`), `frontend/src/app` (Next.js App Router pages).

---

## 10. Database Architecture & Management

- **Default:** SQLite with WAL mode and a 60-second busy timeout (`db/connection.py`), file at `DB_PATH`/`DATABASE_URL`.
- **Alternative:** Postgres, including Supabase, via `DATABASE_URL` (or `SUPABASE_DATABASE_URL`) — same SQLAlchemy models, no code change needed.
- **Schema:** Managed via SQLAlchemy models (see `db/models.py`); core entities include Tender, Document/Page, Requirement/Baseline (versioned), Bidder, Finding, Evidence, AuditLog.
- **Initialization:** `init_db()` creates all tables (and the SQLite FTS5 search index) on first run — idempotent, called automatically on app startup. There is no separate migration framework (e.g. Alembic) — schema changes are applied by editing the models; for SQLite this currently means recreating the DB file for breaking changes.
- **Seeding:** No seed script; `test_data/` holds synthetic sample tender/bidder packs usable for manual testing.
- **Backup:** No automated backup job exists — for SQLite, back up by copying the `.db`/`.db-wal`/`.db-shm` files while the app is stopped (or use SQLite's online backup API); for Supabase, use its built-in backup/export tooling.

---

## 11. API Documentation & Integration

- **Framework:** FastAPI, auto-generated interactive docs at `/docs` (Swagger UI) and `/redoc` when the backend is running.
- **Base URL (local):** `http://localhost:8000`
- **Authentication:** None currently implemented — the API has no login/token layer. Do not expose it directly to the public internet as-is.
- **Request/response shapes:** Defined as Pydantic models in `api/schemas.py`.
- **Key route groups** (`api/routes/`): `tenders`, `specification`, `bidders`, `baseline`, `deliverables`, `working_excel`, `findings`, `reports` (compliance matrix, clarification letters, delta re-verify), `commercial`, `accuracy`, `archive`, `pages` (page-image evidence).
- **Versioning:** None yet — all routes are unversioned (`/tenders/{id}/...`); no deprecation process defined.

---

## 12. Security & Access Control

- **Current state:** No authentication, authorization, or RBAC is implemented on either the FastAPI backend or the Streamlit app. Anyone who can reach the running instance can use it fully. This is acceptable only for local development and a controlled client test environment, not for a public deployment.
- **Data in transit:** No TLS is configured by the app itself — must be terminated by the hosting platform/reverse proxy in any real deployment.
- **Data at rest:** Not encrypted beyond whatever the host OS/disk provides.
- **Input validation:** Request bodies are validated via Pydantic schemas; no additional WAF/rate-limiting is configured.
- **Secrets:** API keys and DB URLs live only in `.env` (gitignored) — never commit real keys.
- **CORS:** Hardcoded allow-list in `api/main.py` (currently `localhost:3000`/`3100`) — must be updated per deployment.

> **These gaps are acceptable for an internal/client-test build but must be addressed (auth, HTTPS, CORS lockdown) before any public or production deployment.**

---

## 13. Logging, Monitoring & Observability

- Streamlit run logs are redirected to `streamlit_out.log` / `streamlit_err.log` / `streamlit_supabase.log` in the project root during local runs.
- FastAPI logs to stdout via Uvicorn's default logging; no structured/centralized logging is configured.
- `/health` endpoint exists on the FastAPI app for basic liveness checking.
- No metrics, tracing, or alerting infrastructure is set up — this would be a prerequisite for any production deployment.

---

## 14. Deployment & CI/CD

- **CI/CD:** None configured yet — no GitHub Actions workflow in this repo. All testing/building is manual.
- **Containerization:** No `Dockerfile` or `docker-compose.yml` exists yet.
- **Current deployment status:** Under evaluation for a client testing window (~10–12 days). A separate shareable deployment plan document compares Render, Oracle Cloud Always Free, and Vercel+Oracle+Supabase combinations — see the team's shared deployment plan artifact rather than this file, since hosting choice is still being finalized.
- **Production deployment steps:** Not yet defined beyond "run `uvicorn api.main:app`" and "run `pnpm build && pnpm start`" — a real deployment runbook should be written once a host is finalized.

---

## 15–19. Release Management, Performance, Error Handling, Data Privacy, Backup/DR

Not yet formalized — there are no tagged releases, no load/performance testing, no disaster-recovery plan, and no written data-retention policy. These should be added once the project moves past the client-testing phase. See §21 for the one data-handling rule that **is** currently enforced (free-tier confidentiality note).

### Common issues (troubleshooting)

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Failed to generate Working Excel` | No approved baseline yet for the tender | Approve a baseline on Requirements Setup first |
| AI verification stuck/erroring with a quota message | Gemini free-tier quota exhausted | Wait for quota reset, or add another `GEMINI_API_KEY_n` |
| Frontend can't reach the backend | CORS origin not in `api/main.py`'s allow-list, or backend not running | Start `uvicorn api.main:app --reload --port 8000`; add your origin to CORS if different from `localhost:3000` |
| Timestamps look off by hours | Naive UTC datetime rendered as local time | Already fixed in `frontend/src/app/page.tsx` / `reports-completion` — re-pull latest if seen elsewhere |

---

## 20. Contributing Guidelines

- No formal branching strategy or commit-message convention is enforced yet (no `CONTRIBUTING.md`). In practice: work on `main`, commit with a clear summary line, and push to the `company` remote (`https://github.com/Exascale-Deeptech-and-AI-Pvt-Ltd/TBE-Workbench.git`) — `origin` is a personal fork, not pushed to by default.
- No PR template or required review process is configured yet.
- Code style: Python has no enforced formatter/linter configured at the repo root (consider adding `ruff`/`black`); the frontend uses ESLint (`pnpm lint`) and TypeScript strict mode.

---

## 21. Known Issues & Limitations

- **Free-tier AI quota:** If a deployment is running on a free-tier Gemini key, heavy concurrent verification (many bidders, multiple testers at once) can hit the daily/per-minute request limit; verification pauses with a quota message until it resets.
- **Single-instance requirement:** The backend's in-memory progress tracking (spec ingestion, delta re-verify) only works correctly with exactly one backend process running — do not scale it horizontally without first moving that state to a shared store.
- **No authentication:** Anyone with network access to a running instance has full access — do not expose a deployment publicly without adding auth first.
- **No automated migrations:** Schema changes to the SQLite DB currently require manual handling, not a migration tool.
- **Planned improvements:** CI pipeline, authentication, a proper deployment runbook once hosting is finalized, `.env.example`, automated test coverage reporting.

> ### ⚠️ Data confidentiality during free-tier testing
> If this deployment uses a **free-tier AI API key** and/or **free-tier hosting**, do **not** upload real, confidential, or commercially sensitive tender/bidder data to it — use sample or anonymized data only. Free-tier infrastructure carries no data-confidentiality guarantee, and **the company is not responsible for any data leak, loss, or exposure** resulting from data uploaded to a free-tier test environment. This restriction lifts once the system moves to paid/production infrastructure under a proper data-handling agreement.

---

## 22. Support & Maintenance

- **Project maintainer / contact:** _[fill in name, email, or phone]_
- **Issue reporting:** Use the repository's GitHub Issues, or report directly to the maintainer above. Include: tender/bidder name, screen, exact action taken, expected vs. actual result, and a screenshot if possible.
- **Maintenance:** No scheduled maintenance windows or dependency-update cadence defined yet — this is an actively developed project.

---

## 23. License & Legal Information

No `LICENSE` file is currently committed to this repository. Until one is added, treat this codebase as proprietary/all-rights-reserved to its owning organization (Exascale Deeptech and AI Pvt Ltd) — do not redistribute without permission.

---

## 24. Authors & Acknowledgements

- **Repository owner / org:** Exascale Deeptech and AI Pvt Ltd
- Built with FastAPI, Next.js, SQLAlchemy, Google Gemini, PyMuPDF, Streamlit, and other open-source libraries listed in `requirements.txt` and `frontend/package.json`.

---

## 25. References & Additional Documentation

- `PROJECT_ARCHITECTURE_DOCUMENTATION.md` — full backend architecture and implementation guide.
- `frontend/ARCHITECTURE.md` — frontend/API design decisions.
- `USER_GUIDE.md` — usage walkthrough.
- `TBE_Accuracy_Matrix_Documentation.docx` / `.pdf` — Accuracy Matrix methodology.
- `TBE_API_Cost_Analysis.docx` — AI API cost analysis.
- FastAPI interactive docs at `/docs` once the backend is running.

---

## 26. Quick Reference — Useful Commands

**Development**
```bash
uvicorn api.main:app --reload --port 8000   # start backend
cd frontend && pnpm dev                     # start frontend
streamlit run app.py                        # start the alternative Streamlit UI
```

**Testing**
```bash
pytest                                      # run backend test suite
pytest tests/test_verifier_step7.py         # run a single test file
cd frontend && pnpm lint                    # lint the frontend
cd frontend && npx tsc --noEmit             # type-check the frontend
```

**Database**
```bash
# No dedicated CLI yet — inspect tbe_workbench.db with any SQLite client,
# or point DATABASE_URL at a Postgres/Supabase instance instead.
```

**Deployment**
```bash
cd frontend && pnpm build && pnpm start     # production build of the frontend
# Backend: run uvicorn api.main:app without --reload, behind a process manager
# (deployment runbook pending — see the shared deployment plan document)
```
