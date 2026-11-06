"""
TBE Working Excel endpoints — document ingestion + AI verification
orchestration, wrapping reading/ingest.py and ai/verifier.py unchanged.
"""
import os
import re
import threading
import zipfile
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    IngestDocumentsResponse,
    BulkIngestStartedResponse,
    BulkIngestProgressResponse,
    VerifyBidderResponse,
    VerifyAllBiddersResponse,
    BidderDocumentResponse,
)
from db.connection import SessionLocal
from db.models import Bidder, Document, Finding
from db.repository import get_tender_by_id
from db.baseline_service import get_bidders_for_tender, get_latest_baseline, get_baseline_requirements
from db.storage import storage_enabled, download_file
from reading.ingest import ingest_documents_concurrently
from ai.verifier import verify_all_requirements_for_bidder, verify_all_bidders
from ai.quota_guard import QuotaExhaustedError
from rules.rule_engine import update_bidder_qualification_status
from api import bulk_ingest_progress

router = APIRouter(prefix="/tenders/{tender_id}", tags=["working-excel"])


def _normalize_bidder_name(name: str) -> str:
    """Same comparison logic as ui/working_excel_view.py's bulk-ZIP bidder
    matching — case/symbol-insensitive but NOT fuzzy, so 'Hira Power' still
    won't match 'Hira Power & Electronics'."""
    if not name:
        return ""
    cleaned = re.sub(r"[_\-.,&]", " ", name.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@router.get("/bidders/{bidder_id}/documents", response_model=List[BidderDocumentResponse])
def list_bidder_documents(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    """Matches the 'Submitted Files' list under each bidder tab."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    docs = db.query(Document).filter(Document.bidder_id == bidder_id).all()
    return [
        BidderDocumentResponse(id=d.id, file_name=d.file_name, page_count=len(d.pages))
        for d in docs
    ]


@router.post("/bidders/{bidder_id}/documents", response_model=IngestDocumentsResponse)
async def ingest_bidder_documents(
    tender_id: int, bidder_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    """Matches the per-bidder 'Fast Parallel Ingest' button."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    files_data = [(f.filename, await f.read()) for f in files]
    count = ingest_documents_concurrently(bidder_id, files_data, max_workers=4)
    return IngestDocumentsResponse(ingested_count=count)


def _load_tender_zip_bytes(tender_id: int) -> bytes:
    zip_filename = f"tender_{tender_id}_bidders.zip"
    zip_bytes = download_file(f"bidder_zips/{zip_filename}") if storage_enabled() else None
    if zip_bytes is None:
        zip_path = os.path.join("data", "bidder_zips", zip_filename)
        if not os.path.exists(zip_path):
            raise HTTPException(
                status_code=404,
                detail="No saved ZIP found for this tender — upload one via 'Add Bidders from ZIP' on Requirements & Setup first.",
            )
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()
    return zip_bytes


def _run_bulk_zip_ingest_in_background(tender_id: int, zip_bytes: bytes) -> None:
    """Runs in a background thread with its own DB session — same reasoning
    as specification.py/reports.py's equivalents: the request's session
    closes as soon as the handler returns."""
    bg_db = SessionLocal()
    try:
        zf = zipfile.ZipFile(__import__("io").BytesIO(zip_bytes))
        folder_to_files: dict[str, list[str]] = {}
        for name in zf.namelist():
            parts = [p for p in name.replace("\\", "/").split("/") if p]
            if len(parts) >= 2 and parts[-1].lower().endswith(".pdf"):
                folder_to_files.setdefault(parts[-2], []).append(name)

        existing_bidders = get_bidders_for_tender(bg_db, tender_id)
        bulk_ingest_progress.start_progress(tender_id, total=len(folder_to_files))

        for folder_name, pdf_paths in folder_to_files.items():
            norm_folder = _normalize_bidder_name(folder_name)
            matched_bidder = next(
                (b for b in existing_bidders if _normalize_bidder_name(b.name) == norm_folder), None
            )

            if not matched_bidder:
                bulk_ingest_progress.report_bidder_done(tender_id, folder_name, "No matching bidder — skipped")
                continue

            files_data = []
            for pdf_path in pdf_paths:
                try:
                    pdf_bytes = zf.read(pdf_path)
                    files_data.append((pdf_path.replace("\\", "/").split("/")[-1], pdf_bytes))
                except Exception:
                    pass

            count = ingest_documents_concurrently(matched_bidder.id, files_data, max_workers=4) if files_data else 0
            bulk_ingest_progress.report_bidder_done(
                tender_id, matched_bidder.name, f"{count} document(s) ingested"
            )

        zf.close()
        bulk_ingest_progress.finish_progress(tender_id)
    except Exception as e:
        bulk_ingest_progress.fail_progress(tender_id, str(e))
    finally:
        bg_db.close()


@router.post("/bulk-zip-ingest", response_model=BulkIngestStartedResponse)
def bulk_zip_ingest(tender_id: int, db: Session = Depends(get_db)):
    """
    Matches the 'Extract & Ingest ALL Bidders from Saved ZIP' button —
    reuses the ZIP already saved by the bulk-add-bidders-from-ZIP feature
    on Requirements & Setup (same file, same path convention). Starts the
    extraction/ingestion in the background and returns immediately; poll
    GET .../bulk-zip-ingest/progress for live per-bidder status.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    zip_bytes = _load_tender_zip_bytes(tender_id)

    thread = threading.Thread(
        target=_run_bulk_zip_ingest_in_background, args=(tender_id, zip_bytes), daemon=True
    )
    thread.start()

    return BulkIngestStartedResponse(status="running")


@router.get("/bulk-zip-ingest/progress", response_model=BulkIngestProgressResponse)
def get_bulk_zip_ingest_progress(tender_id: int):
    state = bulk_ingest_progress.get_progress(tender_id)
    if not state:
        return BulkIngestProgressResponse(status="complete", completed=0, total=0, status_by_bidder={})
    return BulkIngestProgressResponse(**state)


def _finding_counts(db: Session, bidder_id: int, req_ids: List[int]):
    findings = (
        db.query(Finding)
        .filter(Finding.bidder_id == bidder_id, Finding.requirement_id.in_(req_ids))
        .all()
    )
    complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "complied")
    not_complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "not complied")
    review = sum(1 for f in findings if "review" in (f.engineer_status or f.ai_status or "").lower())
    total = len(req_ids)
    accuracy = round((complied / total * 100), 1) if total else 0.0
    return complied, not_complied, review, accuracy


@router.post("/bidders/{bidder_id}/verify", response_model=VerifyBidderResponse)
def verify_bidder(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    """Matches the per-bidder 'Run AI Verification' button."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    try:
        verify_all_requirements_for_bidder(db, tender_id, bidder_id)
    except QuotaExhaustedError as e:
        raise HTTPException(status_code=429, detail=e.message)

    status = update_bidder_qualification_status(db, bidder_id)

    baseline = get_latest_baseline(db, tender_id)
    req_ids = [r.id for r in get_baseline_requirements(db, baseline.id) if not r.not_applicable] if baseline else []
    complied, not_complied, review, accuracy = _finding_counts(db, bidder_id, req_ids)

    return VerifyBidderResponse(
        bidder_id=bidder_id,
        final_status=status,
        complied=complied,
        not_complied=not_complied,
        needs_review=review,
        accuracy_pct=accuracy,
    )


@router.post("/verify-all", response_model=VerifyAllBiddersResponse)
def verify_all(tender_id: int, db: Session = Depends(get_db)):
    """Matches the 'Run AI Verification for ALL Bidders' button."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    try:
        results = verify_all_bidders(db, tender_id)
    except QuotaExhaustedError as e:
        raise HTTPException(status_code=429, detail=e.message)

    return VerifyAllBiddersResponse(results=results)
