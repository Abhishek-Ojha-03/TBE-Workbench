# TBE Workbench — Frontend Architecture & Decision Log

This document tracks the frontend rebuild: what's been decided, why, and how to
pick the work back up. It's a living document — update it as new decisions get
made or new pieces get built, rather than letting this context only live in
chat history.

For the existing Python/Streamlit backend architecture, see
`../PROJECT_ARCHITECTURE_DOCUMENTATION.md` at the project root.

---

## 1. Why a new frontend

A colleague produced a complete UI/UX design (Figma) for the TBE Workbench —
Home/Tenders list, Specification screen, and Requirements & Bidder Setup
screen — intended to replace the current Streamlit UI with a pixel-matched,
production-grade frontend. This directory is that rebuild.

**Goal:** zero visual deviation from the Figma design — no reinterpretation,
no "improvements," exact colors/spacing/typography/components as specified.

---

## 2. Tech Stack & Why Each Piece Was Chosen

| Layer | Choice | Why |
|---|---|---|
| Framework | Next.js 16 (App Router) | Standard, well-supported React framework |
| Language | TypeScript | Catches type/prop mistakes before they become visual bugs — important for a zero-deviation goal |
| Styling | Tailwind CSS v4, configured with the exact Figma design tokens | Utility classes map directly to the Design System page's token list, instead of hand-written CSS per element |
| Font | **Free (Google Fonts) — see Section 4** | — |
| Package manager | pnpm | Faster installs, more efficient than npm's default dependency handling |
| Data fetching (planned) | TanStack Query | Will handle loading/error/caching once screens are wired to the FastAPI backend |
| Tables (planned) | TanStack Table | For the Tenders list, clause tables, bidder tables |
| Forms (planned) | React Hook Form + Zod | Form handling + validation for Create Tender, clause editing |
| Linting | ESLint (scaffolded default config) | Code consistency |
| Backend (planned) | FastAPI | See Section 6 — wraps the existing Python `db/`/`ai/`/`rules/`/`outputs/` modules with REST endpoints a browser-based frontend can call |

**Repo structure:** monorepo — this `frontend/` directory lives inside the
existing `TBE-Workbench` repo, alongside the Python backend. Chosen over a
separate repo for simplicity given team size, and to keep the existing
dual-push habit (`origin` + `company` remotes) working without extra steps.

---

## 3. Design Tokens — Source of Truth

Extracted from the Figma file's own "Design System" page and encoded in
`src/app/globals.css` as Tailwind v4 `@theme` tokens:

- **Colors:** Primary (Violet V50–V500), Neutral (Black scale B50–B500),
  Secondary (Info ramp), Background `#F8F8F8`
- **Typography scale:** Display 38px, H1 32px, H2 28px, H3 24px, B1 18px,
  B2 16px, B3 14px, Label 12px, Caption 10px
- **Spacing:** Tailwind's **default** spacing scale is used as-is — it
  already matches the Figma spacing panel exactly (4/8/12/16/20/24/32/40/
  48/64/80–96px), so no custom spacing config was needed.
- **Border radius:** 2 / 4 / 8 / 12 / 16px, as explicit custom tokens
  (`--radius-xs` … `--radius-xl`)

⚠️ A handful of secondary/neutral hex values were read from a screenshot of
the Figma Design System page rather than copied directly from Figma's
inspect panel — these should be spot-checked against the live file before
this goes to production, since small text in a screenshot has some risk of
a misread digit.

---

## 4. Font

The Figma design specifies a named font ("Urbane"). After evaluation, the
decision was made to use a **free font (Google Fonts)** instead, to keep the
project moving without external dependencies or licensing overhead.

- **Current choice:** Inter, loaded via `next/font/google`
- **Where:** `src/app/layout.tsx`, exposed as the `--font-urbane-placeholder`
  CSS variable, consumed by `--font-display` in `globals.css`
- **If this needs to change later:** swapping the font is a single block
  change in `layout.tsx` (see the inline comment there) — no other file
  needs to be touched, since every component references the `font-display`
  token rather than importing a font directly.

---

## 5. Screens — Status

| Screen | Status | Notes |
|---|---|---|
| Home (Tenders list) | ✅ Built, static/mock data | Tabs (Open/Completed), search, Create New modal, tenders table — matches Figma screenshot |
| Specification | ✅ Built, static/mock data | Upload dropzone, ingestion status cards, extracted-clauses table with QR/N/A checkboxes |
| Requirements & Setup | ✅ Built, real data (wired) | Real version selector + active-baseline banner, real clause table, Mandatory Documents card (static, by design), real Bidders card with All/Qualified/Unqualified filter — see Section 7b |

Shared components introduced: `components/layout/sidebar.tsx` (used by both
inner screens — route group `app/(workspace)/`), `components/layout/
workspace-header.tsx` (title + back/tender-selector row + bell/profile
icons, used identically on both screens).

⚠️ Sidebar nav icons (chart/grid/package glyphs) are generic approximations,
not exported from the Figma file — swap for the real icon SVGs once
available, per the "use original assets" rule.

