"""
Reports & Completion endpoints — compliance/risk matrix (same scoring
logic as ui/reports_view.py), clarification letter drafting, delta
re-verification, and tender completion. All wrap existing functions
unchanged.
"""
import threading
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    ComplianceRow,
    ClarificationLetterResponse,
    ClarificationReplyStartedResponse,
    DeltaReverifyProgressResponse,
    TenderResponse,
)
from api import clarification_progress as progress_store
from db.connection import SessionLocal
from db.models import Bidder, Finding
from db.repository import get_tender_by_id, update_tender_status
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from ai.clarification_service import generate_clarification_letter, handle_clarification_response, recheck_flagged_findings
from rules.rule_engine import update_bidder_qualification_status

router = APIRouter(prefix="/tenders/{tender_id}", tags=["reports"])


def _get_clarification_candidates(db: Session, bidder_id: int) -> List[Finding]:
    """
    Findings worth drafting a clarification letter for: ambiguous ones the
    AI flagged for human review, ones an engineer explicitly flagged, AND
    (per user request — a deliberate widening of the original Streamlit
    scope, which only covered the first two) clear-cut 'Not Complied'
    clauses, e.g. a bidder-declared deviation like offering 20kA against a
    required 25kA — worth giving the bidder a chance to clarify or dispute
    even though the AI's verdict itself isn't ambiguous.
    """
    return (
        db.query(Finding)
        .filter(
            Finding.bidder_id == bidder_id,
            (Finding.ai_status == "Needs Human Review")
            | (Finding.engineer_status == "Needs Human Review")
            | (Finding.ai_status == "Not Complied")
            | (Finding.engineer_status == "Not Complied")
            | (Finding.needs_recheck == True),  # noqa: E712
        )
        .all()
    )


