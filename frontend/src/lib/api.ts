/**
 * Thin fetch wrapper around the FastAPI backend (api/main.py).
 * Every function here maps 1:1 to a real endpoint already built and
 * verified in api/routes/tenders.py and api/routes/specification.py.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options?.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content etc.
  if (res.status === 204) return undefined as T;
  return res.json();
}

/**
 * For endpoints that return a real binary file (Excel/.docx), not JSON —
 * fetches it as a blob and triggers an actual browser download (object URL
 * + a programmatic anchor click), instead of the frontend only pretending
 * a download happened.
 */
async function downloadFile(path: string, fallbackFileName: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "POST" });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // not JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  const blob = await res.blob();

  // Prefer the real filename the backend sent (FileResponse sets this via
  // Content-Disposition), fall back to a sensible default if absent.
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/);
  const fileName = match ? match[1] : fallbackFileName;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Types (mirror api/schemas.py) ──────────────────────────────────────
export interface Tender {
  id: number;
  description: string;
  nit_no: string;
  status: "open" | "completed";
  created_at: string;
  bidder_count: number;
}

export interface SpecificationUploadStarted {
  document_id: number;
  file_name: string;
  total_pages_ingested: number;
  status: string;
}

export interface SpecificationProgress {
  status: "ingesting" | "extracting" | "complete" | "error";
  current_page: number;
  total_pages: number;
  requirements_so_far: number;
  error: string | null;
}

export interface Requirement {
  id: number;
  clause: string | null;
  text: string;
  page_number: number | null;
  is_QR: boolean;
  not_applicable: boolean;
}

export interface Bidder {
  id: number;
  name: string;
  final_status: "Pending" | "Qualified" | "Not Qualified";
}

export interface BaselineVersion {
  version_number: number;
  approved_at: string;
  is_latest: boolean;
}

export interface RequirementInput {
  clause: string | null;
  text: string;
  page_number: number | null;
  is_QR: boolean;
  not_applicable: boolean;
}

// ── Tenders ──────────────────────────────────────────────────────────
export function listTenders(status?: "open" | "completed"): Promise<Tender[]> {
  const query = status ? `?status=${status}` : "";
  return request<Tender[]>(`/tenders${query}`);
}

export function createTender(description: string, nit_no: string): Promise<Tender> {
  return request<Tender>(`/tenders`, {
    method: "POST",
    body: JSON.stringify({ description, nit_no }),
  });
}

export function getTender(tenderId: number): Promise<Tender> {
  return request<Tender>(`/tenders/${tenderId}`);
}

// ── Specification ────────────────────────────────────────────────────
export function uploadSpecification(
  tenderId: number,
  file: File
): Promise<SpecificationUploadStarted> {
  const formData = new FormData();
  formData.append("file", file);
  return request<SpecificationUploadStarted>(`/tenders/${tenderId}/specification`, {
    method: "POST",
    body: formData,
  });
}

export function getSpecificationProgress(tenderId: number): Promise<SpecificationProgress> {
  return request<SpecificationProgress>(`/tenders/${tenderId}/specification/progress`);
}

export function getRequirements(tenderId: number): Promise<Requirement[]> {
  return request<Requirement[]>(`/tenders/${tenderId}/requirements`);
}

// ── Baseline versions ───────────────────────────────────────────────
export function listBaselineVersions(tenderId: number): Promise<BaselineVersion[]> {
  return request<BaselineVersion[]>(`/tenders/${tenderId}/baseline-versions`);
}

export function getRequirementsForVersion(
  tenderId: number,
  versionNumber: number
): Promise<Requirement[]> {
  return request<Requirement[]>(`/tenders/${tenderId}/baseline-versions/${versionNumber}/requirements`);
}

export function createBaselineVersion(
  tenderId: number,
  requirements: RequirementInput[]
): Promise<BaselineVersion> {
  return request<BaselineVersion>(`/tenders/${tenderId}/baseline-versions`, {
    method: "POST",
    body: JSON.stringify({ requirements }),
  });
}

// ── Bidders ──────────────────────────────────────────────────────────
export function listBidders(tenderId: number): Promise<Bidder[]> {
  return request<Bidder[]>(`/tenders/${tenderId}/bidders`);
}

