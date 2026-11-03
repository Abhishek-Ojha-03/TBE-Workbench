"""
TBE Working Excel endpoints — document ingestion + AI verification
orchestration, wrapping reading/ingest.py and ai/verifier.py unchanged.
"""
import os
import re
import zipfile
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    IngestDocumentsResponse,
    BulkZipIngestResult,
    BulkZipIngestResponse,
    VerifyBidderResponse,
    VerifyAllBiddersResponse,
)
from db.models import Bidder, Finding
from db.repository import get_tender_by_id
from db.baseline_service import get_bidders_for_tender, get_latest_baseline, get_baseline_requirements
from reading.ingest import ingest_documents_concurrently
from ai.verifier import verify_all_requirements_for_bidder, verify_all_bidders
from ai.quota_guard import QuotaExhaustedError
from rules.rule_engine import update_bidder_qualification_status

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


@router.post("/bulk-zip-ingest", response_model=BulkZipIngestResponse)
def bulk_zip_ingest(tender_id: int, db: Session = Depends(get_db)):
    """
    Matches the 'Extract & Ingest ALL Bidders from Saved ZIP' button —
    reuses the ZIP already saved by the bulk-add-bidders-from-ZIP feature
    on Requirements & Setup (same file, same path convention).
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    zip_path = os.path.join("data", "bidder_zips", f"tender_{tender_id}_bidders.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(
            status_code=404,
            detail="No saved ZIP found for this tender — upload one via 'Add Bidders from ZIP' on Requirements & Setup first.",
        )

    with open(zip_path, "rb") as f:
        zip_bytes = f.read()

    zf = zipfile.ZipFile(__import__("io").BytesIO(zip_bytes))
    folder_to_files: dict[str, list[str]] = {}
    for name in zf.namelist():
        parts = [p for p in name.replace("\\", "/").split("/") if p]
        if len(parts) >= 2 and parts[-1].lower().endswith(".pdf"):
            folder_to_files.setdefault(parts[-2], []).append(name)

    existing_bidders = get_bidders_for_tender(db, tender_id)
    results: List[BulkZipIngestResult] = []

    for folder_name, pdf_paths in folder_to_files.items():
        norm_folder = _normalize_bidder_name(folder_name)
        matched_bidder = next(
            (b for b in existing_bidders if _normalize_bidder_name(b.name) == norm_folder), None
        )

        if not matched_bidder:
            results.append(
                BulkZipIngestResult(
                    bidder_name=folder_name, bidder_id=None, documents_ingested=0, matched=False
                )
            )
            continue

        files_data = []
        for pdf_path in pdf_paths:
            try:
                pdf_bytes = zf.read(pdf_path)
                files_data.append((pdf_path.replace("\\", "/").split("/")[-1], pdf_bytes))
            except Exception:
                pass

        count = ingest_documents_concurrently(matched_bidder.id, files_data, max_workers=4) if files_data else 0
        results.append(
            BulkZipIngestResult(
                bidder_name=matched_bidder.name, bidder_id=matched_bidder.id, documents_ingested=count, matched=True
            )
        )

    zf.close()
    return BulkZipIngestResponse(results=results)


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