All 3 screens verified: `tsc --noEmit` clean, `eslint` clean, all routes
return HTTP 200, and expected text content confirmed present in rendered
HTML for each page.

All screens are being built **static-first** (mock data, no API calls) before
any backend wiring — this lets visual accuracy be verified independently of
backend correctness.

---

## 6. Why FastAPI Is Needed (Not Yet Built)

The current Streamlit app has **no separation between UI and logic** —
button click handlers in `ui/*.py` call `ai/`, `db/`, `rules/` directly in
the same process. A React/Next.js frontend runs in the browser and has no
access to Python, the database, or API keys — it can only work by sending
requests to a server over the network.

**FastAPI will be that server** — a thin REST layer (e.g. `POST /tenders`,
`POST /tenders/{id}/specification`, `GET /tenders/{id}/requirements`) that
calls the *existing* business logic in `db/`, `ai/`, `rules/`, `outputs/`
unchanged. Not a rewrite of backend logic — a new front door for it.

**Status:** ✅ Initial scaffold built and verified end-to-end. Lives at
`api/` (project root, alongside `db/`, `ai/`, `rules/`, `outputs/` — not
inside `frontend/`, since it's Python).

**Structure:**
- `api/main.py` — FastAPI app, CORS configured for the Next.js dev server
  (`localhost:3000`/`3100`), calls the existing `init_db()` on startup
- `api/deps.py` — DB session dependency, wraps `db/connection.py`'s
  `SessionLocal` (same one the Streamlit app uses)
- `api/schemas.py` — request/response models (separate from `ai/schemas.py`,
  which is for Gemini structured output — different purpose, kept apart)
- `api/routes/tenders.py` — `GET/POST /tenders`, `GET /tenders/{id}` —
  wraps `db/repository.py` unchanged
- `api/routes/specification.py` — `POST /tenders/{id}/specification`
  (upload + ingest + extract), `GET /tenders/{id}/requirements` — wraps
  `reading/ingest.py` + `ai/extractor.py` + `db/baseline_service.py`
  unchanged

**Verified end-to-end against the real local database:** created a test
tender via the API, uploaded `BSES_11kV_VCB_specification.pdf` through
`POST /tenders/{id}/specification`, got back 7 pages ingested / 23
requirements extracted, then confirmed `GET /tenders/{id}/requirements`
returned the real extracted clauses with correct text. Test tender and its
documents/pages were deleted afterward to leave the real DB clean.

**Run it:** `uvicorn api.main:app --reload --port 8000` from the project
root (not `frontend/`).

⚠️ **Found during testing, not yet fixed:** deleting a `Tender` via the ORM
doesn't cascade to its specification `Document`/`Page` rows (only bidder
documents cascade, since that relationship has `cascade="all, delete-orphan"`
— spec documents, which have `bidder_id=None`, don't). Had to delete those
manually during cleanup. Worth a small fix in `db/models.py` before this
matters in production (e.g. a tender-deletion admin feature).

**Not yet built:** bidder endpoints, verification/AI-check endpoints,
commercial/pricing endpoints, report generation endpoints — only the
Home + Specification screens' needs are covered so far.

---

## 7. Known Issues / Setup Notes

- **OneDrive + pnpm symlink conflict:** installing inside a OneDrive-synced
  folder caused `pnpm install` to fail on symlink creation (file locking).
  Fixed via `.npmrc` → `node-linker=hoisted` (installs without symlinks).
- **Dev server port:** defaults to 3000 if free; was run on 3100 during
  testing to avoid conflicting with other local processes. Run with
  `pnpm dev` from `frontend/` and check the printed URL.

---

## 7a. Frontend Wired to Real Backend Data

Home and Specification screens now use real data, not mock data:

- **`src/lib/api.ts`** — typed `fetch` wrapper around every backend endpoint
  built so far (`listTenders`, `createTender`, `uploadSpecification`,
  `getRequirements`), base URL from `NEXT_PUBLIC_API_URL` (`.env.local`,
  defaults to `http://localhost:8000`)
- **`@tanstack/react-query`** — added now that there's real data to fetch;
  handles loading/error states and cache invalidation (e.g. creating a
  tender invalidates the tenders list so it refreshes automatically)
- **`zustand`** (`src/lib/store.ts`) — added now that a real cross-screen
  need appeared: the Specification screen needs to know *which* tender is
  open, the same concept as the existing Streamlit app's
  `st.session_state["active_tender_id"]`. This is the point referenced in
  Section 2 where Zustand's introduction was deferred until actually needed.

**Home screen:** real `GET /tenders` per tab, real `POST /tenders` via the
Create Tender modal (with loading/error states), clicking a tender row sets
it as the active tender and navigates to Specification.

**Specification screen:** guards against being opened with no active tender
(shows a "No tender selected" message with a link back to Home, rather than
crashing); file upload calls the real `POST /tenders/{id}/specification`
endpoint and shows live pages-ingested/requirements-extracted counts; the
clause table is a real `GET /tenders/{id}/requirements` query.

**Verified, not assumed:** `tsc`/`eslint` clean; ran both servers together
against a dedicated throwaway database (`wiring_test.db`, never touched the
real DB); confirmed CORS preflight + actual cross-origin request succeed
(`localhost:3100` → `localhost:8010`, matching what the browser will do in
real use) and return correct tender data; confirmed the "no tender selected"
guard renders correctly when `/specification` is opened directly.

**Update:** Requirements & Setup screen is now also wired to real data (see
Section 7b below) — no screens remain on mock data.

---

## 7b. Requirements & Setup — Bidders and Baseline Versioning

Two new backend routers, built to mirror the EXACT same semantics the
Streamlit app already uses (`db/baseline_service.py`), not a simplified
reinterpretation:

- **`api/routes/bidders.py`** — `GET/POST /tenders/{id}/bidders`,
  `DELETE /tenders/{id}/bidders/{bidder_id}`. Wraps
  `get_bidders_for_tender`/`add_bidder`/`delete_bidder` unchanged.
- **`api/routes/baseline.py`** — `GET /tenders/{id}/baseline-versions` (list
  all versions with `is_latest`), `GET .../baseline-versions/{version}/requirements`
  (view any historical version), `POST /tenders/{id}/baseline-versions`
  (create a new version from a full requirement list). Wraps
  `get_latest_baseline`/`get_baseline_requirements`/`save_baseline_edits`
  unchanged.

**Important semantic note, carried over faithfully from Streamlit:** saving
anything — including "Quick Add Single Requirement" — does NOT edit a row
in place. It creates a brand new immutable `BaselineVersion` containing the
*entire* requirement list (existing rows + the new one). This is the same
model `ui/baseline_view.py` already uses; the frontend's Quick Add form
fetches the currently-viewed version's rows, appends the new one
client-side, and POSTs the full list — exactly mirroring the Streamlit
form's `current_records.append(...)` → `save_baseline_edits(...)` flow.

**Frontend:** the version selector dropdown and "Quick Add Single
Requirement" form (both previously removed as non-functional mockups) are
now real — version switching re-fetches that version's requirements
read-only; Quick Add creates a new version and switches the view to it.
Bidder list, add-bidder modal, and delete now call the real endpoints too.

**Verified, not assumed:** ran the full bidders + baseline-version flow
against a live server — created a tender, added a bidder (plus confirmed
duplicate-name rejection), created baseline v1, simulated the quick-add
flow to create v2, and confirmed v1 stayed untouched (2 requirements) while
v2 correctly had 3 — immutability of prior versions holds. `tsc`/`eslint`
clean. All test data run against the real local DB was cleaned up
immediately after; later checks used an isolated throwaway DB.

---

## 8. Change Log

| Date | Change |
|---|---|
| 2026-11-02 | Project scaffolded (Next.js 16 + TS + Tailwind v4 + pnpm). Design tokens wired into `globals.css`. Font decision made (free/Inter). Home screen built and verified (tsc clean, eslint clean, renders correctly). This document created. |
| 2026-11-02 | Specification and Requirements & Setup screens built, sharing a new sidebar + workspace header. All 3 screens now complete (static/mock data). Verified clean (tsc, eslint, HTTP 200, content checks). Next: FastAPI backend scaffold. |
| 2026-11-02 | FastAPI backend scaffold built (`api/`) — tenders + specification endpoints, wrapping existing `db/`/`reading/`/`ai/` modules unchanged. Verified end-to-end against the real local DB (create tender → upload real spec PDF → extract 23 requirements → fetch them back correctly). Found and documented a cascade-delete gap in `db/models.py` (not yet fixed). Next: wire the Home and Specification frontend screens to these real endpoints, replacing mock data. |
| 2026-11-02 | Home and Specification screens wired to the real FastAPI backend (React Query + Zustand added). Verified both servers running together against a throwaway DB, CORS confirmed working cross-origin, "no tender selected" guard confirmed. Requirements & Setup screen still on mock data pending bidder endpoints. |
| 2026-11-03 | Added `api/routes/bidders.py` and `api/routes/baseline.py`, wrapping existing bidder/versioning logic unchanged. Requirements & Setup screen fully wired: real version selector (switch between historical versions, read-only), real "Quick Add Single Requirement" (creates a new immutable baseline version, matching Streamlit's exact versioning model), real bidder list/add/delete. Verified live: version immutability confirmed (v1 untouched after v2 created), duplicate-bidder rejection confirmed. All screens now on real data. |
| 2026-11-03 | Fixed a real race condition in `ai/quota_guard.py` discovered during live testing: concurrent extraction threads racing on first-time quota-row creation caused a crash that silently killed extraction (every successful Gemini call thrown away, page retried redundantly — actively wasting quota, not just failing quietly). Also fixed a second concurrency bug found while stress-testing the first one: a lost-update race in the usage counter. Both proven fixed via a 10-thread/30-call stress test (0 errors, exact count). Added `POST /tenders/{id}/bidders/bulk-zip` (matches `ui/baseline_view.py`'s "Add Bidders from ZIP" exactly — folder names become bidders, ZIP saved to `data/bidder_zips/` for later reuse by TBE Working Excel) and wired it into the Requirements & Setup screen as a second "📦 Add from ZIP" option alongside the single Add Bidder modal. |