export function createBidder(tenderId: number, name: string): Promise<Bidder> {
  return request<Bidder>(`/tenders/${tenderId}/bidders`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function deleteBidder(tenderId: number, bidderId: number): Promise<void> {
  return request<void>(`/tenders/${tenderId}/bidders/${bidderId}`, {
    method: "DELETE",
  });
}

export interface BulkZipBidderResult {
  added: string[];
  skipped: string[];
}

export function addBiddersFromZip(tenderId: number, file: File): Promise<BulkZipBidderResult> {
  const formData = new FormData();
  formData.append("file", file);
  return request<BulkZipBidderResult>(`/tenders/${tenderId}/bidders/bulk-zip`, {
    method: "POST",
    body: formData,
  });
}

// ── Deliverables (real file downloads) ─────────────────────────────────
export function downloadWorkingExcel(tenderId: number): Promise<void> {
  return downloadFile(`/tenders/${tenderId}/working-excel`, `TBE_Working_${tenderId}.xlsx`);
}

export function downloadMom(tenderId: number): Promise<void> {
  return downloadFile(`/tenders/${tenderId}/mom`, `TBE_MOM_${tenderId}.docx`);
}

export function downloadTer(tenderId: number): Promise<void> {
  return downloadFile(`/tenders/${tenderId}/ter`, `TBE_TER_${tenderId}.docx`);
}

// ── TBE Working Excel: document ingestion + AI verification ───────────
export interface IngestDocumentsResult {
  ingested_count: number;
}

export function ingestBidderDocuments(
  tenderId: number,
  bidderId: number,
  files: File[]
): Promise<IngestDocumentsResult> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  return request<IngestDocumentsResult>(`/tenders/${tenderId}/bidders/${bidderId}/documents`, {
    method: "POST",
    body: formData,
  });
}

export interface BulkZipIngestResult {
  bidder_name: string;
  bidder_id: number | null;
  documents_ingested: number;
  matched: boolean;
}

export interface BulkZipIngestResponse {
  results: BulkZipIngestResult[];
}

export function bulkZipIngest(tenderId: number): Promise<BulkZipIngestResponse> {
  return request<BulkZipIngestResponse>(`/tenders/${tenderId}/bulk-zip-ingest`, {
    method: "POST",
  });
}

export interface VerifyBidderResult {
  bidder_id: number;
  final_status: string;
  complied: number;
  not_complied: number;
  needs_review: number;
  accuracy_pct: number;
}

export function verifyBidder(tenderId: number, bidderId: number): Promise<VerifyBidderResult> {
  return request<VerifyBidderResult>(`/tenders/${tenderId}/bidders/${bidderId}/verify`, {
    method: "POST",
  });
}

export interface VerifyAllBiddersResult {
  results: Record<string, unknown>[];
}

export function verifyAllBidders(tenderId: number): Promise<VerifyAllBiddersResult> {
  return request<VerifyAllBiddersResult>(`/tenders/${tenderId}/verify-all`, {
    method: "POST",
  });
}

// ── Verification Results: findings + confirm/override/flag/qualify ────
export interface Evidence {
  quoted_text: string | null;
  page_number: number | null;
}

export interface AuditLogEntry {
  timestamp: string;
  who: string;
  what_changed: string;
  old_value: string | null;
  new_value: string | null;
  reason: string | null;
}

export interface Finding {
  id: number;
  requirement_id: number;
  clause: string | null;
  requirement_text: string;
  ai_status: string | null;
  engineer_status: string | null;
  remark: string | null;
  evidence: Evidence | null;
  audit_history: AuditLogEntry[];
}

export function getFindings(tenderId: number, bidderId: number): Promise<Finding[]> {
  return request<Finding[]>(`/tenders/${tenderId}/bidders/${bidderId}/findings`);
}

export function confirmFinding(findingId: number): Promise<Finding> {
  return request<Finding>(`/findings/${findingId}/confirm`, { method: "POST" });
}

export function overrideFinding(findingId: number, status: string, reason: string): Promise<Finding> {
  return request<Finding>(`/findings/${findingId}/override`, {
    method: "POST",
    body: JSON.stringify({ status, reason }),
  });
}

export function flagFinding(findingId: number, reason: string): Promise<Finding> {
  return request<Finding>(`/findings/${findingId}/flag`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function qualifyBidder(
  tenderId: number,
  bidderId: number,
  status: "Qualified" | "Not Qualified"
): Promise<Bidder> {
  return request<Bidder>(`/tenders/${tenderId}/bidders/${bidderId}/qualify`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

// ── Reports & Completion: compliance matrix, clarification, complete ──
export interface ComplianceRow {
  bidder_id: number;
  bidder_name: string;
  total_clauses: number;
  complied: number;
  not_complied: number;
  under_review: number;
  score_pct: number;
  risk: string;
  status: string;
}

export function getComplianceMatrix(tenderId: number): Promise<ComplianceRow[]> {
  return request<ComplianceRow[]>(`/tenders/${tenderId}/compliance-matrix`);
}

export interface ClarificationLetterResult {
  letter: string;
  flagged_count: number;
}

export function draftClarificationLetter(
  tenderId: number,
  bidderId: number
): Promise<ClarificationLetterResult> {
  return request<ClarificationLetterResult>(
    `/tenders/${tenderId}/bidders/${bidderId}/clarification-letter`,
    { method: "POST" }
  );
}

export interface DeltaReverifyResult {
  rechecked_count: number;
  new_status: string;
  clauses: string[];
}

export function uploadClarificationReply(
  tenderId: number,
  bidderId: number,
  files: File[]
): Promise<DeltaReverifyResult> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  return request<DeltaReverifyResult>(
    `/tenders/${tenderId}/bidders/${bidderId}/clarification-reply`,
    { method: "POST", body: formData }
  );
}

export function completeTender(tenderId: number): Promise<Tender> {
  return request<Tender>(`/tenders/${tenderId}/complete`, { method: "POST" });
}

// ── Commercial Evaluation: Part 2, price bid opening ───────────────────
export interface CommercialRankingRow {
  rank: number | null;
  label: string;
  bidder_id: number;
  name: string;
  quoted_price: number | null;
  currency: string;
  pct_above_l1: number | null;
  tie: boolean;
  status: string;
}

export function getCommercialRanking(tenderId: number): Promise<CommercialRankingRow[]> {
  return request<CommercialRankingRow[]>(`/tenders/${tenderId}/commercial-ranking`);
}

export interface FetchPricesResponse {
  scanned_count: number;
  ranking: CommercialRankingRow[];
}

export function fetchPricesWithAi(tenderId: number): Promise<FetchPricesResponse> {
  return request<FetchPricesResponse>(`/tenders/${tenderId}/commercial-fetch-prices`, {
    method: "POST",
  });
}

// ── Accuracy Matrix: AI verdicts vs. ground-truth benchmark ───────────
export interface AccuracyMatrixRow {
  bidder: string;
  test_category: string;
  format_type: string;
  clause: string;
  requirement_text: string;
  offered_value: string;
  ground_truth_answer: string;
  ai_verdict: string;
  audit_match: string;
  is_trap_clause: boolean;
  full_quote: string;
  ai_remarks: string;
}

export interface AccuracyMatrixResult {
  has_bidders: boolean;
  total_evals: number;
  bidder_count: number;
  tp: number;
  tn: number;
  fp: number;
  fn: number;
  accuracy_pct: number;
  precision_pct: number;
  recall_pct: number;
  rows: AccuracyMatrixRow[];
}

export function getAccuracyMatrix(tenderId: number): Promise<AccuracyMatrixResult> {
  return request<AccuracyMatrixResult>(`/tenders/${tenderId}/accuracy-matrix`);
}

export function downloadAccuracyFormalReport(tenderId: number): Promise<void> {
  return downloadFile(
    `/tenders/${tenderId}/accuracy-matrix/formal-report`,
    `TBE_Accuracy_Formal_Report_${tenderId}.docx`
  );
}

// ── Tender Archive: read-only summary for a completed tender ──────────
export interface ArchiveDocument {
  id: number;
  file_name: string;
  document_type: string | null;
  available: boolean;
}

export interface ArchiveBidderSummary {
  bidder_id: number;
  name: string;
  final_status: string;
  quoted_price: number | null;
  currency: string;
  commercial_rank_label: string;
}

export interface ArchiveFindingRow {
  clause: string;
  requirement_text: string;
  status: string;
  offered_value: string;
  remark: string;
}

export interface ArchiveBidderDetail {
  bidder_id: number;
  name: string;
  final_status: string;
  findings: ArchiveFindingRow[];
  documents: ArchiveDocument[];
}

export interface ArchiveResult {
  tender: Tender;
  spec_documents: ArchiveDocument[];
  bidders_summary: ArchiveBidderSummary[];
  bidder_details: ArchiveBidderDetail[];
}

export function getArchive(tenderId: number): Promise<ArchiveResult> {
  return request<ArchiveResult>(`/tenders/${tenderId}/archive`);
}

/**
 * GET-based file download (unlike downloadFile() above, which always
 * POSTs) — the archive's document/CSV endpoints are GET since they don't
 * generate anything, just serve an existing file.
 */
async function downloadFileGet(path: string, fallbackFileName: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}${path}`);

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // not JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/);
  const fileName = match ? match[1] : fallbackFileName;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function downloadArchiveDocument(documentId: number, fallbackFileName: string): Promise<void> {
  return downloadFileGet(`/documents/${documentId}/download`, fallbackFileName);
}

export function downloadArchiveFindingsCsv(tenderId: number, bidderId: number, bidderName: string): Promise<void> {
  return downloadFileGet(
    `/tenders/${tenderId}/bidders/${bidderId}/archive-findings-csv`,
    `${bidderName}_findings.csv`
  );
}