@router.get("/compliance-matrix", response_model=List[ComplianceRow])
def compliance_matrix(tender_id: int, db: Session = Depends(get_db)):
    """
    Same scoring/risk logic as ui/reports_view.py's "Preview: Compliance
    Scores & Risk Matrix" expander — QR-clause failures are High Risk
    regardless of overall score, matching the original rule exactly.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidders = get_bidders_for_tender(db, tender_id)
    latest_b = get_latest_baseline(db, tender_id)
    all_reqs = get_baseline_requirements(db, latest_b.id) if latest_b else []
    # Clauses marked N/A on Requirements & Setup are excluded from the
    # compliance score/total — they're intentionally out of scope for this
    # tender, not clauses a bidder failed to address.
    reqs = [r for r in all_reqs if not r.not_applicable]
    req_ids = [r.id for r in reqs]
    total_reqs = len(reqs)
    qr_ids = {r.id for r in reqs if r.is_QR}

    rows: List[ComplianceRow] = []
    for b in bidders:
        findings = db.query(Finding).filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(req_ids)).all()
        complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "complied")
        not_complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "not complied")
        reviews = sum(1 for f in findings if "review" in (f.engineer_status or f.ai_status or "").lower())
        score = round((complied / total_reqs * 100), 1) if total_reqs else 0.0

        qr_failures = sum(
            1 for f in findings
            if f.requirement_id in qr_ids and (f.engineer_status or f.ai_status or "").lower() == "not complied"
        )
        if qr_failures > 0 or b.final_status == "Not Qualified":
            risk = "High Risk"
        elif not_complied > 0 or reviews > 2:
            risk = "Medium Risk"
        elif reviews > 0:
            risk = "Low Risk"
        else:
            risk = "Clean"

        rows.append(
            ComplianceRow(
                bidder_id=b.id,
                bidder_name=b.name,
                total_clauses=total_reqs,
                complied=complied,
                not_complied=not_complied,
                under_review=reviews,
                score_pct=score,
                risk=risk,
                status=b.final_status or "Pending",
            )
        )
    return rows


@router.post("/bidders/{bidder_id}/clarification-letter", response_model=ClarificationLetterResponse)
def draft_clarification_letter(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id, Bidder.tender_id == tender_id).first()
    if not bidder:
        raise HTTPException(status_code=404, detail="Bidder not found")

    flagged = _get_clarification_candidates(db, bidder_id)

    if not flagged:
        return ClarificationLetterResponse(letter="", flagged_count=0)

    letter = generate_clarification_letter(db, tender, bidder, flagged)
    return ClarificationLetterResponse(letter=letter, flagged_count=len(flagged))


def _run_clarification_reply_in_background(
    tender_id: int, bidder_id: int, files_data: List[tuple], affected_ids: List[int], total_flagged: int
):
    """Runs in a background thread with its own DB session — same reasoning
    as specification.py's equivalent: the request's session closes as soon
    as the handler returns, which would race with a thread still using it."""
    bg_db = SessionLocal()
    try:
        progress_store.set_progress(tender_id, bidder_id, status="ingesting", total_flagged=total_flagged)
        for file_name, file_bytes in files_data:
            handle_clarification_response(bg_db, bidder_id, file_bytes, file_name, affected_ids)

        progress_store.set_progress(tender_id, bidder_id, status="reverifying")

        def on_progress(done: int, total: int):
            progress_store.set_progress(tender_id, bidder_id, rechecked_count=done)

        rechecked = recheck_flagged_findings(bg_db, bidder_id, progress_callback=on_progress)
        new_status = update_bidder_qualification_status(bg_db, bidder_id)

        progress_store.set_progress(
            tender_id,
            bidder_id,
            status="complete",
            rechecked_count=len(rechecked),
            new_status=new_status,
            clauses=[f.requirement.clause or "General" for f in rechecked],
        )
    except Exception as e:
        progress_store.set_progress(tender_id, bidder_id, status="error", error=str(e))
    finally:
        bg_db.close()


@router.post("/bidders/{bidder_id}/clarification-reply", response_model=ClarificationReplyStartedResponse)
async def upload_clarification_reply(
    tender_id: int, bidder_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    """Matches 'Upload Clarification Reply & Delta Re-Verify' — re-verifies
    ONLY the previously-flagged rows, not the whole tender. Starts the
    upload/ingest/re-verify pipeline in the background and returns
    immediately; poll GET .../clarification-reply/progress for status,
    same pattern as specification upload's progress polling."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    flagged = _get_clarification_candidates(db, bidder_id)
    affected_ids = [f.requirement_id for f in flagged]

    files_data = [(f.filename, await f.read()) for f in files]

    progress_store.set_progress(
        tender_id, bidder_id, status="uploading", total_flagged=len(affected_ids),
        rechecked_count=0, new_status=None, clauses=[], error=None,
    )

    thread = threading.Thread(
        target=_run_clarification_reply_in_background,
        args=(tender_id, bidder_id, files_data, affected_ids, len(affected_ids)),
        daemon=True,
    )
    thread.start()

    return ClarificationReplyStartedResponse(status="uploading")


@router.get("/bidders/{bidder_id}/clarification-reply/progress", response_model=DeltaReverifyProgressResponse)
def get_clarification_reply_progress(tender_id: int, bidder_id: int):
    state = progress_store.get_progress(tender_id, bidder_id)
    if not state:
        # Nothing started yet (or server restarted since) — treat as complete
        # with nothing rechecked, same convention specification/progress.py uses.
        return DeltaReverifyProgressResponse(
            status="complete", total_flagged=0, rechecked_count=0, new_status=None, clauses=[]
        )
    return DeltaReverifyProgressResponse(**state)


@router.post("/complete", response_model=TenderResponse)
def complete_tender(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    updated = update_tender_status(db, tender_id, "completed")
    return TenderResponse(
        id=updated.id,
        description=updated.description,
        nit_no=updated.nit_no,
        status=updated.status,
        created_at=updated.created_at,
        bidder_count=len(updated.bidders),
    )
