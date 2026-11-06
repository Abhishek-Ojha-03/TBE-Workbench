"""
API request/response schemas.

Named `api/schemas.py` deliberately separate from `ai/schemas.py` — the
latter defines structured-output schemas for Gemini extraction, these
define the HTTP request/response shape for the frontend. Different
purposes, kept apart to avoid confusion.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class TenderCreateRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    nit_no: str = Field(..., min_length=1, max_length=100)


class TenderResponse(BaseModel):
    id: int
    description: str
    nit_no: str
    status: str
    created_at: datetime
    bidder_count: int = 0

    class Config:
        from_attributes = True


class SpecificationUploadStartedResponse(BaseModel):
    """Returned immediately when upload starts — extraction continues in the
    background; poll GET /tenders/{id}/specification/progress for status."""
    document_id: int
    file_name: str
    total_pages_ingested: int
    status: str


class SpecificationProgressResponse(BaseModel):
    status: str  # "ingesting" | "extracting" | "complete" | "error"
    current_page: int
    total_pages: int
    requirements_so_far: int
    error: Optional[str] = None


class RequirementResponse(BaseModel):
    id: int
    clause: Optional[str]
    text: str
    page_number: Optional[int]
    is_QR: bool
    not_applicable: bool

    class Config:
        from_attributes = True


class BaselineVersionResponse(BaseModel):
    version_number: int
    approved_at: datetime
    is_latest: bool


class RequirementInput(BaseModel):
    """One row as sent from the frontend when saving a new baseline version —
    mirrors the dict shape db/baseline_service.py's save_baseline_edits()
    already expects (same function the Streamlit app calls)."""
    clause: Optional[str] = None
    text: str
    page_number: Optional[int] = 1
    is_QR: bool = False
    not_applicable: bool = False


class BaselineVersionCreateRequest(BaseModel):
    requirements: List[RequirementInput]


class BidderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class BulkZipBidderResponse(BaseModel):
    added: List[str]
    skipped: List[str]


class BidderResponse(BaseModel):
    id: int
    name: str
    final_status: str

    class Config:
        from_attributes = True


# ── TBE Working Excel ───────────────────────────────────────────────────
class IngestDocumentsResponse(BaseModel):
    ingested_count: int


class BidderDocumentResponse(BaseModel):
    id: int
    file_name: str
    page_count: int


class BulkZipIngestResult(BaseModel):
    bidder_name: str
    bidder_id: Optional[int]
    documents_ingested: int
    matched: bool  # False if the ZIP folder didn't match any existing bidder


class BulkZipIngestResponse(BaseModel):
    results: List[BulkZipIngestResult]


class BulkIngestStartedResponse(BaseModel):
    status: str  # "running"


class BulkIngestProgressResponse(BaseModel):
    status: str  # "running" | "complete" | "error"
    completed: int
    total: int
    status_by_bidder: dict[str, str]
    error: Optional[str] = None


class VerifyBidderResponse(BaseModel):
    bidder_id: int
    final_status: str
    complied: int
    not_complied: int
    needs_review: int
    accuracy_pct: float


class VerifyAllBiddersResponse(BaseModel):
    results: dict[int, str]  # bidder_id -> final_status


# ── Verification Results ────────────────────────────────────────────────
class EvidenceResponse(BaseModel):
    quoted_text: str
    page_number: Optional[int] = None
    document_name: Optional[str] = None
    page_id: Optional[int] = None


class AuditLogResponse(BaseModel):
    timestamp: datetime
    who: str
    what_changed: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None


class FindingResponse(BaseModel):
    id: int
    requirement_id: int
    clause: Optional[str]
    requirement_text: str
    is_QR: bool = False
    ai_status: str
    engineer_status: Optional[str]
    remark: Optional[str]
    evidence: Optional[EvidenceResponse]
    audit_history: List[AuditLogResponse]


class OverrideRequest(BaseModel):
    status: str  # "Complied" | "Not Complied" | "N/A"
    reason: str = Field(..., min_length=1)


class FlagRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class QualifyRequest(BaseModel):
    status: str  # "Qualified" | "Not Qualified"


# ── Reports & Completion ────────────────────────────────────────────────
class ComplianceRow(BaseModel):
    bidder_id: int
    bidder_name: str
    total_clauses: int
    complied: int
    not_complied: int
    under_review: int
    score_pct: float
    risk: str
    status: str


class ClarificationLetterResponse(BaseModel):
    letter: str
    flagged_count: int


class ClarificationReplyStartedResponse(BaseModel):
    status: str  # always "uploading" immediately after kickoff


class DeltaReverifyProgressResponse(BaseModel):
    status: str  # "uploading" | "ingesting" | "reverifying" | "complete" | "error"
    total_flagged: int
    rechecked_count: int
    new_status: Optional[str] = None
    clauses: List[str] = []
    error: Optional[str] = None


# ── Commercial Evaluation ───────────────────────────────────────────────
class CommercialRankingRow(BaseModel):
    rank: Optional[int]
    label: str
    bidder_id: int
    name: str
    quoted_price: Optional[float]
    currency: str
    pct_above_l1: Optional[float]
    tie: bool
    status: str


class FetchPricesResponse(BaseModel):
    scanned_count: int
    ranking: List[CommercialRankingRow]


# ── Accuracy Matrix ──────────────────────────────────────────────────────
class AccuracyMatrixRow(BaseModel):
    bidder: str
    test_category: str
    format_type: str
    clause: str
    requirement_text: str
    offered_value: str
    ground_truth_answer: str
    ai_verdict: str
    audit_match: str
    is_trap_clause: bool
    full_quote: str
    ai_remarks: str


# ── Tender Archive (completed tenders, read-only) ──────────────────────
class ArchiveDocument(BaseModel):
    id: int
    file_name: str
    document_type: Optional[str] = None
    available: bool  # False if the original file is no longer on disk


class ArchiveBidderSummary(BaseModel):
    bidder_id: int
    name: str
    final_status: str
    quoted_price: Optional[float]
    currency: str
    commercial_rank_label: str


class ArchiveFindingRow(BaseModel):
    clause: str
    requirement_text: str
    status: str
    offered_value: str
    remark: str


class ArchiveBidderDetail(BaseModel):
    bidder_id: int
    name: str
    final_status: str
    findings: List[ArchiveFindingRow]
    documents: List[ArchiveDocument]


class ArchiveResponse(BaseModel):
    tender: TenderResponse
    spec_documents: List[ArchiveDocument]
    bidders_summary: List[ArchiveBidderSummary]
    bidder_details: List[ArchiveBidderDetail]


class AccuracyMatrixResponse(BaseModel):
    has_bidders: bool
    total_evals: int
    bidder_count: int = 0
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    accuracy_pct: float = 0.0
    precision_pct: float = 0.0
    recall_pct: float = 0.0
    rows: List[AccuracyMatrixRow] = []
