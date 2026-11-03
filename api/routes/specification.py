"""
Specification endpoints — thin wrapper around reading/ingest.py + ai/extractor.py.

Matches the Specification screen: upload a PDF, ingest it, extract
requirements, and return the requirement list for the clause table.

IMPORTANT: extraction runs in a background thread so the upload request
returns immediately instead of blocking for minutes on a large PDF (the
35+ page / 2s-per-page throttled path). The frontend polls
GET /tenders/{id}/specification/progress to show live progress.

The background thread opens its OWN fresh SessionLocal() rather than
reusing the request's `db` dependency — that session gets closed by
FastAPI's dependency cleanup as soon as the request handler returns, which
would race with (and likely break) a background thread still using it.
"""
import threading
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    SpecificationUploadStartedResponse,
    SpecificationProgressResponse,
    RequirementResponse,
)
from api import progress as progress_store
from db.connection import SessionLocal
from db.repository import get_tender_by_id
from db.baseline_service import get_latest_baseline, get_baseline_requirements
from reading.ingest import ingest_pdf_document
from ai.extractor import process_specification_document

router = APIRouter(prefix="/tenders/{tender_id}", tags=["specification"])


def _run_extraction_in_background(tender_id: int, document_id: int):
    """Runs in a background thread with its own DB session — see module
    docstring for why this can't reuse the request's session."""
    bg_db = SessionLocal()
    try:
        progress_store.set_progress(tender_id, status="extracting", current_page=0)

        def on_progress(current_page: int, total_pages: int, requirements_so_far: int):
            progress_store.set_progress(
                tender_id,
                status="extracting",
                current_page=current_page,
                total_pages=total_pages,
                requirements_so_far=requirements_so_far,
            )

        baseline = process_specification_document(
            bg_db, tender_id, document_id, progress_callback=on_progress
        )
        progress_store.set_progress(
            tender_id,
            status="complete",
            requirements_so_far=len(baseline.requirements),
        )
    except Exception as e:
        progress_store.set_progress(tender_id, status="error", error=str(e))
    finally:
        bg_db.close()


@router.post("/specification", response_model=SpecificationUploadStartedResponse)
async def upload_specification(
    tender_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Starts the Specification screen's upload flow. Ingests the PDF
    synchronously (fast — this is just PyMuPDF/OCR per page, not the slow
    part), then kicks off AI extraction in the background and returns
    immediately so the frontend can poll progress instead of hanging on
    one long request.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await file.read()

    progress_store.set_progress(
        tender_id, status="ingesting", current_page=0, total_pages=0, requirements_so_far=0, error=None
    )

    doc = ingest_pdf_document(
        db,
        pdf_bytes,
        file.filename,
        "Specification",
        bidder_id=None,
        tender_id=tender_id,
    )

    thread = threading.Thread(
        target=_run_extraction_in_background,
        args=(tender_id, doc.id),
        daemon=True,
    )
    thread.start()

    return SpecificationUploadStartedResponse(
        document_id=doc.id,
        file_name=doc.file_name,
        total_pages_ingested=len(doc.pages),
        status="extracting",
    )


@router.get("/specification/progress", response_model=SpecificationProgressResponse)
def get_specification_progress(tender_id: int):
    """Poll this while status is 'ingesting'/'extracting' to show live progress."""
    state = progress_store.get_progress(tender_id)
    if not state:
        # No extraction has been started for this tender (or server restarted
        # since it ran) — treat as already complete so the frontend doesn't
        # spin forever waiting for a job that doesn't exist.
        return SpecificationProgressResponse(
            status="complete", current_page=0, total_pages=0, requirements_so_far=0
        )
    return SpecificationProgressResponse(**state)


@router.get("/requirements", response_model=List[RequirementResponse])
def get_requirements(tender_id: int, db: Session = Depends(get_db)):
    """
    Matches both the Specification screen's "View & Edit Extracted Clauses"
    table and the Requirements & Setup screen's clause table — same data,
    same source (the latest approved baseline), same as the Streamlit UI uses.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    baseline = get_latest_baseline(db, tender_id)
    if not baseline:
        return []

    requirements = get_baseline_requirements(db, baseline.id)
    return [RequirementResponse.model_validate(r) for r in requirements]
